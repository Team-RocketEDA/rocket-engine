# E2E journey: photonic (MZI/cspdk) — review lane report

Ticket: `docs/tickets/E2E-REREVIEW.md` · Branch: GREEN-the-tests @ `a8aaa09`
Env: `UV_CACHE_DIR=/tmp/uv-cache UV_LINK_MODE=copy`,
`PATH=$HOME/tools/oss-cad-suite/bin:$HOME/tools/bin:$PATH`,
`ROCKETEDA_HOME=/tmp/rocketeda-live`. Toolchain observed: sax 0.18.2,
circulax, meow 0.15.0 (tidy3d 2.10.0), klayout, ngspice, iverilog/vvp;
**gdsfactory absent** (`uv sync --group layout` never run here).
Review-only: no src/tests/scripts/tracked-file edits; this file is the
lane's only artifact.

## Verdict table

| # | Leg | Command / probe | Result |
|---|---|---|---|
| J1 | Scenarios, photonic 4/4 | `.venv/bin/python scripts/scenarios.py /tmp/photonic-scen/` (symlinks to `sax_mzi_{pass,fail}` + `klayout_mzi_{pass,fail}`) | **PASS 4/4, exit 0** |
| J2 | Correctness, photonic flow | `.venv/bin/python scripts/correctness.py --flow photonic` | **GATE PASS 8/8** (mzi-layout-good, mzi-optical-good + 3 mutants × optical/layout), 0 quarantined; `tmp/correctness/report.json` |
| J3 | Mutants, photonic CLI | `scripts/mutate.py recheck` × {`photonic_geometry_mistune`,`photonic_circuit_mistune`} seed 0 | **2/2 proven** (`good PASS` + `mutated FAIL`, `rule_seen`), exit 0 |
| J4 | `run_optical` sax | J1/J2 + probe P9 (sax mutant native) | **PASS/FAIL correct** — mutant native `exit_code 0` → engine verdict **FAIL** (`transmission` only); layout side stays PASS |
| J5 | `run_optical` circulax | engine `run_optical` deck `circulax`, `good_rc.yml` / `slow_rc.yml` | **PASS + FAIL(`transient`)** — second tool live through the Engine, project spec in, transient out |
| J6 | `run_em` meow | engine `run_em` deck `meow`, `matched.yml` / `step.yml` | **NOT_RUN in default env** → F1; with `XDG_CONFIG_HOME=/tmp/xdg-clean` → **PASS** (T=1.0, margins +0.01/+1e-6/+0.01) |
| J7 | `generate_views` | engine `generate_views` recipe `import_gds` on cspdk mzi.gds | Honest **NOT_RUN** `missing_dependency: gdsfactory is not importable … (uv sync --group layout)`; clean-path capabilities row `blocked`/`available:false` |
| J8 | `run_view_sync` MZI | engine `run_view_sync` on `tests/workflows/fixtures/view_sync_mzi.json` | **FAIL with exactly the 5 planted diffs** (`wrong/missing/extra_port`, `unexpected_connection`, `unmapped`) |
| J9 | Repo photonic tests | pytest `test_photonic.py test_sax.py test_circulax_optical.py test_meow_em.py test_photonic_wire.py test_view_sync_mzi.py test_view_sync_wired.py test_generate_views.py test_gdsfactory.py` | **150 passed, 9 loud skips, 4 failed** — all 4 failures are F1 (meow live NOT_RUN); with clean XDG config home the 4 pass (4/4) |
| J10 | I27 falsification | `applicable_stages("photonic", …)` + `capabilities()` + completion-claim search | **HOLDS at planning layer** — 6 blocked stages on true signals (P05/P11/P12/P13/P21 generate_views, P19 thermal); no vacuous "fully verified" claim exists to fire → F3 (false-ready input), F4 (no claim surface) |
| J11 | I09 falsification | exit-0-with-violations, corrupt-envelope, garbage-spec probes | **HOLDS** — exit 0 + violations → FAIL; unparseable → `AdapterError` → engine NOT_RUN with reason; exit code never the verdict |
| J12 | Generalization spot | circulax/meow `execute` source + live runs on project specs | **PASS** — project YAML drives both (widths/wl/cell/modes/targets; R/C/V/t1/observe); no `run_rc_step`/`run_eme_smoke` constants in op path |

No flaky runs observed; nothing quarantined this lane (gate: 0
quarantined). J6/J9 failures are deterministic per-environment
(reproduced 2/2 probe runs + 4/4 tests), not flakes.

## Failure artifacts captured

- `MEOW-STDOUT` native (matched.yml, direct `MeowAdapter().execute`):
  `exit_code 0`, stdout =
  `23:03:19 +04 WARNING: Unable to write to
  '/home/alrida-ismail/.config/tidy3d'; falling back to temporary
  directory.` + `{"ok": true, "meow_version": "0.15.0", …}` envelope.
  Engine verdict on identical job: `{"status": "NOT_RUN", "reason":
  "runner_unavailable: meow driver printed no JSON envelope."}`
  (`/tmp/probe_photonic.py` P3/P4, `/tmp/probe_results.json`,
  rerun `/tmp/probe_rerun.log` — same).
