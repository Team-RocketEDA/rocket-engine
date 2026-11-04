# DEFERRED-LANE-INTENT: Confirm deferred tools never install under full --install

*Status: Backlog · Filed: 2026-11-04 · Source: multi-agent review 2026-11-04*

`check_pymeep`/`check_openems` record absence via `markd_missing`
(`MISSINGD`), but the full-install loop
(`scripts/provision_toolchain.sh:1549-1553`) only installs tools listed
in `MISSING2`. Deferred tools (pymeep, openems, elmer, devsim) therefore
never install under a full `--install`; only `--only <tool>` installs
them. Unclear whether this is the intended deferred-lane design or a
loop bug — and it is the mechanism behind the "Trilinos blocks pymeep"
misread (shared red run, MVP-lane nonzero exit).

## Goal

A recorded intent decision plus exit reporting that keeps the MVP lane
honest without hiding deferred state.

## Scope

- Rule on: intentional (full `--install` = MVP lanes only; deferred
  tools are `--only` by design) vs bug (loop should also drain
  `MISSINGD`).
- If intentional: document in `provision-plan.md` + remedy text, and
  split `verdict()` exit reporting so a deferred-only miss cannot read
  as an MVP failure (the perceptual block).
- If bug: extend the install loop to drain `MISSINGD` with the same
  per-tool isolation (`|| true`).

## Acceptance

- Intent recorded; `--install` and `--only pymeep`/`--only openems`
  each produce a truthful per-lane verdict on a host missing both.
