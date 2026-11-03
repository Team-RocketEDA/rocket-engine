# SIM-SKY130: ngspice sky130.lib proof + SERV regression

*Status: Backlog · Depends: PDK-STORE, FIXTURE-FETCH · Size: M · Roadmap: orch-build-mvp*

## Why

Simulation against real PDK models is the other half of "works
somewhere": a bandgap sim with the wrong models file is theater.
This slice stands up the ngspice adapter path on `sky130.lib.spice`
and wires the already-live Icarus path to a real core (SERV),
so analog and digital sim both prove against accepted fixtures.

## What

- ngspice adapter live run: bandgap DC, Vref within documented
  tolerance; corners as stretch.
- SERV testbench regression through HdlSimAdapter end-to-end.

## Acceptance

- RED-first: bandgap Vref matches documented value within stated
  tolerance; SERV suite green; model-file mismatch (wrong PDK rev)
  fails loudly, never silently sims.
- Scenario coverage; suite green both configs.
