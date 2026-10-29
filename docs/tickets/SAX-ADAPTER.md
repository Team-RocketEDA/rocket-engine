# SAX-ADAPTER: Photonic sim solver via SAX

*Status: Backlog · Depends: none · Size: M · Roadmap: orch-build-mvp*

## Why

P is the only D/A/P/M flow with no engine sim path at all — SAX is
decided (pip `photonic`) but nothing calls it. Without this
adapter, photonic validation can only check layout geometry, never
whether a circuit *behaves* (transmission, resonances). SAX is pure
Python + pip, so this is the cheapest solver slice available.

## What

- ToolAdapter running SAX S-parameter circuit sims (MZI/ring
  reference circuits first), parsed into the
  violations/measurements shape with file/line-style locations
  where meaningful.
- Deck/tool routing per F8 (photonic sim operation + tool select).

## Acceptance

- RED-first: reference MZI reproduces documented transmission
  within tolerance; malformed circuit errors loudly with location.
- Suite green both configs (skip-loudly where SAX uninstalled).
