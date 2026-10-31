"""Vivado-style setup surface: provision catalogue + capability reports.

The engine side of the setup menu (ENGINE-SETUP): `load_catalogue`
reads the shipped provision data (`setup_catalogue.yaml` — one
entry per provisionable unit with detection rules and recipe refs
into install.sh / provision-plan / owning tickets),
`catalogue_state` renders it with live install state for the
checkbox menu, and `report_capabilities` answers the
`get_capabilities` query (per-solver availability from the
adapters' own `capabilities()` plus tool resolution, PDK/deck
state via the store, cloud entries BYOC-gated per I32).

Readiness vocabulary is the engine-api appendix: `ready` (some
registered tool resolves — `deck.tool` selects it), `blocked`
(fixable: reason + missing items + remedy pointing at the
catalogue), `unsupported` (no solver registered — terminal for
this config). `unavailable`/`unknown` are defined but never
emitted here: transient runner states surface on run verdicts,
not capability reports.

Degradation posture: everything reports honestly; nothing
installs or phones home. Store reads never create the skeleton
(`resolve`, never `ensure`); a missing store reports empty with
the PDK remedy. Cloud entries are static gated rows — no key
lookup (CLOUD-AUTH is Backlog, so no keys can exist), no
imports, no network. PDK presence means a valid manifest; deck
rows verify per-deck hashes (tree-wide rehash stays a run-time
concern).
"""

import importlib.metadata
import importlib.util
import shutil
from pathlib import Path

from ruamel.yaml import YAML

from .errors import ContractError
from .paths import slugify
from .pdks import list_pdks, resolve_deck, resolve_engine_root
from .vocabulary import OPERATIONS

CATALOGUE_VERSION = 1
_CATALOGUE_PATH = Path(__file__).parent / "setup_catalogue.yaml"

# (operation, deck-tool) -> detection spec. Each row cites the
# adapter's own resolution as oracle: the binaries its preflight
# `shutil.which`s (or `_resolve`s), the banner probe for netgen
# (`adapters.lvs_netgen.resolve_netgen`), the import probe for sax.
# A registered solver with no row fails loudly (unknown_solver),
# so a new solver cannot slip into the menu undetected. Pure-Python
# solvers take an empty spec: always available, nothing to detect.
SOLVER_DEPS = {
    ("run_drc", "magic"): {"binaries": ["magic"]},
    ("run_drc", "klayout"): {"binaries": ["klayout"]},
    ("run_hdl_test", "icarus"): {"binaries": ["iverilog", "vvp"]},
    ("run_optical", "sax"): {"python": ["sax"]},
    ("run_extraction", "magic"): {"binaries": ["magic"]},
    ("run_lvs", "netgen"): {"binaries": ["netgen"], "banner": "lvs"},
    ("run_spice", "ngspice"): {"binaries": ["ngspice"]},
    ("run_syntax", "slang"): {"binaries": ["slang"]},
    ("run_synth", "yosys"): {"binaries": ["yosys"]},
    ("run_connectivity", "connectgraph"): {},
    ("run_erc", "connectgraph"): {},
}


class SetupError(ContractError):
    """Setup-surface violation with a stable machine code.

    Args:
        code: Stable machine-readable error code.
        message: Human-readable detail.
        fields: Itemized fields, when the error names any.
    """


