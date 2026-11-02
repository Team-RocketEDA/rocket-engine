# I22-AMEND: approvals enforced at the client edge

*Status: Done · Depends: user I22 ruling · Size: S ·
Roadmap: caller-blind API (MVP track)*

## Why

Fuel registers per-tool permissions at MCP setup
(`rocket_* allow` baseline, `rocket_apply_revision` /
`rocket_generate_views` / `rocket_export_project` ask —
fuel `harness/opencode.json`). The human approves in the
client; the engine must honor an approval arriving over
MCP the same as one from the IDE. Today it cannot:
`resolve_python_approval` raises `approval_forbidden`
for any non-UI transport
(`src/execution/python_exec.py:1361`), which contradicts
the caller-blind API. I22 as written ("python_execute
always with permission") assumed engine-side UI
enforcement and needs explicit amendment, not silent
reinterpretation.

## What

- Amend I22: permission is enforced at the client edge;
  the engine requires the approval attestation on the
  request and records it in the ledger.
- Replace the `via != ui` transport check with
  attestation handling: any transport may present an
  approval; missing attestation still refuses loud.
- Trust boundary is the localhost edge (all transports
  local); document that the engine cannot and does not
  verify the human click.
- Contract + api_spec regen; full suite + gate green.

## Acceptance

- `python_execute` over MCP with a fuel-issued
  attestation executes; without attestation it refuses
  with a structured code naming the remedy.
- Ledger records the attestation source per execution.
- No transport-discriminating code paths remain in the
  approval flow.

*RULING-04 (2026-11-02): I22 RULED — trusted-local deployment, NO cloud hosting ever. All clients user-controlled; permission stays user-side (incl. MCP); NO auth in-engine (prune auth.py per HTTP-HARDEN). Supersedes UI-only, attestation, and two-tier positions for the engine. Sandbox choice delegated to BWRAP-STUDY.*
