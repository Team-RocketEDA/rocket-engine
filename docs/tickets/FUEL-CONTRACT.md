# FUEL-CONTRACT: Pin fuel mcp-stub to the engine contract

*Status: Backlog · Depends: API-GEN · Size: S · Roadmap: codesign*

## Why

rocket_fuel develops against `mcp-stub/`, a mock engine with
its own shapes and tests. Every sprint the stub and the real
engine evolve separately, fuel codes against a fantasy engine
— the contract-first FAIL case (mock/production shape
mismatch). This is the first codesign commit and should land
before features pile on either side. It also joins the audit
trails: fuel's `.rocket/audit.jsonl` and the engine event log
must share request/run ids.

## What

- Consume the engine's generated contract artifact
  (API-GEN schemas) from the stub: generated or verified
  shapes, never hand-copied. Pin mechanism + version handshake
  documented (stale stub fails loudly, not silently).
- Shared request/run id plumbing so both audit trails join.
- A contract-drift check runnable from either repo (stub
  shapes validate against engine schemas).

## Acceptance

- Stub regenerates/revalidates clean against current engine
  schemas; a deliberately skewed stub field fails the drift
  check naming the field; one E2E submit→run_job round trip
  through stub-shaped calls matches engine behavior.
