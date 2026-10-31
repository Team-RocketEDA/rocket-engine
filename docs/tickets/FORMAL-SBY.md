# FORMAL-SBY: run_formal via sby (bounded proof, honestly reported)

*Status: Ready · Depends: PROV (oss-cad-suite tarball) · Size: M ·
Roadmap: to-GDS lane (MVP track, PRD tech-stack formal row)*

## Why

stages.py step D08 requires clock/reset and formal-property
checks with entrypoint `run_formal` — which no adapter
serves. Simulation can only show the presence of bugs;
the PRD promises proof/cover/equivalence with the scope
stated honestly (proven vs bounded vs unknown vs timeout).
sby inside the pinned oss-cad-suite is the vehicle, with
its bundled SMT engines (Z3 et al.) per the inspected
release contents.

## What

- RED-first: `run_formal` ToolAdapter driving pinned `sby`;
  verdicts carry scope explicitly (proven/bounded/unknown/
  timeout) plus assumptions and counterexamples — never a
  bare PASS.
- deck.tool `sby`; missing binary → loud
  `missing_dependency` naming the PROV bundle.
- Counterexample fixtures: a known-bad property fails with
  a trace the agent can consume; timeout fixtures report
  timeout, never hang the engine (bounded, cancellable).

## Acceptance

- Formal check on a SERV property returns a scoped
  verdict with evidence; unknown/timeout paths green.
- Contract + api_spec regen; full suite + gate green.
