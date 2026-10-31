# AGENTS.md — contributor contract for rocket-engine (human and agent)

## The rule

Every adapter operation/query handler carries a Google-style
docstring: a one-line summary, then `Args:` naming every
parameter, `Returns:` when it returns a value, `Raises:` when it
can raise, and a `Caution:` line where the endpoint can bite.
Constructor parameters live in the class docstring under `Args:`.
New endpoints ship documented from day one — no undocumented
handlers land, even behind a feature flag.

## Why: docstrings are the contract (ADR-003)

[ADR-003](docs/adr/003-docstring-generated-api-contract.md) makes
docstrings the API contract source. One text feeds three
consumers — the human API reference, per-operation JSON Schemas
(IDE types, fuel stubs), and MCP tool descriptions plus help —
so drift becomes structurally impossible. `docs/engine-api.md`
endpoint prose migrates into docstrings; once generated, that
file is output plus a pointer, never hand-edited again.

## The two laws every endpoint doc respects

- **BYOC doctrine ([F12/I32](docs/prd-feedforward.md)).** The hot
  path is local-first; cloud backends are bring-your-own-credential
  opt-in and degradation is a loud typed verdict, never a silent
  fallback or a faked result. If your endpoint touches an
  optional cloud path, document the gate, the key state, and the
  remedy — never a default cloud path.
- **Ledger law ([ADR-002](docs/adr/002-engine-owns-project-ledger.md)).**
  The engine owns the project ledger: every mutation advances the
  revision, stale `expected_revision` fails with
  `revision_conflict` instead of merging, every event carries its
  actor, and verdicts are engine-owned (clients ask for a run and
  read back). Document revision, actor, and verdict behavior; never
  promise a merge, an overwrite, or a client-written result.

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
