---
name: rocket-engine
description: Use RocketEDA's local headless engine to discover PDK/IP building blocks, edit circuit projects, run supported ASIC and circuit checks, or inspect simulation datasets. Use for engine operations; it does not design the chatbot or implement an unrelated EDA solver.
metadata:
  short-description: Author and verify RocketEDA circuit projects
---

# RocketEDA engine

Work through the engine attached to the user's local project. The engine owns
canonical circuit identities, source revisions, hierarchy, connectivity, task
execution and evidence. The frontend renders it; the agent does not mint trusted
verification results or maintain a parallel project database.

## Choose the actual API version

Inspect the tools/capabilities exposed by the attached runtime before calling
operations. The source repository's v1 contract is a design target during
migration, not proof that the running provider supports it. Read
[API versions](references/versions.md) when the runtime and examples differ.
Do not call a declared-but-unwired operation or treat a local mock as a solver.

For a conforming v1 runtime, use six methods:

| Method | Job |
|---|---|
| `describe` | Get exact method/task/template schemas and contextual requirements. |
| `query` | Read a supplied project, PDK, library, package, hierarchy or evidence source. |
| `edit` | Commit typed project/editor/source transactions. |
| `run` | Start a workflow or task, or control an unfinished run. |
| `script` | Use prepared Python/native libraries with managed project access. |
| `watch` | Follow project effects, results, logs and capacity. |

Read the selected task's input schema and readiness for its exact target, PDK
and profile. Registration, installation, qualification and target readiness are
different facts. Unknown/unavailable capability is a useful result, not a reason
to fabricate a substitute output.

## Select the relevant workflow

- For component discovery, hierarchy, sources, symbols, layout or testbench
  edits, read [project authoring](references/authoring.md).
- For DC/AC/transient, HDL/cocotb, physical checks, optical circuit simulation,
  result datasets or evidence, read [tasks and results](references/results.md).
- For a missing convenience wrapper, use full installed GDSFactory/Python APIs
  through `script` in the user's permitted local profile. Ordinary script
  libraries are not restricted to the registered task catalog. Publish project
  geometry/source through engine edits or documented managed checkpoints.

## Preserve the engine invariants

Use a fresh request ID for a genuinely new mutation/run. Retry the identical
payload with the same ID after a disconnect or a retryable pre-admission
response. A changed payload under an existing ID is a conflict. On capacity
pause, retain the request and wait for resume; never spin or drop accepted work.

Use the returned snapshot and per-entity revisions. Resolve conflicts by reading
the affected entities; do not silently overwrite or invent a merged revision.
Working project source links follow saved edits; explicitly pinned references
stay fixed. Query/help must not execute project factories just to discover them.

Every consumed source, `canvas.toml` reference, DUT/bench binding, port map,
model/PDK/technology/deck, tool/profile version, seed and effective setting must
belong to the run's I28 input closure. Generated native configs and outputs are
artifacts until explicitly adopted as design input. Process exit zero, a file
called GDS, or a package import does not establish a trusted PASS.

Use the owner's client-edge allow/ask/deny policy for AI execution. Human
permission can cover a script and its internal imports/helper calls; do not
invent a fresh approval for every function. Local scripts are normal power-user
work. Respect the selected execution profile and existing authorization; do not
silently move execution or project data to a cloud service. A local execution
failure is not permission to expand access or replace the selected solver.

Keep user-visible responses compact: the result and actionable blockers when
needed. Structured plots/tables/violations belong to result views, and verbose
native logs belong to the output terminal. Do not add explanatory UI prose,
decorative readiness labels, or fake chart values.

## Source-of-truth references

In an engine source checkout, the canonical boundary is
`contracts/engine-v1.schema.json`; its generated catalog, examples and client
types live in `contracts/generated/`. The installed runtime should expose the
same versioned information through `describe`. Read source files only when
maintaining the engine; consumers should discover the attached runtime.

The November 4, 2026 MVP is local Electron/React. FPGA and advanced EM/FEM,
field/mode/device and thermal workflows are deferred; their defined contracts
and RED acceptance cases do not mean deployed support. Respect current roadmap
capabilities rather than promising every registered task.
