# API-GENERALIZE: Frontend protocol — queue, microcommits, catalogue, symbols

*Status: Backlog · Depends: none · Size: L (phased) · Roadmap: orch-build-mvp*

## Why

The IDE bolts onto engine duplex channels (STDIO first) as pure
presentation: engine owns truth, frontend owns pixels. Three gaps
block pick-and-place/drag-and-drop at KiCad comfort today: (1) no
durable never-drop request path under UI spam, (2) no component
catalogue query + place op (frontend cannot import gdsfactory),
(3) no symbol serving (PDK has 685 xschem `.sym`, zero SVGs).
Frontend/engine disagreement is catastrophic-class: every gap
below closes a divergence vector.

## What (phased slices)

1. Durable request log + worker pool: append-first per-project
   log, `request_id` dedupe, in-order drain, one ack per request,
   boot replay. Refusal/backpressure shape, never silent drop.
2. Microcommit delta format: coalesced frontend edits (move/add/
   wire) → one revision bump via existing hash machinery.
3. Catalogue index query: versioned cell list (cell, PDK, ports,
   default params) introspected from upstream, plus
   `place_cell` durable project mutation.
4. Raw asset serving (I29): serve PDK bytes verbatim at every
   granularity — single `.sym` as-is, metadata, bulk. No
   conversion, no rendering; parsing and styling stay
   frontend-side. Hash-checked identity on every serve.

## Acceptance

- Spam test: N rapid placement edits → all N acked exactly once,
  frontend revision equals engine revision, zero divergence.
- Catalogue round-trip: list → place → simulate → verdict,
  all through the duplex channel, no console needed.
- Kill-and-reboot mid-queue: log replays, every request still
  acked exactly once.

## Revision (2026-10-30): partially superseded, narrowed

- Slice 1 (durable log half) → LEDGER-DURABLE. The worker
  pool half (in-order drain, backpressure/refusal shape,
  boot replay) REMAINS here.
- Slice 2 (microcommits) → CRUD-API (`apply_mutations` batch).
- Slice 3 (catalogue index + `place_cell`) REMAINS here —
  no other ticket covers the component catalogue.
- Slice 4 (raw asset serving, I29) REMAINS here — no other
  ticket covers verbatim PDK byte serving.
- New scope: pool/drain/backpressure + catalogue/place_cell
  + raw serving. Kill-and-reboot acceptance stays (needs
  pool, not just log).