def load_catalogue(path=None):
    """Load and structurally validate the provision catalogue.

    Args:
        path: Catalogue YAML path; the bundled data when omitted.

    Returns:
        Validated catalogue mapping (version + entries).

    Raises:
        SetupError: invalid_catalogue for an unloadable file, a
            wrong catalogue_version, a missing entry list, or a
            malformed entry.
    """
    catalogue_path = Path(path) if path is not None else _CATALOGUE_PATH
    try:
        data = YAML(typ="safe").load(catalogue_path.read_text())
    except OSError as exc:
        raise SetupError(
            "invalid_catalogue", f"Cannot read catalogue {catalogue_path}: {exc}."
        ) from exc
    if not isinstance(data, dict) or data.get("catalogue_version") != CATALOGUE_VERSION:
        raise SetupError(
            "invalid_catalogue",
            f"Catalogue {catalogue_path} must carry catalogue_version "
            f"{CATALOGUE_VERSION}.",
        )
    entries = data.get("entries")
    if not isinstance(entries, list) or not entries:
        raise SetupError(
            "invalid_catalogue", f"Catalogue {catalogue_path} has no entries."
        )
    for entry in entries:
        _check_entry(entry, catalogue_path)
    return {"catalogue_version": data["catalogue_version"], "entries": list(entries)}


def _check_entry(entry, catalogue_path):
    if not isinstance(entry, dict):
        raise SetupError(
            "invalid_catalogue", f"Catalogue {catalogue_path} has a malformed entry."
        )
    for field in ("id", "kind", "label", "remedy", "recipe"):
        if not entry.get(field) or not isinstance(entry.get(field), str):
            raise SetupError(
                "invalid_catalogue",
                f"Catalogue entry {entry.get('id')!r} misses text field {field}.",
            )
    kind = entry["kind"]
    if kind == "tool":
        if not entry.get("binaries"):
            raise SetupError(
                "invalid_catalogue",
                f"Catalogue entry {entry['id']!r} needs binaries.",
            )
    elif kind == "python":
        if not entry.get("python"):
            raise SetupError(
                "invalid_catalogue",
                f"Catalogue entry {entry['id']!r} needs python modules.",
            )
    elif kind == "pdk":
        if not entry.get("pdk_id") or not entry.get("decks"):
            raise SetupError(
                "invalid_catalogue",
                f"Catalogue entry {entry['id']!r} needs pdk_id and decks.",
            )
    elif kind == "cloud":
        if not entry.get("service"):
            raise SetupError(
                "invalid_catalogue",
                f"Catalogue entry {entry['id']!r} needs a service name.",
            )
    else:
        raise SetupError(
            "invalid_catalogue",
            f"Catalogue entry {entry['id']!r} has unknown kind {kind!r}.",
        )


def _resolve_netgen():
    """Banner-verified netgen path via the LVS adapter (lazy import)."""
    from ..adapters.lvs_netgen import resolve_netgen

    return resolve_netgen()


def _detect_binaries(names, banner=None):
    """Split binary names into found paths and missing names."""
    found, missing = {}, []
    for name in names:
        if banner == "lvs" and name == "netgen":
            # PATH presence is NOT enough (Schoeberl impostor):
            # only the adapter's banner probe admits.
            path = _resolve_netgen()
        else:
            path = shutil.which(name)
        if path is None:
            missing.append(name)
        else:
            found[name] = path
    return found, missing


