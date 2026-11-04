# SETUP-PAGE: Vivado-style installer page in the IDE (UIUX-owned, engine-contract-driven)

*Status: Backlog · Filed: 2026-11-04 · Source: setup-surface review 2026-11-04*

PRD `frontend-requirements.md` §14 specifies the installer/setup page:
PDK installs AND missing-tool installs in one Vivado-style checkbox
menu with sizes/states; per item the user chooses **engine-provided**
(engine runs its provision recipe) or **user-provisioned path**
(register an external install; engine verifies + pins it). Engine side
is done ([ENGINE-SETUP](ENGINE-SETUP.md): catalogue + detection +
`report_capabilities`); page + state live in UIUX. UIUX has no such
page today (verified 2026-11-04: "setup" hits are timing-setup only).

## Contract (contract-first: no handwritten shapes)

- Authoritative artifacts: `src/interfaces/setup_catalogue.yaml`
  (catalogue v1), `contracts/engine-v1.schema.json`,
  `Engine.capabilities` / `report_capabilities` responses.
- UIUX consumes generated types only (`api-schema.json` / generated
  client); no hand-written capability/entry shapes, no prose-derived
  field names. Any new field the page needs lands in the catalogue or
  v1 contract first, with provider + consumer verification.
- Per-item actions map to existing machinery: engine-provided →
  provision recipe (`provision_toolchain.sh --only <tool>`,
  `install.sh --pdk-only`); user-provisioned path → register +
  engine verify-and-pin (PDK store `register/verify`, tool
  version-assert).

## Scope (UIUX owner; engine seam support only)

- Checkbox menu over catalogue entries with live state
  (installed / missing + remedy / degraded / cloud-gated), sizes
  where known, and the honest-checkbox rule: prerequisites shown
  BEFORE the user ticks (BUILD-LOCAL stage 3).
- Engine-provided vs user-provisioned-path choice per item, PDKs
  included (`source_default` + deck list from the catalogue).
- Degraded tools (e.g. unprovisionable Xyce, `provisionable: false`
  palace) render as visible-disabled with reason + remedy — never
  hidden, never green.

## Acceptance

- Fresh machine: page lists every catalogue unit with correct state;
  ticking one item flips exactly its row (mirrors ENGINE-SETUP
  flip-exactly-one tests, now through the UI).
- Contract check: UI fixtures validate against the same catalogue +
  v1 schema the engine verifies against; no consumer uses
  undocumented fields.
