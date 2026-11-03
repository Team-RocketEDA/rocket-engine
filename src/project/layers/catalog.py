"""Editable project layer catalog with stable identities.

Layers carry identity (lid) separate from display (name, color,
visibility): renames, saves, and reloads keep the lid, so saved
geometry addressed by lid is never reinterpreted when a profile
is missing or changed.
"""

import copy
import itertools

_COUNTER = itertools.count(1)


def _mint_lid(existing):
    """Mint one stable layer id.

    Args:
        existing: Lids already in use.

    Returns:
        Fresh lid string not present in existing.
    """
    while True:
        candidate = f"lyr-{next(_COUNTER):04d}"
        if candidate not in existing:
            return candidate


class LayerCatalog:
    """Editable layer vocabulary for one project.

    Args:
        profile: Resolved technology profile mapping (name,
            version) or None when no profile is selected.
        revision: Starting catalog revision for a fresh
            catalog.
    """

    def __init__(self, profile=None, revision=1):
        self._profile = copy.deepcopy(profile)
        self._revision = revision
        self._layers = {}

    @property
    def setup_visible(self):
        """Whether missing-profile setup must be shown.

        Returns:
            True when no technology profile is resolved.
        """
        return self._profile is None

    @property
    def revision(self):
        """Current catalog revision.

        Returns:
            Integer revision bumped by every mutation.
        """
        return self._revision

    @property
    def profile(self):
        """Resolved technology profile, if any.

        Returns:
            Deep copy of the profile mapping or None.
        """
        return copy.deepcopy(self._profile)

    def add_layer(self, name, purpose="drawing", color="#ffffff",
                  order=0, visible=True, aliases=()):
        """Add one project layer with a stable identity.

        Args:
            name: Display name for the layer.
            purpose: Process purpose label (display only;
                semantics come from bindings).
            color: Display color for editors.
            order: Stack order for editors.
            visible: Display visibility flag.
            aliases: Extra names resolving to this layer.

        Returns:
            Deep copy of the created layer record.

        Raises:
            ValueError: If the name is empty or already used.
        """
        if not name:
            raise ValueError("Layer name must not be empty.")
        if any(layer["name"] == name for layer in
               self._layers.values()):
            raise ValueError(f"Duplicate layer name: {name!r}.")
        lid = _mint_lid(set(self._layers))
        self._layers[lid] = {
            "aliases": list(aliases),
            "color": color,
            "lid": lid,
            "name": name,
            "order": order,
            "purpose": purpose,
            "visible": bool(visible),
        }
        self._revision += 1
        return copy.deepcopy(self._layers[lid])

    def rename_layer(self, lid, name):
        """Rename one layer without changing its identity.

        Args:
            lid: Stable layer id to rename.
            name: New display name.

        Returns:
            Deep copy of the renamed layer record.

        Raises:
            ValueError: For an unknown lid, an empty name, or
                a name already in use.
        """
        if lid not in self._layers:
            raise ValueError(f"Unknown layer: {lid!r}.")
        if not name:
            raise ValueError("Layer name must not be empty.")
        self._layers[lid]["name"] = name
        self._revision += 1
        return copy.deepcopy(self._layers[lid])

    def set_display(self, lid, color=None, visible=None, order=None):
        """Change display-only flags of one layer.

        Args:
            lid: Stable layer id to update.
            color: New display color, if given.
            visible: New visibility flag, if given.
            order: New stack order, if given.

        Returns:
            Deep copy of the updated layer record.

        Raises:
            ValueError: For an unknown lid.
        """
        if lid not in self._layers:
            raise ValueError(f"Unknown layer: {lid!r}.")
        layer = self._layers[lid]
        if color is not None:
            layer["color"] = color
        if visible is not None:
            layer["visible"] = bool(visible)
        if order is not None:
            layer["order"] = order
        self._revision += 1
        return copy.deepcopy(layer)

    def get_layer(self, lid):
        """Return one layer record by stable id.

        Args:
            lid: Stable layer id to read.

        Returns:
            Deep copy of the layer record.

        Raises:
            ValueError: For an unknown lid.
        """
        if lid not in self._layers:
            raise ValueError(f"Unknown layer: {lid!r}.")
        return copy.deepcopy(self._layers[lid])

    def list_layers(self):
        """List every layer ordered by stack order.

        Returns:
            List of deep-copied layer records.
        """
        return sorted(
            (copy.deepcopy(layer) for layer in
             self._layers.values()),
            key=lambda layer: (layer["order"], layer["lid"]),
        )

    def attach_profile(self, profile):
        """Resolve a technology profile without moving geometry.

        Args:
            profile: Technology profile mapping with at least
                name and version.

        Returns:
            Deep copy of the attached profile.
        """
        self._profile = copy.deepcopy(profile)
        self._revision += 1
        return copy.deepcopy(self._profile)

    def to_dict(self):
        """Serialize the catalog including its revision pin.

        Returns:
            Plain mapping with profile, revision, and layers.
        """
        return {
            "layers": self.list_layers(),
            "profile": copy.deepcopy(self._profile),
            "revision": self._revision,
        }

    @classmethod
    def from_dict(cls, data):
        """Rebuild a catalog from serialized state.

        Args:
            data: Mapping produced by to_dict.

        Returns:
            LayerCatalog with stable lids preserved.
        """
        catalog = cls(
            profile=data.get("profile"),
            revision=data.get("revision", 1),
        )
        for layer in data.get("layers", ()):
            catalog._layers[layer["lid"]] = copy.deepcopy(layer)
        return catalog
