# I29-SERVING: own verbatim PDK serving end to end with PRD-name aliases

*Status: Ready · Depends: none · Size: M · Roadmap: design serving (MVP track) · Parent: CANVAS-CST (Step 6c)*

## Why

Today the frontend renders bundled `spectrum`/`waveformSignals` fixtures and
handwritten scalar DTOs because the engine does not serve PDK knowledge
itself. The invariant is that the engine is FULLY capable of serving its PDKs
at every granularity — metadata, cells, layers, timing, models, bulk — so any
consumer (IDE, MCP agent) renders from engine data alone, no fixture
knowledge baked into clients.

Verbatim is non-negotiable: liberty/models/cells are served as the PDK ships
them. PRD-name aliases ride alongside the canonical names so humans and
agents query by the names the PRD uses while the wire always carries the
PDK's own identifiers. This is what makes the IDE a presentation layer over
engine truth.

## What

- Engine-owned serving endpoints over the existing ports covering PDK
  metadata/cells/layers/timing/models at bulk and fine granularity.
- Verbatim PDK payloads + PRD-name aliases on the same records.
- Frontend gap doc updated from "handwritten DTOs + fixtures" to engine
  schemas driven by the serving contract.

## Acceptance

- Serving tests over stdio/HTTP assert verbatim fields plus alias lookup for
  the pinned PDK set (tests pin).
- Any PDK served verbatim round-trips: bulk list → cell record → timing/
  model payload, no fixture source in the path.
- Contract + api_spec regen if surfaces change; suite green.
