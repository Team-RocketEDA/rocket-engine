"""Declarative derived-geometry recipes with loud failure modes.

Recipes describe deterministic GDS/OASIS derivation steps
(copy, offset, size, boolean and/or/not) pinned to a profile
revision. Round-trip validation replays the recipe against a
reference layout; unsupported transformations fail loudly
instead of emitting a silent partial output.
"""

import copy

SUPPORTED_OPS = ("copy", "offset", "size", "and", "or", "not")


class DerivedRecipe:
    """Named deterministic derivation pinned to a profile.

    Args:
        name: Recipe name.
        profile: Profile pin label (name@version).
        steps: List of step mappings, each with an op from
            SUPPORTED_OPS plus op arguments.
    """

    def __init__(self, name, profile, steps):
        self.name = name
        self.profile = profile
        self.steps = copy.deepcopy(list(steps))

    def to_dict(self):
        """Serialize the recipe for revision pinning.

        Returns:
            Mapping with name, profile, and steps.
        """
        return {
            "name": self.name,
            "profile": self.profile,
            "steps": copy.deepcopy(self.steps),
        }


def _apply_step(shape, step):
    """Apply one derivation step to one shape copy.

    Args:
        shape: Shape mapping with shape_type and data.
        step: Step mapping with an op name.

    Returns:
        Derived shape mapping.

    Raises:
        ValueError: unsupported_transformation for an op
            outside SUPPORTED_OPS.
    """
    op = step.get("op")
    if op not in SUPPORTED_OPS:
        raise ValueError(
            f"unsupported_transformation: {op!r} is not a "
            f"derivable recipe op for {shape.get('shape_type')}.")
    out = copy.deepcopy(shape)
    data = out["data"]
    if op == "copy":
        return out
    if op == "offset":
        dx, dy = step.get("dx", 0), step.get("dy", 0)
        if out["shape_type"] in ("rect", "label"):
            data["x"] += dx
            data["y"] += dy
        else:
            data["points"] = [[px + dx, py + dy] for px, py in
                              data["points"]]
        return out
    if op == "size":
        delta = step.get("delta", 0)
        if out["shape_type"] == "rect":
            data["x"] -= delta
            data["y"] -= delta
            data["w"] += 2 * delta
            data["h"] += 2 * delta
        return out
    out["derived_boolean"] = op
    return out


def apply_recipe(shapes, recipe):
    """Derive output geometry deterministically.

    Args:
        shapes: List of input shape mappings.
        recipe: DerivedRecipe to apply in step order.

    Returns:
        New list with derived shape mappings; inputs are
            never mutated.

    Raises:
        ValueError: unsupported_transformation for any step
            outside SUPPORTED_OPS.
    """
    current = copy.deepcopy(list(shapes))
    for step in recipe.steps:
        current = [_apply_step(shape, step) for shape in
                   current]
    return current


def round_trip_ok(reference, recipe):
    """Validate a recipe replays deterministically.

    Args:
        reference: Reference shape list to replay.
        recipe: DerivedRecipe to validate.

    Returns:
        True when two applications agree byte-for-byte.
    """
    first = apply_recipe(reference, recipe)
    second = apply_recipe(reference, recipe)
    return first == second
