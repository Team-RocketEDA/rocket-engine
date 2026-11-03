# Magic extraction + Netgen LVS proof, and the sky130.lvs verdict (EXTRACT-SKY130, 2026-10-29)

Known-good cell throughout: `sky130_fd_sc_hd__inv_2` from the
registered PDK (`sky130a@v1.0.588`). Tool versions: magic 8.3.685,
netgen 1.5.316, KLayout 0.28.16, sky130A tech 1.0.588. All PDK paths
below resolve via `resolve_deck`, so manifest hashes are checked.

## Proof 1: Magic extraction (`sky130A.tech`)

Recipe (argv only, Tcl over stdin):

- `magic -dnull -noconsole -T <libs.tech/magic/sky130A.tech>` with
  `load <cell>`, `select top cell`, `extract all`, `ext2spice lvs`,
  `ext2spice`, `quit`.
- Outputs `<cell>.ext` + `<cell>.spice` in the workdir; success
  marker `exttospice finished.` on stdout (exit code is 0 either
  way — parse, don't trust it).

Result: 4 FETs, `sky130_fd_pr__nfet_01v8` 2x w=0.65 l=0.15 and
`sky130_fd_pr__pfet_01v8_hvt` 2x w=1.0 l=0.15 — the exact device
complement of the PDK schematic. Engine surface: `run_extraction`
via `MagicExtractAdapter` (`src/adapters/extract_magic/`).

## Proof 2: Netgen LVS compare

Recipe: `netgen -batch lvs <layout_flat> <schematic_flat>
<libs.tech/netgen/sky130A_setup.tcl> <report>` with DISPLAY
scrubbed (batch still inits Tk; an unreachable `$DISPLAY` aborts
startup). Netgen's one-shot `lvs` compares TOP-level circuits, so
both sides are flattened first (single-`.subckt` wrappers dropped;
libraries sliced by cell — see `flatten_spice`). Exit code is 0 on
match AND mismatch — the verdict is parsed.

- Good (extracted layout vs the PDK `.spice` subckt): `Circuits
  match uniquely.` → PASS.
- Mismatch probe (one net edited, `VPB` → `VPB_BAD` on X3):
  `Netlists do not match.` with `*** MISMATCH ***` counts plus
  named `Net:` / `Instance:` fragments (`Net: VPB_BAD`,
  `Instance: sky130_fd_pr__pfet_01v8_hvt:3`) → FAIL with named
  diffs. Engine surface: `run_lvs` via `NetgenLvsAdapter`
  (`src/adapters/lvs_netgen/`).

## Verdict: the KLayout `sky130.lvs` path FAILS — Magic stays (evidence-locked)

Attempted on the same cell: single-cell GDS pulled from
`libs.ref/sky130_fd_sc_hd/gds/sky130_fd_sc_hd.gds`, schematic from
the PDK `.spice` lib (and separately the `.cdl`), run as the deck's
own `run_lvs.py` invokes it:

- `klayout -b -r <libs.tech/klayout/lvs/sky130.lvs> -rd
  input=inv_2.gds -rd report=inv_2.lvsdb -rd schematic=<netlist>
  -rd target_netlist=extracted.cir -rd run_mode=flat ...`

Three attempts, all `ERROR : Netlists don't match` (deck exits 1):

1. `.spice` (X-device) schematic, documented switches
   (`convert_subckts` default `false`): the log shows `Flatten
   schematic circuit (no layout): SKY130_FD_PR__NFET_01V8...` —
   schematic devices never convert to primitives.
2. Same + `-rd convert_subckts=true`: the `.lvsdb` shows schematic
   classes UPPERCASE (`SKY130_FD_PR__NFET_01V8`) against layout
   classes lowercase (`sky130_fd_pr__nfet_01v8`). KLayout's SPICE
   reader uppercases; the deck compares case-sensitively. This is
   the upstream case bug (MAGIC-EXIT trigger #531), reproduced.
3. `.cdl` (M-device) schematic + `convert_subckts=true`: still
   mismatch (primitive `NFET_01V8` vs `sky130_fd_pr__nfet_01v8`
   classes — no equate in the deck).

Notably the layout side is healthy: `extracted.cir` holds the
correct 4 FETs, nets, and W/L. Only the schematic-compare side is
broken, and fixing it means changing the deck or the invocation
beyond its documented recipe — out of scope for this slice.

So: no second LVS path lands here, and there is deliberately no
KLayout LVS solver in the engine. Magic extraction + Netgen LVS is
the evidence-locked loop until trigger #531 fires (re-run attempt
2 above against the new tree; a `Congratulations! Netlists match.`
reopens the migration slice).
