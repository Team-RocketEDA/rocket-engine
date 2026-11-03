"""Component catalogue (API-GENERALIZE): versioned cell index + place_cell.

The frontend cannot import gdsfactory, so the engine introspects cell
libraries upstream and serves plain data: every entry carries cell,
PDK, PDK revision, ports, and default params, all JSON-serializable.
Entries come from providers — callables returning entry lists — so the
upstream source stays replaceable: `gdsfactory_provider` introspects
installed gdsfactory cell modules (ports from best-effort
instantiation, default params from factory signatures, never raising),
`static_provider` serves fixed entries for seeds and tests.

`place_cell` turns a catalogue entry into a durable project mutation:
the instance lands as a `components/<instance_id>.yaml` document
through the ledger's atomic batch path, so every placement advances
the revision, appends an actor-attributed event, and replays
idempotently by request id.
"""

import copy
import importlib
import inspect
import io
import uuid
from contextlib import redirect_stdout

from ruamel.yaml import YAML

try:
    from .errors import LibraryError
    from ..project.errors import ProjectError
except ImportError:  # standalone verification before install
    from rocket_engine.library.errors import LibraryError
    from rocket_engine.project.errors import ProjectError

CATALOG_VERSION = 1

_yaml = YAML(typ="safe")


def _request_admitted(project, request_id):
    """True when the ledger already admitted a request id.

    A replayed placement skips the instance-exists guard: the batch
    path returns the stored mapping instead of writing. New request
    ids keep the guard, so a reused instance name is refused loudly
    instead of overwritten silently.
    """
    try:
        events = project.events_since(0)
    except Exception:
        return False
    return any(event.get("request_id") == request_id for event in events)


_ENTRY_KEYS = (
    "cell", "pdk", "pdk_revision", "ports", "default_params",
    "catalog_version", "source",
)


