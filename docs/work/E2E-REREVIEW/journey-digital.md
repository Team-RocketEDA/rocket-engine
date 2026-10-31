# E2E journey: digital (SERV + picorv32) — review lane report

Ticket: `docs/tickets/E2E-REREVIEW.md` · Branch: GREEN-the-tests @ `a8aaa09`
Env: `UV_CACHE_DIR=/tmp/uv-cache UV_LINK_MODE=copy`,
`PATH=$HOME/tools/oss-cad-suite/bin:$HOME/tools/bin:$PATH`,
`ROCKETEDA_HOME=/tmp/rocketeda-live`. Toolchain observed: iverilog/vvp,
yosys 0.70+219, sby v0.70-9-g79fc9ed (+boolector), klayout, magic, netgen;
**librelane/openroad absent**. Review-only: no src/tests/scripts/track
ed-file edits; this file is the lane's only artifact.

## Verdict table

| # | Leg | Command / probe | Result |
|---|---|---|---|
| J1 | Scenario gate, full | `.venv/bin/python scripts/scenarios.py scenarios/` | **PASS 26/26, exit 0** — incl. `serv live pass/fail`, `picorv32 live pass/fail`, `hdl live pass/fail`, `sdm_rx live pass/fail` |
| J2 | Correctness, digital flow | `.venv/bin/python scripts/correctness.py --flow digital` | **GATE PASS 16/16** (serv-good, picorv32-good + 14 mutants), exit 0; report `tmp/correctness/report.json` |
| J3 | Mutants, digital (9) | `scripts/mutate.py recheck` × {serv,picorv32,digital}_{reset_break,truncation,unconnected_port} seed 0 | **9/9 proven, exit 0** each (good PASS + mutated FAIL) |
| J4 | `run_synth` SERV | engine `run_synth`, 18 `fixtures/upstream/serv/rtl/*.v`, top `serv_top` | **PASS** — 1196 cells / 1508 wires, 2 `synth_warning` (serv_rf_ram.v:41); netlist `synth_netlist.v` + `synth_stat.txt` in workdir |
| J5 | `run_synth` picorv32 | engine `run_synth`, `fixtures/upstream/picorv32/picorv32.v`, top `picorv32` | **PASS** — 9442 cells / 7135 wires, zero findings |
| J6 | `run_formal` SERV ALU prop | engine `run_formal`, serv_alu.v + tests/adapters/fixtures/formal/serv_alu_prop.v, bmc d5 | **PASS, scope=bounded**, 1 assert site (serv_alu_prop.v:37), sby rc 0 |
| J7 | `run_formal` picorv32 raw | engine `run_formal`, picorv32.v, bmc d5 | **PASS, scope=bounded** — legitimate: yosys elaborates 11 real `$assert` cells; see F2 for measurement noise |
| J8 | `run_digital_flow` SERV | engine `run_digital_flow`, SERV RTL, pdk sky130A | **NOT_RUN `missing_dependency`** naming librelane + pinned-3.0.17 remedy — Blocked-live claim in `docs/work/DIGITAL-FLOW/report.md` **verified honest**; adapter suite 52 passed + 3 loud skips (PDK-root reason) |
| J9 | DRC leg | gate `drc sky130 pass/fail` + `mutate.py recheck layout_drc_violation` s0 | **PASS** — gate green; recheck proven (mutated FAIL `spacing`), exit 0 |
| J10 | LVS leg | gate `lvs sky130 pass/fail` + `mutate.py recheck netlist_lvs_mismatch` s0–s2 | **PARTIAL** — gate green, but mutant **escapes**: mutated PASS on seeds 0,1,2, harness honestly exits 1 `proven:false` → F3 (cross-lane: layout) |
| J11 | I27 falsification | flow-notool, synth bad-top, code read | **HOLDS** — missing tool → NOT_RUN (never PASS); missing top → FAIL via `hierarchy -check`; `digital_flow` clean-exit-with-missing-gate → failure (`src/adapters/digital_flow/__init__.py:342-343`); no vacuous completion claim found |
| J12 | I09 falsification | synth-broken, formal-vacuous, CLI exits | **HOLDS except F1** — broken RTL → `e.run` returns (no raise) with verdict FAIL in payload; fail-scenarios + FAIL verdicts coexist with gate exit 0 (exit = expectation-match, verdict = payload); **but** zero-property `run_formal` returns engine PASS (sby rc 0 → PASS with `properties: []`) → F1 |

No flaky runs observed; nothing quarantined this lane. All FAIL/NOT_RUN
cases above are deterministic (LVS escape reproduced 3/3 seeds).

## Failure artifacts captured

- `FLOW-NOTOOL` verdict: `{"status": "NOT_RUN", "reason":
  "missing_dependency: librelane not on PATH — install the pinned
  LibreLane 3.0.17 … (see src/interfaces/setup_catalogue.yaml id
  librelane)."}` (`/tmp/dig_probe5.py` run).
- `SYNTH-BADTOP` (top `no_such_top`): verdict FAIL, 2 error + 2
  warning; native `synth.log` carries yosys `ERROR:` hierarchy lines.
