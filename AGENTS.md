# AGENTS.md — contributor contract for rocket-engine (human and agent)

## The rule

Every adapter operation/query handler carries a Google-style
docstring: a one-line summary, then `Args:` naming every
parameter, `Returns:` when it returns a value, `Raises:` when it
can raise, and a `Caution:` line where the endpoint can bite.
Constructor parameters live in the class docstring under `Args:`.
New endpoints ship documented from day one — no undocumented
handlers land, even behind a feature flag.

## Contract authority: v1 schema bundle, v0 docstring generation

[ADR-014](docs/adr/014-contract-first-editor-and-tool-api.md) makes
[`contracts/engine-v1.schema.json`](contracts/engine-v1.schema.json) the
canonical v1 boundary bundle. Change its typed shapes and examples before
changing providers/consumers. Derive client types/help/expanded schema with
`.venv/bin/python scripts/check_v1_contract.py --write`, then check without
`--write`. Docstrings explain implementations and must conform to v1.

[ADR-003](docs/adr/003-docstring-generated-api-contract.md) still governs
current v0 handlers: `scripts/api_spec.py` generates their human reference,
per-operation schemas and help. Existing generated `docs/engine-api.md`,
`docs/api-schema.json` and `docs/api-help.json` remain output, never
hand-edited. Their existence does not prove v1 provider conformance.

## Contract map (read these, don't duplicate them)

- Boundary shapes: [`contracts/engine-v1.schema.json`](contracts/engine-v1.schema.json)
  (manifest) + `contracts/v1/schemas/*.schema.json` (modules own each
  definition once) + `contracts/v1/catalog/*.json` (methods, tasks with
  `io`/`presentation`/`delivery`, tools, workflows). Start at
  [`contracts/README.md`](contracts/README.md).
- Generated output (never hand-edit): `contracts/generated/` — expanded
  schema, `client-types.d.ts`, `help.json`, `CATALOG.md`, `EXAMPLES.md`,
  `edit-inputs.schema.json`, `python/` (Pydantic boundary). Regenerate with
  `scripts/check_v1_contract.py --write`, then verify without `--write`.
- The lock: manifest `$defs` must exactly match authored/derived exports;
  the checker enforces it plus fixture validity, task/tool consistency,
  and generated-artifact freshness. `tests/contracts/` pins result shapes
  and the Python boundary; `contracts/conformance/deferred/` stays RED
  by user direction (deferred solvers, not missing definitions).
- Results vocabulary: datasets/views/results/stages/arrays schemas define
  series, tables, matrices, markers, digital, fields, trees. Task results
  are data + short diagnostics; rendering belongs to React.
- Direction: [ADR-014](docs/adr/014-contract-first-editor-and-tool-api.md)
  (v1 design), [ADR-015](docs/adr/015-local-desktop-results-and-roadmap.md)
  (local desktop, results, roadmap), `docs/roadmap.md` (status/thresholds).
- AI-client usage: [`skills/rocket-engine/SKILL.md`](skills/rocket-engine/SKILL.md)
  (discover live v0 vs future v1, I28, permissions, deferred features).

## The laws every endpoint doc respects

- **BYOC doctrine ([F12/I32](docs/prd-feedforward.md)).** The hot
  path is local-first; cloud backends are bring-your-own-credential
  opt-in and degradation is a loud typed verdict, never a silent
  fallback or a faked result. If your endpoint touches an
  optional cloud path, document the gate, the key state, and the
  remedy — never a default cloud path.
- **Ledger law ([ADR-002](docs/adr/002-engine-owns-project-ledger.md)).**
  The engine owns the project ledger: every design transaction advances the
  global snapshot revision; v1 checks per-entity CAS under ADR-008,
  stale entity versions fail with `revision_conflict` instead of merging;
  unrelated entity edits do not conflict merely on the global cursor.
  Every event carries its actor, and verdicts are engine-owned (clients ask for a run and
  read back). Document revision, actor, and verdict behavior; never
  promise a merge, an overwrite, or a client-written result.
