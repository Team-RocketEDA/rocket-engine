# ENGINE-SETUP: Vivado-style setup surface (capability + provision)

*Status: Done · Relates: B10, PROV, CLOUD-AUTH · Size: M · Roadmap: convergence*

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

## Field notes (2026-10-31, GREEN-the-tests)

Commits `95228aa` (RED: 13 tests), `b32fddf` (GREEN:
surface + wiring + regen), `82e98c6` (order-independent
cloud-import guard — full suite caught a global-`sys.modules`
assert polluted by test_meow; replaced with a report-diff
assert). `.venv` mirror kept: `diff -rq` shows only
`__pycache__`.

Landed:

- `src/interfaces/setup_catalogue.yaml` (new, versioned): 12
  provision units — digital-bundle (7 oss-cad-suite
  binaries), ngspice, netgen (banner-verified), magic,
  klayout, bwrap, sax (photonic group), cvc/openroad
  (`provisionable: false`, no recipe yet), pdk-sky130A (4
  canonical deck rels from scenarios.py), cloud-tidy3d +
  cloud-gdsfactory-plus. Every entry carries label, remedy,
  and recipe ref (install.sh mode / provision-plan /
  owning ticket).
- `src/interfaces/setup.py` (new): loader + install-state
  detection + `report_capabilities`. Detection reuses
  adapter oracles (shutil.which semantics, LVS
  `resolve_netgen` banner denylist, sax find_spec, store
  list/resolve_deck). Netgen impostor surfaces the
  NGSPICE-LIVE remedy; PDK presence is manifest validity,
  decks verify per-deck hashes; drifted decks report
  `drifted`, never silently missing.
- `Engine.capabilities` + submit wiring (composition.py):
  per-operation readiness in the appendix vocabulary —
  `ready` (some tool resolves, or Engine-served like CRUD /
  run_job), `blocked` (reason + missing + remedy),
  `unsupported` (no solver registered). Per-tool rows carry
  `adapter.capabilities(target)` verbatim. Query is
  read-only: never creates the store skeleton, never
  attempts network; cloud rows are static gated /
  key_state missing (CLOUD-AUTH Backlog — no keys can
  exist). A registered solver without a detection spec
  fails loud (`unknown_solver`), so new solvers cannot
  slip into the menu undetected.
- Contract seam: `QUERY_ENGINE_METHODS` in composition.py;
  api_spec.py + MCP `describe_tool` read Engine handler
  docstrings through it (same double-use as
  QUERY_METHODS). Regenerated engine-api.md, api-schema.json,
  api-help.json, contract.json (freshness-pinned).

Proofs (all observed this session):

- New: 14/14 `tests/interfaces/test_setup.py`, incl.
  fresh-machine honesty (bare PATH + amputated socket +
  no sax: every missing tool named with its remedy),
  single-tool and single-PDK flip-exactly-one tests,
  netgen-impostor trap, sax-remedy pin, cloud
  gated-without-keys + no-network, adapter passthrough,
  Engine-served ready, read-without-creating-store.
- Neighbors: 60/60 (pdk_store, api_spec, contract,
  check_contract, mcp_server, docstrings, no_cloud);
  `api_spec --check`, `contract --check`,
  `check_docstrings`, `check_no_cloud` all clean;
  scenarios 22/22 on tools PATH + live store.
- Live (`ROCKETEDA_HOME=/tmp/rocketeda-live`): 7 solver
  ops ready, sky130A + 4 decks installed with hashes,
  cvc/openroad missing, clouds gated.
- Full suite: 840 passed / 33 skipped / 0 failed
  (live-tool env, 27 min; first run caught the
  order-dependent assert above, fixed and re-run green).

Acceptance check: fresh-machine report names every
missing tool with remedy; catalogue lists all 12 units
with state; one install flips exactly its row (tool and
PDK proven); cloud gated without keys, zero network
(socket amputated in-test); suite + gates + scenarios
green. B10/PROV/CLOUD-AUTH untouched (cited, not
duplicated).
