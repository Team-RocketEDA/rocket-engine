# GDSFactory+ parity (clean-room, public sources only)

*Date: 2026-11-04 · Method: 6 parallel researchers over public docs
(gdsfactory.com/plus, docs, changelog, public GitHub), paraphrased —
no paywall bypass, no code copied. Companions: [replacement map](gdsfactory-replacement-map.md), [GUI abstraction](gdsfactory-gui-abstraction.md).

## 1. What Plus is (public shape)

Paid VS Code extension/environment on the open library: graphical
schematic + layout editors, verification, simulation, AI agent. OSS
keeps working standalone. Venues: Local (user machine) and Cloud
(browser VS Code via portal). Licensing: per-user portal API key,
license-server check at startup; no public price list (quote-based).
Trial expiry pauses licensed PDKs/features; user files untouched.

PDK coverage is the moat: 43–50+ processes, per-process
layout/DRC/model matrix + distribution column. NDA kits distributed
by foundries/brokers, entitlement-gated. Custom internal PDKs
registrable from GDS + layer map.

## 2. Parity map vs our stack

| Area | Status | Notes |
|---|---|---|
| Editors (schematic-driven layout) | BUILD | Our canvas spec (§5/11/13) exceeds public Plus detail; impl viewer-only |
| GDS/KLayout/SPICE interop | BUILD | File-level both sides; no live round-trip either side |
| PDK catalogue | HAVE entries + BUILD marketplace | sky130A/ihp units exist; missing: searchable verified catalog, flavour filtering, entitlement-aware installs, CONF-style settings, worker health |
| Sim/verify local lineup | HAVE | KLayout/Magic DRC, Netgen LVS, ngspice, SAX/Circulax/MEOW |
| Cloud FDTD / cloud DRC | POLICY-BLOCKED | Local-only rule; BYOC opt-in rows only |
| License-server-at-startup | POLICY-BLOCKED | Closest allowed: BYOC key entry |
| Agent + MCP + SDK + CLI | BUILD | Our chat/MCP/approval is the counterpart; repair loops + own MCP server pending |
| Setup/installer page | HAVE catalogue + BUILD page | §14 Vivado-style page; matches Plus auto-resolve + interpreter selection |
| Org seats / shared cloud workspaces | GAP | Needs new design; no Plus live-co-edit evidence either |

Key Plus patterns worth mirroring: sample-project-first PDK
onboarding (project file declares PDK, auto-resolve, selector
dropdown, flavour-filtered pickers); repo-based tapeout flow
(one repo per tapeout, frozen PDK copy, pinned deps, XOR
regression); worker health + registry UX (cell-list filtering
fail-open with warning, per-project CONF settings).

## 3. Frontend bake-in order

1. Sample-project-first PDK onboarding (highest value).
2. Schematic-driven layout flow with side-panel sim controls +
   error-to-layout navigation.
3. Verification-first UX (quick actions, fixed error taxonomy).
4. Worker Health + registry UX.
5. Agent/chat parity (mode chips, quick actions, gating tiers).
6. Repo-based tapeout template; defer live co-editing.

## 4. Non-goals

Cloud-only execution as default; paywalled unknowns (prices, tiers,
token caps, NDA contents, portal internals); unverified internals
(save-back semantics, registry schema, per-version PDK pins).

## Gaps

Exact tiers/prices/token caps; panel SAX/SPICE/FEM venue (local vs
cloud); schematic save-back + polygon toolset depth; per-version PDK
pin flow; private-upload scoping; registry catalog schema; deck/model
provenance schema; MCP auth/versioning.
