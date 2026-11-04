# TRILINOS-LOG: Capture the Trilinos make-phase failure log

*Status: Backlog · Filed: 2026-11-04 · Source: multi-agent review 2026-11-04*

Three provision commits (`dff39be`, `aa3b8fc`, `bb124d5`) harden the
Trilinos 14-4-0 configure path (SuiteSparse AMD TPL dirs, Epetra set,
fossil guard) but no failing make-phase log is on record: the review
could not confirm what actually fails after a successful configure.

## Goal

One recorded failing build log, a named root cause, and a recipe fix —
or a scoped-out verdict with the blocker named.

## Scope

- Run `install_xyce` (or the Trilinos configure+make half) on the user
  host with output captured to a file; attach the tail + the failing
  command to this ticket (or `docs/provision-sources.md`).
- Fix the recipe (flags, TPL, package set, or pin change) or record why
  the serial Trilinos build cannot proceed on the reference host and
  what unparks it (Step 18 xyce leg stays parked until then).

## Acceptance

- Failing log evidence recorded; root cause named (configure vs make,
  which package/TPL).
- `install_xyce` green on the reference host, or an explicit
  still-blocked note with owner + next probe.


---

*Appended 2026-11-04.*

# Stale catalogue line (2026-11-04)

`src/interfaces/setup_catalogue.yaml` xyce entry still remedies
"Trilinos trilinos-release-17-2-1 first" while
`scripts/provision_toolchain.sh` pins `TRILINOS_REF=trilinos-release-14-4-0`
(17.x deleted the Epetra stack Xyce 7.10 needs). Update the entry's
remedy + recipe to 14-4-0 when this ticket's build work lands, and keep
catalogue pins mirrored with the script from then on.
