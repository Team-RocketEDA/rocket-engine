# PHOTONIC-WIRE lane report — photonic solvers wired to engine ops

Ticket: `docs/tickets/PHOTONIC-WIRE.md`. Branch `GREEN-the-tests`.
Nothing committed, nothing pushed (integrator commits). No tracked
file edited — all wiring into existing files is delivered below as
an exact unified-diff patch (verified with `git apply --check` and
behaviorally for regen on a `/tmp` stage copy).

## Outcome

`wire_photonics(engine)` in the new module
`src/workflows/photonic_wire.py` registers the proven photonic
solvers on any Engine: circulax as the second run_optical
deck.tool (sax stays first, so the default never moves) and meow
behind run_em (the only tool, opening P06). Both lanes dispatch
as engine ops with run_ids, ledger `run_completed` events,
findings, and structured verdicts; FDTD/FEM stay out (unknown
deck tools raise `unsupported_operation`). The wiring patch bakes
the same registrations into `Engine.__init__` plus the
`SOLVER_DEPS` detection rows, provision-catalogue entries, and
the one-line-class api_spec extension the regen needs.

## Files added (new files only — no existing file edited)

- `src/workflows/photonic_wire.py` — the wiring seam
  (`PHOTONIC_TOOLS`, `PHOTONIC_DEPS`, `wire_photonics`).
- `tests/workflows/test_photonic_wire.py` — RED-first lane tests
  (seam registration, sax-default preservation, canned PASS/FAIL
  dispatch with run_ids + ledger + findings on both lanes,
  unknown-tool refusal, post-patch probe tests, live solver
  runs).
- `docs/work/PHOTONIC-WIRE/report.md` — this file.

## Same-ticket inputs assumed present (not mine, not edited)

The lane builds on the adapter modules already in the working
tree (same ticket, landed untracked alongside this lane):

- `src/adapters/circulax/adapter.py` (`CirculaxAdapter`,
  `OPERATION == "run_optical"`) + `src/adapters/circulax/_driver.py`
- `src/adapters/meow/adapter.py` (`MeowAdapter`,
  `OPERATION == "run_em"`) + `src/adapters/meow/_driver.py`

The seam imports these canonically
(`rocket_engine.adapters.circulax.adapter`, ...); a missing lane
module raises `ModuleNotFoundError` loudly, never a faked
verdict. The integrator lands them with `git add` (new files, no
patch needed) and reconciles if their owners moved them.

## Seam design

`wire_photonics(engine, *, runner=None)` performs exactly the
two `register_solver` calls the patch bakes into
`Engine.__init__`, and returns
`{"run_optical": "circulax", "run_em": "meow"}`. It also adds the
two `PHOTONIC_DEPS` detection rows to `SOLVER_DEPS` via
`setdefault` — additive only, never overwriting the
integrator-patched static rows. That runtime row is required,
not cosmetic: without it any wired engine breaks
`get_capabilities` with `unknown_solver`, since
`report_capabilities` fails loudly on a registered
(operation, tool) it cannot probe. Detection mirrors the sax row
(top-level solver import only: `circulax`, `meow`); deeper
pip-transitive deps fail loud at run time, never as a
misreported capability. Post-patch the helper is an idempotent
re-registration of identical keys (proven by test).

Generalization law: the adapters consume project specs —
circuit YAML in, transient out; device YAML in, S-params plus
two-resolution convergence out. The lane tests pin this with
non-proof inputs: a 2k/1nF project RC checked against the
analytic 1-e^-t/tau oracle, and a 600nm project strip width
carrying convergence evidence. Proof replays (good/slow RC,
matched/step strip) travel as op runs with run_ids.

## Why the patch imports adapter modules (not packages)

`scripts/api_spec.py:solver_map` resolves adapter docstrings
through composition's from-imports, and `_handler_ref` already
anticipates non-package modules
(`rocket_engine.adapters.<name>.<mod>.<Class>`). A package-level
re-export (`from .adapter import CirculaxAdapter` in
`circulax/__init__.py`) would leave no `ClassDef` for the AST
lookup (`doc_of` → `None` → empty summary/job_keys in the
regenerated contract — verified by reading `parse_docstring`).
So the patch imports the adapter modules directly
(`from .adapters.circulax.adapter import ...`) and extends
`solver_map` to 3-part adapter paths (2-part behavior
unchanged). Regen proof on the patched stage copy below shows
both lanes fully contracted.