def _detect_python(names):
    """Split module names into found versions and missing names."""
    found, missing = {}, []
    for name in names:
        if importlib.util.find_spec(name) is None:
            missing.append(name)
            continue
        try:
            found[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            found[name] = True
    return found, missing


def _covering_remedy(catalogue, binaries, python):
    """Join the catalogue remedies covering the missing deps."""
    want_binaries, want_python = set(binaries), set(python)
    remedies = []
    for entry in catalogue["entries"]:
        provides_binaries = set(entry.get("binaries") or [])
        provides_python = set(entry.get("python") or [])
        if (
            want_binaries & provides_binaries or want_python & provides_python
        ) and entry["remedy"] not in remedies:
            remedies.append(entry["remedy"])
    if remedies:
        return " ".join(remedies)
    return "Provision the missing tooling (see docs/provision-plan.md)."


def _pdk_rows(catalogue, root):
    """(pdks, store_present, store_reason, deck_rows) from the store."""
    try:
        pdks = list_pdks(engine_root=root)
    except ContractError as exc:
        # Fresh machine (or a broken entry): report empty with the
        # cause — never raise, never create the skeleton.
        return [], False, str(exc), _missing_deck_rows(catalogue, None)
    rows = []
    for entry in catalogue["entries"]:
        if entry["kind"] != "pdk":
            continue
        slug = slugify(entry["pdk_id"])
        revisions = sorted(
            {p["revision"] for p in pdks if slugify(p["id"]) == slug}
        )
        if not revisions:
            rows.extend(_missing_deck_rows(catalogue, entry))
            continue
        for revision in revisions:
            for rel in entry["decks"]:
                rows.append(_deck_row(entry, revision, rel, root))
    return pdks, True, "", rows


def _missing_deck_rows(catalogue, entry):
    if entry is None:
        rows = []
        for candidate in catalogue["entries"]:
            if candidate["kind"] == "pdk":
                rows.extend(_missing_deck_rows(catalogue, candidate))
        return rows
    return [
        {
            "pdk_id": entry["pdk_id"],
            "revision": None,
            "rel": rel,
            "state": "missing",
            "reason": f"PDK {entry['pdk_id']} not registered.",
            "remedy": entry["remedy"],
        }
        for rel in entry["decks"]
    ]


def _deck_row(entry, revision, rel, root):
    try:
        hit = resolve_deck(entry["pdk_id"], revision, rel, engine_root=root)
    except ContractError as exc:
        state = "drifted" if exc.code == "pdk_drift" else "missing"
        return {
            "pdk_id": entry["pdk_id"],
            "revision": revision,
            "rel": rel,
            "state": state,
            "reason": str(exc),
            "remedy": entry["remedy"],
        }
    return {
        "pdk_id": entry["pdk_id"],
        "revision": revision,
        "rel": rel,
        "state": "installed",
        "sha256": hit["sha256"],
    }


def entry_state(entry, engine_root=None):
    """Render one catalogue entry with its live install state.

    Args:
        entry: Catalogue entry mapping (from load_catalogue).
        engine_root: Explicit store root; resolved when omitted.

    Returns:
        Entry fields plus state (installed/missing/gated) and a
            kind-shaped detail mapping.
    """
    root = resolve_engine_root(engine_root)
    base = {
        "id": entry["id"],
        "kind": entry["kind"],
        "label": entry["label"],
        "remedy": entry["remedy"],
        "recipe": entry["recipe"],
        "provisionable": entry.get("provisionable", True),
    }
    if entry["kind"] == "tool":
        found, missing = _detect_binaries(
            entry["binaries"], banner=entry.get("banner")
        )
        base["state"] = "installed" if not missing else "missing"
        base["detail"] = {"found": found, "missing": missing}
        return base
    if entry["kind"] == "python":
        found, missing = _detect_python(entry["python"])
        base["state"] = "installed" if not missing else "missing"
        base["detail"] = {"found": found, "missing": missing}
        return base
    if entry["kind"] == "cloud":
        # Static gated row: no key lookup (no store exists yet),
        # no imports, no network — BYOC per I32.
        base["provisionable"] = False
        base["state"] = "gated"
        base["detail"] = {"key_state": "missing", "service": entry["service"]}
        return base
    try:
        pdks = list_pdks(engine_root=root)
    except ContractError:
        pdks = []
    slug = slugify(entry["pdk_id"])
    revisions = sorted({p["revision"] for p in pdks if slugify(p["id"]) == slug})
    decks = []
    if not revisions:
        decks = _missing_deck_rows({"entries": [entry]}, entry)
    else:
        for revision in revisions:
            for rel in entry["decks"]:
                decks.append(_deck_row(entry, revision, rel, root))
    base["state"] = "installed" if revisions else "missing"
    base["detail"] = {"revisions": revisions, "decks": decks}
    return base


def catalogue_state(engine_root=None):
    """Render the full checkbox menu: entries plus install state.

    Args:
        engine_root: Explicit store root; resolved when omitted.

    Returns:
        Catalogue version plus per-entry states.
    """
    catalogue = load_catalogue()
    root = resolve_engine_root(engine_root)
    return {
        "catalogue_version": catalogue["catalogue_version"],
        "entries": [entry_state(e, engine_root=root) for e in catalogue["entries"]],
    }


def report_capabilities(solvers, target=None, engine_root=None, served=()):
    """Report availability, store state, and the provision menu.

    Args:
        solvers: Operation -> {deck-tool: adapter} registry (the
            Engine solver map; each adapter serves capabilities()).
        target: Target passed to each adapter's capabilities().
        engine_root: Explicit store root; resolved when omitted.
        served: Operations the Engine serves directly without a
            solver (CRUD mutations, run_job); reported ready.

    Returns:
        Mapping with per-operation readiness (ready/blocked/
            unsupported) plus per-tool availability, the store
            root/presence, registered PDKs, per-deck states,
            BYOC-gated cloud rows, and the checkbox catalogue.

    Raises:
        SetupError: unknown_solver when a registered (operation,
            tool) has no detection spec — the menu must never
            silently misreport a solver it cannot probe.
    """
    catalogue = load_catalogue()
    root = resolve_engine_root(engine_root)
    pdks, store_present, store_reason, decks = _pdk_rows(catalogue, root)
    cloud = {
        entry["id"]: {
            "label": entry["label"],
            "service": entry["service"],
            "status": "gated",
            "key_state": "missing",
            "remedy": entry["remedy"],
            "recipe": entry["recipe"],
        }
        for entry in catalogue["entries"]
        if entry["kind"] == "cloud"
    }
    operations = {}
    for operation in sorted(OPERATIONS):
        tools = solvers.get(operation) or {}
        if not tools:
            if operation in served:
                operations[operation] = {
                    "readiness": "ready",
                    "reason": "Served by the Engine directly (no solver needed).",
                    "tools": {},
                }
                continue
            operations[operation] = {
                "readiness": "unsupported",
                "reason": f"No solver registered: {operation}.",
                "tools": {},
            }
            continue
        per_tool, missing_all, binaries_all, python_all = {}, [], [], []
        for tool, adapter in tools.items():
            spec = SOLVER_DEPS.get((operation, tool))
            if spec is None:
                raise SetupError(
                    "unknown_solver",
                    f"No detection spec for solver {operation}/{tool}; "
                    "extend the provision catalogue.",
                )
            found_binaries, missing_binaries = _detect_binaries(
                spec.get("binaries") or [], banner=spec.get("banner")
            )
            found_python, missing_python = _detect_python(spec.get("python") or [])
            missing = missing_binaries + missing_python
            detail = {
                "available": not missing,
                "capability": adapter.capabilities(target),
                "found": {**found_binaries, **found_python},
                "missing": missing,
            }
            if missing:
                detail["remedy"] = _covering_remedy(
                    catalogue, missing_binaries, missing_python
                )
            per_tool[tool] = detail
            missing_all.extend(missing)
            binaries_all.extend(missing_binaries)
            python_all.extend(missing_python)
        if any(entry["available"] for entry in per_tool.values()):
            operations[operation] = {"readiness": "ready", "tools": per_tool}
        else:
            operations[operation] = {
                "readiness": "blocked",
                "reason": f"No {operation} tool resolves on this machine.",
                "missing": sorted(set(missing_all)),
                "remedy": _covering_remedy(catalogue, binaries_all, python_all),
                "tools": per_tool,
            }
    store = {"root": str(root), "present": store_present}
    if not store_present:
        store["reason"] = store_reason
        store["remedy"] = next(
            e["remedy"] for e in catalogue["entries"] if e["kind"] == "pdk"
        )
    return {
        "operations": operations,
        "store": store,
        "pdks": pdks,
        "decks": decks,
        "cloud": cloud,
        "catalogue": catalogue_state(engine_root=root),
    }
