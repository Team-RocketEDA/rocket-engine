# PDK-LXT: Luxelligence GF support (TFLN + gated DRC deck)

*Status: Backlog · Size: M · Roadmap: pdk-onboarding (MVP track)*

## Why

Thin-film lithium niobate/tantalate electro-optic PDK on a GF
foundry service (`lxt_pdk_gf`, editable pip + install_tech.py):
layout + compact frequency-domain models. Two firsts for the
ladder: a non-silicon stack, and DRC decks that exist but are
access-gated (request-a-download, not in the repo) — the
perfect exercise of the user-supplied-deck path (fetch,
register, `resolve_deck` hash-pins it).

## What

- RED-first: profile entry; provision recipe; live proofs
  (cell build; model check — confirm SAX-compatible or
  record the actual sim path); user-supplied-deck flow
  proven with a fixture deck standing in for the gated
  `.lydrc` (fetch step documented, never faked).
- Capability matrix rows: layout ✓, sim per verified path,
  drc user-supplied (gated upstream, documented with the
  fetch recipe), lvs n/a.

## Acceptance

- Proofs green; gated-deck flow honest (no deck → loud
  unavailability naming the fetch recipe, never fake-green).

## Field notes (2026-11-01)

- Canonical source confirmed: `github.com/Luxtelligence/
  lxt_pdk_gf` (+ docs `luxtelligence.github.io/lxt_pdk_gf/`),
  cloned shallow to `/tmp/pdk-sources/lxt` (6.9M). Two
  variants: `lnoi400` (LiNbO3) + `ltoi300` (LiTaO3), each
  with cells, compact models, sample notebooks, and
  `klayout/*.lyp`.
- Install per upstream docs: `pip install -e .` + `python
  install_tech.py` (Python 3.12), restart KLayout.
- DRC gate confirmed: `.lydrc` runsets live behind
  `resources.luxtelligence.ai/request-access?resource=drc`
  (request-a-download, not in the repo) — the ticket's
  gated-deck acceptance stands as written.