def _json_scalar(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_scalar(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _json_scalar(item) for key, item in value.items()
        }
    return repr(value)


def _normalize(entry, source):
    normalized = {
        "cell": str(entry["cell"]),
        "pdk": str(entry["pdk"]),
        "pdk_revision": str(entry.get("pdk_revision", "")),
        "ports": [str(port) for port in entry.get("ports", [])],
        "default_params": {
            str(key): _json_scalar(value)
            for key, value in dict(entry.get("default_params", {})).items()
        },
        "catalog_version": CATALOG_VERSION,
        "source": source,
    }
    return {key: normalized[key] for key in _ENTRY_KEYS}


def static_provider(entries, source="static"):
    """Serve fixed catalogue entries (seeds, fixtures, tests).

    Args:
        entries: Entry mappings with cell, pdk, pdk_revision,
            ports, and default_params.
        source: Source label stamped on every entry.

    Returns:
        Provider callable returning normalized entries.
    """
    frozen = [_normalize(entry, source) for entry in entries]

    def provide():
        return [dict(entry) for entry in frozen]

    return provide


def gdsfactory_provider(modules=("gdsfactory.components",), pdk="gdsfactory",
                        pdk_revision=None, instantiate=True):
    """Introspect gdsfactory cell modules into catalogue entries.

    gdsfactory is imported lazily inside the provider, engine-side
    only — the served entries are plain data, so the frontend never
    needs the import. Missing gdsfactory, missing modules, and broken
    factories all degrade to fewer entries, never an exception.

    Args:
        modules: Cell-module names searched via `get_cells`.
        pdk: PDK label stamped on every entry.
        pdk_revision: PDK revision stamped on every entry; the
            installed gdsfactory version when omitted.
        instantiate: Best-effort instantiate each factory with
            defaults to read port names; factories that refuse
            keep empty ports rather than failing the listing.

    Returns:
        Provider callable returning normalized entries (possibly
            none when gdsfactory is unavailable).
    """
    def provide():
        try:
            gf = importlib.import_module("gdsfactory")
        except ImportError:
            return []
        revision = pdk_revision or getattr(gf, "__version__", "")
        found = {}
        for name in modules:
            try:
                module = importlib.import_module(name)
            except ImportError:
                continue
            try:
                cells = gf.get_cells([module])
            except Exception:
                continue
            for cell_name, factory in cells.items():
                found.setdefault(cell_name, factory)
        entries = []
        for cell_name in sorted(found):
            factory = found[cell_name]
            try:
                signature = inspect.signature(factory)
            except (TypeError, ValueError):
                signature = None
            defaults = {}
            if signature is not None:
                for param in signature.parameters.values():
                    if param.default is not inspect.Parameter.empty:
                        defaults[param.name] = _json_scalar(param.default)
            ports = []
            if instantiate:
                try:
                    # Best-effort probe: some factories print
                    # while instantiating; keep the engine quiet.
                    with redirect_stdout(io.StringIO()):
                        component = factory()
                    ports = [str(name) for name in list(component.ports)]
                except Exception:
                    ports = []
            entries.append(_normalize({
                "cell": cell_name,
                "pdk": pdk,
                "pdk_revision": revision,
                "ports": ports,
                "default_params": defaults,
            }, "gdsfactory"))
        return entries

    return provide


class ApigCatalog:
    """Versioned component index with durable placement.

    Args:
        root: Store root reserved for manifest-backed providers;
            introspection providers ignore it.
        providers: Provider callables returning entry lists; later
            providers lose on (pdk, cell) collisions.
    """

    def __init__(self, root=".", providers=()):
        self._root = root
        self._providers = list(providers)
        self._cache = None

    def add_provider(self, provider):
        """Append a fallback provider to the index.

        Args:
            provider: Provider callable returning entry lists.

        Returns:
            Mapping with the provider count now serving.
        """
        self._providers.append(provider)
        self._cache = None
        return {"providers": len(self._providers)}

    def refresh(self):
        """Drop the cached index so providers run again.

        Returns:
            Mapping with the cell count after rebuilding.
        """
        self._cache = None
        return {"cells": len(self.list_cells()["cells"])}

    def _index(self):
        if self._cache is None:
            index = {}
            for provider in self._providers:
                for entry in provider():
                    index.setdefault((entry["pdk"], entry["cell"]), entry)
            self._cache = index
        return self._cache

    def list_cells(self, pdk=None):
        """List versioned catalogue entries, optionally for one PDK.

        Args:
            pdk: Restrict to one PDK label; all entries when
                omitted.

        Returns:
            Listing with catalog_version and cells sorted by
                (pdk, cell). Every entry is plain JSON data.
        """
        entries = [
            copy.deepcopy(entry)
            for (entry_pdk, _cell), entry in self._index().items()
            if pdk is None or entry_pdk == pdk
        ]
        entries.sort(key=lambda e: (e["pdk"], e["cell"]))
        return {"catalog_version": CATALOG_VERSION, "cells": entries}

    def get_cell(self, cell, pdk=None):
        """Read one catalogue entry by cell, optionally by PDK.

        Args:
            cell: Cell name to look up.
            pdk: PDK label disambiguating same-named cells.

        Returns:
            Catalogue entry for the cell.

        Raises:
            LibraryError: unknown_cell when no entry matches,
                ambiguous_cell when the cell exists in several
                PDKs and none was named.
        """
        matches = [
            entry for (entry_pdk, entry_cell), entry in self._index().items()
            if entry_cell == cell and (pdk is None or entry_pdk == pdk)
        ]
        if not matches:
            raise LibraryError(
                "unknown_cell", f"Unknown cell: {cell!r}."
            )
        if len(matches) > 1:
            labels = sorted(entry["pdk"] for entry in matches)
            raise LibraryError(
                "ambiguous_cell",
                f"Cell {cell!r} exists in several PDKs ({', '.join(labels)}); "
                "name one.",
            )
        return copy.deepcopy(matches[0])

    def place_cell(self, project, cell, request_id, expected_revision=None,
                   pdk=None, instance_id=None, params=None,
                   connections=None, path_prefix="components"):
        """Place a catalogue cell as a durable project mutation.

        The instance lands as `<prefix>/<instance_id>.yaml` through
        the ledger's atomic batch path: one new revision, one
        actor-attributed event, idempotent replay by request id.

        Args:
            project: Project port with `apply_mutations` and
                `read_doc` (ProjectService serves).
            cell: Catalogue cell name.
            request_id: Client envelope id for idempotent replay.
            expected_revision: Revision the writer read.
            pdk: PDK label disambiguating same-named cells.
            instance_id: Instance name; `<cell>_<8 hex>` when
                omitted.
            params: Override values for the cell's default params;
                unknown names are refused, never stored.
            connections: Connection mappings; every port must
                exist on the cell.
            path_prefix: Document directory for instances.

        Returns:
            Mutation mapping with the revision transition, new
                head, actor, event, and request id.

        Raises:
            LibraryError: unknown_cell, ambiguous_cell,
                unknown_param, incompatible_port, or
                instance_exists when the instance document already
                exists under a different request.
            ProjectError: revision_conflict for a stale head,
                request_conflict for a reused id with new text.
        """
        entry = self.get_cell(cell, pdk=pdk)
        params = dict(params or {})
        unknown = sorted(set(params) - set(entry["default_params"]))
        if unknown:
            raise LibraryError(
                "unknown_param",
                f"Unknown params for {entry['cell']!r}: "
                f"{', '.join(unknown)}.",
            )
        ports = set(entry["ports"])
        for conn in connections or []:
            if (conn.get("port")) not in ports:
                raise LibraryError(
                    "incompatible_port", f"Unknown port: {conn.get('port')}."
                )
        instance = instance_id or f"{entry['cell']}_{uuid.uuid4().hex[:8]}"
        path = f"{path_prefix}/{instance}.yaml"
        try:
            project.read_doc(path)
        except ProjectError as exc:
            if exc.code != "unknown_document":
                raise
            exists = False
        else:
            exists = True
        if exists and not _request_admitted(project, request_id):
            raise LibraryError(
                "instance_exists",
                f"Instance already placed: {instance!r}.",
            )
        record = {
            "instance_id": instance,
            "cell": entry["cell"],
            "pdk": entry["pdk"],
            "pdk_revision": entry["pdk_revision"],
            "catalog_version": CATALOG_VERSION,
            "params": {**entry["default_params"], **params},
            "connections": list(connections or []),
        }
        buf = io.StringIO()
        _yaml.dump(
            {"operation": "place_cell",
             "arguments": {
                 "cell": cell, "pdk": entry["pdk"],
                 "instance_id": instance, "params": params,
                 "connections": list(connections or []),
             }},
            buf,
        )
        content = io.StringIO()
        _yaml.dump(record, content)
        return project.apply_mutations(
            [{"op": "write", "path": path, "content": content.getvalue()}],
            request_id,
            buf.getvalue(),
            expected_revision=expected_revision,
        )
