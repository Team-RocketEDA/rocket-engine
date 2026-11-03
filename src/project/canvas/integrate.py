"""Canvas integration: project, submit, and I28 run closure."""

from pathlib import Path

from .templates import generate
from .validate import CANVAS_FILENAME, dump_canvas_toml, load_project_canvas


def wizard_create(project_root, pdk_id):
    """Create a project canvas through the creation wizard.

    Args:
        project_root: Project dir the canvas.toml lands in.
        pdk_id: PDK id the template is generated for.

    Returns:
        Path to the written canvas.toml (validates clean).
    """
    root = Path(project_root)
    root.mkdir(parents=True, exist_ok=True)
    doc = generate(pdk_id)
    (root / CANVAS_FILENAME).write_text(dump_canvas_toml(doc))
    loaded = load_project_canvas(root)
    return Path(loaded["path"])


def canvas_run_closure(project_root):
    """Load the canvas closure for one I28 run.

    Args:
        project_root: Project dir holding canvas.toml.

    Returns:
        Closure mapping pinning canvas plus refs.
    """
    return load_project_canvas(project_root)["closure"]


def validate_submit_canvas(project_root):
    """Validate the canvas on the submit path.

    Args:
        project_root: Project dir holding canvas.toml.

    Returns:
        Validated config mapping (raises CanvasError otherwise).
    """
    return load_project_canvas(project_root)["config"]
