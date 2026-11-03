# vtt capability-matrix rows (proposed, PDK-VTT)

Proposed rows for the ENGINE-SETUP capability matrix / catalogue
(the integrator places them; this lane only proposes). Verdict is
BLOCKED: no behavioral proof exists, so every runnable capability is
`blocked` (not `✓`), and LVS is honest `n/a (photonic)`. Lane column:
`tests/pdk_vtt/` (9 pass: inventory + verdict pins, no live behavior).

| Capability | Status | Proved by |
|---|---|---|
| layout (VTT cell build) | blocked (B1) | nothing -- `import gvtt` raises ImportError under every installable gdsfactory (9.40.2/9.45.0/9.51.0); lane `test_inventory.py` pins only the static layer inventory (67 views, golden numbers) |
| drc (klayout) | blocked (B2) | no deck ships upstream (no .lydrc/.lyd25/.drc); only tech.lyt + layers.lyp + boolean helper macro. No engine-substitute rules written: no design-rule doc ships to derive them from |
| optical-sim (sax) | blocked (B3) | no models registry, no sparameters dir, no .lib/.spice upstream; nothing to simulate against |
| lvs | n/a (photonic) | no transistors to recognize; connectivity compare would be kfnetlist's role once layout unblocks, out of this slice |

Caveats (honest n/a + limits, keep with the rows):

- B1: One-line root cause, verified three ways (report.md). Diagnostic
  shim (`gdsfactory.pdk.constants = Constants()`, process-local, ships
  nowhere) builds all 12 cells under 9.45.0 AND the repo's 9.51.0 with
  identical bboxes; XOR vs upstream refs is clean except sub-nm mmi1x2
  drift. Upstream fix: drop `constants` from the `gdsfactory.pdk` import
  and the `Pdk(...)` kwargs (as cspdk/ubc/gf180/ihp already do) and raise
  the `<9.46.0` ceiling to admit >=9.51. Until then VTT cannot share an
  environment with the repo layout closure (test pins the exclusion).
- B2: Do NOT mark drc `✓ with caveat` on engine-written rules: unlike
  lanes with a design-guideline PDF, VTT ships no rule values at all, so
  any threshold would be invented. Row stays `blocked` until a foundry
  deck or rule document appears.
- B3: Same for optical-sim: no placeholder models exist to pin, so no
  SAX goldens were written. Row stays `blocked` until models ship.
- P1: `pip install gvtt` / `uv sync` were NOT run -- sandbox has no PyPI
  route (tunnel-error evidence in report.md). The locked gdsfactory 9.0.1
  path (upstream CI's config) is therefore UNVERIFIED, not green.
- P2: Only the `3umsoi` single variant exists upstream; there is nothing
  else to inventory.
- P3: `python install_tech.py` (KLayout tech symlink) is the one upstream
  command verified working in this lane (exit 0, redirected HOME).
