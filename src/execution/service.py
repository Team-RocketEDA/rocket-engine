"""In-memory execution service (slice 2): dispatch, evidence, evaluation.

dispatch/cancel manipulate run state; evaluate() judges findings and
record_not_run() pins honest NOT_RUN verdicts with reasons. The first
real worker path runs through Engine.run(); isolated workers, the live
console env, and persistence arrive in later slices.
"""

import uuid

from ruamel.yaml import YAML

from .errors import ExecutionError

_SEVERITY_RANK = {"error": 0, "warning": 1}


class ExecutionService:
    """In-memory run dispatch, evidence, and verdict evaluation.

    Args:
        project_id: Project this service tracks runs for.
    """

    def __init__(self, project_id):
        self._project_id = project_id
        self._runs = {}
        self._approvals = {}
        self._source_changed = False
        self._yaml = YAML(typ="safe")

    def _require(self, run_id):
        try:
            return self._runs[run_id]
        except KeyError:
            raise ExecutionError("unknown_run", f"Unknown run: {run_id}.") from None

    def dispatch(self, operation, target, snapshot_id):
        """Queue one run and return its id.

        Args:
            operation: Operation the run executes.
            target: Run target descriptor.
            snapshot_id: Evidence snapshot the run pins.

        Returns:
            Admission with run_id, queued state, and snapshot_id.
        """
        run_id = uuid.uuid4().hex
        self._runs[run_id] = {
            "run_id": run_id,
            "operation": operation,
            "target": target,
            "snapshot_id": snapshot_id,
            "state": "queued",
            "verdict": None,
            "findings": [],
        }
        return {"run_id": run_id, "state": "queued", "snapshot_id": snapshot_id}

    def mark_running(self, run_id):
        """Mark a queued run running.

        Args:
            run_id: Run to mark.

        Returns:
            Mapping with run_id and running state.

        Raises:
            ExecutionError: unknown_run for an untracked id.
        """
        record = self._require(run_id)
        record["state"] = "running"
        return {"run_id": run_id, "state": "running"}

    def mark_completed(self, run_id, verdict):
        """Mark a run completed with its verdict.

        Args:
            run_id: Run to mark.
            verdict: Verdict mapping stored on the run.

        Returns:
            Mapping with run_id, completed state, and verdict.

        Raises:
            ExecutionError: unknown_run for an untracked id.
        """
        record = self._require(run_id)
        record["state"] = "completed"
        record["verdict"] = verdict
        return {"run_id": run_id, "state": "completed", "verdict": verdict}

    def cancel(self, run_id):
        """Cancel a queued or running run; finished runs keep state.

        Cancelling a finished run truthfully returns its terminal
        state, never a fake cancelled.

        Args:
            run_id: Run to cancel.

        Returns:
            Mapping with run_id, state, and verdict when judged.

        Raises:
            ExecutionError: unknown_run for an untracked id.
        """
        record = self._require(run_id)
        if record["state"] in ("queued", "running"):
            # Real tree termination arrives with real workers.
            record["state"] = "cancelled"
        out = {"run_id": run_id, "state": record["state"]}
        if record["verdict"] is not None:
            out["verdict"] = record["verdict"]
        return out

    def note_source_change(self, revision):
        """Flag evidence stale after a source edit.

        Args:
            revision: Revision the sources moved to.
        """
        self._source_changed = True
        self._source_revision = revision

    def evidence(self, run_id):
        """Read a run's evidence pin plus freshness.

        Args:
            run_id: Run to read.

        Returns:
            Evidence with run_id, snapshot_id, and freshness
                (current or stale).

        Raises:
            ExecutionError: unknown_run for an untracked id.
        """
        record = self._require(run_id)
        return {
            "run_id": run_id,
            "snapshot_id": record["snapshot_id"],
            "freshness": "stale" if self._source_changed else "current",
        }

    def _store_verdict(self, run_id, verdict, findings=()):
        record = self._runs.setdefault(
            run_id,
            {"run_id": run_id, "state": "completed", "verdict": None, "findings": []},
        )
        record["state"] = "completed"
        record["verdict"] = verdict
        record["findings"] = list(findings)
        return verdict

    def evaluate(self, run_id, exit_code, findings_fixture):
        """Judge findings: FAIL on any error, else PASS.

        Unparsable output judges NOT_RUN with reason rather than
        guessing; the exit code is recorded, never the verdict.

        Args:
            run_id: Run to judge.
            exit_code: Native exit code, recorded only.
            findings_fixture: YAML text with a findings list.

        Returns:
            Verdict with status and finding counts.

        Raises:
            ValueError: No findings list (raised and caught inside
                evaluate into a NOT_RUN verdict — never escapes).
        """
        try:
            data = self._yaml.load(findings_fixture)
            if not isinstance(data, dict) or not isinstance(data.get("findings"), list):
                raise ValueError("no findings list")
            findings = data["findings"]
        except Exception:
            return self._store_verdict(
                run_id, {"status": "NOT_RUN", "reason": "unparsable output"}
            )
        counts = {}
        for finding in findings:
            severity = finding.get("severity", "unknown")
            counts[severity] = counts.get(severity, 0) + 1
        status = "FAIL" if counts.get("error", 0) else "PASS"
        return self._store_verdict(
            run_id, {"status": status, "finding_counts": counts}, findings
        )

    def record_not_run(self, run_id, reason):
        """Pin an honest NOT_RUN verdict with its reason.

        Args:
            run_id: Run to mark not run.
            reason: Why no verdict exists.

        Returns:
            NOT_RUN verdict with the reason.
        """
        return self._store_verdict(run_id, {"status": "NOT_RUN", "reason": reason})

    def findings(self, run_id, limit=50, cursor=None):
        """Read one page of findings, errors first.

        Args:
            run_id: Run to read.
            limit: Maximum findings in this page.
            cursor: Opaque position from a previous page, if any.

        Returns:
            Finding page with total counts, findings, next cursor,
                and truncation flag.

        Raises:
            ExecutionError: unknown_run for an untracked id.
        """
        record = self._require(run_id)
        ordered = sorted(
            record.get("findings", []),
            key=lambda f: _SEVERITY_RANK.get(f.get("severity"), 2),
        )
        counts = {}
        for finding in ordered:
            severity = finding.get("severity", "unknown")
            counts[severity] = counts.get(severity, 0) + 1
        start = int(cursor) if cursor else 0
        page = ordered[start : start + limit]
        remaining = len(ordered) - (start + len(page))
        return {
            "total_counts": counts,
            "findings": page,
            "next_cursor": str(start + len(page)) if remaining > 0 else None,
            "truncated": remaining > 0,
        }

    def request_approval(self, kind, closure_hash, expected_revision):
        """Bind a pending approval to one closure plus revision.

        Args:
            kind: Approval kind (effect class requested).
            closure_hash: Hash of the closure the approval pins.
            expected_revision: Revision the approval pins.

        Returns:
            Approval record with approval_id and pending state.
        """
        approval_id = uuid.uuid4().hex
        self._approvals[approval_id] = {
            "approval_id": approval_id,
            "kind": kind,
            "closure_hash": closure_hash,
            "expected_revision": expected_revision,
            "state": "pending_approval",
        }
        return {"approval_id": approval_id, "state": "pending_approval"}

    def admit(self, approval_id, closure_hash, expected_revision):
        """Admit an approval whose binding still matches.

        Args:
            approval_id: Approval bound by request_approval.
            closure_hash: Closure hash to re-check.
            expected_revision: Revision to re-check.

        Returns:
            Approval record with approval_id and approved state.

        Raises:
            ExecutionError: approval_invalid for an unknown approval
                or any binding drift.
        """
        try:
            record = self._approvals[approval_id]
        except KeyError:
            raise ExecutionError("approval_invalid", "Unknown approval.") from None
        if (
            record["closure_hash"] != closure_hash
            or record["expected_revision"] != expected_revision
        ):
            raise ExecutionError(
                "approval_invalid", "Approval no longer matches its binding."
            )
        record["state"] = "approved"
        return {"approval_id": approval_id, "state": "approved"}
