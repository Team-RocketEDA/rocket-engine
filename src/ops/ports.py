"""Store port seam: protocols plus the default concrete bindings.

DECOMP-CORE moves the four project stores behind ports: service
and engine code binds stores through this module, never by
importing ``stores`` ad hoc. Protocols declare the seam each
store serves; ``default_ports`` documents the concrete binding
the engine ships. Behavior is byte-identical to the direct
store imports — the seam exists so the next slice can inject
fakes without touching call sites.
"""

from typing import Protocol

from ..stores import ecs
from ..stores import layers
from ..stores import settings
from ..stores import wireplace


class EntityPort(Protocol):
    """Entity-store seam the project ledger writes through."""

    def validate_component_name(self, component):
        """Validate one component name, raising on misuse.

        Args:
            component: Component name to validate.
        """


class SettingsPort(Protocol):
    """Settings-store seam the project service persists through."""

    def validate_kind(self, kind):
        """Validate one settings kind, raising on misuse.

        Args:
            kind: Settings kind to validate.
        """


class WirePort(Protocol):
    """Wireplace seam for wire/junction admission."""

    def validate_wire(self, wire):
        """Validate one wire payload, raising on misuse.

        Args:
            wire: Wire payload to validate.
        """


class LayerPort(Protocol):
    """Layer-store seam for stackup and preset serving."""

    def stackup(self, pdk_id):
        """Return the stackup rows for one PDK id.

        Args:
            pdk_id: PDK id to serve the stackup for.
        """


def default_ports():
    """Return the concrete store bindings the engine ships.

    Returns:
        Mapping of port name to the concrete store module
            serving it (ecs, settings, wireplace, layers).
    """
    return {
        "ecs": ecs,
        "settings": settings,
        "wireplace": wireplace,
        "layers": layers,
    }
