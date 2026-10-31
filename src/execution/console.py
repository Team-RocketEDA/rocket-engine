"""In-memory console surface (B8, slice 6): approvals, lifecycle, help.

Binding semantics are real: approvals pin code, history cursor,
environment digest, and revision, and reset kills every outstanding
approval. execute_cell records history without running code;
isolated execution lives in worker.py — CellRunner admits through
admit_cell and runs each cell in a fresh BwrapRunner-confined
worker (I23/I24).
"""

import uuid

from .errors import ExecutionError

CONTRACT_VERSION = "rocketeda/tooling/v0.1"

_HELP = {
    "run_drc": {
        "signature": "run_drc(target, deck, profile?)",
        "example": "op = run_drc(target='amplifier', deck='sky130A/decks.drc')",
    },
    "run_spice": {
        "signature": "run_spice(netlist, benches, corners?)",
        "example": "op = run_spice(netlist='amp_tb', benches=['ac', 'tran'])",
    },
    "python_execute": {
        "signature": "python_execute(code_ref, profile)",
        "example": "cell = python_execute(code_ref='analysis/fit.py', profile='design')",
    },
}


def get_help(topic):
    """Return versioned help metadata. Pure data — executes nothing.

    Args:
        topic: Help topic name (run_drc, run_spice, python_execute).

    Returns:
        Help entry with topic, contract version, signature, and
            example.

    Raises:
        ExecutionError: unknown_topic for an unlisted topic.
    """
    try:
        entry = _HELP[topic]
    except KeyError:
        raise ExecutionError("unknown_topic", f"Unknown help topic: {topic}.") from None
    return {"topic": topic, "version": CONTRACT_VERSION, **entry}


class ConsoleSession:
    """In-memory console approvals with binding semantics.

    Args:
        project_id: Project this session approves cells for.
        actor: Actor recorded on approvals.
    """

    def __init__(self, project_id, actor):
        self._project_id = project_id
        self._actor = actor
        self.generation = uuid.uuid4().hex
        self._approvals = {}
        self._cursor = 0

    def request_cell_approval(self, code, history_cursor, env_digest, expected_revision):
        """Bind a pending approval to one cell plus its context.

        Args:
            code: Full worker source the approval pins.
            history_cursor: History position the approval pins.
            env_digest: Environment digest the approval pins.
            expected_revision: Revision the approval pins.

        Returns:
            Approval record with approval_id and pending state.
        """
        approval_id = uuid.uuid4().hex
        self._approvals[approval_id] = {
            "approval_id": approval_id,
            "code": code,
            "history_cursor": history_cursor,
            "env_digest": env_digest,
            "expected_revision": expected_revision,
            "state": "pending_approval",
        }
        return {"approval_id": approval_id, "state": "pending_approval"}

    def _binding(self, approval_id):
        try:
            return self._approvals[approval_id]
        except KeyError:
            raise ExecutionError(
                "approval_invalid", "Unknown or expired approval."
            ) from None

    def admit_cell(self, approval_id, code, history_cursor, env_digest,
                   expected_revision):
        """Admit a cell whose context still matches its binding.

        Any drift in code, cursor, env, or revision fails instead
        of running a stranger's cell.

        Args:
            approval_id: Approval bound by request_cell_approval.
            code: Full worker source to re-check against the binding.
            history_cursor: History position to re-check.
            env_digest: Environment digest to re-check.
            expected_revision: Revision to re-check.

        Returns:
            Approval record with approval_id and approved state.

        Raises:
            ExecutionError: approval_invalid for an unknown approval
                or any binding drift.
        """
        binding = self._binding(approval_id)
        if (
            binding["code"] != code
            or binding["history_cursor"] != history_cursor
            or binding["env_digest"] != env_digest
            or binding["expected_revision"] != expected_revision
        ):
            raise ExecutionError(
                "approval_invalid", "Approval no longer matches its binding."
            )
        binding["state"] = "approved"
        return {"approval_id": approval_id, "state": "approved"}

    def execute_cell(self, approval_id, code):
        """Record a cell execution without running code.

        Args:
            approval_id: Approval whose code must match.
            code: Cell code to re-check against the binding.

        Returns:
            Record with the advanced cursor and recorded state.

        Raises:
            ExecutionError: approval_invalid for an unknown approval
                or code that differs from the approved code.
        """
        binding = self._binding(approval_id)
        if binding["code"] != code:
            raise ExecutionError(
                "approval_invalid", "Cell code differs from the approved code."
            )
        self._cursor += 1
        return {"cursor": self._cursor, "state": "recorded"}

    def reset(self):
        """Retire the generation and kill every outstanding approval.

        Returns:
            Mapping with the fresh generation id.
        """
        self.generation = uuid.uuid4().hex
        self._approvals = {}
        self._cursor = 0
        return {"generation": self.generation}
