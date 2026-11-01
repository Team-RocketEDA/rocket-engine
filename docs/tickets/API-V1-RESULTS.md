# API-V1-RESULTS: Freeze typed result/renderer contracts and task io classification

*Status: Ready · Design: ADR-014, ADR-015 · Created: 2026-11-01*

Depends: API-V1-CONTRACT. Read contracts/README.md and docs/adr/015-local-desktop-results-and-roadmap.md. Contracts only; no provider/runtime changes.

Classify every v1 task result into neutral data/rendering types (series/traces, tables, trees, markers, digital, matrices, fields). LibreLane stage/timing/area/check summaries are tables + stage trees. Results carry data + short diagnostics only; help owns explanations; verbose tool output streams to the terminal. Never force heatmaps onto spectrum-only data. Add TreeDataset/TreeView, Dataset/DataView unions, TaskContract ports, per-task io/presentation/delivery metadata (FPGA off_mvp, field/thermal/device post_mvp). Lock via manifest exports + checker + tests/contracts/test_result_schema.py GREEN.
