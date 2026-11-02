Problem batch (core execution integrity):
1. Solver runs have no core timeout/cancel/tree-kill (cancel flips a flag; "Real tree termination arrives with real workers"); runner.py timeouts exist but core never applies them to solver path. MC-28.
2. No core confinement: direct adapter invocation; bwrap only for console/pyexec cells. MC-28.
3. No drift check on resume/replay (stored command re-executes with no head comparison). MC-34.
4. Findings + native logs in-memory only; reboot loses per-finding evidence (unknown_run after reboot). MC-35.
5. run.request knobs validated+frozen but never consumed by any solver path — consume or retire. MC-33.
6. Generic approval ledger (request_approval/admit) is dead code — retire per RULING-04 (pyexec UI-route approvals are the live path). MC-45.
Expected-per: frontend-tooling-spec §3; REPLAY-SAFE; I28; RULING-04.
