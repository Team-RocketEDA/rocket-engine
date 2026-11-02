# librelane — output dissection

Root-authored (post-synthesis addendum, 2026-11-02): LibreLane is the
physical-design frontend; OpenROAD is its internal engine (see
`docs/tool-frontends-review.md`). Same 5-section shape as the
dissector reports.

## Evidence

- Clone SHA: `64ef80802d3d189b476636d2a6b17888c03304ee`
- Clone date: `2026-10-26`
- Pin: `LIBRELANE_PIN="3.0.17"`, `LIBRELANE_COMMIT="64ef8080…"`
  (`scripts/provision_toolchain.sh:59-60`) — clone HEAD **equals** the
  pin. All file:line below verified at this SHA.
- Upstream: https://github.com/librelane/librelane,
  https://librelane.readthedocs.io/

## 1. Result channels

| # | Channel | Producing call | Filename pattern |
|---|---|---|---|
| R1 | Run-dir tree | `Flow.start(tag=…)` (`flows/flow.py:589`) | `<design_dir>/runs/<tag>/`; default tag `RUN_%Y-%m-%d_%H-%M-%S` (`flow.py:569-571`); step dirs `NN-StepName/` (ordinal parse `flow.py:599-615`); `tmp/` toolbox (`flow.py:645`) |
| R2 | Per-step JSON | every step finish (`steps/step.py:852-854,1143,1192`) | `<step_dir>/{config.json,state_in.json,state_out.json}` + `runtime.txt` (elapsed, `step.py:1195-1197`) |
| R3 | Metrics JSON+CSV | `State.save_snapshot(path)` (`state/state.py:193-227`); signoff `metrics.csv` (`flows/flow.py:898`) | `<snapshot>/{metrics.json,metrics.csv}`; CSV header `Metric,Value` (`state.py:224-227`) |
| R4 | Metrics-repo naming | `librelane.common.metrics` CLI (`common/metrics/__main__.py:136`) | `{pdk}-{scl}-{design}.metrics.json` |
| R5 | Views (design artifacts) | steps return `ViewsUpdate` (`step.py:1203`) | paths inside state JSON (see §2); files are ODB/GDS/SPEF/DEF/LEF/netlists |
| R6 | Tool-native files | colocated by each tool in its step dir | OpenROAD/Yosys/KLayout logs + reports + `.odb`/`.gds` (what `digital_flow` scans today) |
| R7 | Python API returns | `Flow.start()` → `(success, states)`; `Step.run()` → `(ViewsUpdate, MetricsUpdate)` (`step.py:244-245,1203`) | in-process (`MetricsUpdate = Dict[str, Any]`) |
| R8 | Tool-stdout metrics | `DefaultOutputProcessor` (`step.py:131-193`) | parsed inside LibreLane into `generated_metrics` dict — never our problem |

## 2. Format grammars

- **state_out.json**: `State.dumps()` (`step.py:1192-1193`). `State`
  is `GenericImmutableDict[str, StateElement]` (`state.py:45`) with a
  `metrics` dict attached (`to_raw_dict(metrics=True)`,
  `state.py:139-143`). `StateElement = Union[Path, List[Path],
  Dict[str, Union[Path, List[Path]]], None]` (`state.py:42`) —
  views are **paths**, metrics are scalars. Keyed by `DesignFormat`
  (`state.py:118-127`). Resume loads the latest `state_out.json` by
  mtime (`flow.py:629-637`).
- **metrics.json**: `self.metrics.dumps()` (`state.py:225-227`) —
  flat `{name: value}` JSON. **Key names are dynamic per step**
  (whatever each step's processor emits); the audit's "metrics.json
  keys unconfirmed" gap stands — confirm with a fixture run, do not
  hardcode a key list.
- **metrics.csv**: header row `Metric,Value`, one row per metric
  (`state.py:224-227`). Parse positionally; values are metric-typed
  scalars.
- **config.json / state_in.json**: step input echo (`step.py:852-854,
  1143`) — provenance, same JSON shapes as state.
- **runtime.txt**: `format_elapsed_time(end-start)` human elapsed
  (`step.py:1195-1197`) — informational only.
- **Step contract**: `Step` ABC (`step.py:344`) with `id`/`inputs`/
  `outputs` class vars (`step.py:385-415`); `run()` returns
  `(ViewsUpdate, MetricsUpdate)` where `ViewsUpdate =
  Dict[DesignFormat, StateElement]` (`step.py:244`).

## 3. Python bindings

NATIVE — it IS Python (`import librelane`, `py.typed`,
`Step`/`Flow`/`State` classes). Audit row stands, with the standing
caveat: the pip route is flow-infra-only, bring-own-tools. No
bindings work needed — the adapter reads run dirs + optionally
imports `State` for `State.loads()` parsing.

## 4. STDIO-ONLY RESIDUE

Near zero for our purposes. Tool stdout is consumed *by LibreLane
itself* (`DefaultOutputProcessor` → metrics dict); flow logs go to
console. Everything an adapter needs is in R1–R5 files. The only
genuine residue is tool-native free text inside step logs (R6),
which `digital_flow` already scans with bounded tails.

## 5. Adapter recommendation

1. **Structured files (primary)**: parse the latest `state_out.json`
   per step dir (`State.loads` semantics: views paths + metrics
   dict) + `metrics.csv` for the flat scalar table. Never scrape
   step logs for numbers that exist in state.
2. **Upgrade path for `digital_flow`**: replace/augment step-dir
   text scanning with `state_out.json` metrics + view-path
   existence checks (`.gds` non-empty stays the D24 gate).
3. **Do not** hardcode metrics.json key lists — assert presence of
   the keys each fixture run produces, and fail loud on missing
   keys (key drift = upstream step change).

Verified at: clone 64ef8080 (2026-10-26) == provision pin 3.0.17.
