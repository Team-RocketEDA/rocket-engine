# ENGINE-SETUP: Vivado-style setup surface (capability + provision)

*Status: Backlog · Relates: B10, PROV, CLOUD-AUTH · Size: M · Roadmap: convergence*

## Why

The engine ships with its own setup menu: checkboxes to pull
any/all tooling (solvers, PDKs, decks) with install state,
Vivado-style — the surface RocketIDE's convergence build and
first-run UX drive. Today the pieces are scattered: B10 covers
install.sh + capability matrix, PROV the toolchain/PDK
provision, CLOUD-AUTH the opt-in credential store — but no
single query reports "what can this engine do, what is
installed, what is installable, and what needs a key."
`get_capabilities` is vocabulary but unwired. This ticket is
the engine side of the setup menu (convergence scripts stay in
RocketIDE, out of scope).

## What

- RED-first: wire `get_capabilities` reporting per-solver
  availability (installed / missing + remedy / cloud-gated +
  key state), PDK/deck install state, and provisionable
  tooling catalogue entries for the checkbox menu.
- Provision actions behind the menu reuse install/provision
  machinery (B10/PROV); cloud entries stay BYOC opt-in per
  I32 and never activate without CLOUD-AUTH-supplied keys.
- Degradation posture: everything reports honestly; nothing
  installs or phones home without an explicit user action.

## Acceptance

- Fresh machine: capabilities report names every missing tool
  with its remedy; menu catalogue lists all provisionables
  with state; installing one checkbox item flips exactly its
  state; cloud entries show gated without keys and never
  attempt network.
- Full suite + gate + scenarios green.
