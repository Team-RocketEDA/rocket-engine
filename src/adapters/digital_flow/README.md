# LibreLane digital-flow adapter

LibrelaneFlowAdapter serves run_digital_flow with the librelane deck tool. It stages project RTL and flow configuration, runs the Classic flow under a timeout, and parses stage output into findings, measurements, and artifact references for the D11–D27 gates.

The adapter requires the pinned LibreLane 3.0.17 distribution and a compatible PDK root. Tool resolution uses PATH or the job tool_dir; version mismatch refuses. When supplied, BwrapRunner confines the flow with tool and PDK roots read-only and the work directory writable.

Hermetic qualification covers synthetic run trees, parse outcomes, timeouts, and failure gates. The live SERV RTL-to-GDS proof is currently blocked because this environment lacks the pinned distribution and PDK root. Adapter registration is not a claim that the full flow has passed live qualification.

See the [DIGITAL-FLOW report](../../../docs/work/DIGITAL-FLOW/report.md) and [provision plan](../../../docs/provision-plan.md).
