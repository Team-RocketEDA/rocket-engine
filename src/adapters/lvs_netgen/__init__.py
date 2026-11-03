"""Netgen LVS solver adapter (EXTRACT-SKY130): layout vs schematic.

Protocol, verified against netgen 1.5.316 + sky130A_setup.tcl: the
one-shot `netgen -batch lvs <layout> <schematic> <setup> <report>`
compares TOP-level circuits, so both sides are first flattened to
top level (leaf-cell normalization: the single `.subckt` wrapper is
dropped; a library file needs `cell` to select its block). Netgen
exits 0 on match and mismatch alike, so the verdict always comes
from parsed output, never the exit code. Batch runs with DISPLAY
scrubbed: netgen's Tk init fails against an unreachable display.
Because netgen matches by topology, a rename of a singly-connected
net escapes it (LVS-ESCAPE): the flattened net-name inventories are
compared too, and name-only-on-one-side nets fail as
`lvs_net_mismatch`.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

from ...execution.errors import ExecutionError
from ...interfaces import ToolAdapter
from ...interfaces.runparams import MAX_TIMEOUT_S, MIN_TIMEOUT_S
from ..errors import AdapterError

OPERATION = "run_lvs"
_TIMEOUT_S = 120
_IDENTIFY_TIMEOUT_S = 10


def _budget_or_raise(job):
    """Job solver budget: validated, or the adapter default.

    Args:
        job: Solver job, maybe with a `timeout_s`.

    Returns:
        Budget seconds for every `_run` call.

    Raises:
        AdapterError: invalid_command for a boolean,
            non-number, or out-of-bounds budget.
    """
    timeout = job.get("timeout_s", _TIMEOUT_S)
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not MIN_TIMEOUT_S <= timeout <= MAX_TIMEOUT_S
    ):
        raise AdapterError(
            "invalid_command", f"Bad timeout_s: {timeout!r}."
        )
    return timeout

# Observed impostor markers (Oct 2026): the `netgen` apt package is
# the Schoeberl mesh generator — same name, different tool. Denylist
# only: NGSPICE-LIVE promotes this to a strict allowlist once the
# real LVS banner is verifiable against an installed binary.
_IMPOSTOR_RE = re.compile(
    r"Schoeberl|Vienna University|RWTH Aachen|Johannes Kepler"
)

_SUBCKT_RE = re.compile(r"^\s*\.subckt\s+(\S+)", re.IGNORECASE)
_ENDS_RE = re.compile(r"^\s*\.ends\b", re.IGNORECASE)
_DEVICE_RE = re.compile(
    r"^X(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)(.*)$",
    re.IGNORECASE,
)
_MATCH_RE = re.compile(r"(Circuits match uniquely|Netlists match uniquely)\.")
_MISMATCH_RES = (
    re.compile(r"Netlists do not match\."),
    re.compile(r"\*\*\* MISMATCH \*\*\*"),
)
_NET_RE = re.compile(r"Net:\s+(\S+)")
_INSTANCE_RE = re.compile(r"Instance:\s+(\S+)")


def slice_subckt(text, cell):
    """Return the wrapped `.subckt cell ... .ends` block from a library.

    Args:
        text: Netlist library text to slice.
        cell: Subcircuit name to select (case-insensitive).

    Returns:
        The wrapped .subckt block with its closing .ends.

    Raises:
        AdapterError: invalid_command when the cell is absent or
            has no closing .ends.
    """
    lines = text.splitlines()
    start = next(
        (
            i
            for i, line in enumerate(lines)
            if (m := _SUBCKT_RE.match(line)) and m.group(1).lower() == cell.lower()
        ),
        None,
    )
    if start is None:
        raise AdapterError(
            "invalid_command", f"No .subckt {cell} in the netlist."
        )
    end = next(
        (i for i in range(start + 1, len(lines)) if _ENDS_RE.match(lines[i])),
        None,
    )
    if end is None:
        raise AdapterError(
            "invalid_command", f".subckt {cell} has no closing .ends."
        )
    return "\n".join(lines[start : end + 1]) + "\n"


def flatten_spice(text, cell=None):
    """Normalize a netlist to top level for netgen's one-shot lvs.

    A bare netlist passes through; a single `.subckt` wrapper is
    dropped; a library needs `cell` to select its block, else the
    call refuses instead of guessing.

    Args:
        text: Netlist text to normalize.
        cell: Subcircuit to select from a library, or None for a
            bare or single-wrapper netlist.

    Returns:
        Top-level netlist text with .subckt/.ends lines dropped.

    Raises:
        AdapterError: invalid_command for an ambiguous multi-block
            library without cell, or a missing/unclosed block.
    """
    if cell is not None:
        text = slice_subckt(text, cell)
    elif sum(1 for line in text.splitlines() if _SUBCKT_RE.match(line)) > 1:
        raise AdapterError(
            "invalid_command", "Ambiguous netlist: pass cell to select a block."
        )
    return "\n".join(
        line
        for line in text.splitlines()
        if not _SUBCKT_RE.match(line) and not _ENDS_RE.match(line)
    ) + "\n"


def _device_nets(tokens):
    """Net names of one X/M device line's token body.

    Args:
        tokens: Bare tokens after the device name (nets, class,
            then `k=v` params).

    Returns:
        Net names: every bare token except the trailing class.
    """
    params_at = next(
        (i for i, token in enumerate(tokens) if "=" in token), len(tokens)
    )
    bare = tokens[:params_at]
    if params_at < len(tokens):
        bare = bare[:-1] if bare else []
    return bare


def inventory_nets(text):
    """Net names of the flattened netlist's X and M device lines.

    Netgen's one-shot `lvs` matches by topology, so a rename of a
    singly-connected net escapes it (LVS-ESCAPE). This inventory
    keeps the dropped name evidence: comment, subckt/ends, empty,
    and non-device lines never contribute; params (`k=v`) never
    count as nets; the class token is the last bare token before
    the params start. M-lines cover the klt/reference format both
    bandgap sides use; X-lines cover ext2spice output.

    Args:
        text: Flattened netlist text to inventory.

    Returns:
        Set of net names on X and M device lines.
    """
    nets = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("*") or stripped.startswith("."):
            continue
        tokens = stripped.split()
        if not tokens or not tokens[0][:1].upper() in ("X", "M"):
            continue
        nets.update(_device_nets(tokens[1:]))
    return nets


def _split_subckts(text):
    """Subckt blocks of a netlist in file order.

    Args:
        text: Netlist text, possibly hierarchical.

    Returns:
        List of (name, ports, body lines) per `.subckt` block;
            lines outside any block are dropped.
    """
    blocks = []
    current = None
    for line in text.splitlines():
        match = _SUBCKT_RE.match(line)
        if match is not None:
            parts = line.strip().split()
            current = [parts[1], parts[2:], []]
            blocks.append(current)
            continue
        if _ENDS_RE.match(line):
            current = None
            continue
        if current is not None:
            current[2].append(line)
    return [(name, ports, body) for name, ports, body in blocks]


def _instance_class(line):
    """Class token of an X instance line, or None.

    Args:
        line: One netlist line (already stripped).

    Returns:
        Last bare token before params start, or None when the
            line is not an X instance line.
    """
    tokens = line.split()
    if not tokens or not tokens[0].upper().startswith("X"):
        return None
    body = tokens[1:]
    params_at = next(
        (i for i, token in enumerate(body) if "=" in token), len(body)
    )
    bare = body[:params_at]
    if params_at < len(body):
        bare = bare[:-1] if bare else []
    if not bare:
        return None
    return bare[-1]


def flatten_hierarchy(text, top=None):
    """Inline hierarchical subckt instances to flat top level.

    Magic ext2spice writes one `.subckt` per layout cell, but
    netgen's one-shot LVS compares TOP-level circuits, so the
    engine-extracted bandgap netlist needs inlining past the
    single-wrapper strip of `flatten_spice`. Leaf instances whose
    class names a known block expand with port nets mapped onto
    the instance nets and private nets qualified as
    `INST_net`; X/M device cards map the same way. Cards that are
    neither X nor M device lines pass through unmapped
    (documented boundary: engine-extracted leaves are FET-only).

    Args:
        text: Hierarchical netlist text to flatten.
        top: Subckt to flatten from, or None to take the single
            never-instantiated (root) block.

    Returns:
        Flat netlist text with no `.subckt`/`.ends` lines.
            Texts without any block pass through unchanged.

    Raises:
        AdapterError: invalid_command for a missing top, or
            for zero or several roots without top.
    """
    blocks = {
        name.lower(): (name, ports, body)
        for name, ports, body in _split_subckts(text)
    }
    if not blocks:
        return text if text.endswith("\n") else text + "\n"
    referenced = set()
    for _, _, body in blocks.values():
        for line in body:
            cls = _instance_class(line.strip())
            if cls is not None and cls.lower() in blocks:
                referenced.add(cls.lower())
    if top is not None:
        root_key = top.lower()
        if root_key not in blocks:
            raise AdapterError(
                "invalid_command", f"No .subckt {top} in the netlist."
            )
    else:
        roots = [key for key in blocks if key not in referenced]
        if len(roots) != 1:
            raise AdapterError(
                "invalid_command",
                "Ambiguous hierarchy: pass top to select the root block.",
            )
        root_key = roots[0]

    def emit(block_key, scope, prefix, out):
        """Inline one block: ports map via scope, privates qualify."""
        _, ports, body = blocks[block_key]
        for line in body:
            stripped = line.strip()
            cls = _instance_class(stripped)
            if cls is not None and cls.lower() in blocks:
                tokens = stripped.split()
                inst = tokens[0]
                nets = _device_nets(tokens[1:])
                _, sub_ports, _ = blocks[cls.lower()]
                child_scope = {}
                for port, net in zip(sub_ports, nets):
                    child_scope[port] = scope.get(net, net)
                child_prefix = f"{prefix}_{inst}" if prefix else inst
                emit(cls.lower(), child_scope, child_prefix, out)
                continue
            mapped = _map_device_line(stripped, scope, prefix)
            if mapped is None:
                out.append(line)
                continue
            if prefix:
                head, _, rest = mapped.partition(" ")
                mapped = f"{prefix}_{head} {rest}"
            out.append(mapped)

    _, root_ports, _ = blocks[root_key]
    out = []
    emit(root_key, {port: port for port in root_ports}, "", out)
    return "\n".join(out) + "\n"


def _map_device_line(stripped, scope, prefix):
    """One device line with block-local nets mapped to flat names.

    Args:
        stripped: One stripped netlist line.
        scope: Local net to flat name mapping (ports bound).
        prefix: Instance qualifier for private nets ("" at root).

    Returns:
        Remapped X/M device line, or None for other cards.
    """
    tokens = stripped.split()
    if not tokens or tokens[0][:1].upper() not in ("X", "M"):
        return None
    body = tokens[1:]
    params_at = next(
        (i for i, token in enumerate(body) if "=" in token), len(body)
    )
    bare = body[:params_at]
    if not bare:
        return None
    cls = bare[-1] if params_at < len(body) else None
    nets = bare[:-1] if cls is not None else bare
    flat_nets = [scope.get(net, f"{prefix}_{net}" if prefix else net) for net in nets]
    tail = body[params_at:]
    parts = [tokens[0]] + flat_nets
    if cls is not None:
        parts.append(cls)
    parts.extend(tail)
    return " ".join(parts)


def retype_by_bulk(text, n_bulk_nets, p_bulk_nets):
    """Re-type sky130 X-FET lines by their bulk terminal.

    Wave-1 bulk-grouping evidence (docs/probe-extract-gds.md):
    magic's uniform-pfet typing is wrong where the bulk says
    otherwise — 52 devices share one common (p) bulk mirroring the
    klt pfet split, the rest bulk to VSS. The bulk net
    adjudicates: a pfet-family line bulked to an n-family net
    re-types to the nfet flavor with its suffix kept
    (`pfet_01v8_hvt` -> `nfet_01v8_hvt`), and vice versa. Bulk
    nets outside both families never re-type (conservative).

    Args:
        text: Flat netlist text to adjudicate.
        n_bulk_nets: Net names treated as n-family bulk (VSS...).
        p_bulk_nets: Net names treated as p-family bulk (VDD...).

    Returns:
        (New text, number of re-typed lines).
    """
    n_bulk = {net for net in n_bulk_nets}
    p_bulk = {net for net in p_bulk_nets}
    count = 0
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        match = _DEVICE_RE.match(stripped)
        if match is None:
            out.append(line)
            continue
        name, drain, gate, source, bulk, cls, params = match.groups()
        lowered = cls.lower()
        if "pfet" in lowered and bulk in n_bulk:
            cls = cls.replace("pfet", "nfet").replace("PFET", "NFET")
            count += 1
        elif "nfet" in lowered and bulk in p_bulk:
            cls = cls.replace("nfet", "pfet").replace("NFET", "PFET")
            count += 1
        out.append(f"X{name} {drain} {gate} {source} {bulk} {cls}{params}")
    return "\n".join(out) + "\n", count


def _inventory_violations(layout_nets, schematic_nets):
    """Name-only-on-one-side nets as `lvs_net_mismatch` violations.

    Args:
        layout_nets: Net names on the layout side.
        schematic_nets: Net names on the schematic side.

    Returns:
        Violations naming each asymmetric net with its side.
    """
    violations = []
    for net in sorted(set(layout_nets) - set(schematic_nets)):
        violations.append(
            {
                "rule": "lvs_net_mismatch",
                "message": f"Net: {net} (only in layout)",
                "net": net,
                "severity": "error",
            }
        )
    for net in sorted(set(schematic_nets) - set(layout_nets)):
        violations.append(
            {
                "rule": "lvs_net_mismatch",
                "message": f"Net: {net} (only in schematic)",
                "net": net,
                "severity": "error",
            }
        )
    return violations


def netgen_env():
    """Process env for netgen: DISPLAY scrubbed, the rest intact.

    Returns:
        Process environment mapping without DISPLAY (netgen's Tk
            init fails against an unreachable display).
    """
    env = dict(os.environ)
    env.pop("DISPLAY", None)
    return env


def _identify_netgen(path):
    """Banner check: None if usable, else the rejection cause."""
    try:
        proc = subprocess.run(
            [path, "-help"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=_IDENTIFY_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        return (
            f"netgen at {path} is unprovable: the identity probe "
            "failed (see docs/tickets/NGSPICE-LIVE.md)."
        )
    banner = (proc.stdout or "") + (proc.stderr or "")
    if _IMPOSTOR_RE.search(banner):
        first = banner.strip().splitlines()[0] if banner.strip() else "empty banner"
        return (
            f"netgen at {path} is the Schoeberl mesh-generator "
            f"impostor, not the LVS netgen ({first}); install "
            "opencircuitdesign netgen (see docs/tickets/NGSPICE-LIVE.md)."
        )
    return None


def resolve_netgen():
    """Path to a usable LVS netgen, or None.

    PATH presence is NOT enough: the `netgen` apt package is the
    Schoeberl mesh generator, a same-named different tool (caught
    live Oct 2026). Denylist: only observed impostor markers
    reject; an unknown banner admits — NGSPICE-LIVE promotes this
    to a strict allowlist once the real binary is verifiable.

    Returns:
        Path to a usable LVS netgen, or None when missing or
            rejected by the banner probe.
    """
    found = shutil.which("netgen")
    if found is None:
        return None
    if _identify_netgen(found) is not None:
        return None
    return found


def _count_subckts(text):
    """Number of `.subckt` blocks in netlist text.

    Args:
        text: Netlist text to scan.

    Returns:
        Count of `.subckt` header lines (case-insensitive).
    """
    return sum(1 for line in text.splitlines() if _SUBCKT_RE.match(line))


def _prepare_flat(text, cell):
    """Flatten one netlist side to top level for the one-shot LVS.

    A named cell slices a library; a single wrapper (or none)
    strips as before; several blocks without a cell inline the
    hierarchy from its root instead of refusing.

    Args:
        text: Netlist text to flatten.
        cell: Subcircuit to select, or None.

    Returns:
        Flat top-level netlist text.
    """
    if cell is not None:
        if _count_subckts(text) > 1:
            return flatten_hierarchy(text, top=cell)
        return flatten_spice(text, cell)
    if _count_subckts(text) > 1:
        return flatten_hierarchy(text)
    return flatten_spice(text)


def _bulk_or_raise(job):
    """Bulk-net families for p/n adjudication, or None.

    Args:
        job: Solver job, maybe with a `bulk_nets` mapping of
            `n`/`p` net-name lists.

    Returns:
        (n_bulk, p_bulk) frozensets, or None when the job names
            no families (retype skipped, old behavior kept).

    Raises:
        AdapterError: invalid_command for a malformed mapping.
    """
    bulk = job.get("bulk_nets")
    if bulk is None:
        return None
    if not isinstance(bulk, dict):
        raise AdapterError(
            "invalid_command", f"Bad bulk_nets (not a mapping): {bulk!r}."
        )
    clean = {}
    for family in ("n", "p"):
        nets = bulk.get(family, [])
        if not isinstance(nets, (list, tuple)) or not all(
            isinstance(net, str) and net for net in nets
        ):
            raise AdapterError(
                "invalid_command", f"Bad bulk_nets[{family!r}]: {nets!r}."
            )
        clean[family] = frozenset(nets)
    return clean


def _setup_file_or_raise(job):
    deck = job.get("deck") if isinstance(job.get("deck"), dict) else {}
    for candidate in (
        job.get("setup_file"),
        deck.get("path"),
        deck.get("setup_file"),
        deck.get("setup"),
        deck.get("file"),
    ):
        if candidate is not None:
            if not candidate or not Path(candidate).is_file():
                raise AdapterError(
                    "invalid_reference", f"Netgen setup not found: {candidate}."
                )
            return str(candidate)
    raise AdapterError("invalid_command", "LVS needs a netgen setup file.")


def _parse_mismatches(report):
    violations = []
    net_section, _, device_section = report.partition("DEVICE mismatches:")
    seen = set()
    for name in _NET_RE.findall(net_section):
        if name not in seen:
            seen.add(name)
            violations.append(
                {
                    "rule": "lvs_net_mismatch",
                    "message": f"Net: {name}",
                    "net": name,
                    "severity": "error",
                }
            )
    for _ in re.finditer(r"\(no matching net\)", net_section):
        violations.append(
            {
                "rule": "lvs_net_mismatch",
                "message": "(no matching net)",
                "severity": "error",
            }
        )
    seen = set()
    for name in _INSTANCE_RE.findall(device_section):
        if name not in seen:
            seen.add(name)
            violations.append(
                {
                    "rule": "lvs_device_mismatch",
                    "message": f"Instance: {name}",
                    "instance": name,
                    "severity": "error",
                }
            )
    for _ in re.finditer(r"\(no matching instance\)", device_section):
        violations.append(
            {
                "rule": "lvs_device_mismatch",
                "message": "(no matching instance)",
                "severity": "error",
            }
        )
    return violations


class NetgenLvsAdapter(ToolAdapter):
    """run_lvs via Netgen: layout vs schematic, TOP-level compare.

    Serves the run_lvs operation with deck.tool `netgen` (the only
    tool). Both netlists flatten to top level first (a library file
    needs `cell` to select its block), then the one-shot batch LVS
    runs; the result is {match, total, violations[]} with net and
    device mismatches.

    Job keys:
        layout_spice (required): Layout netlist path.
        schematic_spice (required): Schematic netlist path.
        setup_file (required): Netgen setup path — one setup form
            is required (setup_file or deck.path/setup_file/setup/
            file).
        deck: Optional mapping naming the setup file (see above).
        cell: .subckt block to select from library netlists.
        bulk_nets: Optional {n: [...], p: [...]} bulk-net
            families; X-FET lines bulked to the opposite family
            re-type before compare (bandgap p/n adjudication).
        workdir: Run directory (default ".").

    Args:
        runner: Optional isolated runner; direct subprocess when None.

    Caution: Netgen exits 0 on match and mismatch alike — the
        verdict always comes from parsed output, never the exit
        code. PATH presence is not enough: same-named impostor
        binaries are rejected by banner probe.
    """

    def __init__(self, runner=None):
        self._runner = runner

    def capabilities(self, target):
        """Report the served operation and tool name.

        Args:
            target: Target the capabilities are reported for
                (accepted, unused — one netlist pair per job).

        Returns:
            Capability mapping with operations and tool.
        """
        return {"operations": [OPERATION], "tool": "netgen"}

    def preflight(self, job):
        """Check operation, banner-proved binary, setup, and netlists.

        Args:
            job: Solver job with operation run_lvs plus netlist,
                setup, and cell inputs.

        Returns:
            Checked mapping with setup_file, both netlist paths,
                and cell when given.

        Raises:
            AdapterError: unsupported_operation for another
                operation, missing_dependency for a missing netgen
                or a banner-rejected impostor, invalid_reference
                for missing netlist files, invalid_command when no
                setup form is given.
        """
        if job.get("operation") != OPERATION:
            raise AdapterError(
                "unsupported_operation",
                f"Netgen LVS handles {OPERATION}, got {job.get('operation')}.",
            )
        timeout = _budget_or_raise(job)
        found = shutil.which("netgen")
        if found is None:
            raise AdapterError("missing_dependency", "netgen binary not found.")
        cause = _identify_netgen(found)
        if cause is not None:
            raise AdapterError("missing_dependency", cause)
        checked = {"setup_file": _setup_file_or_raise(job)}
        for key in ("layout_spice", "schematic_spice"):
            path = job.get(key)
            if not path or not Path(path).is_file():
                raise AdapterError(
                    "invalid_reference", f"Netlist file not found: {path}."
                )
            checked[key] = path
        if job.get("cell") is not None:
            checked["cell"] = str(job["cell"])
        bulk = _bulk_or_raise(job)
        if bulk is not None:
            checked["bulk_nets"] = {
                "n": sorted(bulk["n"]),
                "p": sorted(bulk["p"]),
            }
        checked["timeout_s"] = timeout
        return checked

    def execute(self, job):
        """Flatten both sides, then run the one-shot batch LVS.

        Batch runs with DISPLAY scrubbed: netgen's Tk init fails
        against an unreachable display. Hierarchical sides inline
        from their root; a `bulk_nets` job key re-types uniform
        ext2spice FETs by bulk before compare (bandgap leg).

        Args:
            job: Solver job with operation run_lvs plus netlist,
                setup, cell, and bulk_nets inputs.

        Returns:
            Native output with exit_code, stdout/stderr, report
                file/text, both netlist paths, and the per-side
                retype counts.

        Raises:
            AdapterError: invalid_reference for a missing workdir,
                invalid_command for an ambiguous library without
                cell, runner_unavailable when netgen produces no
                report, plus the preflight codes (execute
                re-checks first).
        """
        checked = self.preflight(job)
        workdir = job.get("workdir", ".")
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}."
            )
        cell = checked.get("cell")
        bulk = checked.get("bulk_nets")
        staged = {}
        flats = {}
        retyped = {}
        for key, name in (
            ("layout_spice", "layout_flat.spice"),
            ("schematic_spice", "schematic_flat.spice"),
        ):
            flat = _prepare_flat(
                Path(checked[key]).read_text(encoding="utf-8"), cell
            )
            count = 0
            if bulk is not None:
                flat, count = retype_by_bulk(flat, bulk["n"], bulk["p"])
            staged[key] = Path(workdir) / name
            staged[key].write_text(flat, encoding="utf-8")
            flats[key] = flat
            retyped[key] = count
        report_file = Path(workdir) / "lvs_report.out"
        proc = self._run(
            [
                "netgen",
                "-batch",
                "lvs",
                str(staged["layout_spice"]),
                str(staged["schematic_spice"]),
                checked["setup_file"],
                str(report_file),
            ],
            workdir,
            timeout=checked["timeout_s"],
        )
        if not report_file.is_file():
            raise AdapterError(
                "runner_unavailable",
                f"netgen produced no report: {proc.stderr[:500]}.",
            )
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "report_file": str(report_file),
            "report_text": report_file.read_text(encoding="utf-8"),
            "layout_spice": checked["layout_spice"],
            "schematic_spice": checked["schematic_spice"],
            "layout_nets": sorted(inventory_nets(flats["layout_spice"])),
            "schematic_nets": sorted(inventory_nets(flats["schematic_spice"])),
            "layout_retyped": retyped["layout_spice"],
            "schematic_retyped": retyped["schematic_spice"],
        }

    def parse(self, native_output):
        """Parse the match line or the net/device mismatches.

        A match returns zero violations — unless the flattened net
        inventories disagree (a rename of a singly-connected net
        is topologically invisible to netgen, LVS-ESCAPE), in which
        case the name-only-on-one-side nets fail as
        lvs_net_mismatch. Mismatches parse per net and instance
        plus any inventory extras; anything without a verdict
        raises instead of guessing.

        Args:
            native_output: Native output with the report text/file
                or stdout fallback, plus optional layout_nets /
                schematic_nets inventories from execute (absent in
                legacy outputs, which parse exactly as before).

        Returns:
            {match, total, violations[]} with lvs_net_mismatch and
                lvs_device_mismatch rules.

        Raises:
            AdapterError: runner_unavailable when the output has no
                LVS verdict.
        """
        report = native_output.get("report_text")
        if report is None:
            report_file = native_output.get("report_file")
            if report_file and Path(report_file).is_file():
                report = Path(report_file).read_text(encoding="utf-8")
            else:
                report = native_output.get("stdout", "")
        layout_nets = native_output.get("layout_nets")
        schematic_nets = native_output.get("schematic_nets")
        extra = []
        if layout_nets is not None and schematic_nets is not None:
            extra = _inventory_violations(layout_nets, schematic_nets)
        if _MATCH_RE.search(report):
            if extra:
                return {"match": False, "total": len(extra), "violations": extra}
            return {"match": True, "total": 0, "violations": []}
        if any(rx.search(report) for rx in _MISMATCH_RES):
            violations = _parse_mismatches(report)
            seen = {violation["message"] for violation in violations}
            for violation in extra:
                if violation["message"] not in seen:
                    violations.append(violation)
                    seen.add(violation["message"])
            return {
                "match": False,
                "total": len(violations),
                "violations": violations,
            }
        raise AdapterError(
            "runner_unavailable", "netgen output has no LVS verdict."
        )

    def _run(self, argv, workdir, timeout=_TIMEOUT_S):
        if self._runner is not None:
            try:
                return self._runner.run(argv, workdir, timeout)
            except ExecutionError as exc:
                raise AdapterError(exc.code, str(exc)) from exc
        if not Path(workdir).is_dir():
            raise AdapterError(
                "invalid_reference", f"Workdir not found: {workdir}."
            )
        try:
            return subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=workdir,
                env=netgen_env(),
            )
        except subprocess.TimeoutExpired as exc:
            raise AdapterError(
                "runner_unavailable", f"netgen timed out after {timeout}s."
            ) from exc