## RED → GREEN evidence

RED (tests written first, seam module absent; sealed env):

    $ .venv/bin/python -m pytest tests/workflows/test_photonic_wire.py -q
    11 failed, 7 skipped in 0.15s

Every failure is `ModuleNotFoundError: No module named
'rocket_engine.workflows.photonic_wire'`; the 7 skips are the
4 live solver tests (photonic group not yet installed) plus the
3 post-patch probe tests (unwired tree).

GREEN (seam module added + sealed env + photonic group):

    $ .venv/bin/python -m pytest tests/workflows/test_photonic_wire.py -q
    15 passed, 3 skipped in 22.35s

The 3 skips are the post-patch probe tests (they run once the
integrator applies the patch). Live solver evidence: the 2k/1nF
project RC hits the analytic 1-e^-2.5 = 0.9179 (PASS), the 47k
project RC fails honestly, the matched 500nm strip replays
T=1.0/neff 2.3108 with convergence_dT = 0.0 (PASS), and the
600nm project width ships passing convergence evidence — every
run under its own run_id with ledger events.

## Test commands + results

Env for runs below: `PATH` with the live-tools bins,
`MPLCONFIGDIR=/tmp/mpl`, `XDG_CONFIG_HOME=/tmp/xdg` (the XDG
var is required in this sandbox — see the tidy3d note).

| Command (from `rocket-engine/`, `.venv/bin/python`) | Result |
|---|---|
| `python -m pytest tests/workflows/test_photonic_wire.py -q` | 15 passed, 3 skipped (skips = post-patch probes) |
| Neighbors: `test_sax.py test_circulax.py test_meow.py` | 41 passed (sax path untouched and green) |
| Neighbors: `test_circulax_optical.py test_meow_em.py` | 41 passed (same-ticket op lanes) |
| Gate tests: `test_api_spec.py test_contract.py test_docstrings.py test_no_cloud.py test_packaging.py` | 22 passed |
| `python scripts/check_docstrings.py` (full tree) | clean |
| `python scripts/api_spec.py --check` / `contract.py --check` | exit 0 / exit 0 (pre-patch tree consistent) |
| added-line 100-col audit (`awk`, new files + patch) | clean |
| `git apply --check` on the embedded patch | clean |
| api_spec regen on patched `/tmp` stage copy | 42 op schemas build; run_em tools [meow] required [sources]; run_optical tools [circulax, sax]; run_em summary resolves the MeowAdapter docstring; reference + help mention both adapters |

Full suite never run (lane rule). No `tests/pdk_*/` or
`docs/pdk/*/` touched. Provision: `scripts/install.sh --install`
(the only env path) plus `uv sync --group photonic` for the
repo-declared solver group (sax 0.18.2, circulax 0.2.5, meow
0.15.0 — the proven pins), then the install.sh seal command
(`uv pip install --python .venv/bin/python --no-deps .`) once
more, because any `uv sync --no-install-project` prunes the
sealed `rocket_engine` as extraneous — the integrator must seal
AFTER the last group sync. The install.sh PDK-register tail
fails in this sandbox (read-only `ROCKETEDA_HOME`) after the
venv + seal succeed; the lane needs no PDK.

Sandbox notes (findings, not lane defects). (1) With a
read-only `$HOME/.config`, tidy3d prints its fallback warning
to the driver's stdout, breaking the one-JSON-document
envelope: live meow runs go NOT_RUN (`runner_unavailable`).
`XDG_CONFIG_HOME` to a writable dir restores PASS; the meow
adapter lane may additionally want last-`{`-anchored envelope
parsing. (2) Concurrent lanes rebuild `.venv` during the
session; all results above were taken in sealed windows and
re-verified after the final seal.

## Integrator instructions

1. Land the new files: `git add src/workflows/photonic_wire.py
   tests/workflows/test_photonic_wire.py docs/work/PHOTONIC-WIRE/report.md`
   plus the same-ticket adapter inputs listed above (with their
   tests/fixtures from their owning lane reports).
2. Apply the patch: save the fenced block below to a file, then
   `git apply --check` and `git apply` it.
