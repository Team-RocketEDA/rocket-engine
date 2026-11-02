Problem: Engine.submit admits, drains, and merges completion inline (composition.py:395-406,683,690) — the run_id arrives with the verdict already attached. No deferred handle exists to watch.
Expected-per: frontend-tooling-spec.md:117 (prompt ack without verdict) + :158-162 (job_queued/started/progress/finished events). Audit MC-02, X-07.
Actual-per: submit always blocks to completion; none of the lifecycle events are emitted.
Ruling: RULING-02 (contract wins) — implement prompt-ack/deferred-handle mode + lifecycle events. Note X-07: MCP-CONTRACT's "run controls + watch/query" reading is equally unmet (no watch exists) until this + PUSH-EVENTS land.
