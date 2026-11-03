"""Run evidence trail: confinement + per-run evidence files.

Pure helpers behind the Engine evidence seam (TRANSPORT-PARITY):
sources resolve inside the project, the engine chooses the workdir,
and every transport leaves the identical evidence file. The Engine
keeps thin wrappers so the MCP server's ``Engine.confine_spice_arguments``
seam and the submit/run call sites do not move.
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from ..adapters.errors import AdapterError


def confine_spice_arguments(arguments, project_dir):
    """Resolve run_spice sources inside the project; fix the workdir.

    The engine-side confinement every transport shares
    (TRANSPORT-PARITY): sources resolve inside the project dir,
    a caller workdir is refused, and the workdir is the
    results/engine-runs folder the evidence trail records
    into. Unbound engines (no project dir) pass arguments
    through untouched.

    Args:
        arguments: Submitted run_spice arguments.
        project_dir: Project folder sources resolve inside, or
            None for an unbound engine.

    Returns:
        Arguments with absolute confined sources and the
            engine-chosen workdir (unchanged when unbound).

    Raises:
        AdapterError: invalid_reference for a source outside
            the project, invalid_command for a caller workdir.
    """
    if project_dir is None:
        return arguments
    root = Path(project_dir).resolve()
    confined = dict(arguments)
    workdir = root / "results" / "engine-runs"
    sources = confined.get("sources")
    if isinstance(sources, list):
        resolved = []
        for source in sources:
            path = (root / str(source)).resolve()
            if not path.is_relative_to(root):
                raise AdapterError(
                    "invalid_reference",
                    f"Source outside the project: {source}.",
                )
            resolved.append(str(path))
        confined["sources"] = resolved
    if "workdir" in confined and confined["workdir"] != str(workdir):
        raise AdapterError(
            "invalid_command",
            "workdir is chosen by the engine, not the caller.",
        )
    workdir.mkdir(parents=True, exist_ok=True)
    confined["workdir"] = str(workdir)
    return confined


def evidence_source_state(root):
    """Probe (short commit, dirty) of the project tree.

    Twin of the MCP server's source probe (kept local so the
    composition root never imports an adapter): git metadata
    when readable, (None, None) otherwise.

    Args:
        root: Project folder to probe.

    Returns:
        (commit, dirty) pair, (None, None) outside git.
    """
    git = ["git", "-C", str(root)]
    head = subprocess.run(
        [*git, "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True,
    )
    if head.returncode != 0:
        return None, None
    status = subprocess.run(
        [*git, "status", "--porcelain", "--",
         "design", "tests", "constraints.yaml"],
        capture_output=True, text=True,
    )
    return head.stdout.strip(), bool(status.stdout.strip())


def record_run_evidence(outcome, arguments, project_dir, log_text):
    """Persist one finished run under results/engine-runs.

    The same record shape the MCP server writes, recorded by
    the engine itself so every transport leaves the identical
    evidence file (TRANSPORT-PARITY): IDE buttons and agent
    calls share one evidence trail whoever submitted.

    Args:
        outcome: Completion mapping with run_id, operation,
            and verdict.
        arguments: Submitted arguments (for the run's source
            list).
        project_dir: Project folder, or None for an unbound
            engine (no file is written).
        log_text: Callable taking a run_id and returning the
            run's log text.

    Returns:
        Evidence file path string, or None when the engine is
        unbound (no project dir anywhere).
    """
    if project_dir is None:
        return None
    folder = Path(project_dir).resolve() / "results" / "engine-runs"
    folder.mkdir(parents=True, exist_ok=True)
    commit, dirty = evidence_source_state(Path(project_dir).resolve())
    sources = []
    for source in arguments.get("sources") or []:
        path = Path(str(source))
        if path.is_absolute():
            try:
                sources.append(str(path.relative_to(
                    Path(project_dir).resolve())))
                continue
            except ValueError:
                pass
        sources.append(str(source))
    record = {
        "producer": "rocket-engine",
        "run_id": outcome["run_id"],
        "operation": outcome["operation"],
        "verdict": outcome["verdict"],
        "finished_at": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "source_commit": commit,
        "source_dirty": dirty,
        "sources": sources,
        "log": log_text(outcome["run_id"]),
    }
    path = folder / f"{outcome['run_id']}.json"
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return str(path)


def maybe_record_evidence(project_dir, run_jobs, log_text,
                           operation, completion, arguments):
    """Record one completion when the engine is project-bound.

    No-op for unbound engines, non-completions, and
    verdict-less payloads (acks, batch mappings, queries).
    run_job fetches resolve sources from the admitted
    arguments, never the fetch envelope.

    Args:
        project_dir: Engine project folder, or None when
            unbound.
        run_jobs: Admitted run-job records by run_id.
        log_text: Callable taking a run_id and returning the
            run's log text.
        operation: Operation hint when the completion omits it.
        completion: Completion mapping, batch mapping, or ack.
        arguments: Submitted arguments for the source list.

    Returns:
        Evidence file path string, or None when skipped.
    """
    if project_dir is None:
        return None
    if not isinstance(completion, dict):
        return None
    run_id = completion.get("run_id")
    verdict = completion.get("verdict")
    if run_id is None or verdict is None:
        return None
    pending = run_jobs.get(run_id, {})
    sources = pending.get("arguments", arguments)
    if not isinstance(sources, dict):
        sources = arguments
    return record_run_evidence(
        {
            "run_id": run_id,
            "operation": completion.get("operation", operation),
            "verdict": verdict,
        },
        sources,
        project_dir,
        log_text,
    )