3. Regen the contract artifacts (freshness-pinned):
   `python scripts/api_spec.py --write` then
   `python scripts/contract.py --write`.
4. Reinstall the sealed env: `scripts/install.sh --install`
   (then the photonic group for live runs).
5. Run: `python -m pytest tests/workflows/test_photonic_wire.py -q`
   — expect the 3 post-patch probe tests to flip from skip to
   pass — plus the neighbor files and the gate suite.

## Wiring patch (exact — `git apply` this block)

Covers `src/composition.py` (imports, tool-list docstring, the
two `_solvers` registrations), `src/interfaces/setup.py`
(`SOLVER_DEPS` rows), `src/interfaces/setup_catalogue.yaml`
(provision entries mirroring sax), `src/adapters/sax/__init__.py`
(`(the only tool)` → `(the default tool)`), and
`scripts/api_spec.py` (3-part adapter module resolution).
Generated docs (`engine-api.md`, `api-schema.json`,
`api-help.json`, `contract.json`) are NOT in the patch — the
integrator regenerates them per step 3.

```diff
--- a/src/composition.py
+++ b/src/composition.py
@@ -25,10 +25,10 @@
 one — is refused.
 `run()` executes registered solvers synchronously. Each operation
 maps to named solvers; `deck.tool` selects one, defaulting to the
-first registered (run_drc: magic, then klayout; run_optical: sax;
-run_extraction: magic; run_lvs: netgen; run_spice: ngspice;
-run_syntax: slang; run_hdl_test: icarus; run_connectivity:
-connectgraph; run_erc: connectgraph).
+first registered (run_drc: magic, then klayout; run_optical: sax,
+then circulax; run_em: meow; run_extraction: magic; run_lvs:
+netgen; run_spice: ngspice; run_syntax: slang; run_hdl_test:
+icarus; run_connectivity: connectgraph; run_erc: connectgraph).
 Unregistered operations and unknown deck tools raise instead of
 faking a verdict.
 """
@@ -38,6 +38,7 @@
 
 from ruamel.yaml import YAML
 
+from .adapters.circulax.adapter import CirculaxAdapter
 from .adapters.connectivity import ConnectivityAdapter
 from .adapters.drc import MagicDrcAdapter
 from .adapters.drc_kl import KlayoutDrcAdapter
@@ -45,6 +46,7 @@
 from .adapters.extract_magic import MagicExtractAdapter
 from .adapters.hdl_sim import HdlSimAdapter
 from .adapters.lvs_netgen import NetgenLvsAdapter
+from .adapters.meow.adapter import MeowAdapter
 from .adapters.ngspice import NgspiceAdapter
 from .adapters.sax import SaxAdapter
 from .adapters.syntax import SyntaxAdapter
@@ -263,7 +265,8 @@
         self._solvers = {
             "run_drc": {"magic": MagicDrcAdapter(), "klayout": KlayoutDrcAdapter()},
             "run_hdl_test": {"icarus": HdlSimAdapter()},
-            "run_optical": {"sax": SaxAdapter()},
+            "run_optical": {"sax": SaxAdapter(), "circulax": CirculaxAdapter()},
+            "run_em": {"meow": MeowAdapter()},
             "run_extraction": {"magic": MagicExtractAdapter()},
             "run_lvs": {"netgen": NetgenLvsAdapter()},
             "run_spice": {"ngspice": NgspiceAdapter()},
--- a/src/interfaces/setup.py
+++ b/src/interfaces/setup.py
@@ -55,6 +55,8 @@
     ("run_drc", "klayout"): {"binaries": ["klayout"]},
     ("run_hdl_test", "icarus"): {"binaries": ["iverilog", "vvp"]},
     ("run_optical", "sax"): {"python": ["sax"]},
+    ("run_optical", "circulax"): {"python": ["circulax"]},
+    ("run_em", "meow"): {"python": ["meow"]},
     ("run_extraction", "magic"): {"binaries": ["magic"]},
     ("run_lvs", "netgen"): {"binaries": ["netgen"], "banner": "lvs"},
     ("run_spice", "ngspice"): {"binaries": ["ngspice"]},
--- a/src/interfaces/setup_catalogue.yaml
+++ b/src/interfaces/setup_catalogue.yaml
@@ -65,6 +65,18 @@
     python: [sax]
     remedy: "sax not installed, uv sync --group photonic (B10-owned tooling)"
     recipe: "pyproject.toml [dependency-groups] photonic: uv sync --group photonic (B10)."
+  - id: circulax
+    kind: python
+    label: Circulax (time-domain circuit sim)
+    python: [circulax]
+    remedy: "circulax not installed, uv sync --group photonic (B10-owned tooling)"
+    recipe: "pyproject.toml [dependency-groups] photonic: uv sync --group photonic (B10)."
+  - id: meow
+    kind: python
+    label: Meow (EME mode/field solver)
+    python: [meow]
+    remedy: "meow not installed, uv sync --group photonic (B10-owned tooling)"
+    recipe: "pyproject.toml [dependency-groups] photonic: uv sync --group photonic (B10)."
   - id: cvc
     kind: tool
     label: cvc
--- a/src/adapters/sax/__init__.py
+++ b/src/adapters/sax/__init__.py
@@ -194,9 +194,9 @@
 class SaxAdapter(ToolAdapter):
     """run_optical via SAX: frequency-domain photonic circuit sim.
 
-    Serves the run_optical operation with deck.tool `sax` (the only
-    tool). Stages the sim driver plus a job JSON, runs it under a
-    timeout, and parses the JSON envelope: spectra plus per-target
+    Serves the run_optical operation with deck.tool `sax` (the
+    default tool). Stages the sim driver plus a job JSON, runs it
+    under a timeout, and parses the JSON envelope: spectra plus per-target
     transmission measurements against min_db/max_db bounds.
 
     Job keys:
--- a/scripts/api_spec.py
+++ b/scripts/api_spec.py
@@ -134,7 +134,8 @@
     """{op: [(tool, adapter_class, module_rel)]} from Engine._solvers.
 
     Tool order is registration order (first = deck.tool default);
-    adapter modules resolve through composition's from-imports.
+    adapter modules resolve through composition's from-imports,
+    package (adapters/<name>) or module (adapters/<name>/<mod>).
     """
     root = Path(root) if root is not None else SRC
     tree = ast.parse((root / "composition.py").read_text())
@@ -143,8 +144,11 @@
         if not isinstance(node, ast.ImportFrom) or node.level != 1:
             continue
         parts = (node.module or "").split(".")
-        if len(parts) == 2 and parts[0] == "adapters":
-            rel = f"adapters/{parts[1]}/__init__.py"
+        if parts[0] == "adapters" and len(parts) in (2, 3):
+            if len(parts) == 2:
+                rel = f"adapters/{parts[1]}/__init__.py"
+            else:
+                rel = f"adapters/{parts[1]}/{parts[2]}.py"
             for alias in node.names:
                 locations[alias.asname or alias.name] = rel
     solvers = {}
```

