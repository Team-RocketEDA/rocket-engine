Problem (RULING-04): console sandbox undecided. The console is a plain python console in a trusted-local, never-cloud deployment with user-side permissions — so the only question is hygiene vs friction.
Study (comparative, evidence-based): (1) bwrap-keep: system hygiene gains vs adoption friction + observed/predicted future-bug surface (breakage reports, failure modes); (2) raw python exec: friction wins vs hygiene loss; (3) prepackaged scripting contexts (project-aware preludes, safe stdlib surface) as middle path.
Standing requirement (RULING-07): live env provides every library a client may need for scripting, with appropriate project contexts — evaluate each option against it.
Deliverable: decision + rationale recorded; feeds CONSOLE-LIFECYCLE (T-08). No code until the study lands.

## Verdict (2026-11-03, landed)

Study landed as `docs/probe-bwrap-console.md` (no code, per the
ticket). Decision: keep bwrap-confined workers as the only
cell-execution substrate — no raw-exec mode — and grow prepackaged
project-aware preludes as the friction reducer. Evidence weighed:
`docs/probe-bwrap-isolation.md` (userns confinement proven,
net-ns unprovable here), current `CellRunner`/`PythonExecRunner`
already confine with loud refusal (`runner_unavailable`, never
silent escape), a fresh probe on this host (`/usr/bin/bwrap`
preflights OK; the oss-cad-suite shadow binary refuses loudly with
"No permissions to create a new namespace" — the predicted friction
case, failing closed), and the existing digest-pinned preamble
templates meeting RULING-07 inside the sandbox. CONSOLE-LIFECYCLE feed:
lifecycle (generation + approval binding + reset) unchanged; where
bwrap is unprovable the console records but admits nothing.
Open for B10: re-prove `--unshare-net` on target Ubuntu; decide
bwrap provenance/PATH order.
