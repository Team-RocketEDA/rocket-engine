# REPLAY-SAFE: Report-not-run survivors + explicit resume + poison quarantine

*Status: Ready · Depends: none · Size: M ·
Roadmap: convergence (MVP track, user-gated replay)*

## Why

Boot replay that auto-executes is a grief loop: a hung
deck gets pkill'd, the engine reboots, and faithfully
re-runs the exact job that hung — because at boot the
engine cannot distinguish "user killed me to escape" from
"the power died." The safe default when escape and
accident are indistinguishable is: don't act, report.
Durability never needed auto-replay anyway — the ledger
holding the jobs IS the 0%-drop guarantee; replay is pure
convenience, and conveniences don't fire without intent.
Every replay surface stays gated by explicit user
decision, with poison jobs quarantined so the deck that
killed you can never auto-run again.

## What

- RED-first: boot NEVER executes; boot reports survivors
  (ledger-admitted, no completion event) with per-run
  Resume/Discard + resume-all-retryable. No replay
  surface fires without explicit user decision.
- Survivor taxonomy: RETRYABLE (never-started queued) →
  offered resume; AMBIGUOUS (interrupted mid-execution) →
  explicit resume once; POISON (content key interrupted
  twice) → quarantined, resume only with force.
- Typed refusal codes + user-facing messages (friendly,
  no internals) with full context logged dev-side; ledger
  counts admitted→interrupted transitions per content key.
- Pkill-then-boot message: session ended unexpectedly, N
  unfinished, nothing re-ran automatically.
- Unattended auto-resume stays an explicit opt-in
  (flag/config), backlog, never default.

## Acceptance

- Kill -9 mid-queue → reboot → zero executions, full
  survivor report; resume works; twice-interrupted key
  quarantines and refuses without force.
- Contract + api_spec regen; full suite + gate green.
