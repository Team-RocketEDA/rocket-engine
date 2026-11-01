# KLayout DRC adapter

KlayoutDrcAdapter serves run_drc when deck.tool is klayout. It supports synthetic width/space rules and foundry .lydrc decks. For a foundry deck it runs KLayout in batch mode and parses the report database; for synthetic rules it renders a pya check script and normalizes the findings.

The adapter is registered in Engine. The implementation supports synthetic GDS rules and the .lydrc report-database path. Qualification remains process-specific: readiness depends on the registered PDK deck and installed KLayout; use get_capabilities before relying on a deck.

KLayout can exit zero when violations are present. The verdict comes from parsed output, never the exit code alone. The older Ruby-DSL probe describes a separate batch limitation; XML-macro .lydrc decks use the current batch recipe. See the [KLayout DRC probe](../../../docs/probe-klayout-drc.md).
