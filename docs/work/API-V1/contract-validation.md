# Engine v1 design validation

Date: 2026-11-01. This records contract/tooling validation, not live engine or solver conformance.

## Delivered boundary

The canonical root is `contracts/engine-v1.schema.json`. It allowlists 17 authored schema modules, six catalog files and accepted/rejected fixtures. Every authored module remains below 3,000 lines. Source definitions occur once; edit inputs permitting transaction-local IDs are derived from stored entity definitions. The compiler emits a standalone expanded schema, TypeScript consumer types, help metadata, task/tool reference and examples.

The vocabulary has six methods, 33 typed tasks and 65 tools/packages. Task providers are distinct from subordinate dependencies, and dispatch options/tool selectors/target kinds are checked against the catalog. All task options are closed schemas. Full native libraries remain a managed scripting capability.

## Checks performed

- `.venv/bin/python scripts/check_v1_contract.py --write`: generated the consumer outputs and validated **75 accepted / 23 rejected fixtures**.
- `.venv/bin/python scripts/check_v1_contract.py`: checked schema safety, allowlisted references, exact manifest exports, registry consistency, coverage of every task, source/expanded schema agreement, and generated-output freshness.
- Both the root bundle with its offline registry and standalone schema accept/reject the same examples. Retrieval of unknown schema resources is disabled.
- `/usr/bin/tsc --noEmit --strict --skipLibCheck false contracts/generated/client-types.d.ts`: generated structural consumer declarations compile.
- Active PRD invariant/catalog YAML parses with duplicate keys disabled; invariant IDs are unique.
- Local links in the contract guide, decision, review notes and changed primary PRD documents resolve.
- `git diff --check` in rocket-engine and PRD: clean.

## Meaningful negative boundaries

Fixtures reject unknown/opaque task options, mismatched tool drivers, missing transient settings, missing project/CAS context, client-written verdicts, duplicate code/source script inputs, finished-run replay action, quarantine override on cancel, missing I28 lock, queued PASS, resume/discard mismatch, invalid queue-full/cursor errors, unconfigured stored benches, missing component SPICE availability, foreign authoring language, unresolved local refs in stored records, and manufactured ASIC targeting of a testbench harness.

Accepted fixtures cover every task, all six success envelopes, PDK/IP/GDSFactory/hierarchy/request discovery, all three requested component presets, scoped SPICE/cocotb templates, saved source editing, direct layout paint, plot annotations, real-library scripting checkpoints, durable run/evidence records, partial script effects, authored canvas settings, native Amaranth testbench selection and qualified Xyce harmonic-balance bench selection.

## Required implementation evidence

These are structural/contract checks. They do not prove relational DUT containment, atomically persisted edits, scheduler durability, full I28 restoration, OS worker isolation, actual tool compatibility, or real provider responses. Those are explicit provider requirements in the canonical semantic rules, [execution acceptance matrix](execution-review.md), [editor/testbench review](editor-review.md), [tool qualification note](toolchain-review.md) and API-V1-CONFORMANCE ticket.

Existing v0 generated documents and provider implementations were preserved. The new deployment claim remains gated on provider and consumer conformance against the same contract plus representative installed-tool workflows.
