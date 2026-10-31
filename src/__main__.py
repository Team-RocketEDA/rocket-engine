"""`python -m rocket_engine`: the `rocket-engine` command surface.

Thin entry over the CLI inbound adapter (`adapters.cli`); a
`[project.scripts]` binary alias can point here once packaging
wires it. Exits: 0 execution-ok (even FAIL verdicts), 1 engine
error, 2 usage error.
"""

from .adapters.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
