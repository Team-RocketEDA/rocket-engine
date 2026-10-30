# Provision plan (PROV seed, B10 input)

How the engine's native toolchain gets installed and pinned. Python deps
are already locked in `uv.lock`; this doc covers everything `uv` cannot
install: simulators, PDKs, and decks.

## External dependency guideline (standing)

Read the docs, read the docs, read the docs. Every provision recipe
MUST use the tool's own documented, most-correct install method —
never a stale convenience channel. apt lags upstream by years for
the tools we care about: Magic/Netgen-family tools install from
source (clone → configure → make → install, per the
rtimothyedwards sites) with configure flags chosen for the
engine's needs, and every other tool gets the same treatment from
its own documentation. A recipe that cannot cite its upstream doc
is not done.

## Ambient census (2026-10-30, x86-64, Python 3.12.3, uv 0.13.5, dev-PATH = oss-cad-suite + ~/tools/bin)

| Tool | State | Note |
|---|---|---|
| magic 8.3.685 | present | CLI works (`/usr/local/bin`, source build) |
| KLayout 0.28.16 | present | `-b` batch works; GUI broken (xcb) — engine uses batch only |
| ngspice-42 | present | `/usr/bin`, KLU solver; live proofs green |
| netgen 1.5.326 | present | `~/tools/bin` (needs PATH), opencircuitdesign source build; live LVS green |
| icarus 14.0-devel, vvp | present | oss-cad-suite; live HDL proofs green |
| verilator 5.053-devel | present | oss-cad-suite |
| ghdl 7.0-dev, slang 12.0, sby v0.70, yosys 0.70 | present | oss-cad-suite |
| xschem | present | `/usr/local/bin`, requires X; display-side, RocketIDE concern |
| gtkwave | present | oss-cad-suite; requires X; display-side |
| bwrap | present | user-ns ok; netns denied in sandbox (re-prove on target) |
| cvc, openroad | absent | batch roles per B10 matrix; no recipe yet |

## Provision approach (plan, not yet executed)

- `scripts/install.sh` (B10) installs one pinned source per role, verifies
  with `tests/installed/`, and records the result in the capability matrix.
- Preferred channels on Ubuntu 24.04 LTS: pinned oss-cad-suite tarball for
  the digital bundle (verilator, icarus, ghdl, yosys, sby); apt pins or
  source builds where the bundle lags (ngspice); existing ambient magic /
  KLayout kept and version-asserted, not reinstalled.
- Engine/display split: only batch-capable tools are engine deps. Anything
  needing X (xschem GUI, KLayout GUI, GTKWave GUI, Surfer) is RocketIDE-side
  and must never gate engine tests.

## Reinstall proof (clean-room, 2026-10-28)

Fresh tree from `git archive HEAD` in `/tmp/proof`, fresh venv, locked sync:

```sh
bash scripts/install.sh --install   # one command: venv + locked deps + sealed package
.venv/bin/pytest -q                 # 51 passed
```

Result: **51 passed**. The locked Python env reproduces from zero.

## Blockers

- Deck-source decision (vendor sky130A snapshot vs user-installed PDK path)
  gates PDK/deck provisioning and the DRC slices.
- Corpus repo review gates known-good/known-bad fixtures per D/A/P/M.
