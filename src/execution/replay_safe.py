"""Report-not-run survivors + explicit resume + poison quarantine (REPLAY-SAFE).

Boot replay that auto-executes is a grief loop: a hung deck gets
pkill'd, the engine reboots, and faithfully re-runs the exact job
that hung. The safe default when escape and accident are
indistinguishable is: don't act, report. The ledger holding the jobs
IS the 0%-drop guarantee; replay is pure convenience, and this module
keeps every replay surface gated behind an explicit user decision.

Survivors are ledger-admitted runs (`job_queued`) with no completion
event (`run_completed`/`run_failed`) and no discard event
(`run_discarded`): `boot()` lists them and NEVER executes. Each
survivor carries one taxonomy kind: RETRYABLE (never started),
AMBIGUOUS (started, no completion — outage or poison), or POISON (its
content key was interrupted twice — quarantined, resume only with
force). Interruption counts live in the ledger as `run_interrupted`
events keyed by content key, so a rebooted process classifies
correctly with no in-memory state.

Finished runs are NEVER re-executed, and no transcript of completed
job ids is ever re-run: runs are reproducible from (snapshot + deck
+ params), so resubmit-when-wanted covers everything.
"""

import hashlib
import json
import logging

try:
    from .errors import ExecutionError
except ImportError:  # standalone verification before install
    from rocket_engine.execution.errors import ExecutionError

REPLAY_SAFE_VERSION = 1

# Twice-interrupted content keys quarantine: the deck that killed you
# can never auto-run again.
POISON_THRESHOLD = 2

RETRYABLE = "retryable"
AMBIGUOUS = "ambiguous"
POISON = "poison"

JOB_QUEUED = "job_queued"
RUN_STARTED = "run_started"
RUN_INTERRUPTED = "run_interrupted"
RUN_DISCARDED = "run_discarded"
_RUN_OUTCOMES = ("run_completed", "run_failed")

# Typed refusal codes -> user-facing messages. Friendly, no internals:
# never a run id, content key, seq, or traceback. Full context goes to
# the dev-side log at each refusal site instead.
USER_MESSAGES = {
    "unknown_survivor": (
        "We couldn't find that unfinished run. "
        "It may have already been handled."
    ),
    "already_completed": (
        "That run already finished, so there is nothing to resume."
    ),
    "already_decided": "That run was already handled in this session.",
    "poison_quarantined": (
        "This run is paused for safety after repeated interruptions. "
        "Please review it before retrying."
    ),
    "ambiguous_requires_explicit_resume": (
        "This run stopped partway through, so it needs your individual "
        "review before resuming."
    ),
}

logger = logging.getLogger(__name__)