- **Run replay law (I28).** Every run preserves the full ingredient
  closure needed to reproduce it: project revision (including
  `canvas.toml` and contained references), PDK id/revision/manifest
  hash, deck, solver/version, seeds, resolved configuration, and
  any other consumed input. Replay must reproduce verdicts,
  findings, and measurements; native output bytes may differ.
  Missing or drifted ingredients fail loudly. Generated configs and
  outputs are exhaust, never design truth. See
  [storage-policy.md](docs/storage-policy.md).

## Shape

```python
def run_widget(widget, timeout_s=30):
    """Run a widget to completion.

    Args:
        widget: Widget to run.
        timeout_s: Timeout in seconds.

    Returns:
        Result mapping with run evidence.

    Raises:
        ValueError: If the timeout is negative.

    Caution: Irreversible once started — there is no cancel.
    """
```

Write `Caution:` where the endpoint bites: side effects,
irreversible actions, scope denials, silent-looking defaults,
and anywhere exit-zero-is-not-PASS applies (the verdict lives in
the payload, never in the exit path).

Solver adapters document their job-dict keys in the class
docstring under `Job keys:` — `name:` or `name (required):`
items with descriptions. The generator parses these exact item
shapes into per-operation JSON Schemas, so keep them plain
(one key per item, continuation lines indented). Envelope-carried
arguments elsewhere use `Request keys:` the same way.

## Generalization law: smokes qualify, projects are the product

A library smoke proves the library imports — that is never
the feature. Every adapter generalizes its library to run on
ANY Rocket project: netlists, sources, geometry, and decks
come from the project through the job, never from hardcoded
fixtures. A new adapter lands with (1) a smoke that qualifies
the solver, and (2) a real op that consumes project inputs —
the smoke alone is an unfinished lane, and its docstring must
say what the follow-up is until it lands.

Adapters are duplex: results flow back into the engine as
structured evidence (measurements, findings, artifacts with
run_ids), and the engine routes each result to its correct
consumer (ledger, frontend effects, agent replies). An
adapter that cannot say where its outputs go is not done.

Fixtures are external and representative, never handrolled
toys: picorv32-class for pure digital, sigma-delta-class
for mixed challenge. Each fixture proves the engine routes
its texture through the right build tools and returns
comparable results with nothing dropped — adapter
unit-tests plus promised-workflow proofs in one. That
routing fidelity over an open project standard is the
product: many tools, one IDE, verification and synthesis
where possible.

## Module-size rule

Keep every engine source module below 3,000 lines. Split a
module by cohesive responsibility before it reaches the limit;
do not grow an existing oversized module. Current decomposition
debt in `src/project/service.py` must be reduced, and
`src/composition.py` should be split before it approaches the
limit. This is an architecture constraint, not a test-only
style preference.

## Environment: install.sh is the only path

`scripts/install.sh --install` provisions everything (UV sync,
pinned deps, in-project `.venv`) — the `npm ci` equivalent.
Agents never handroll environments: no scratch `/tmp` venvs,
no bare `pip install`, no `uv pip` by hand. If the env looks
stale or broken, re-run `install.sh --install` instead of
working around it with shims.

## Enforcement

`scripts/check_docstrings.py` is the gate — same posture as the
no-cloud guard: missing or malformed endpoint docstrings fail
loudly, naming the endpoint. Run it bare to scan the enforced
manifest (`ENFORCED` in the script); pass paths to scan those.
`tests/test_docstrings.py` pins the behavior: a deliberately
broken docstring fails with the endpoint named, a good one
passes, and the enforced tree scans clean.

Slice note (API-GEN-B, done): the manifest enforces the full
`src` tree; `docs/engine-api.md`, `docs/api-schema.json`, and
`docs/api-help.json` are generated by `scripts/api_spec.py` from
these docstrings — never hand-edit them, regenerate with
`--write` (freshness-pinned by `tests/test_api_spec.py`). MCP
tool descriptions read the same handler docstrings, so docs and
agent help cannot drift apart.
