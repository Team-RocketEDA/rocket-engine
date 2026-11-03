# RUAMEL-DUMPER: Fresh dumpers for Engine/ProjectService YAML writes

*Status: Ready · Depends: none · Size: XS ·
Roadmap: hardening (follow-up from CONSOLE-ROUTE lane)*

## Why

The CONSOLE-ROUTE lane proved a nasty failure mode: a
failed ruamel `safe_dump` poisons the dumper instance,
which then emits empty text forever. The lane's own
module uses fresh dumpers with a pinned regression test
— but Engine/ProjectService long-lived dumpers share
the exposure. One failed write today could silently
hollow all later writes through the same instance.

## What

- RED-first: reproduce the poisoned-dumper silence on
  the Engine/ProjectService write path, then switch to
  fresh dumpers (or a verified reset) with the same
  regression pin the lane used.
- No behavior change on the happy path; the fix only
  removes the silent-empty tail risk.

## Acceptance

- Poison scenario emits loud errors, never empty text;
  full suite + gate green.