def content_key_for(operation, arguments):
    """Stable identity for one run's normalized content.

    The key covers the operation plus its arguments (deck hash rides
    inside the arguments), so identical resubmits share one key and
    one interruption count while any argument change starts fresh.

    Args:
        operation: Cataloged operation name.
        arguments: Operation arguments mapping.

    Returns:
        Content key (`ck_` plus 16 hex chars), stable over key order.
    """
    payload = json.dumps(
        {"operation": operation, "arguments": arguments or {}},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"ck_{digest}"


def interrupt_counts_from_events(events):
    """Admitted->interrupted transitions per content key.

    Args:
        events: Ledger events with event and data.content_key entries.

    Returns:
        Mapping of content key to its `run_interrupted` count.
    """
    counts = {}
    for event in events:
        if event.get("event") != RUN_INTERRUPTED:
            continue
        key = (event.get("data") or {}).get("content_key")
        if key:
            counts[key] = counts.get(key, 0) + 1
    return counts


def survivors_from_events(events, resolve=None):
    """Ledger-admitted runs with no completion or discard, oldest first.

    Kinds: never-started runs are RETRYABLE; started-but-uncompleted
    runs are AMBIGUOUS; runs whose content key reached
    POISON_THRESHOLD interruptions are POISON (quarantined). A missing
    content key never quarantines: without a key there is no count.

    Args:
        events: Ledger events with seq, event, request_id, and
            data.run_id entries; `job_queued` data may carry
            content_key (post-wiring ledgers).
        resolve: Optional `request_id -> (command, ack)` for
            pre-wiring ledgers whose `job_queued` events lack
            content_key. May raise or return None per id; either
            leaves that survivor keyless, never skipped.

    Returns:
        Survivor mappings in admit order, each with run_id,
            request_id, operation, content_key (None when
            unresolvable), kind, interrupts, quarantined, and the
            always-offered actions ["resume", "discard"].
    """
    queued = {}
    order = []
    completed = set()
    discarded = set()
    started = set()
    for event in sorted(events, key=lambda e: e.get("seq", 0)):
        name = event.get("event")
        data = event.get("data") or {}
        run_id = data.get("run_id")
        if run_id is None:
            continue
        if name == JOB_QUEUED:
            if run_id not in queued:
                order.append(run_id)
            queued[run_id] = {
                "request_id": event.get("request_id"),
                "operation": data.get("operation"),
                "content_key": data.get("content_key"),
            }
        elif name in _RUN_OUTCOMES:
            completed.add(run_id)
        elif name == RUN_DISCARDED:
            discarded.add(run_id)
        elif name == RUN_STARTED:
            started.add(run_id)
    counts = interrupt_counts_from_events(events)
    survivors = []
    for run_id in order:
        if run_id in completed or run_id in discarded:
            continue
        entry = queued[run_id]
        key = entry["content_key"]
        if key is None and resolve is not None:
            try:
                resolved = resolve(entry["request_id"])
            except Exception:
                resolved = None
            if resolved is not None:
                command, _ack = resolved
                key = content_key_for(
                    command.get("operation"),
                    command.get("arguments") or {},
                )
        interrupts = counts.get(key, 0) if key else 0
        if key is not None and interrupts >= POISON_THRESHOLD:
            kind = POISON
        elif run_id in started:
            kind = AMBIGUOUS
        else:
            kind = RETRYABLE
        survivors.append({
            "run_id": run_id,
            "request_id": entry["request_id"],
            "operation": entry["operation"],
            "content_key": key,
            "kind": kind,
            "interrupts": interrupts,
            "quarantined": kind == POISON,
            "actions": ["resume", "discard"],
        })
    return survivors


def boot_message(unfinished):
    """Pkill-then-boot message: what happened, what did not run.

    Args:
        unfinished: Survivor count from the boot report.

    Returns:
        Session-ended message naming the unfinished count plus the
            nothing-re-ran promise (or the clean-session variant when
            zero), always pointing at per-run Resume/Discard.
    """
    if unfinished <= 0:
        return (
            "Last session ended cleanly. "
            "No unfinished runs \u2014 nothing to resume."
        )
    noun = "run" if unfinished == 1 else "runs"
    return (
        f"Last session ended unexpectedly. {unfinished} {noun} "
        "unfinished \u2014 nothing re-ran automatically. "
        "Review each run to Resume or Discard it."
    )


def user_message_for(code):
    """Friendly user-facing message for one refusal code.

    Args:
        code: Typed refusal code.

    Returns:
        User-facing message with no internals; a generic
            review-prompt for unknown codes (never a KeyError).
    """
    return USER_MESSAGES.get(
        code, "This run needs your review before it can continue."
    )


def refuse(code, dev_detail):
    """Log full dev context, then raise the friendly typed refusal.

    Args:
        code: Typed refusal code (keys USER_MESSAGES).
        dev_detail: Dev-side context (ids, keys, counts) for the
            log only — never surfaced to the user.

    Raises:
        ExecutionError: Always, carrying the code plus the
            user-facing message.
    """
    logger.warning("replay_safe refusal code=%s detail=%s", code, dev_detail)
    raise ExecutionError(code, user_message_for(code))


def _latest_seq(events, name, run_id):
    """Latest seq of one event name for one run (-1 when absent)."""
    best = -1
    for event in events:
        if event.get("event") != name:
            continue
        if (event.get("data") or {}).get("run_id") != run_id:
            continue
        seq = event.get("seq", 0)
        if seq > best:
            best = seq
    return best


class ReplaySafe:
    """Explicit-decision replay controller over a durable ledger.

    Boot reports, the user decides, and only then does anything run:
    `boot()` never executes, `discard()` only records, and the
    executor fires solely inside an explicit `resume()` or
    `resume_all_retryable()` call.

    Args:
        project: Ledger port with `events_since(cursor)`,
            `command_for(request_id)`, and
            `append_replay_event(event, request_id, data)`.
        executor: Callable `(operation, arguments, snapshot_id,
            request_id, run_id)` returning a completion mapping.
            It fires only on explicit resume, never on boot.

    Caution: One instance per boot: per-run decisions
        (resumed/discarded) are tracked in memory so a second
        action on the same run refuses instead of double-running.
    """

    def __init__(self, project, executor):
        self._project = project
        self._executor = executor
        self._decided = {}

    def _resolve_soft(self, request_id):
        """Admitted (command, ack), or None when unresolvable."""
        try:
            return self._project.command_for(request_id)
        except Exception:
            return None

    def _live_survivors(self, events):
        by_id = {}
        for survivor in survivors_from_events(
            events, self._resolve_soft
        ):
            by_id[survivor["run_id"]] = survivor
        return by_id

    def _completed_runs(self, events):
        """Run ids with a completion event."""
        return {
            (event.get("data") or {}).get("run_id")
            for event in events
            if event.get("event") in _RUN_OUTCOMES
        } - {None}

    def _check_decided(self, run_id):
        """Refuse resumed/discarded runs; completed ones stay live."""
        if run_id in self._decided:
            refuse(
                "already_decided",
                f"run_id={run_id} decision={self._decided[run_id]}",
            )

    def boot(self):
        """Report crash survivors without executing anything.

        Started-but-uncompleted runs gain one ledger
        `run_interrupted` mark each (idempotent: a mark counts until
        the next `run_started`), so the taxonomy reflects this boot's
        outages before the report is built.

        Returns:
            Report with version, the pkill-then-boot message, the
                unfinished count, survivors in admit order,
                quarantined run ids, and unresolved entries
                (pre-wiring admissions whose command is gone — each
                with request_id, run_id, and reason).

        Caution: Report-only by construction: the executor is never
            invoked here, only inside an explicit resume call.
        """
        events = self._project.events_since(0)
        request_run = {}
        for event in events:
            if event.get("event") == JOB_QUEUED:
                request_run[event.get("request_id")] = (
                    event.get("data") or {}
                ).get("run_id")
        unresolved = []

        def _resolve(request_id):
            try:
                return self._project.command_for(request_id)
            except Exception as exc:
                unresolved.append({
                    "request_id": request_id,
                    "run_id": request_run.get(request_id),
                    "reason": f"{type(exc).__name__}: {exc}",
                })
                return None

        survivors = survivors_from_events(events, _resolve)
        for survivor in survivors:
            key = survivor["content_key"]
            if key is None:
                continue
            run_id = survivor["run_id"]
            if _latest_seq(events, RUN_STARTED, run_id) > _latest_seq(
                events, RUN_INTERRUPTED, run_id
            ):
                self._project.append_replay_event(
                    RUN_INTERRUPTED,
                    survivor["request_id"],
                    {
                        "run_id": run_id,
                        "content_key": key,
                        "operation": survivor["operation"],
                    },
                )
                logger.info(
                    "replay_safe interrupted run_id=%s key=%s",
                    run_id,
                    key,
                )
        events = self._project.events_since(0)
        survivors = survivors_from_events(events, _resolve)
        quarantined = [
            survivor["run_id"]
            for survivor in survivors
            if survivor["quarantined"]
        ]
        logger.info(
            "replay_safe boot unfinished=%d quarantined=%d",
            len(survivors),
            len(quarantined),
        )
        return {
            "version": REPLAY_SAFE_VERSION,
            "message": boot_message(len(survivors)),
            "unfinished": len(survivors),
            "survivors": survivors,
            "quarantined": quarantined,
            "unresolved": unresolved,
        }

    def resume(self, run_id, force=False):
        """Explicitly resume one survivor through the executor.

        Quarantined (POISON) runs resume only with force; every other
        survivor resumes on the explicit call. A `run_started` mark is
        appended first, so a kill mid-resume classifies AMBIGUOUS (or
        POISON) at the next boot instead of vanishing.

        Args:
            run_id: Survivor to resume.
            force: Required for quarantined runs; refused loudly
                without it. Force bypasses quarantine only — the
                run still executes for real.

        Returns:
            Executor completion for the run.

        Raises:
            ExecutionError: already_decided for a run handled this
                session, already_completed for a run that finished
                since the report, unknown_survivor for an id with
                no unfinished run, poison_quarantined for a
                quarantined run resumed without force.

        Caution: This executes the run — the one replay surface
            that does, and only on this explicit call.
        """
        events = self._project.events_since(0)
        self._check_decided(run_id)
        if run_id in self._completed_runs(events):
            refuse(
                "already_completed",
                f"run_id={run_id} completed_since_report=True",
            )
        survivor = self._live_survivors(events).get(run_id)
        if survivor is None:
            refuse("unknown_survivor", f"run_id={run_id}")
        if survivor["quarantined"] and not force:
            refuse(
                "poison_quarantined",
                f"run_id={run_id} key={survivor['content_key']} "
                f"interrupts={survivor['interrupts']} force={force}",
            )
        try:
            command, ack = self._project.command_for(
                survivor["request_id"]
            )
        except Exception as exc:
            refuse(
                "unknown_survivor",
                f"run_id={run_id} "
                f"request_id={survivor['request_id']} "
                f"resolve_failed={type(exc).__name__}: {exc}",
            )
        self._project.append_replay_event(
            RUN_STARTED,
            survivor["request_id"],
            {
                "run_id": run_id,
                "content_key": survivor["content_key"],
                "operation": survivor["operation"],
            },
        )
        completion = self._executor(
            command.get("operation"),
            dict(command.get("arguments") or {}),
            ack.get("snapshot_id", ""),
            survivor["request_id"],
            run_id,
        )
        self._decided[run_id] = "resumed"
        logger.info(
            "replay_safe resumed run_id=%s kind=%s forced=%s",
            run_id,
            survivor["kind"],
            bool(force),
        )
        return completion

    def discard(self, run_id):
        """Explicitly discard one survivor, never executing it.

        The run gains a `run_discarded` ledger event and leaves all
        future survivor reports.

        Args:
            run_id: Survivor to discard.

        Returns:
            Discard record with run_id, discarded state, and the
                run's operation.

        Raises:
            ExecutionError: already_decided for a run handled this
                session, already_completed for a finished run,
                unknown_survivor for an id with no unfinished run.
        """
        events = self._project.events_since(0)
        self._check_decided(run_id)
        if run_id in self._completed_runs(events):
            refuse(
                "already_completed",
                f"run_id={run_id} completed_since_report=True",
            )
        survivor = self._live_survivors(events).get(run_id)
        if survivor is None:
            refuse("unknown_survivor", f"run_id={run_id}")
        self._project.append_replay_event(
            RUN_DISCARDED,
            survivor["request_id"],
            {"run_id": run_id, "operation": survivor["operation"]},
        )
        self._decided[run_id] = "discarded"
        logger.info("replay_safe discarded run_id=%s", run_id)
        return {
            "run_id": run_id,
            "state": "discarded",
            "operation": survivor["operation"],
        }

    def resume_all_retryable(self):
        """Resume every RETRYABLE survivor, oldest first.

        AMBIGUOUS runs need individual review and POISON runs need
        per-run force, so both are skipped loudly — never swept up.

        Returns:
            Batch with resumed run ids, their completions, and
                skipped entries (each with run_id, typed code, and
                user-facing message).

        Raises:
            ExecutionError: Propagates the first executor failure
                unchanged — earlier resumes in the batch stand,
                later ones never fire.

        Caution: This executes runs — only the RETRYABLE,
            non-quarantined survivors, and only on this call.
        """
        events = self._project.events_since(0)
        resumed = []
        completions = []
        skipped = []
        for survivor in survivors_from_events(events, self._resolve_soft):
            run_id = survivor["run_id"]
            if run_id in self._decided:
                code = "already_decided"
            elif survivor["quarantined"]:
                code = "poison_quarantined"
            elif survivor["kind"] != RETRYABLE:
                code = "ambiguous_requires_explicit_resume"
            else:
                completions.append(self.resume(run_id))
                resumed.append(run_id)
                continue
            skipped.append({
                "run_id": run_id,
                "code": code,
                "message": user_message_for(code),
            })
            logger.info(
                "replay_safe skipped run_id=%s code=%s", run_id, code
            )
        return {
            "resumed": resumed,
            "completions": completions,
            "skipped": skipped,
        }
