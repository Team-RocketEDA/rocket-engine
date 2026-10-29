# Mutation operators (MUTATE-HARNESS)

Systematic incorrect-design generator: each operator stages scratch
copies of a committed base fixture under `tmp/scratch/` (vendored
and committed trees are never mutated in place), applies a seeded
mutation, and declares the expected engine verdict. The pytest runner
(`tests/mutate/test_mutations.py`) and the CLI runner
(`scripts/mutate.py recheck`) both recheck good-PASS then
mutated-expected-FAIL end-to-end through `Engine.run`.

Variant selection is `seed % len(variants)` — every mutation is
reproducible from its seed, and the evidence dict records the
operator, seed, variant, and expected verdict/rules.

## Operator → verdict map

| Operator | Domain | Base fixture | Engine op | Good | Mutated |
|---|---|---|---|---|---|
| `digital_reset_break` | digital | `tests/adapters/fixtures/hdl/counter.v` + `tb_pass.v` | `run_hdl_test` (icarus) | PASS | FAIL (`assert_fatal`) |
| `digital_truncation` | digital | `tests/adapters/fixtures/hdl/counter.v` + `tb_pass.v` | `run_hdl_test` (icarus) | PASS | FAIL (`assert_fatal`) |
| `digital_unconnected_port` | digital | `tests/adapters/fixtures/hdl/tb_pass.v` | `run_hdl_test` (icarus) | PASS | FAIL (`assert_fatal`) |
| `analog_sizing_out_of_spec` | analog | `tests/adapters/fixtures/ngspice/rc_divider.spice` | `run_spice` (ngspice) | PASS | FAIL (`measurement`) |
| `analog_open_net` | analog | `tests/adapters/fixtures/ngspice/rc_divider.spice` | `run_spice` (ngspice) | PASS | FAIL (`measurement`) |
| `layout_drc_violation` | layout | `tests/adapters/fixtures/drc/good.mag` | `run_drc` (magic scmos) | PASS | FAIL (`spacing`/`width`) |
| `netlist_lvs_mismatch` | layout | `tests/mutate/fixtures/lvs_inv/` pair | `run_lvs` (netgen) | PASS (match) | FAIL (`lvs_net_mismatch`) |
| `photonic_geometry_mistune` | photonic | `tests/adapters/fixtures/sax/mzi.yml` | `run_optical` (sax) | PASS | FAIL (`transmission`) |
| `photonic_circuit_mistune` | photonic | `tests/adapters/fixtures/sax/mzi.yml` | `run_optical` (sax) | PASS | FAIL (`transmission`) |

"Only the target flips" is asserted per operator: the mutated run's
error-severity findings carry exactly the declared rule(s) — e.g.
digital mutations yield `assert_fatal` with zero compile diagnostics,
so the break is behavioral, not syntactic.

## Per-operator notes

- `digital_reset_break` (2 variants): seed 0 inverts the reset
  condition (`if (!rst_n)` → `if (rst_n)`), seed 1 sticks reset
  active (`if (1'b1)`). Either way the count is 0 at the check and
  the bench `$fatal`s. Verified live with iverilog 14.0 + vvp.
- `digital_truncation` (3 variants): the count update is masked to
  3 bits (`& 4'h7`, max 7), 2 bits (`& 4'h3`, max 3), or
  zero-extended from 3 bits (max 8) — the bench expects 10 and
  `$fatal`s. Verified live with iverilog 14.0 + vvp.
- `digital_unconnected_port` (2 variants): seed 0 opens `.rst_n()`
  (reset floats, count never clears), seed 1 opens `.clk()` (no
  edges, count never advances). Verified live with iverilog + vvp.
- `analog_sizing_out_of_spec` (3 variants): R2 8k → 4k / 2k / 16k,
  so Vout = 0.9 / 0.6 / 1.44 V against the [1.199, 1.201] V bound.
  PDK-free divider: live where ngspice exists, otherwise
  quarantined (see `docs/tickets/NGSPICE-LIVE.md`); the verdict
  mapping is pinned by canned-envelope parse tests.
- `analog_open_net` (2 variants): R2 lifted from `out` (renamed
  node or commented device). No value changes — the topology break
  unloads the divider, `out` rises to the 1.8 V rail, and the vout
  measurement misses. Same quarantine/parse story as sizing.
- `layout_drc_violation` (2 variants): seed 0 shifts the second
  rect to 1λ spacing (mirrors `bad_spacing.mag`), seed 1 narrows
  the first rect to 1λ width (mirrors `bad_width.mag`). Verified
  live with magic 8.3.685 + scmos ("... metal spacing/width must
  be at least 3").
- `netlist_lvs_mismatch` (2 variants): seed 0 renames the pfet
  bulk VPB → VPB_BAD, seed 1 the nfet bulk VNB → VNB_BAD, on the
  schematic copy only. The site shape mirrors the proven
  EXTRACT-SKY130 probe and hits exactly once in the real
  `sky130_fd_sc_hd__inv_2` lib slice (verified read-only against
  the scratch PDK store). Live needs netgen + the sky130 setup
  (quarantined per NGSPICE-LIVE); the verdict mapping is pinned by
  the verbatim recorded netgen match/mismatch reports.
- `photonic_geometry_mistune` (2 variants): bottom arm +0.2 μm
  (mirrors `mistuned.yml`: 0.33972 / −4.689 dB) or +0.4 μm
  (0.10276 / −9.882 dB) at 1550 nm against the −0.5 dB cross
  target. Verified against real sax 0.18.2.
- `photonic_circuit_mistune` (1 variant): output coupler coupling
  0.5 → 0.1, cross drops to 0.8 (−0.969 dB) against the −0.5 dB
  target. Verified against real sax 0.18.2. Live rechecks need the
  `photonic` group (`uv sync --group photonic`, B10-owned);
  otherwise quarantined loudly, with canned-envelope parse tests
  pinning the mapping.

## Vendored-design follow-up (VALIDATE-*) 

These operators target small committed fixtures so the RED-first
flip per operator stays fast and hermetic. VALIDATE-D/A/P/M reuse
the same operator shapes on the vendored trees (SERV reset/trunc/
port breaks, bandgap sizing/opens, sigma-delta seam pairs, cspdk
geometry/circuit mistunes) — same evidence shape, same
good-PASS/mutated-FAIL runner pattern.
