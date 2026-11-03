# CANVAS-PHOTONIC-NO-HDL: canvas v1 requires hdl even for photonic-only projects

*Status: Backlog · Depends: API-V1-CORE · Size: XS*

## Why

Scaffolding the `photonic_matmul` demo (GDSFactory MZI mesh on CORNERSTONE
Si340, no digital content) hit a usability bug in the v1 contract:
`CanvasConfig` in `contracts/v1/schemas/canvas.schema.json` lists `hdl` in
`required`, and `hdl.language` is itself required. A photonic-only canvas has
no authored HDL, so the author must either write a false `hdl` block (claiming
e.g. Verilog that does not exist, which then enters I28 run ingredients and
lies to every downstream consumer) or ship a knowingly schema-invalid
`canvas.toml`. Both options punish the exact photonic-first workflow the
hackathon demo needs, and a false `hdl` risks confusing the digital flow
adapters later. Small paper cut today, real trust hazard if it ships.

## What

- Make `hdl` optional on `CanvasConfig` for canvases with no authored digital
  content (preferred: omit the key; alternatively an explicit photonic-only
  marker — pick one, never both).
- If `hdl` is absent, the engine must treat the canvas as having no digital
  flow: digital-only tasks stay UNSUPPORTED with a clear reason, never implied.
- Regenerate via `scripts/check_v1_contract.py --write` (expanded schema,
  client types, help, examples) and re-verify without `--write`.
- Add an accepted `canvas.toml` example for a photonic-only project alongside
  the existing `contracts/v1/examples/accepted.json` coverage.

## Acceptance

- A photonic-only `canvas.toml` with no `hdl` key validates against the v1
  bundle and the engine admits it without inventing a language.
- A digital canvas missing `hdl` still fails loudly (no silent default).
- Contract checker + affected suite green; generated artifacts fresh.

## Verdict (2026-11-03, landed)

Done as specified (omit-the-key, never a marker): `hdl` left
`CanvasConfig.required` in `contracts/v1/schemas/canvas.schema.json`,
with the photonic-omission semantics written into the
`CanvasConfig`/`hdl` descriptions (absent hdl = no authored digital
content; digital-only tasks stay UNSUPPORTED, never implied; an
empty `hdl: {}` still fails on the required `language` — no silent
default). RED: new photonic accepted fixture failed the checker
with `'hdl' is a required property`; GREEN after the schema edit.
Added `contracts/v1/examples/accepted.json` "Photonic-only
canvas.toml (no authored HDL)" alongside the existing coverage, plus
`contracts/v1/examples/rejected.json` "Canvas hdl block without a
language is not photonic (omit the key)" pinning the loud failure.
Regenerated via `scripts/check_v1_contract.py --write` (76
accepted / 24 rejected; expanded schema, client types with optional
`hdl?`, help, examples, python models fresh) and re-verified clean;
`tsc --noEmit` on the regenerated `client-types.d.ts` passes and
`scripts/contract.py --check`, `scripts/api_spec.py --check` plus
the contract test files stay green. No engine code invents a
language for hdl-less canvases (nothing in `src/` reads canvas
`hdl`); digital-task gating rides the existing task dispatch, which
fails loudly without a canvas language.
