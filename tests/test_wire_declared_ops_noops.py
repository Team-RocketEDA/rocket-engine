"""WIRE-DECLARED-OPS no-store pins: parse_report/get_status are no-ops.

Neither op has a backing store, so neither is wired — and no
store is invented for them. `get_job_status` covers the
get_status read (per-run state by id) and `get_check_results`
covers the verdict read; parse_report has no equivalent because
adapter parses never persist outside their run. These pins fail
if anyone wires the phantom ops or removes the covering reads.
"""

COVERING = ("get_job_status", "get_check_results", "get_events_since")


def test_phantom_ops_stay_unwired():
    from rocket_engine.interfaces import vocabulary

    wired = set(vocabulary.OPERATIONS) | set(vocabulary.QUERIES)
    assert "parse_report" not in wired
    assert "get_status" not in wired


def test_covering_reads_stay_wired():
    from rocket_engine.interfaces import vocabulary

    assert set(COVERING) <= set(vocabulary.QUERIES)


def test_engine_serves_the_covering_reads():
    from rocket_engine.composition import Engine

    assert callable(Engine.job_status)
    assert callable(Engine.check_results)
