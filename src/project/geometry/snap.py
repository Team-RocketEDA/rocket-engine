"""Project grid separation: storage, UI snap, manufacturing grid.

Authored geometry is stored exactly as drawn. The UI snap grid
only guides new pointer positions and the profile manufacturing
grid only constrains process checks and export — neither ever
rewrites stored coordinates.
"""


def snap_to_grid(value, grid):
    """Snap one coordinate to the nearest grid multiple.

    Args:
        value: Authored coordinate in storage units.
        grid: Snap grid pitch in the same units.

    Returns:
        Nearest multiple of the grid pitch.

    Raises:
        ValueError: For a non-positive grid pitch.
    """
    if grid <= 0:
        raise ValueError(f"Grid pitch must be positive: {grid!r}.")
    return round(value / grid) * grid


def quantize_storage(value, units):
    """Quantize one value for integer storage units.

    Args:
        value: Authored coordinate value.
        units: Storage units label (nm stores integers).

    Returns:
        Stored value (rounded integer for nm, else input).
    """
    if units == "nm":
        return int(round(value))
    return value


def check_mfg_grid(point, grid):
    """Check one authored point against the manufacturing grid.

    Args:
        point: Mapping with x and y authored coordinates.
        grid: Manufacturing grid pitch in storage units.

    Returns:
        Verdict with state ok or violation; violations keep
        the authored point untouched for the caller to move.

    Raises:
        ValueError: For a non-positive grid pitch.
    """
    if grid <= 0:
        raise ValueError(f"Grid pitch must be positive: {grid!r}.")
    off_x = point["x"] % grid
    off_y = point["y"] % grid
    if off_x == 0 and off_y == 0:
        return {"authored": dict(point), "state": "ok"}
    return {
        "authored": dict(point),
        "reason": (
            f"Point {point} is off the {grid}-unit "
            "manufacturing grid; authored geometry unchanged."
        ),
        "state": "violation",
    }


def snap_point(point, grid):
    """Snap one point dict to the UI grid for new edits.

    Args:
        point: Mapping with x and y coordinates.
        grid: UI snap grid pitch in storage units.

    Returns:
        New point mapping with snapped coordinates.
    """
    return {
        "x": snap_to_grid(point["x"], grid),
        "y": snap_to_grid(point["y"], grid),
    }


def storage_box(x, y, units):
    """Store one anchor point without grid rewriting.

    Args:
        x: Authored x coordinate.
        y: Authored y coordinate.
        units: Storage units label.

    Returns:
        Mapping with quantized x and y.
    """
    return {
        "x": quantize_storage(x, units),
        "y": quantize_storage(y, units),
    }