- `MEOW-REMEDY`: same job with `XDG_CONFIG_HOME=/tmp/xdg-clean` →
  `{"status": "PASS", … measurements [transmission 1.0,
  reflection 0.0, convergence_dT 0.0]}`; the 4 failing repo tests
  pass 4/4 under the same remedy.
- `GF-SHADOW`: `/tmp/gdsfactory/` (empty dir, foreign residue) + a
  probe executed from /tmp → `find_spec('gdsfactory')` returns a
  namespace spec → capabilities `generate_views: ready/True` and
  `applicable_stages` flips P05/P11/P12/P13/P21 to ready
  (`/tmp/bisect_caps.py`: base already SET). Clean-path (`-c`,
  no /tmp on path): `find_spec None`, row `blocked`/`False`,
  6 blocked stages, 17 ready.
- `I09-HOLD`: sax mutant native `{"exit_code": 0}` → engine FAIL;
  `SaxAdapter().parse({stdout: "NOT JSON {{{"})` raises
  `AdapterError: sax driver printed no JSON envelope`; garbage-spec
  engine run → NOT_RUN `invalid_reference: Circuit spec is not YAML:
  …mzi.yml:1:1 …` (P9/P10).
- `VIEWSYNC-5`: engine `run_view_sync` verdict FAIL, rules
  `{view_sync.extra_port, view_sync.missing_port,
  view_sync.unexpected_connection, view_sync.unmapped,
  view_sync.wrong_port}` (P6).
- CLI rechecks: `/tmp/recheck-geo`, `/tmp/recheck-circ`
  (`proven:true` each). Gate report: `tmp/correctness/report.json`.

## Findings

### F1 — run_em live NOT_RUNs wherever tidy3d warns on stdout (meow strict parse)

Severity: high.
`src/adapters/meow/adapter.py:339` (`json.loads` of the whole
stdout) plus `:341-344` (any impurity → `runner_unavailable`) meets
tidy3d printing its unwritable-config warning to **stdout**, so a
healthy solve (`exit 0`, valid envelope, T=1.0) parses as "no JSON
envelope" and the Engine stamps NOT_RUN. This contradicts the
driver contract `src/adapters/meow/_driver.py:5-6` ("solver
warnings go to stderr untouched") — falsified in this environment.
Blast radius observed: 4 repo tests red
(`tests/adapters/test_meow_em.py` live ×2,
`tests/workflows/test_photonic_wire.py::test_live_meow_*` ×2);
any user with an unwritable `~/.config/tidy3d` loses `run_em`
entirely while capabilities still reports `run_em: ready`.
Proposed ticket title: `MEOW-STDOUT: tolerate solver warnings on stdout in run_em parse`.

### F2 — strict whole-stdout envelope parse is shared by all photonic adapters (latent)

Severity: medium.
Identical `json.loads(stdout)` strictness in
`src/adapters/sax/__init__.py:366`,
`src/adapters/circulax/adapter.py:397`, and
`src/adapters/gdsfactory/adapter.py:455`. Not triggered here (sax
and circulax drivers print clean envelopes in this env), but any
future stdout impurity (warning, banner, progress line) turns a
good solve into NOT_RUN the same way as F1.
Proposed ticket title: `ADAPTER-PARSE: shared stdout envelope extraction for solver drivers`.

### F3 — python availability probe false-positives on import shadows (I27 input)

Severity: medium.
`src/interfaces/setup.py:195` uses bare `find_spec`, which counts
an empty namespace directory as "installed", and `:431`/`445`
turn that into `available:true`/`readiness:ready` without
consulting the version lookup. Observed: foreign empty
`/tmp/gdsfactory/` + /tmp on `sys.path` → `generate_views`
reported ready and `applicable_stages("photonic", …)` marked
P05/P11/P12/P13/P21 ready, while the op itself honestly NOT_RUNs
(J7). Any `sys.path` shadow (stray dir, partial wheel, namespace
residue) can thus feed I27's planner a false ready.
Proposed ticket title: `SETUP-PROBE: require loader + version for python tool availability`.

### F4 — I27 has no completion-claim surface to falsify end to end

Severity: info.
`src/workflows/stages.py:146-147` + `applicable_stages` keep
missing-backend stages `required`-but-`blocked` (never dropped),
`Engine.capabilities` reports `blocked` with reason + remedy
(`src/interfaces/setup.py:447-453`), and the clean-path photonic
plan shows exactly the 6 expected blocked stages — the planning
half of I27 holds. But no IDE/MCP "design completion" or "fully
verified" endpoint exists in `src/` (only docstring mentions),
so the invariant's reporting clause is untestable rather than
proven; no vacuous claim was found either.
Proposed ticket title: `I27-COMPLETION: define or explicitly defer the completion-claim API`.

### F5 — no scenario covers the photonic circuit mistune

Severity: low.
`scenarios/sax_mzi_fail.yaml:5` runs only
`photonic_geometry_mistune` seed 0; `photonic_circuit_mistune`
(seed 0) is proven by the correctness gate (J2) and CLI recheck
(J3) but has no `scenarios.py` leg, so a scenario-only run never
exercises the coupler-detune path.
Proposed ticket title: `SCENARIO-P: add sax_mzi circuit-mistune fail scenario`.
