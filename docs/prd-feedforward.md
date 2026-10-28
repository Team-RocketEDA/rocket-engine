# PRD feedforward (draft from rocket-engine)

Proposals for the PRD maintainers. Each item maps to the PRD section it
amends. Nothing here edits the PRD; carry these as a review batch.

## F1 — Preferred operating system: Ubuntu 24.04 LTS (x86-64)

Amends: `tech-stack.md` ("Initial full-toolchain release target is
Linux x86-64") and B10/runner isolation qualification.

Proposed text: the initial qualification target is Ubuntu 24.04 LTS on
x86-64. It fixes the glibc and kernel baseline for Bubblewrap
user-namespaces, seccomp profiles, wheel tags, and native-pack builds.
Other distributions are best-effort until separately qualified;
macOS/Windows keep their existing "separately qualified" status. B10
installed tests and the python-console isolation tests run on 24.04.

## F2 — Hexagonal ports vs duplex edges (architecture clarification)

Amends: `frontend-tooling-spec.md` §6 boundaries, blueprint B1/B5/B9
owned paths.

Proposed rule: `interfaces/` holds ports — wire schemas, typed
commands, events, outbound port definitions. Zero I/O. `adapters/`
holds one duplex adapter per channel: each owns its full round trip
(transport adapters do bytes ↔ ports; solver adapters do jobs ↔ tool).
No inbound/outbound grouping; no adapter imports another adapter.
Dependency arrows: `adapters/* → interfaces/ + project/ + execution/`;
`execution/ → interfaces/` ports only.

Consequence: B1's owned path `contracts/` merges into `interfaces/`
(single source of truth; schemas authoritative, port types generated).
Record as a contract amendment per the blueprint's own amendment rule.

## F3 — Modular monolith, defined

Amends: blueprint §Review/plan-changes (new term) or PRD glossary.

Proposed definition: one deployable artifact; hard module boundaries
enforced as import boundaries in review; one bounded context per
top-level module; a single explicit composition root wiring adapters
to ports to use cases (proposed location: `src/composition.py`,
to be created with slice 1). No shared mutable state across modules;
cross-module facts travel as events or evidence records.

## F4 — Project shell and portable rebuilds

Amends: `tech-stack.md` packaging/UV sections; B10.

Observed working template (rocket-engine, verified): `pyproject.toml`
(requires-python `==3.12.*`, Hatch `force-include {"src" =
"rocket_engine"}`), `.python-version`, `uv.lock`, pure-Python wheel
(`py3-none-any`, portable across platforms), per-profile locks for
native/solver profiles. Rule: the wheel carries no solvers; native
packs (LibreLane closure, OSS-CAD-Suite, ngspice, PDK wrappers) ship
per-platform beside it, pinned by digest. "Rebuild on any platform"
means the pure wheel rebuilds anywhere; native packs qualify per
platform, 24.04 first.

## F5 — Vocabulary (adopt engine-wide)

| Term | Rule |
|---|---|
| Engine ports | `interfaces/` types. Never "interface" alone near UI text. |
| Transport adapter | A duplex adapter speaking a protocol (`http`, `stdio`, `mcp`, `cli`). |
| Solver adapter | A duplex adapter speaking a tool (`ngspice`, `magic`, `sax`). |
| `adapters/http` | Renamed from `adapters/api`: `api_*` is taken by API-discovery ops (`api_search/info/help`). |
| Runtime profile | Prepared locked env (`engine`, `design`, …). Never bare "profile". |
| Agent mode | Harness Auto/Approval behavior. Never "profile". |
| Console worker / job worker | Always qualify which worker. |
| Operation target | Pinned component reference. Platform builds are "platform targets". |
| Design project | The user's chip. The engine side is the "project service". |
| Check / run / evidence / finding | PRD meanings verbatim; exit zero is not PASS. |
| CLI-first | Transport implementation order: CLI, stdio, HTTP, MCP. |

## F6 — Process confirmations (no change, please confirm)

- Exit-zero-is-not-PASS, readiness states, and evidence ownership: adopted as written.
- CSPDK (9.51.x) vs SKY130-wrapper (9.48.x) env split: our template keeps GDSFactory out of the engine profile until per-profile locks exist. Confirm separate-env rule stands for B10.
- PDK installation/discovery stays explicit; no redistribution without rights.

## F7 — Agent analytical access + analog s-domain loop (new appendix)

Proposed new PRD appendix (harness + engine contract impact):

1. Dual representation rule. Every engine output a human would read
   as a graph MUST ship as (a) a full-fidelity dataset artifact the
   agent can analyze with scripts (no silent downsampling), plus
   (b) an optionally generated image for visual intuition on
   multimodal models. Inline previews MUST declare n_total vs
   n_shown and the downsampling method.
2. Analysis-ready datasets. Sequential data uses columnar artifacts
   with explicit units; the design profile guarantees
   numpy/scipy/pandas/matplotlib so the agent can curve-fit, FFT,
   and compare against models (e.g. fit a SPICE transient against
   the target s-domain step response and measure stray).
3. Two-tier console permission (amends the always-approve reading of
   I22): tier 1, analysis sandbox — standing user permission,
   read-only project data plus scratch, no host/network/evidence
   writes, no execution outside the sandbox; tier 2, effectful
   execution (runs, file staging, submissions) — per-action
   approval binding exactly as specified today. Agent
   self-approval stays forbidden in both tiers. NEEDS PRD SECURITY
   SIGN-OFF.
4. Reference analog agentic loop (guidance, non-normative). For an
   analog task the agent SHOULD: state the system-level goal as a
   desired s-domain equation with tolerances and WHY it pursues
   it; stitch a candidate component; simulate; fit measured
   response against the goal; read sample designs; iterate
   SPICE↔schematics until margins pass or it declares good-enough
   with reasons; keep human-in-the-loop on spec changes and
   sign-off. Engine support already exists: measurements carry
   target/margin/status (no new schema needed).

Of course just so you know, the analog s-domain loop is JUST an example, however it is a direction for how the agent MUST be guided. It should take the proper electronics course of action loop where it goes:

- Design System-level blocks at high level (save in markdown)
- For each block, specify mathematical desired response (S-domain, z-domain for digital, transient response, it can be anything) as a goal
- Build circuit 
- Verify circuit achieves desired output in both theory (schematic) and practical simulation (layout)
- One example is comparing the resultant vs design goal, and to iterate the agent harness UNTIL the error is minimal or the result is acceptable.
- And the best part? this loop can be coordinated using multiple agents each with their own modular subcircuit UNTIL the big circuit is there and done.