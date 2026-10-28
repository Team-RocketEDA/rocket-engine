"""In-memory catalog (slice 3): PDK lookup, readiness, IP registry.

Readiness answers per-operation availability from PDK manifests. The
IP registry snapshots submission manifests and tracks project/global
scope. Persistent storage and natural-language discovery arrive in
later slices.
"""

import uuid
from pathlib import Path

from ruamel.yaml import YAML

from ..interfaces import resolve_reference
from .errors import LibraryError


class Catalog:
    def __init__(self, root):
        self._root = Path(root)
        self._registry = {}
        self._yaml = YAML(typ="safe")

    def resolve(self, pdk_id, revision):
        return resolve_reference(
            {"scope": "global", "id": pdk_id, "revision": revision},
            root=self._root,
        )

    def active_context(self, job):
        return {"job": job, "token": uuid.uuid4().hex}

    def capabilities(self, pdk_id, revision):
        doc = self.resolve(pdk_id, revision)
        objects = doc.get("objects", {}) or {}
        decks = doc.get("decks", {}) or {}
        generate = {"readiness": "ready" if objects else "unsupported"}
        if not objects:
            generate["reason"] = f"no generatable objects for {pdk_id} {revision}"
        lvs = {"readiness": "ready" if decks else "unsupported"}
        if not decks:
            lvs["reason"] = f"no LVS deck for {pdk_id} {revision}"
        return {"generate_views": generate, "run_lvs": lvs}

    def register(self, text, scope):
        # Submission manifests are parsed plainly here; reconciling the
        # submission shape with stored-record validation is a hardening item.
        try:
            doc = self._yaml.load(text)
        except Exception as exc:
            raise LibraryError("invalid_yaml", f"Cannot parse manifest: {exc}") from exc
        if not isinstance(doc, dict) or "id" not in doc:
            raise LibraryError("invalid_yaml", "Manifest must be a mapping with an id.")
        ref = {
            "scope": scope,
            "id": doc["id"],
            "revision": doc.get("revision", "r1"),
            "status": "UNVERIFIED",
        }
        self._registry[(scope, doc["id"], ref["revision"])] = doc
        return ref

    def _registered(self, ref):
        try:
            return self._registry[(ref["scope"], ref["id"], ref["revision"])]
        except KeyError:
            raise LibraryError(
                "invalid_reference",
                f"Unknown component: {ref.get('scope')}/{ref.get('id')}.",
            ) from None

    def instantiate(self, ref, instance_id, project_id, connections=None):
        doc = self._registered(ref)
        ports = doc.get("ports", {})
        for conn in connections or []:
            if conn.get("port") not in ports:
                raise LibraryError(
                    "incompatible_port", f"Unknown port: {conn.get('port')}."
                )
        return {
            "instance_id": instance_id,
            "project_id": project_id,
            "component": {
                "scope": ref["scope"],
                "id": ref["id"],
                "revision": ref["revision"],
            },
        }

    def promote(self, ref):
        doc = self._registered(ref)
        closure = [
            {"scope": "global", "id": dep.get("id"), "revision": dep.get("revision")}
            for dep in doc.get("dependencies", [])
        ]
        glob = {
            "scope": "global",
            "id": ref["id"],
            "revision": ref["revision"],
            "status": "UNVERIFIED",
            "dependency_closure": closure,
        }
        self._registry[("global", ref["id"], ref["revision"])] = doc
        return glob
