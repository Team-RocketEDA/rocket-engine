"""Versioned technology-profile semantics and capability gates.

A TechProfile pins the exact technology semantics process
operations consume (name, version, source hash, units, grid,
contact/connectivity notes, capability map). Nothing is inferred
from display names: a missing mapping, grid, rule, or tool
yields a named unsupported/incomplete verdict and authored
geometry stays intact. Binary-gated backends (opensta,
librelane, klayout, docker) probe loudly and report
BLOCKED-needs-host instead of faking a result.
"""

import copy
import shutil

GATED_TOOLS = ("opensta", "librelane", "klayout", "docker")
CAPABILITIES = (
    "drc", "extraction", "export_gds", "export_oasis",
    "connectivity",
)


class TechProfile:
    """Versioned technology semantics for one process.

    Args:
        name: Technology profile name (a PDK or another
            explicitly supported technology).
        version: Profile version string.
        source_hash: Hash of the profile source the pin came
            from (deck hash, file sha, or manifest hash).
        units: Coordinate units label.
        grid: Manufacturing grid pitch in storage units.
        deck: Backend deck/tool version label, if any.
        contacts: Contact/residue and overlap notes.
        connectivity: Connectivity relation notes.
        capabilities: Mapping of capability name to state
            (supported, missing, or incompatible).
    """

    def __init__(self, name, version, source_hash, units="nm",
                 grid=1, deck=None, contacts=None,
                 connectivity=None, capabilities=None):
        self.name = name
        self.version = version
        self.source_hash = source_hash
        self.units = units
        self.grid = grid
        self.deck = deck
        self.contacts = copy.deepcopy(contacts or {})
        self.connectivity = copy.deepcopy(connectivity or {})
        self.capabilities = dict(capabilities or {})

    def pin(self):
        """Return the I28 ingredient pin for this profile.

        Returns:
            Mapping with name, version, source hash, deck,
            units, and grid.
        """
        return {
            "deck": self.deck,
            "grid": self.grid,
            "name": self.name,
            "source_hash": self.source_hash,
            "units": self.units,
            "version": self.version,
        }

    def label(self):
        """Return the short name@version label.

        Returns:
            Profile label string.
        """
        return f"{self.name}@{self.version}"


def bind_layer(profile, layer, purpose, gds=None,
               capability="supported"):
    """Bind one project layer to process destinations.

    Args:
        profile: TechProfile the binding resolves under.
        layer: Stable project layer lid.
        purpose: Process purpose (drawing, contact, marker).
        gds: Optional (layer, datatype) destination tuple.
        capability: Binding state (supported, missing, or
            incompatible).

    Returns:
        Binding mapping with source pin, destination,
            purpose, and capability state.

    Raises:
        ValueError: For an unknown capability state.
    """
    if capability not in ("supported", "missing",
                          "incompatible"):
        raise ValueError(
            f"Unknown capability state: {capability!r}.")
    return {
        "capability": capability,
        "destination": gds,
        "layer": layer,
        "profile": profile.label(),
        "purpose": purpose,
        "source_hash": profile.source_hash,
    }


def check_capability(profile, operation, bindings):
    """Check whether one operation may run under a profile.

    Args:
        profile: TechProfile the operation would consume.
        operation: Operation name (drc, extraction,
            export_gds, export_oasis, connectivity).
        bindings: Layer bindings the design needs (empty
            means the design needs no mapped layer).

    Returns:
        Verdict with state supported, unsupported, or
            incomplete, naming the exact profile/deck pin.
            Unsupported results never imply a valid run.
    """
    state = profile.capabilities.get(operation, "missing")
    if state == "supported" and bindings:
        missing = [binding for binding in bindings if
                   binding.get("capability") != "supported"]
        if missing:
            return {
                "operation": operation,
                "profile": profile.label(),
                "reason": (
                    f"{len(missing)} layer binding(s) are not "
                    "supported; authored geometry is intact."
                ),
                "state": "incomplete",
            }
        return {
            "operation": operation,
            "profile": profile.label(),
            "reason": "Profile and bindings cover the run.",
            "state": "supported",
        }
    if state == "supported":
        return {
            "operation": operation,
            "profile": profile.label(),
            "reason": "Profile covers the run.",
            "state": "supported",
        }
    return {
        "operation": operation,
        "profile": profile.label(),
        "reason": (
            f"Profile {profile.label()} reports {operation} "
            f"as {state}; deck {profile.deck}."
        ),
        "state": "unsupported",
    }


def probe_tool(tool):
    """Probe one binary-gated backend without faking results.

    Args:
        tool: Tool binary name (opensta, librelane, klayout,
            docker, or another backend binary).

    Returns:
        Probe mapping with tool, state (available or
            BLOCKED-needs-host), path, and reason. Absent
            binaries report BLOCKED-needs-host loudly.
    """
    path = shutil.which(tool)
    if path is None:
        return {
            "path": None,
            "reason": (
                f"{tool} is not on PATH in this environment; "
                "the operation is BLOCKED-needs-host."
            ),
            "state": "BLOCKED-needs-host",
            "tool": tool,
        }
    return {
        "path": path,
        "reason": f"{tool} resolved at {path}.",
        "state": "available",
        "tool": tool,
    }
