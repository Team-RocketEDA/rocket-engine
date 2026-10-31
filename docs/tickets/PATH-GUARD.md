# PATH-GUARD: Path safety module, RED-first

*Status: Backlog · Depends: STORAGE-REV · Size: M · Roadmap: orch-build-mvp*

## Why

Paths are the trust boundary: user PDK dirs, linked workspaces, and
engine-minted names all flow through one module. EDA tooling is
full of naive string handling (Tcl, shell wrappers, PDK scripts),
so the engine must normalize everything it meets and mint only
boring names itself. Getting this wrong means traversal escapes,
Windows-ambush backslashes, or slug collisions that corrupt the
project store — all silent until catastrophic.

## What

- `to_unix()` normalizer (backslash folding) + containment checks
  (resolve, reject `..` and symlink escapes, root-join only).
- Slug minting: strict charset, **append-only** dedup (`adc-2` →
  `adc-2-1`, never reinterpret user digits), stored
  (display_name, slug) pair, render by lookup.
- Policy: minted-strict, encountered-robust — spaces survived,
  never minted, never rejected.

## Acceptance

- RED-first evil-input tests: spaced paths work, `\` normalized,
  `..`/symlink-escape rejected, `adc`/`adc`/`adc-2`/literal
  `adc (1)` dedup cases all distinct and stable.
- No `shell=True` / string-interpolated commands in new code (argv
  arrays only); grep-verified in review.
