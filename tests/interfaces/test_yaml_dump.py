"""RUAMEL-DUMPER — fresh ruamel dumpers for YAML writes.

RED-first: this suite imports
`rocket_engine.interfaces.yaml_dump`, which does not exist yet.
Valid RED = collection error on that import; valid GREEN = every
test below passes with the module in place and zero edits to any
tracked file.

The contract under test: a failed ruamel dump poisons that
dumper instance (later dumps emit empty text forever), so every
YAML write on the Engine/ProjectService path dumps through a
fresh instance per call. Failures raise loudly; later writes are
unaffected; distinct payloads keep distinct identities.
"""

import io

import pytest
from ruamel.yaml import YAML

from rocket_engine.interfaces.yaml_dump import dump_yaml_text

_yaml = YAML(typ="safe")


def _fresh(data):
    buf = io.StringIO()
    YAML(typ="safe").dump(data, buf)
    return buf.getvalue()


def test_dump_matches_fresh_ruamel_bytes():
    payload = {
        "operation": "write_doc",
        "arguments": {"path": "a.txt", "content": "hi"},
    }
    assert dump_yaml_text(payload) == _fresh(payload)
    findings = {"findings": [{"severity": "error", "rule": "r1"}]}
    assert dump_yaml_text(findings) == _fresh(findings)
    assert dump_yaml_text([]) == _fresh([])


def test_failed_dump_does_not_poison_later_dumps():
    with pytest.raises(Exception):
        dump_yaml_text({"bad": object()})
    first = dump_yaml_text(
        {"operation": "write_doc", "arguments": {"path": "a"}}
    )
    second = dump_yaml_text(
        {"operation": "write_doc", "arguments": {"path": "b"}}
    )
    assert first != ""
    assert second != ""
    assert first != second
    assert _yaml.load(first) == {
        "operation": "write_doc", "arguments": {"path": "a"},
    }


def test_never_emits_empty_text():
    payloads = [
        {"operation": "write_doc", "arguments": {"path": "a"}},
        {"findings": []},
        {"a": 1},
        {},
        [],
        [1, 2],
    ]
    for payload in payloads:
        assert dump_yaml_text(payload) != "", payload


def test_round_trip_preserves_data():
    payloads = [
        {"operation": "write_doc",
         "arguments": {"path": "a.txt", "content": "hi"}},
        {"findings": [{"severity": "error", "rule": "r1",
                        "message": "m", "location": {}}]},
        [],
        {"project_id": "demo", "current_revision": "p13",
         "requests": {}},
    ]
    for payload in payloads:
        assert _yaml.load(dump_yaml_text(payload)) == payload


def test_distinct_payloads_have_distinct_identities():
    first = dump_yaml_text({"path": "a.txt", "content": "hi"})
    second = dump_yaml_text({"path": "a.txt", "content": "other"})
    assert first != second
