"""Migrated Python client entry (API-V1-CLIENTS).

`connect` builds one Engine and serves its integrated runtime
through the shared RuntimeClient — the same semantic calls from
this client admit the same runs, with the same completions, as
every other transport. No legacy op renames exist in the tree
(verified: no legacy adapter map ships any), so no deprecation
translation rides this path; any future rename lands here with a
DeprecationWarning instead of a silent break.
"""

from rocket_engine.clients.runtime import RuntimeClient
from rocket_engine.composition import Engine

__all__ = ["RuntimeClient", "connect"]


def connect(project_id, actor="python-client", **engine_kwargs):
    """Connect one engine's integrated runtime for Python callers.

    Args:
        project_id: Project the engine binds to; cross-project
            envelopes are denied, never routed.
        actor: Attribution for mutations this client submits.
        engine_kwargs: Extra Engine constructor keyword
            arguments (engine_root, project_dir, constraints).

    Returns:
        RuntimeClient bound to the fresh engine.
    """
    return RuntimeClient(Engine(project_id, actor=actor, **engine_kwargs))
