# LVS-ESCAPE: Bulk-rename mutant escapes LVS 3/3 seeds (FIXED 2026-11-03)

*Status: Ready · Depends: none · Size: S ·
Roadmap: hardening (E2E-REREVIEW FIND-07, MED)*

## Why

The netlist_lvs_mismatch operator escapes on all 3
seeds: mutated netlists still PASS LVS (harness
honestly reports exit 1, so the gate holds — but the
mutant proves a detection hole). Root cause undiagnosed
(netgen setup vs operator, operators.py:437-461 vs
lvs adapter:300-310); possible shared root with
LVS-BANDGAP-TRIAGE, kept separate until proven.

## What

- Diagnose with evidence, fix the losing side
  (setup or operator), pin the escape as a regression
  (escape → FAIL).
- All 3 seeds must fail post-fix.

## Acceptance

- 3/3 escape seeds FAIL LVS; root cause in report.
- Contract + api_spec regen; full suite + gate green.

## Verdict (2026-11-03, adapter-local fix, GREEN)

Reproduced pre-fix with netgen 1.5.326 + `sky130A_setup.tcl`
(store `sky130a@5f09001e`): the `lvs_inv` single-device pair with
`VPB->VPB_BAD` (seed 0/2) or `VNB->VNB_BAD` (seed 1) on the
schematic side reports `Circuits match uniquely` — escape on all
3 seeds, exit 0.

Root cause, losing side = the adapter surface (not the setup, not
the operator). The setup file carries no global/net-merging
directives (only `permute`/`property`/`ignore` + `OFFGRID`; verified
by grep). The operator truly renames (the mutation lands in the
file and survives flatten — the file/shape harness tests pass).
Netgen's one-shot `lvs` with `permute default` matches by
topology, and renaming a singly-connected net preserves the
topology exactly — invisible to ANY isomorphism-based compare.
The adapter dropped the name evidence; that is the hole.

Fix (`src/adapters/lvs_netgen/`, this wave): `execute` records
`layout_nets`/`schematic_nets` inventories of the flattened
X-lines; `parse` fails a netgen MATCH with asymmetric names as
`match: False` with `lvs_net_mismatch` violations naming each
net and side (`Net: VPB_BAD (only in schematic)`), and merges the
extras into netgen MISMATCH verdicts. Legacy native outputs
without inventories parse exactly as before. Post-fix: 3/3 seeds
FAIL with the bad net named; byte-identical pairs and the
extracted-vs-PDK inv_2 good path still PASS (net-name sets equal
there — verified live).

Regression pinned: `tests/adapters/test_lvs_escape.py` (10
tests: parse units + 3 live seeds FAIL + 1 live good-pair PASS).

Handoffs: engine-level `test_lvs_mutated_fails_live` still errors
on a pre-existing `composition.py` `_maybe_record_evidence`
AttributeError, identical on the pristine install — another
agent's in-flight work, not this fix. `scripts/api_spec.py
--check` / `scripts/contract.py --check` crash on the same foreign
breakage; the generated schema already carries the (unchanged)
`run_lvs` surface, so no regen is owed by this ticket. A
considerate follow-up for the mutate owner: prefer shared-net
renames (topology-visible) for future LVS operators, since
singly-connected renames now fail only via the inventory
tripwire, not the isomorphism.
