# lxt provision recipe (PDK-LXT)

Fresh provision for the Luxelligence GF PDK, both variants (ltoi300 +
lnoi400). Every command below is taken from the PDK's own README at
the pinned revision; each carries the verification status from this
lane (2026-10-31, x86-64, KLayout 0.28.16, repo env with gdsfactory
9.51.0 + sax 0.18.2).

Pin: `https://github.com/Luxtelligence/lxt_pdk_gf.git` @
`d16db6a4882657feb1ce696c16c604ff6cb7ccfa` (2026-06-01, package
`lxt_pdk_gf` 2.0, MIT). Upstream dep floor: Python ~=3.12,
`gdsfactory~=9.34`, `gplugins>=1.4,<2`, `sax~=0.16.3`.

## 1. Clone + editable install (PDK README, "Installation")

Upstream says:

```sh
git clone https://github.com/Luxtelligence/lxt_pdk_gf.git
cd lxt_pdk_gf
pip install -e .
python install_tech.py
```

Status:

- `git clone https://github.com/Luxtelligence/lxt_pdk_gf.git` —
  VERIFIED (shallow clone to /tmp/lxt-pdk; HEAD `d16db6a…` matches
  `git ls-remote` HEAD).
- `pip install -e .` — NOT-RUN-HERE. This sandbox has no PyPI route
  (`uv run --with ...` fails after retries: `Failed to fetch:
  https://pypi.org/simple/...`, connect timeout), so the
  dependency install could not execute here. The integrator re-runs
  it on a networked host. Verified equivalent: all lane proofs ran
  against the real upstream tree via `PYTHONPATH=/tmp/lxt-pdk`
  (byte-identical clone at the pinned revision) plus `gplugins`
  1.4.2 source from GitHub (tag `v1.4.2`, commit `f47ed3d…`, within
  the upstream `>=1.4,<2` range) on `PYTHONPATH`, with the repo
  env's gdsfactory 9.51.0 + sax 0.18.2 standing in for the pinned
  `~=9.34` / `~=0.16.3` (PyPI-blocked). Geometry and straight-model
  goldens are physics-stable across that drift, but the integrator
  MUST re-run `LXT_LIVE=1 pytest tests/pdk_lxt` in the pinned env —
  the goldens will honestly flag any drift as failure.
- `python install_tech.py` — VERIFIED (same script against a scratch
  HOME, KLayout 0.28.16 batch):

```sh
HOME=/tmp/fakehome-lxt python install_tech.py
# link made: From: <clone>/lnoi400/klayout
#            To:   /tmp/fakehome-lxt/.klayout/tech/lnoi400
HOME=/tmp/fakehome-lxt klayout -b -r probe_tech.py
# TECHS: ['', 'LNOI400']
# HAS_LNOI400: True
```

The real `~/.klayout` was not touched; the recipe above is the
operator's command. Restart KLayout afterwards (upstream README).

Upstream gap for the integrator: `install_tech.py` links ONLY
`lnoi400/klayout`. ltoi300 needs the same shape done manually
(`ltoi300/klayout` holds just `ltoi300.lyp`, no `.lyt`):

```sh
ln -s "<clone>/ltoi300/klayout" ~/.klayout/tech/ltoi300
```

Status: NOT-RUN-HERE (mechanical `ln -s`; operator/integrator runs
it). The lane tests do not depend on it.

## 2. Verify probe (PDK import + proof cell + proof model)

```sh
python -c "import ltoi300, lnoi400; \
ltoi300.PDK.activate(); c = ltoi300.cells.straight_rwg900_cband(length=10.0); \
print('cells', len(ltoi300.PDK.cells), '| models', len(ltoi300.PDK.models), \
'| ports', sorted(p.name for p in c.ports), \
'| bbox', (c.bbox().width(), c.bbox().height())); \
import numpy as np; s = ltoi300.PDK.models['straight_rwg900_cband'](wl=1.55); \
print('|s21|', abs(complex(np.asarray(s[('o2','o1')]).reshape(-1)[0])))"
```

Expected output:

```text
cells 26 | models 13 | ports ['o1', 'o2'] | bbox (10.0, 12.9) |s21| 0.999942437
```

Status: VERIFIED (ran green via the PYTHONPATH equivalent; the
identical command works against the `pip install -e .` tree once
step 1 runs on a networked host). Upstream's own fuller check is the
`docs/notebooks` Jupyter notebooks (README "Examples") — NOT-RUN-HERE
(no notebook runner in this sandbox).

## 3. DRC position (GATED — access request required)

There is deliberately no install command here. Upstream (README "KLayout
DRC") documents this flow, verified by reading the pinned README on
2026-10-31:

1. Request access at <https://resources.luxtelligence.ai/request-access?resource=drc>
   (page: "LXT Design Manual - Foundry Design Guidelines"). The
   `.lydrc` runsets are stack-specific downloads, not repo files —
   verified: the pinned tree contains zero `*.lydrc`/`*.lylvs`/deck
   files, and no numeric rule values anywhere in `lnoi400/`,
   `ltoi300/`, or `_utils/`. (The in-repo `lnoi400/klayout/d25/
   LNOI400.lyd25` is a 2.5D layer-stack view script, not a deck.)
2. Place the downloaded `.lydrc` file(s) in `<user home>/Klayout/drc/`.
3. Keep only ONE `.lydrc` in that folder at a time (KLayout known
   issue: only the first DRC file is used).
4. Run in the KLayout GUI: open the GDS, Tools → DRC → Edit DRC
   Script → select the stack's `.lydrc` → run. No upstream batch
   command is documented.
5. Read the results with the upstream caveat: flagged violations may
   be advisory or context-dependent, and the deck does not guarantee
   catching every design error.

Status: GATE DOCUMENTED, DECK NOT FETCHED (fetching requires the
access grant, which this lane does not hold and does not fake). The
lane instead proves the honest remainder:

- the gate requirement verbatim (profile `drc.gate_requirement`,
  pinned by `test_profile.py`);
- the user-supplied-deck flow (`register_pdk` → `resolve_deck` hash
  pin → `verify_pdk`, missing deck → loud `unknown_pdk`) against a
  labelled stand-in deck, pinned by `test_user_deck.py`;
- a labelled 100 nm width/space GEOMETRY SANITY check on the built
  GDS (klayout batch, 0 violations) — smoke only, never presented
  as DRC, pinned by `test_proofs.py`.
