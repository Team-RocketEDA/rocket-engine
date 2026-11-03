"""Built-in layer visibility presets (viewer aids, not semantics)."""

BUILTIN_PRESETS = ("All", "None", "All-metal", "Top", "Bottom")


def builtin_presets():
    """List every built-in preset name.

    Returns:
        Tuple of preset names.
    """
    return BUILTIN_PRESETS


def apply_preset(name, layer_names):
    """Apply one built-in preset to a layer name list.

    Args:
        name: Preset name from builtin_presets.
        layer_names: Available layer names to filter.

    Returns:
        Mapping with preset name and enabled layer names.

    Raises:
        ValueError: For an unknown preset name.
    """
    if name not in BUILTIN_PRESETS:
        raise ValueError(f"Unknown preset: {name!r}.")
    names = list(layer_names)
    if name == "All":
        enabled = names
    elif name == "None":
        enabled = []
    elif name == "All-metal":
        enabled = [layer for layer in names
                   if "met" in layer.lower() or "metal" in
                   layer.lower()]
    elif name == "Top":
        enabled = names[-1:] if names else []
    else:
        enabled = names[:1] if names else []
    return {"enabled": enabled, "preset": name}
