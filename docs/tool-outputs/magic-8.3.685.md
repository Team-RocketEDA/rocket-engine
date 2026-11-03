# magic 8.3.685 + scmos 8.2.8 — DRC batch output (run_drc)

Version provenance: verified against magic 8.3.685 + scmos tech 8.2.8
per `src/adapters/drc/magic.py:1-10`. No golden committed here; the
grammar below is transcribed from the adapter's verified protocol
note plus its parse regexes.

## Report inventory

One mode only: batch DRC over a loaded `.mag` cell
(`src/adapters/drc/magic.py:182-230`). Native output is
`{exit_code, stdout, stderr, tech, cell}`; the verdict lives in
stdout text. Machine-readable contract: the total line plus the
per-area blocks. Everything else on stdout (tech banner, load
echo) is human log.

## Grammar

Count line (`src/adapters/drc/magic.py:27`):

```ebnf
"Total DRC errors found: " INT
```

Per-area block (`src/adapters/drc/magic.py:28`), one per error area
`1..total`, consumed by the detail pass (`magic.py:202-216`):

```ebnf
"Error area #" INT ":\n" RULE_TEXT "\n" INT " " INT " " INT " " INT
```

Coordinates are lambda-unit bbox ints `[x0, y0, x1, y1]`
(`magic.py:252-259`). Parsed result: `{total, violations[]}` with
`area`, `rule`, `bbox`.

## Exit states

- Exit 0 clean AND exit 0 broken: magic exits 0 for unknown techs
  and broken cells alike (`magic.py:6-9`). The verdict always comes
  from parsed output, never the exit code.
- Missing total line (crash, truncated write, tech failed to load):
  `parse` raises `runner_unavailable` (`magic.py:246-251`) — never
  a silent clean.
- Timeout: the job budget kills the run; `runner_unavailable`
  (`magic.py:284-287`).

## Version sensitivity

Stable: total line, `Error area #N` block shape. Incidental: tech
banner text, rule message wording (rules come from the tech file,
not magic).

## Out of scope

Interactive `drc` subcommands beyond `check`/`catchup`/`count`/
`find`/`why`; `.mag` cell schema; extraction output (see the
magic-extract note in a later wave).

## Fixtures

- `tests/adapters/fixtures/drc/good.mag` (clean).
- `tests/adapters/fixtures/drc/bad_spacing.mag` (rule #7.2).
- `tests/adapters/fixtures/drc/bad_width.mag` (rule #7.1).
