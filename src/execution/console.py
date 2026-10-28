"""In-memory console surface (B8, slice 6): approvals, lifecycle, help.

Binding semantics are real: approvals pin code, history cursor,
environment digest, and revision, and reset kills every outstanding
approval. Workers are not real yet — execute_cell records history
without running code. Real isolated execution arrives with the worker
substrate (I16/I23/I24 stay unwritten until then).
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
    """Return versioned help metadata. Pure data — executes nothing."""
    try:
        entry = _HELP[topic]
    except KeyError:
        raise ExecutionError("unknown_topic", f"Unknown help topic: {topic}.") from None
    return {"topic": topic, "version": CONTRACT_VERSION, **entry}


class ConsoleSession:
    def __init__(self, project_id, actor):
        self._project_id = project_id
        self._actor = actor
        self.generation = uuid.uuid4().hex
        self._approvals = {}
        self._cursor = 0

    def request_cell_approval(self, code, history_cursor, env_digest, expected_revision):
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
        binding = self._binding(approval_id)
        if binding["code"] != code:
            raise ExecutionError(
                "approval_invalid", "Cell code differs from the approved code."
            )
        self._cursor += 1
        return {"cursor": self._cursor, "state": "recorded"}

    def reset(self):
        self.generation = uuid.uuid4().hex
        self._approvals = {}
        self._cursor = 0
        return {"generation": self.generation}
