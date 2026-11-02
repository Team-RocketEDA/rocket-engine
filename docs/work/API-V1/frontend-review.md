# Local frontend data-contract review

Date: 2026-11-01. Scope: source and existing requirement documents only.
The product owner's [ADR-015](../../adr/015-local-desktop-results-and-roadmap.md)
was written before this review inspected UIUX implementation source. The desired
frontend contract is therefore independent of claims about existing implementation.
No application was started, no screenshots were taken, and no rendered finish,
spacing, accessibility or responsive-layout gate is claimed. UIUX files were not edited.

## Desired presentation boundary

The engine is headless and supplies typed simulation/check data. Electron/React
owns the editor shell, plotting implementation, docking, settings, chatbot and
view state. Arrays, axes, units, complex values, condition/corner metadata,
measurements, violations and provenance are engine-owned data; HTML/JS/React
components and general explanatory page copy are not engine result payloads.

Default result views are data-driven: DRC/LVS violations with cross-probing,
DC/transient traces, AC complex response/Bode views, photonic spectra or
S-parameter matrices as appropriate, and typed tables. A spatial heatmap needs
actual spatial/matrix data. Every run can have its own closeable result tab;
verbose native output remains in the output terminal. A dense engineering
workspace has meaningful labels, units, errors and controls, without decorative
operational badges, repeated explanations of controls, fake charts or large
marketing-like cards.

ECC's Frontend Design Direction supports a dense, quiet, utilitarian tool,
using existing tokens/controls, restrained motion and domain-specific hierarchy.
Its rendered evidence gate remains unperformed here; source reading cannot pass it.
The user's explicit direction supersedes generic skill suggestions to add success
copy or a next-action paragraph when ordinary EDA controls already communicate it.

## Existing frontend contract already contains useful requirements

