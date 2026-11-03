"""PDK profile records: data-driven simulator resolution (PDK-PROFILE).

Adapters read PDK profile records (data), never PDK special-cases
(code): per-PDK simulator needs (model relpaths, corner names,
spiceinit lines) live in profile data under docs/pdk/<lane>/,
with a builtin copy here for contexts where the docs tree is not
shipped. New PDKs arrive as profile entries, never adapter edits.

Shape follows the PDK-PROFILE direction lock: {gdsfactory package
pin, KLayout tech, decks, models}. The `sim` section carries what
a SPICE adapter needs: `model_rel` (default deck relpath under
the registered store entry), `corners` (valid corner names), and
`spiceinit_extra` (PDK-only .spiceinit lines beyond the base).
"""

from pathlib import Path

from ruamel.yaml import YAML

from ..interfaces.paths import slugify
from .errors import AdapterError

PROFILE_SCHEMA = "rocketeda/pdk-profile/v0.1"

_BASE_SPICEINIT = (
    "set ngbehavior=hsa     ; HSPICE-ish compatibility for PDK model libs",
    "set ng_nomodcheck      ; do not check model parameters",
    "option noinit          ; do not dump operating point data into the log",
    "option klu             ; KLU direct linear solver",
)

#: Builtin sim record, mirroring docs/pdk/sky130a/profile.yaml
#: (the authority). Used only when the docs tree is not beside
#: the package (installed wheels ship code, not docs/).
_BUILTIN_SIM = {
    "sky130a": {
        "model_rel": "libs.tech/combined/sky130.lib.spice",
        "corners": ["tt", "ss", "ff", "sf", "fs"],
        "spiceinit_extra": [
            "set skywaterpdk        ; skip some checks for faster lib loading",
        ],
    },
}


def _checkout_root():
    """Engine checkout root, or None outside a source tree.

    Returns:
        Checkout root when this file sits inside one (a
        pyproject marker beside src/), else None.
    """
    root = Path(__file__).resolve().parents[2]
    if (root / "pyproject.toml").is_file():
        return root
    return None


def lane_profile_path(pdk_id):
    """Profile file for one PDK lane, when the docs tree is present.

    Args:
        pdk_id: Canonical PDK display id (either spelling resolves).

    Returns:
        Profile path, or None when the id is missing, when no
        checkout docs tree is beside the package, or when the lane
        file is absent.
    """
    if not pdk_id or not isinstance(pdk_id, str):
        return None
    root = _checkout_root()
    if root is None:
        return None
    candidate = root / "docs" / "pdk" / slugify(pdk_id) / "profile.yaml"
    if candidate.is_file():
        return candidate
    return None


def load_profile_record(path):
    """Load and validate one lane profile file.

    Args:
        path: Profile YAML path.

    Returns:
        Validated profile mapping.

    Raises:
        AdapterError: invalid_profile for an unreadable file or a
            record failing schema validation.
    """
    try:
        data = YAML(typ="safe").load(Path(path).read_text())
    except OSError as exc:
        raise AdapterError(
            "invalid_profile", f"Cannot read PDK profile {path}: {exc}."
        ) from exc
    return validate_record(data, source=str(path))


def validate_record(record, source="record"):
    """Validate one profile mapping against the profile schema.

    Args:
        record: Profile mapping under check.
        source: Where the record came from (for messages).

    Returns:
        The same mapping, validated.

    Raises:
        AdapterError: invalid_profile for a non-mapping record, a
            wrong schema version, or a missing id.
    """
    if not isinstance(record, dict):
        raise AdapterError(
            "invalid_profile", f"PDK profile must be a mapping: {source}."
        )
    if record.get("schema") != PROFILE_SCHEMA:
        raise AdapterError(
            "invalid_profile",
            f"PDK profile {source} must carry schema {PROFILE_SCHEMA}.",
        )
    if not record.get("id") or not isinstance(record.get("id"), str):
        raise AdapterError(
            "invalid_profile", f"PDK profile {source} misses id."
        )
    return record


def sim_for(pdk_id, record=None):
    """Sim record for one PDK: lane file first, builtin next.

    Args:
        pdk_id: Canonical PDK display id (either spelling resolves).
        record: Optional already-loaded profile mapping, winning
            over the lane file and the builtin.

    Returns:
        Sim mapping (model_rel, corners, spiceinit_extra), or None
        when the PDK declares no sim profile.
    """
    if isinstance(record, dict):
        sim = record.get("sim")
        if isinstance(sim, dict):
            return sim
    if not pdk_id or not isinstance(pdk_id, str):
        return None
    path = lane_profile_path(pdk_id)
    if path is not None:
        try:
            sim = load_profile_record(path).get("sim")
        except AdapterError:
            sim = None
        if isinstance(sim, dict):
            return sim
    return _BUILTIN_SIM.get(slugify(pdk_id))


def default_model_rel(pdk_id, record=None):
    """Default store model relpath for one PDK, if profiled.

    Args:
        pdk_id: Canonical PDK display id (either spelling resolves).
        record: Optional already-loaded profile mapping.

    Returns:
        Default model relpath, or None when the PDK declares no
        sim profile (callers fail loudly, never guess a relpath).
    """
    sim = sim_for(pdk_id, record=record)
    if not isinstance(sim, dict):
        return None
    rel = sim.get("model_rel")
    return rel if isinstance(rel, str) and rel else None


def base_spiceinit():
    """PDK-neutral .spiceinit lines every SPICE run stages.

    Returns:
        Base .spiceinit lines (no PDK-only flags; those ride the
        profile `spiceinit_extra`).
    """
    return list(_BASE_SPICEINIT)


def spiceinit_for(pdk_id, record=None):
    """Full .spiceinit lines for one PDK: base plus profile extras.

    Args:
        pdk_id: Canonical PDK display id (either spelling resolves).
        record: Optional already-loaded profile mapping.

    Returns:
        .spiceinit lines; base only when the PDK declares no sim
        profile.
    """
    lines = base_spiceinit()
    sim = sim_for(pdk_id, record=record)
    if isinstance(sim, dict):
        for line in sim.get("spiceinit_extra") or []:
            if isinstance(line, str) and line and line not in lines:
                lines.append(line)
    return lines


def render_spiceinit(lines):
    """Render .spiceinit text from staged lines.

    Args:
        lines: .spiceinit lines (base plus profile extras).

    Returns:
        .spiceinit file text with a profile-driven header.
    """
    head = "* rocket_engine ngspice init (profile-driven: see docs/pdk/)."
    return head + "\n" + "\n".join(lines) + "\n"
