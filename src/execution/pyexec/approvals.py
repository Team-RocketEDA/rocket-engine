"""Approval state machine for python_execute (mixin)."""

import uuid

from ..errors import ExecutionError


class _ApprovalMixin:
    """UI-resolved approvals: pending/approved/denied/expired."""

    def _binding(self, approval_id):
        try:
            return self._approvals[approval_id]
        except KeyError:
            raise ExecutionError(
                "approval_invalid", "Unknown or expired approval."
            ) from None

    def approval_status(self, approval_id):
        """Read one approval's state (approvals, never job state).

        Args:
            approval_id: Approval bound by request_execution.

        Returns:
            Approval state mapping with approval_id, approval_state,
                execution_id, and the run_id only once admitted.

        Raises:
            ExecutionError: approval_invalid for an unknown approval.
        """
        record = self._binding(approval_id)
        self._sweep_expired()
        out = {
            "approval_id": approval_id,
            "approval_state": record["state"],
            "execution_id": record["execution_id"],
        }
        if record["run_id"] is not None:
            out["run_id"] = record["run_id"]
        if record.get("reason"):
            out["reason"] = record["reason"]
        return out

    def resolve_approval(self, approval_id, decision, via="ui", actor=None):
        """Resolve an approval through the human UI route.

        Agent calls request approval; they never grant it: any `via`
        other than the human UI route raises approval_forbidden and
        the approval stays pending. Approving admits exactly one
        queued run; denying lapses the approval with no run.

        Args:
            approval_id: Approval bound by request_execution.
            decision: `approved` to admit one run, `denied` to
                lapse the approval with no run.
            via: Resolution route; only `ui` (the trusted human
                route) resolves.
            actor: Human actor the decision is attributed to.

        Returns:
            Resolution with approval_id, approval_state,
                execution_id, and the run_id once admitted.

        Raises:
            ExecutionError: approval_invalid for an unknown approval
                or any binding drift, approval_forbidden for a
                non-UI route, approval_denied when a lapsed
                approval is approved, approval_expired when a
                lapsed approval is approved, invalid_command for
                any other decision text.
        """
        record = self._binding(approval_id)
        if decision not in ("approved", "denied"):
            raise ExecutionError(
                "invalid_command",
                f"decision must be approved or denied, got {decision!r}.",
            )
        if via != "ui":
            raise ExecutionError(
                "approval_forbidden",
                "Approvals resolve through the human UI route only; "
                "agent calls cannot self-approve.",
            )
        state = record["state"]
        if state == "denied":
            raise ExecutionError(
                "approval_denied", "Approval was denied; no run exists."
            )
        if state == "expired":
            raise ExecutionError(
                "approval_expired", "Approval expired; no run exists."
            )
        if state == "approved":
            return {
                "approval_id": approval_id,
                "approval_state": "approved",
                "execution_id": record["execution_id"],
                "run_id": record["run_id"],
            }
        if decision == "denied":
            record["state"] = "denied"
            record["reason"] = "Denied on the human UI route."
            record["resolved_by"] = actor or self._actor
            self._persist_approval(record)
            self._reap_terminal()
            return {
                "approval_id": approval_id,
                "approval_state": "denied",
                "execution_id": record["execution_id"],
            }
        self._sweep_expired()
        if record["state"] == "expired":
            raise ExecutionError(
                "approval_expired", "Approval expired; no run exists."
            )
        if record["generation"] != self._generation:
            record["state"] = "expired"
            record["reason"] = "Approval generation retired; request again."
            self._persist_approval(record)
            raise ExecutionError(
                "approval_expired", "Approval expired; no run exists."
            )
        if record["history_cursor"] != self._cursor:
            raise ExecutionError(
                "approval_invalid",
                "History moved since the approval was bound.",
            )
        if self._cell_digest(record["execution_id"]) != record["code_sha256"]:
            raise ExecutionError(
                "approval_invalid",
                "Cell bytes changed under their approval.",
            )
        if self._revision_provider is not None:
            current = self._revision_provider()
            if current != record["expected_revision"]:
                raise ExecutionError(
                    "approval_invalid",
                    f"Project moved since approval: {record['expected_revision']} "
                    f"is stale at {current}.",
                )
        run_id = record["run_id"] or uuid.uuid4().hex
        self._execution.dispatch(
            "python_execute",
            {"project": self._project_id,
             "revision": record["expected_revision"]},
            "",
            run_id=run_id,
        )
        record["run_id"] = run_id
        record["state"] = "approved"
        record["resolved_by"] = actor or self._actor
        self._runs[run_id] = record["execution_id"]
        self._persist_approval(record)
        return {
            "approval_id": approval_id,
            "approval_state": "approved",
            "execution_id": record["execution_id"],
            "run_id": run_id,
        }

    def _persist_approval(self, record):
        (self._root / "approvals" / ("%s.yaml" % record["approval_id"])).write_text(
            self._dump({**record, "project_id": self._project_id}),
            encoding="utf-8",
        )

    def _lapse_reason(self, record):
        if record["generation"] != self._generation:
            return "Approval generation retired before dispatch."
        if self._clock() > record["expires_at"]:
            return "Approval expired before dispatch."
        return None