- [frontend-requirements.md:35](../../../../PRD/tools-research/frontend-requirements.md#L35)
  calls for on-demand plots, a fresh tab per DC/AC/TRAN run and a modal DRC
  violation list. This is consistent with the user's requested result routing.
- [frontend-requirements.md:150](../../../../PRD/tools-research/frontend-requirements.md#L150)
  describes trace/corner/measurement/provenance data, but leaves the bulk series
  contract planned. Its unconditional verdict-banner wording is superseded by
  ADR-015's restrained data-first presentation.
- [frontend-requirements.md:163](../../../../PRD/tools-research/frontend-requirements.md#L163)
  assigns native logs to Output and actual findings to Problems/cross-probing.
- [frontend-tooling-spec.md:308](../../../../PRD/tools-research/frontend-tooling-spec.md#L308)
  already requires generated consumer types and drift checking rather than
  independently maintained payload fields.
- [frontend-tooling-spec.md:318](../../../../PRD/tools-research/frontend-tooling-spec.md#L318)
  gives docking/editor/terminal stack guidance and separates durable engine
  design settings from frontend-local view state.

These documents need the canonical result shapes and ADR-015 precedence, rather
than a second independent renderer payload definition.

## Observed source gaps

| Source evidence | Implication for the contract/refactor |
|---|---|
| [PlotsSurface.tsx:5](../../../../UIUX/src/components/PlotsSurface.tsx#L5) imports `spectrum` and `waveformSignals` from bundled data. [Lines 43–45](../../../../UIUX/src/components/PlotsSurface.tsx#L43) export those samples as CSV. | A successful engine run cannot yet be assumed to supply the displayed arrays; the generic renderer must consume engine dataset references and preserve source identity. Fixture charts need clear fixture provenance during development, never substitution for live result data. |
| [PlotsSurface.tsx:9](../../../../UIUX/src/components/PlotsSurface.tsx#L9) has fixed timing/spectrum/metrics tabs; [line 335](../../../../UIUX/src/components/PlotsSurface.tsx#L335) defaults one component-level tab state. | Result views need typed dataset/view descriptors plus run-owned tab identities. A new analysis must not require changing one hand-coded enum or overwriting the prior run's plot. |
| [PlotsSurface.tsx:95](../../../../UIUX/src/components/PlotsSurface.tsx#L95) assumes 32 digital samples; [line 179](../../../../UIUX/src/components/PlotsSurface.tsx#L179) fixes the optical range, and [line 183](../../../../UIUX/src/components/PlotsSurface.tsx#L183) computes a particular display transform. | Axes, sample counts, conditions and real/complex semantics must come from the dataset contract. Display transforms need explicit valid inputs, reference levels and provenance rather than fixture-specific assumptions. |
| [UIUX engine/types.ts:48](../../../../UIUX/src/engine/types.ts#L48) hand-defines scalar Measurement/Artifact/RunVerdict shapes; [line 17](../../../../UIUX/src/engine/types.ts#L17) uses opaque `arguments`, and [line 29](../../../../UIUX/src/engine/types.ts#L29) uses opaque event data. | Generated boundary types must include datasets, chunks, view descriptors, marker geometry and stage I/O, not only scalar measurement lists or generic bags. Consumers need real serialized-response validation against the same artifact. |
| [UIUX engine/client.ts:60](../../../../UIUX/src/engine/client.ts#L60) correctly labels deterministic local measurements as fixtures; [line 343](../../../../UIUX/src/engine/client.ts#L343) defaults to LocalContractEngine when no base URL is supplied. | Keep fixture/local-contract mode identifiable in provenance. An in-memory contract fixture must not become evidence that the shared Python engine executed a solver. |
| [RunConsole.tsx:70](../../../../UIUX/src/components/RunConsole.tsx#L70) derives a Problems summary by regex over failed job logs. | Problems should consume typed Finding/Violation records. The output terminal can retain full logs; downstream tasks and result widgets must not recover normal typed data by scraping log prose. |
| [App.tsx:90](../../../../UIUX/src/App.tsx#L90) maps individual tool IDs to legacy operations, including MEOW to `run_optical`. | Buttons should invoke catalog-declared task/workflow contracts and readiness, avoiding frontend-specific tool/analysis routing or accidental conflation of optical circuits with deferred field solvers. |

The current implementation has some compact engineering controls and real
interaction affordances; the data boundary is the material engine-facing gap.
This review does not require rebuilding the frontend during the engine contract task.

## Prose and spacing: source evidence has limits

JSX retains introductory text such as the verification explanation at
[VerificationSurface.tsx:62](../../../../UIUX/src/components/VerificationSurface.tsx#L62),
repeated status explanations at [line 81](../../../../UIUX/src/components/VerificationSurface.tsx#L81)
and [line 130](../../../../UIUX/src/components/VerificationSurface.tsx#L130),
and plot footnotes at [PlotsSurface.tsx:167](../../../../UIUX/src/components/PlotsSurface.tsx#L167)
and [line 284](../../../../UIUX/src/components/PlotsSurface.tsx#L284). This is
source-maintenance debt relative to the requested minimal product copy.

However, the current CSS already contains compaction/declutter overrides:
[styles.css:5610](../../../../UIUX/src/styles.css#L5610) reduces page padding,
[line 5618](../../../../UIUX/src/styles.css#L5618) hides subtitle paragraphs,
[line 5835](../../../../UIUX/src/styles.css#L5835) removes fill-surface padding/gaps,
and [line 5877](../../../../UIUX/src/styles.css#L5877) hides the entire surface
header, verification summary/footer, status-explainer and plot-stats blocks.
Several overrides are repeated at [line 5828](../../../../UIUX/src/styles.css#L5828)
and [line 5852](../../../../UIUX/src/styles.css#L5852). Therefore earlier CSS
padding values and retained JSX text cannot honestly be reported as currently
visible whitespace/prose. Cascade consolidation should accompany a later
rendered frontend review, preserving meaningful task controls and result units.

No literal `OPERATIONAL` was found in the reviewed sources. The generic active
dot has static CSS color in [styles.css:971](../../../../UIUX/src/styles.css#L971);
this review does not claim a blinking operational badge was observed. Actual
run progress feedback is distinct from ornamental status decoration.

## Handoff and required evidence

The engine data-contract ticket should produce one canonical ResultBundle/data
registry and Pydantic/TypeScript boundaries, adapter normalization fixtures and
stable stage I/O references. The frontend consumer ticket should prove:

1. A DC sweep, complex AC sweep, transient trace, digital waveform, optical
   spectrum/matrix and DRC violation set render from engine-owned data without
   analysis-specific hardcoded arrays or prose parsing.
2. Empty violations render no fake marker or explanatory dashboard; partial,
   missing, stale and failed data remain explicit without a success facade.
3. Each run retains a closeable result identity and provenance; new runs do not
   overwrite earlier plot tabs or reset their view state unnecessarily.
4. Verbose stdout/stderr goes to Output; typed findings go to Problems and
   violation dialogs with cross-probe identities/coordinates.
5. Chunked arrays preserve ordering/shape/units and retain full downloadable
   source data; display decimation is labeled and cannot alter trusted values.
6. A rendered review at agreed desktop viewports tests actual density, control
   reachability, focus, large datasets, partial data and errors. Only then can
   the visual contract's finish gate pass.

## Suggested code-organization rules for the engine

Use feature packages with domain/use-case/port/adapter boundaries and explicit
composition wiring. Names use one word per segment; nest the
responsibility rather than create ever-longer module names. Keep reusable pure
primitives in small `src/common/paths.py`, `units.py`, `hashes.py`-style modules
only when shared semantics justify them. `common` imports no feature/adapters;
feature-specific helpers stay beside their feature. Avoid a dumping-ground
`utils.py`, hidden service locators and adapters calling each other. Split
before 3,000 lines, ordinarily much earlier, and document modules, classes and
public functions in Google style. Root updates AGENTS.md and refactor tickets;
this source review changes no runtime module structure.
