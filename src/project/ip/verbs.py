"""IP editor verbs: per-PDK registry mutations behind ProjectService.

First REFACTOR-SERVICE slice: the ip_register/ip_instantiate/
ip_promote verbs live here as _IpMixin so src/project/service.py
stays under the architecture line limit. ProjectService binds
this mixin, so the verbs keep their bound path
(rocket_engine.project.service.ProjectService.<verb>); the API
contract generator reads the contract docstrings from this
module (see scripts/api_spec.py _SERVICE_DOC_HOME).
"""

from ...ops import editors as _editors

from . import lifecycle as _ip


class _IpMixin:
    """IP registry verbs (per-PDK invariant, RULING-01)."""

    def ip_register(self, pdk, name, version, symbol, cell,
                    request_id, command_text, pin_map=None,
                    scope="pdk", reason="",
                    expected_revision=None):
        """Register one prebuilt IP block revision under its PDK.

        Args:
            pdk: Owning PDK id (the per-PDK invariant key).
            name: Block name within the PDK registry.
            version: Revision label ("" forbidden).
            symbol: Linked schematic symbol reference.
            cell: Linked footprint cell reference.
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.
            pin_map: Explicit [{symPin, cellPin}] entries.
            scope: "pdk" (default) or "shared" with a reason.
            reason: Recorded justification for shared scope.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with receipt, events, and cursor.

        Raises:
            ProjectError: request_conflict, revision_conflict,
                invalid_pdk, ip_exists, invalid_ip, invalid_scope.
        """
        return _editors.editor_mutation(self,
            "ip_register", request_id, command_text,
            expected_revision,
            lambda store, _rid, _rt, _live: _ip.ip_register(
                store, self._actor, pdk, name, version, symbol,
                cell, pin_map=pin_map or [], scope=scope,
                reason=reason),
            lambda receipt: f"registered IP {pdk}/{name}@{version}",
        )

    def ip_instantiate(self, pdk, name, sheet, x, y,
                       request_id, command_text, version=None,
                       rotation=0, mirror=False, properties=None,
                       expected_revision=None):
        """Place one registered IP block with linkage intact.

        Args:
            pdk: Consuming PDK id (must own the block unless the
                block opted into shared scope).
            name: Block name within the PDK registry.
            sheet: Sheet entity id hosting the instance.
            x: X position in schematic units.
            y: Y position in schematic units.
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.
            version: Revision label, or None for the latest.
            rotation: Rotation in degrees (0/90/180/270).
            mirror: Mirror flag.
            properties: Text-to-text instance properties.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with receipt, events, and cursor.

        Raises:
            ProjectError: request_conflict, revision_conflict,
                unknown_ip, pdk_mismatch, unknown_sheet,
                invalid_instance.
        """
        return _editors.editor_mutation(self,
            "ip_instantiate", request_id, command_text,
            expected_revision,
            lambda store, _rid, _rt, _live: _ip.ip_instantiate(
                store, self._actor, pdk, name, sheet, x, y,
                version=version, rotation=rotation, mirror=mirror,
                properties=properties),
            lambda receipt: (
                f"instantiated IP {pdk}/{name}"
                f"@{receipt.get('version')}"),
        )

    def ip_promote(self, pdk, name, version,
                   request_id, command_text,
                   expected_revision=None):
        """Promote one block version as the registry's recommended one.

        Args:
            pdk: Owning PDK id scoping the registry.
            name: Block name within the PDK registry.
            version: Revision label to promote.
            request_id: Client envelope id for idempotent replay.
            command_text: YAML command text for identity comparison.
            expected_revision: Revision the writer read.

        Returns:
            Mutation mapping with receipt, events, and cursor.

        Raises:
            ProjectError: request_conflict, revision_conflict,
                unknown_ip, invalid_pdk.
        """
        return _editors.editor_mutation(self,
            "ip_promote", request_id, command_text,
            expected_revision,
            lambda store, _rid, _rt, _live: _ip.ip_promote(
                store, self._actor, pdk, name, version),
            lambda receipt: f"promoted IP {pdk}/{name}@{version}",
        )
