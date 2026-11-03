"""Fresh ruamel dumpers for YAML writes (RUAMEL-DUMPER).

A failed ruamel ``YAML(typ="safe").dump`` poisons that dumper
instance: every later dump through it emits empty text instead
of raising. A long-lived dumper therefore collapses distinct
writes onto one hollow identity after a single failure. Every
YAML write on the Engine/ProjectService path dumps through a
fresh instance per call, so a failure raises loudly and later
writes are unaffected.
"""

import io

from ruamel.yaml import YAML

__all__ = ["dump_yaml_text"]


def dump_yaml_text(data):
    """Render one YAML text through a fresh dumper.

    Args:
        data: Mapping or list to serialize.

    Returns:
        YAML text for the payload, byte-identical to a direct
        fresh ``YAML(typ="safe")`` dump and never empty.
    """
    buf = io.StringIO()
    YAML(typ="safe").dump(data, buf)
    return buf.getvalue()
