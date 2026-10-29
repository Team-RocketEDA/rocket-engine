# ASIC fixture candidates: research report

*Generated: 2026-10-29 | Sources: 14 | Confidence: High on digital, Medium on analog (young repos)*

Goal: shortlist open-source ASIC designs to vendor as known-good
fixtures (and mutate into known-bad) for the Nov 4 MVP. Defaults:
sky130-first (matches the installed PDK), small over complete,
permissive license mandatory for vendoring.

## Executive summary

Digital is easy: three canonical, highly-starred, permissively
licensed RISC-V cores, all active. Analog/mixed is thin: no
high-star options exist — the credible picks are young Apache-2.0
repos (a toolsmith canary, efabless CACE blocks, a documented
TinyTapeout ADC). Two tempting analog repos are **unlicensed and
excluded from vendoring**. Negatives come from curated mutations,
not upstream bugs.

## 1. Digital (strong field)

| Candidate | Stars | License | Pushed | Verdict |
|---|---|---|---|---|
| [YosysHQ/picorv32](https://github.com/YosysHQ/picorv32) | 4394 | ISC | 2026-09-07 | ✅ MVP pick (canonical, testbenches) |
| [olofk/serv](https://github.com/olofk/serv) | 1909 | ISC | 2026-08-25 | ✅ MVP pick (bit-serial, small, fast sims) |
| [stnolting/neorv32](https://github.com/stnolting/neorv32) | 2302 | BSD-3 | 2026-10-24 | Stretch (MCU-class, heavier) |

All three ship Verilog + testbenches and run under Icarus/Verilator
today. SERV is the lean-MVP workhorse (tiny, quick); picorv32 is
the credibility anchor.

## 2. Analog (thin field, license-gated)

| Candidate | Stars | License | Pushed | Verdict |
|---|---|---|---|---|
| [2amlogic/sky130-bandgap](https://github.com/2amlogic/sky130-bandgap) | 0 | Apache-2.0 | 2026-10-28 | ✅ MVP pick (spec + xschem + ngspice + GDS + DRC/LVS reports claimed; toolsmith org, very active) |
| [efabless/sky130_ef_ip__rdac3v_8bit](https://github.com/efabless/sky130_ef_ip__rdac3v_8bit) | 1 | Apache-2.0 | 2025-02 | ✅ alternate (efabless org, CACE characterization included — serves our CACE decision) |
| [efabless/sky130_ef_ip__samplehold](https://github.com/efabless/sky130_ef_ip__samplehold) | 0 | Apache-2.0 | 2025-02 | alternate |
| [arunbalaji-ee/bandgap-reference-circuit-sky130-pdk](https://github.com/arunbalaji-ee/bandgap-reference-circuit-sky130-pdk) | 0 | **NONE** | 2026-04 | ❌ excluded (no license; may poke manually, never vendor) |
| [jethanroberts/10-bit_sar_adc](https://github.com/jethanroberts/10-bit_sar_adc) | 0 | **NONE** | 2026-02 | ❌ excluded (no license) |

Bandgap is the right first analog block (DC + corners + a reference
voltage to assert against). The 2amlogic canary is preferred over
the efabless DAC for MVP because it claims layout + verification
reports, not just schematic — verify on fetch; fall back to the
efabless RDAC if the canary is immature.

## 3. Mixed-signal

| Candidate | Stars | License | Pushed | Verdict |
|---|---|---|---|---|
| [pthomas/ttsky-sigma-delta](https://github.com/pthomas/ttsky-sigma-delta) | 0 | Apache-2.0 | 2026-08 | ✅ MVP pick (CT sigma-delta ADC, design doc + measured results, TinyTapeout sky130; GitLab primary) |
| [2amlogic/sky130-sar-adc](https://github.com/2amlogic/sky130-sar-adc) | 1 | Apache-2.0 | 2026-10-28 | alternate (explicitly early/dogfood maturity) |

## 4. Negatives (known-bad)

No hunt for upstream bugs — negatives are **curated mutations** of
the good fixtures, documented per fixture: digital (broken reset,
truncation, unconnected port), analog (wrong device size pushing a
spec out of range, open net), layout (DRC violation cell, LVS
mismatch net). Deterministic, license-clean, and each mutation maps
to exactly one expected verdict.

## MVP fixture plan (lean)

Vendor: SERV + picorv32 (D), 2amlogic bandgap (A), pthomas
sigma-delta (M) — each with 1–2 documented mutations. Defer:
neorv32, efabless CACE blocks (revisit if bandgap disappoints),
photonics (cspdk, separate category), caravel-scale anything.

## Sources

- GitHub API repo metadata (stars/license/pushed) for all 10 candidates
- [CACE PyPI](https://pypi.org/project/cace/2.1.10/) — ef_ip block list with CACE characterization
- [TinyTapeout runs](https://tinytapeout.com/runs/) via TT paper — design index for small digital
- [awesome-open-ic foundry programs](https://github.com/vibeic/awesome-open-ic/blob/HEAD/docs/foundry-programs.md) — shuttle/template landscape

## Methodology

4 query threads (tiny digital, bandgap, ADC, CACE) across web
search; 10 candidates deep-checked via GitHub API for
stars/license/recency. License gate applied before any other
criterion. Analog confidence is Medium: the field is young and
low-star, so picks rest on org credibility + activity + claimed
artifacts, to be verified on fetch.
