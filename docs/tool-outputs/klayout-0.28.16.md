# klayout 0.28.16 — DRC reports (run_drc, synthetic + deck modes)

Version provenance: verified against KLayout 0.28.16 per
`src/adapters/drc/klayout.py:1-13`. Grammars transcribed from the
adapter's regexes and report parser; canned deck XML in
`tests/test_coverage_wave1.py` is transcribed, not a live run.

## Report inventory

Two modes (`klayout.py:182-206`):

- Synthetic: the adapter renders a `pya` check script
  (`klayout.py:64-86`) and runs `klayout -b -r`; stdout carries
  `VIOL`/`TOTAL` lines. Machine-readable.
- Deck: a foundry `.lydrc` (e.g. `sky130A.lydrc`) runs via
  `klayout -b -rd input=<gds> -rd report=<lyrdb> -r <deck>`
  (`klayout.py:296-324`); the `.lyrdb` report XML is the
  machine-readable contract. `report_file` + `report_xml` ride the
  native output.

## Grammar

Synthetic stdout (`klayout.py:56-61`):

```ebnf
"VIOL rule=" RULE " bbox_um=" NUM "," NUM "," NUM "," NUM
"TOTAL " INT
```

`RULE` has no spaces; coordinates are metric `bbox_um`
(`klayout.py:376-380`). Deck XML (`klayout.py:140-179`):
`categories/category/{name, description}` plus
`items/item/{category, multiplicity, values/value}`; the rule is
the item category (quotes stripped), the message appends the
joined values, `bbox_um` is parsed from value text when it holds
at least four numbers (even count), else omitted.

## Exit states

- KLayout exits 0 regardless (`klayout.py:11-12`); the verdict
  always comes from parsed output, never the exit code.
- Deck run with no report file: `runner_unavailable`
  (`klayout.py:311-315`). Non-XML report: `runner_unavailable`
  (`klayout.py:141-146`). Synthetic stdout with no TOTAL line:
  `runner_unavailable` (`klayout.py:371-375`).
- Timeout: `runner_unavailable` (`klayout.py:393-399`).

## Version sensitivity

Stable: `TOTAL`/`VIOL` line shape (adapter-rendered, not
KLayout's), `.lyrdb` XML schema (KLayout report-database format).
Incidental: deck rule names and messages (deck-defined);
synthetic rule labels embed the caller-supplied name.

## Out of scope

`.lydrc` deck DSL authoring; GDS read diagnostics; RDB content
beyond category/message/geometry.

## Fixtures

- `tests/adapters/fixtures/drc_kl/good.gds` (clean).
- `tests/adapters/fixtures/drc_kl/bad_space.gds`.
- `tests/adapters/fixtures/drc_kl/bad_width.gds`.
- `tests/adapters/fixtures/drc_kl/make_cells.py` (cell generator).