- `SYNTH-BROKEN` (`q <= ;`): verdict FAIL, 2 errors, `e.run` raised
  nothing — I09-holds evidence at API level.
- `FORMAL-VACUOUS` (property-free `plain.v`, bmc d5): verdict
  `{"status": "PASS", … "properties": [], "sby_status": "PASS",
  "sby_rc": 0, "scope": "bounded"}` — F1 evidence (native
  `/tmp/dig-formal-vac/plain.v` + `formal/` sby tree retained in /tmp).
- `FORMAL-PICO` measurements list 26 assert sites incl.
  `picorv32.v:40` (×2) and `:47` — the `` `define assert(…) `` macro
  *definition* lines — F2 evidence.
- LVS escape: `/tmp/mut-lvs.log`, `/tmp/mut-lvs-1.log`,
  `/tmp/mut-lvs-2.log` — `{"good": "PASS", "mutated": "PASS",
  "proven": false}`, exit 1 (harness honest).
- Synth natives: `/tmp/dig-synth-serv/{synth.log,synth.ys,
  synth_stat.txt,synth_netlist.v}`, same under `/tmp/dig-synth-pico/`.
- Formal natives: `/tmp/dig-formal-ok/`, `/tmp/dig-formal-pico/
  formal/{logfile.txt,status,engine_0/}`, `/tmp/dig-formal-vac/`.
- Gate outputs: J1 stdout (26 passed), J2 `tmp/correctness/report.json`
  (`failed_cases: []`), `/tmp/mut-<op>.log` ×9 digital rechecks.

## Findings

### F1 — run_formal PASS on a property-free design (vacuous proof)
- **Severity:** Medium.
- **Evidence:** `src/adapters/formal_sby/__init__.py:540-543` (`if
  status == "PASS"` returns `total: 0` with no checked-property
  requirement) → `src/execution/service.py:221` (zero errors → engine
  PASS). Probe: `run_formal` on assert-free `plain.v` returns PASS,
  `scope: bounded`, `properties: []`, `sby_rc: 0`. No test covers
  vacuity (no `vacuous|zero propert|no propert` in
  `tests/adapters/test_formal_sby.py`). Contradicts the parse
  docstring's "PASS always means some scope was earned"
  (`src/adapters/formal_sby/__init__.py:460`). I09-adjacent: sby's
  exit-0 vacuous PASS propagates as engine PASS; I27-adjacent: a
  missing proof obligation does not block the PASS claim.
- **Proposed ticket title:** `FORMAL-VACUITY: refuse or UNKNOWN
  run_formal with zero checked properties`.

### F2 — property-site scan counts macro definitions, is ifdef-blind
- **Severity:** Low (annotation noise; verdict scope unaffected —
  picorv32 PASS is backed by 11 real `$assert` cells verified via
  yosys `prep -top` with and without `-DFORMAL`).
- **Evidence:** `src/adapters/formal_sby/__init__.py:68` (`_PROP_RE`)
  + `:71-74` (`_property_sites`, comment-blind only): picorv32
  measurements claim 26 assert sites including the `` `define
  assert(assert_expr)… `` definition lines
  `fixtures/upstream/picorv32/picorv32.v:40` (matched twice) and `:47`,
  which are never proof obligations. Consumers must not treat
  `properties[]` as the proven set.
- **Proposed ticket title:** `FORMAL-SITES: make _property_sites
  define/ifdef-aware so measurements match checked assertions`.

### F3 — netlist_lvs_mismatch mutant escapes (mutated PASS, 3/3 seeds)
- **Severity:** Medium. **Cross-lane:** layout owns the fix; recorded
  here because this journey's DRC/LVS leg depends on it.
- **Evidence:** `src/mutate/operators.py:437-461` (schematic-only bulk
  rename `VPB/VNB → *_BAD`) vs `src/mutate/__init__.py:300-310`
  (`expected_verdict: FAIL`, `expected_rules: [lvs_net_mismatch]`):
  `scripts/mutate.py recheck --operator netlist_lvs_mismatch --seed
  {0,1,2}` all yield mutated PASS, `proven: false`, exit 1
  (`/tmp/mut-lvs*.log`). The harness is honest (exit 1, not
  fake-green); the escape is in the mutant/check pair — likely netgen
  sky130 setup swallowing bulk-net differences. Gate `lvs sky130
  pass/fail` scenarios still green (different fixture,
  `sky130_fd_sc_hd__inv_2`).
- **Proposed ticket title:** `LVS-MUTANT-ESCAPE: bulk-rename mutant
  does not flip run_lvs (netgen setup or operator fix)`.

## Notes for the invariant lane

- Generalization law (digital adapters): `run_synth`, `run_formal`,
  `run_hdl_test` all consumed external project inputs here (SERV
  18-file RTL, picorv32 vendor RTL, staged property files) — no
  smoke-only adapter found on the digital path. `run_digital_flow`
  stages project RTL by code read but is live-unproven (blocked on
  the pinned LibreLane distribution, loudly).
- `state: completed` on NOT_RUN/FAIL runs means "the run finished",
  never "the work passed" — the verdict object is the only claim
  carrier; no code path was found treating state or exit code as PASS.
