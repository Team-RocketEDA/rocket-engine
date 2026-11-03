# API-V1-PYTHON: Finish and lock Pydantic boundary generation

*Status: Done · Design: ADR-014 · Created: 2026-11-01*

Depends: API-V1-CONTRACT, API-V1-RESULTS. Read contracts/README.md. Contracts/tooling only; no provider/runtime changes.

Finish scripts/schema_models.py boundary generator (strict wire validation, nonfinite rejection, explicit-null-vs-absent, forward refs), hook render_python into check_v1_contract render with importlib-safe sibling import, regenerate contracts/generated/python, lock via tests/contracts/test_python_models.py GREEN + freshness check. Boundary types only; domain logic stays framework-independent.

*Audit 2026-11-02 (T-26): flipped to Done on landing-commit + code evidence per RULING-06 (was Ready/Backlog in-file, Done on board).*
