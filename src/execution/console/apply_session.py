"""Approval-bound console cells on the atomic apply-context.

CONSOLE-SESSION-MIGRATE (ADR-016 follow-up): the old in-memory
`ConsoleSession` (approved code plus history cursor, environment
digest, and revision binding, with reset killing every outstanding
approval) now rides `ApplySession` instead of standing beside it.
One object owns both halves: the approval binding admits one
worker run, and any worker-staged intents the run leaves behind
land as exactly one atomic batch through `Engine.apply_batch` —
the same path the editor surface uses, so console writes are
never a side-channel writer.

Identity follows ADR-016: one live instance per (console,
generation). `reset` retires the apply side (dropping buffered
and staged intents), rotates the generation, kills every
outstanding approval, and rearms the context for the next
generation. `retire` from `ApplySession` is permanent and is
only used inside `reset`, never by callers.
"""

import uuid

from ..errors import ExecutionError
from ..pyexec.apply_context import ApplySession

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


class ConsoleSession(ApplySession):
    """Approval-bound console cells on one atomic apply-context.

    The approval half pins one cell plus its context (full worker
    source, history cursor, environment digest, expected revision);
    admitting re-checks every field and any drift fails instead
    of running a stranger's cell. The apply half stages worker
    intent lines and emits one batch per outermost clean exit;
    `land_worker_intents` drains a worker ops log and lands the
    emitted batch through `Engine.apply_batch`.

    Args:
        project_id: Project this session approves cells for.
        actor: Actor recorded on approvals.
        console_id: Console owning this context; minted when
            omitted.
        pdk_name: PDK auto-activated at first block entry.
        activate_pdk: Callable mapping the PDK name to proof;
            a no-op activator when omitted.
        resolve_layer: Callable mapping a layer spec to its lid;
            the identity mapping when omitted.
        emit: Callable receiving each outermost-exit batch;
            batches accumulate on `emitted` when omitted.
    """

    def __init__(self, project_id, actor, console_id=None,
                 pdk_name="sky130", activate_pdk=None,
                 resolve_layer=None, emit=None):
        self._actor = actor
        self._approvals = {}
        self._cursor = 0
        self._emitted = []
        super().__init__(
            emit=emit if emit is not None else self._emitted.append,
            project_id=project_id,
            console_id=console_id or uuid.uuid4().hex,
            generation=uuid.uuid4().hex,
            pdk_name=pdk_name,
            activate_pdk=(activate_pdk if activate_pdk is not None
                          else (lambda name: {"pdk": name,
                                              "activated": True})),
            resolve_layer=(resolve_layer if resolve_layer is not None
                           else (lambda spec: spec)),
        )

    @property
    def console_id(self):
        """Console owning this context (fixed for its lifetime).

        Returns:
            Console id string.
        """
        return self._console_id

    @property
    def generation(self):
        """Current approval generation; reset retires it.

        Reads and writes the generation the apply-context
        stamps on every emitted batch, so approval fencing and
        batch identity can never disagree.

        Returns:
            Generation id string.
        """
        return self._generation

    @generation.setter
    def generation(self, value):
        """Sync the generation (for example, after a restart reload).

        Args:
            value: Generation id to fence on from here.
        """
        self._generation = value

    @property
    def emitted(self):
        """Batches emitted so far, oldest first (evidence only).

        Returns:
            Emitted batch mappings in emission order.
        """
        return list(self._emitted)

    def request_cell_approval(self, code, history_cursor, env_digest,
                              expected_revision):
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
        """Return the live binding for one approval.

        Args:
            approval_id: Approval bound by request_cell_approval.

        Returns:
            Live approval record.

        Raises:
            ExecutionError: approval_invalid for an unknown or
                expired approval.
        """
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
        of running a stranger's cell. This is the seam the worker
        lane (`CellRunner.run_cell`) admits through.

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

        The worker run itself happens in the worker lane (admitted
        through `admit_cell`); landing worker-staged intents is
        `land_worker_intents`, not this method.

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

    def land_worker_intents(self, engine, ops_log_path, label):
        """Drain worker intent lines and land one atomic batch.

        Lines shaped ``{"apply_intent": {...}}`` in the worker ops
        log join the session; anything else in the log is not ours
        and stays unread. The staged intents emit as one batch at
        the outermost exit and land through
        `Engine.apply_batch` — one transaction, one revision.

        Args:
            engine: Engine landing the batch; when it has no
                `apply_batch`, nothing is collected and None
                returns.
            ops_log_path: Worker ops-log path to drain.
            label: Batch label carried on the envelope.

        Returns:
            Landing with ok True, the engine receipt, and the
                intent count — or None when nothing was staged
                or the engine cannot land.

        Raises:
            ProjectError: retired_session on a retired session;
                invalid_command for an unknown sink kind;
                revision_conflict when the head moved under the
                batch.
        """
        land = getattr(engine, "apply_batch", None)
        if land is None:
            return None
        staged = self.collect_ops(ops_log_path)
        if staged == 0 and not self._staged:
            return None
        with self.edit(label):
            pass
        batch = self.last_batch
        if batch is None:
            return None
        receipt = land(batch)
        return {"ok": True, "receipt": receipt,
                "intents": len(batch["intents"]), "label": batch["label"]}

    def reset(self):
        """Retire the generation and kill every outstanding approval.

        The apply side retires too (buffered and staged intents
        drop), then the context rearms under a fresh generation:
        in-flight blocks must never span a reset — blocks are
        synchronous, so a reset lands between cells, never inside
        one.

        Returns:
            Mapping with the fresh generation id.
        """
        self.retire()
        self._generation = uuid.uuid4().hex
        self._approvals = {}
        self._cursor = 0
        self._retired = False
        self._depth = 0
        self._buffer = []
        self._span = []
        self._staged = []
        self._pdk_active = False
        return {"generation": self._generation}
