Follow-up to the CONSOLE-APPLY retire commit: ConsoleSession
(console/session.py) is still the live approval-bound cell surface
used by lifecycle.py and stdio_console.py, while ApplySession is the
new atomic host-side context. Migrate the session cell path onto
ApplySession (behavioral slice: worker replay, approvals binding,
lifecycle status), then remove session.py. Needs its own RED first.


---

*Appended 2026-11-04.*

# Review question (2026-11-04): CONSOLE-APPLY seam scope

The 2026-11-04 review could not determine the seam between Done
[CONSOLE-APPLY](CONSOLE-APPLY.md) and this migration: CONSOLE-APPLY's
Done evidence says "ConsoleSession kept; its migration is
CONSOLE-SESSION-MIGRATE", and the dirty tree has the new
`execution/console/apply_session.py:53,402` — but whether the session
cell path already lands through `apply_batch` somewhere vs needs its
own RED first is unclear. Please confirm in this file: (a) current
cell path (old route vs ApplySession), (b) whether a RED test for the
migration exists yet, (c) what "remove session.py" deletes beyond the
cell path. Step 11A stays RED until answered.
