# API-V1-PYTHON: Finish and lock Pydantic boundary generation

*Status: Ready · Design: ADR-014 · Created: 2026-11-01*

Depends: API-V1-CONTRACT, API-V1-RESULTS. Read contracts/README.md. Contracts/tooling only; no provider/runtime changes.

Finish scripts/schema_models.py boundary generator (strict wire validation, nonfinite rejection, explicit-null-vs-absent, forward refs), hook render_python into check_v1_contract render with importlib-safe sibling import, regenerate contracts/generated/python, lock via tests/contracts/test_python_models.py GREEN + freshness check. Boundary types only; domain logic stays framework-independent.
