# ADR-005: Fuel owns language and approvals; the engine is caller-blind

*Status: accepted (2026-11-01) | Tickets: [I22-AMEND](../tickets/I22-AMEND.md), [MCP-SCHEMA](../tickets/MCP-SCHEMA.md), [MCP-CONTRACT](../tickets/MCP-CONTRACT.md)*

## Context

Three repos divide the system: fuel (agent), engine
(tools), IDE (rendering). Natural-language understanding
and human-approval dialogs both need a home, and the
engine's `python_execute` gate was human-UI-only by
transport check — which blocks fuel's permission model
(per-tool allow/ask registered at MCP setup in fuel's
`harness/opencode.json`) from ever approving engine work.

## Decision

Fuel owns NL → plans → tool calls and the full approval
UX (per-tool allow/ask/deny at MCP registration). The
engine is caller-blind: MCP, stdio, CLI, and HTTP are
one API; approval arrives as an attestation on the
request from any transport, recorded in the ledger.
I22 is amended: permission is enforced at the client
edge; the engine requires the attestation, never the
transport. The UI is the joining point rendering fuel
chat and engine results side by side over shared
run_id/request_id.

## Alternatives considered

1. **Engine-side approval dialogs.** Rejected: the
   engine is headless with no UI; transport-sniffing
   (`via != ui`) discriminates against legitimate
   localhost clients without adding real security.
2. **No approvals (trust all callers).** Rejected:
   `python_execute` runs arbitrary code; human
   oversight is a product requirement, just placed at
   the edge that has the human.
3. **Per-transport engine policies.** Rejected: N
   policies to keep consistent; the loopback boundary
   (ADR-006) makes them redundant.

## Consequences

- Positive: one permission model (fuel's), one engine
  API, no transport-specific code paths.
- Positive: new transports (HTTP today, broker later)
  inherit the full policy surface free.
- Negative: the engine cannot verify a human clicked;
  a compromised localhost client is fully trusted.
  Mitigation: loopback-only binding (ADR-006), ledger
  records every attestation source for audit.