## Refused / deliberately not changed (with reasons)

- `src/interfaces/vocabulary.py`: no change needed. `run_em`
  is already cataloged (P06/P16/P19 entrypoint); only the
  solver registration was missing.
- `src/workflows/stages.py`: no change needed. P06/P09 name
  operations (`run_em`/`run_optical`), never deck tools — the
  new tools serve the existing stage buttons.
- `src/adapters/circulax/__init__.py` /
  `src/adapters/meow/__init__.py`: no change in this patch.
  Their stale "follow-up, out of scope" prose is owned by the
  adapter lanes that landed `adapter.py`; the integrator
  reconciles. No re-export is added (the AST regen cannot
  follow re-exports — see above).
- `src/adapters/sax/_driver.py`, solver drivers: untouched —
  the sax path is byte-identical; only its class docstring's
  "(the only tool)" claim is refreshed.
- `scripts/contract.py`: no code change needed. It probes live
  ack/completion envelope shapes plus the api-spec schemas;
  regen re-pins the hash.
- Meow detection stays `{"python": ["meow"]}` (no tidy3d/sax
  row): mirrors the sax row's top-level-import oracle, and
  both are pip-transitive under `meow-sim`. A present-but-broken
  backend fails loud at run time.
- Fixture files: the lane tests inline their specs in
  `tmp_path` instead of adding fixture YAML — the proof
  fixtures already exist under
  `tests/adapters/fixtures/{circulax,meow}/`, and inline specs
  keep this lane's generalization cases (non-proof R/C/widths)
  next to their oracles.
