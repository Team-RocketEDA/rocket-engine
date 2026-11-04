"""Run-dir machine-file readout for the digital_flow gates.

LibreLane writes one state_out.json plus metrics.json/metrics.csv
per step dir (docs/tools/librelane.md section 2). The D22/D25/D26/D27
verdicts read those machine files only: report text is evidence, never
the verdict. Steps without machine files fail loudly (key drift means
an upstream step change, never a silent pass).
"""

import csv
import json
from pathlib import Path

STATE_FILES = ("state_out.json", "metrics.json", "metrics.csv")

# Signoff JSON reports the live 3.0.17 run writes under step dirs
# (docs/tools/librelane.md section 6): exact filenames, never globs.
SIGNOFF_DRC_NAME = "drc.klayout.json"
SIGNOFF_LVS_NAME = "lvs.netgen.json"

STA_WS_KEYS = (
    "timing__setup__ws",
    "timing__hold__ws",
    "wns_setup",
    "wns_hold",
)
STA_TNS_KEYS = (
    "timing__setup__tns",
    "timing__hold__tns",
    "tns_setup",
    "tns_hold",
)
DRC_KEYS = ("drc__violations", "drc_total", "violations")
# LibreLane 3.x signoff counts (exact names, no corner suffix).
DRC_ERROR_KEYS = ("magic__drc_error__count", "klayout__drc_error__count")
LVS_KEYS = ("lvs__match", "lvs_match", "match")
# LibreLane 3.x LVS mismatch counts (0 means match).
LVS_MISMATCH_KEYS = (
    "design__lvs_unmatched_device__count",
    "design__lvs_unmatched_net__count",
    "design__lvs_unmatched_pin__count",
)
EQY_KEYS = ("equiv__equivalent", "equivalent", "equiv_pass", "equiv__proven")


def read_metrics(step_dir):
    """Merge one step dir's machine metrics into a flat mapping.

    Args:
        step_dir: Step directory path holding state_out.json,
            metrics.json, or metrics.csv.

    Returns:
        (metrics, files): flat metric mapping (later files fill
            missing keys only) plus the state file paths read.
    """
    metrics = {}
    files = []
    state = Path(step_dir) / "state_out.json"
    raw = _read_json(state)
    if isinstance(raw, dict):
        for key, value in raw.get("metrics", raw).items():
            metrics.setdefault(str(key), value)
        files.append(str(state))
    snap = Path(step_dir) / "metrics.json"
    raw = _read_json(snap)
    if isinstance(raw, dict):
        for key, value in raw.items():
            metrics.setdefault(str(key), value)
        files.append(str(snap))
    table = Path(step_dir) / "metrics.csv"
    for key, value in _read_csv(table).items():
        metrics.setdefault(key, value)
    if metrics:
        files.append(str(table)) if table.is_file() else None
    return metrics, [path for path in files if Path(path).is_file()]


def read_run_states(run_dir):
    """Read machine metrics plus state views for every step dir.

    Args:
        run_dir: runs/<tag>/ dir path, or None when the flow never
            created it.

    Returns:
        Step-dir name to {"metrics": mapping, "files": paths,
            "views": paths}.
    """
    states = {}
    if run_dir is None or not Path(run_dir).is_dir():
        return states
    for child in sorted(Path(run_dir).iterdir()):
        if child.is_dir():
            metrics, files = read_metrics(child)
            states[child.name] = {
                "metrics": metrics,
                "files": files,
                "views": read_views(child),
            }
    return states


def read_views(step_dir):
    """Read state view paths from one step dir's state_out.json.

    LibreLane State dumps its DesignFormat views as path-valued
    entries alongside the ``metrics`` mapping (docs/tools/librelane.md
    section 2): a top-level string is one view path, a list holds
    several, a mapping holds named ones. Only paths resolving to real
    files count — dangling entries are dropped, never failed on.

    Args:
        step_dir: Step directory path holding state_out.json.

    Returns:
        Sorted existing view file paths (strings).
    """
    raw = _read_json(Path(step_dir) / "state_out.json")
    if not isinstance(raw, dict):
        return []
    candidates = []
    for key, value in raw.items():
        if key == "metrics":
            continue
        if isinstance(value, str):
            candidates.append(value)
        elif isinstance(value, list):
            candidates.extend(item for item in value if isinstance(item, str))
        elif isinstance(value, dict):
            candidates.extend(
                item for item in value.values() if isinstance(item, str)
            )
    found = []
    for candidate in candidates:
        path = Path(candidate)
        if not path.is_absolute():
            path = Path(step_dir) / candidate
        if path.is_file():
            found.append(str(path))
    return sorted(set(found))


def _signoff_file(run_dir, name):
    """First exact-name signoff report under a run root, or None.

    Args:
        run_dir: runs/<tag>/ dir path, or None when the flow never
            created it.
        name: Exact report filename (no globs, no substrings).

    Returns:
        Sorted-first matching path, or None.
    """
    if run_dir is None or not Path(run_dir).is_dir():
        return None
    matches = sorted(
        path
        for path in Path(run_dir).rglob(name)
        if path.is_file() and path.name == name
    )
    return str(matches[0]) if matches else None


def signoff_drc_total(run_dir):
    """Read the signoff DRC total from drc.klayout.json.

    The live 3.0.17 run writes ``{rule: count, ..., "total": N}``
    (docs/tools/librelane.md section 6); only that exact ``total``
    key judges — per-rule counts are evidence, never the verdict.

    Args:
        run_dir: runs/<tag>/ dir path, or None when the flow never
            created it.

    Returns:
        (total, path): integer total plus the report path, or
            (None, None) when the report or its total is absent.
    """
    path = _signoff_file(run_dir, SIGNOFF_DRC_NAME)
    raw = _read_json(path) if path is not None else None
    if not isinstance(raw, dict):
        return None, None
    total = number(raw.get("total"))
    if total is None:
        return None, None
    return int(total), path


def signoff_lvs_report(run_dir):
    """Locate the signoff lvs.netgen.json report under a run root.

    The per-element pin-comparison list has no pinned pass shape, so
    the report rides as evidence only — it never judges the gate.

    Args:
        run_dir: runs/<tag>/ dir path, or None when the flow never
            created it.

    Returns:
        Report path, or None when absent.
    """
    return _signoff_file(run_dir, SIGNOFF_LVS_NAME)


def lookup(metrics, *names):
    """Case-insensitive exact lookup over metric keys.

    Args:
        metrics: Flat metric mapping from read_metrics.
        names: Candidate key names in priority order.

    Returns:
        (key, value) for the first candidate present, else
            (None, None).
    """
    lowered = {str(key).lower(): key for key in metrics}
    for name in names:
        if name.lower() in lowered:
            key = lowered[name.lower()]
            return key, metrics[key]
    return None, None


def number(value):
    """Coerce one metric value to float, or None when not numeric.

    Args:
        value: Raw metric value (number, numeric string, or bool).

    Returns:
        Float value, or None when the value carries no number.
    """
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def boolean(value):
    """Coerce one metric value to bool, or None when unclear.

    Accepts 1/0, true/false, yes/no, pass/fail, and match/mismatch
    spellings (case-insensitive).

    Args:
        value: Raw metric value.

    Returns:
        True, False, or None when the value is not a verdict shape.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        word = value.strip().lower()
        if word in ("1", "true", "yes", "pass", "passed", "match",
                     "equivalent", "proven"):
            return True
        if word in ("0", "false", "no", "fail", "failed", "mismatch",
                     "inequivalent", "unproven"):
            return False
    return None


def _prefixed_numerals(metrics, *bases):
    """Collect numeric values for exact or corner-suffixed keys.

    LibreLane 3.x writes corner-suffixed keys
    (`timing__setup__ws__corner:nom_tt_025C_1v80`); older steps
    write the bare base name. Both are machine evidence.

    Args:
        metrics: Flat metric mapping.
        bases: Base key names to accept exactly or with a
            `__corner:*` (or any `__`-suffixed) extension.

    Returns:
        (key, numeral) pairs for every matching numeric entry.
    """
    found = []
    for key, value in metrics.items():
        for base in bases:
            if key == base or key.startswith(base + "__"):
                numeral = number(value)
                if numeral is not None:
                    found.append((str(key), numeral))
                break
    return found


def sta_verdict(metrics):
    """Judge post-PNR timing from STA machine metrics.

    Worst slack wins across corners: any negative corner slack
    fails the gate.

    Args:
        metrics: Merged STA step metrics (ws/tns slack keys,
            bare or corner-suffixed).

    Returns:
        (ok, detail): ok True/False, or None when no STA metric key
            is present; detail names the deciding key or the keys
            seen.
    """
    slacks = _prefixed_numerals(metrics, *(STA_WS_KEYS + STA_TNS_KEYS))
    if not slacks:
        return None, f"keys present: {sorted(metrics) or 'none'}"
    worst = min(slacks, key=lambda item: item[1])
    if worst[1] < 0:
        return False, f"timing violated ({worst[0]}={worst[1]})"
    return True, f"worst slack {worst[1]} ns ({worst[0]})"


def drc_verdict(metrics):
    """Judge foundry-deck DRC from DRC machine metrics.

    Args:
        metrics: Merged DRC step metrics (violation-count keys).

    Returns:
        (ok, detail, total): total None when no DRC count key is
            present; detail names the deciding key or keys seen.
    """
    seen = []
    for name in DRC_KEYS + DRC_ERROR_KEYS:
        key, value = lookup(metrics, name)
        numeral = number(value) if key is not None else None
        if numeral is not None:
            seen.append((key, int(numeral)))
    if seen:
        total = sum(count for _, count in seen)
        names = "+".join(key for key, _ in seen)
        if total > 0:
            return False, f"{total} DRC violations ({names})", total
        return True, f"DRC total 0 ({names})", total
    return None, f"keys present: {sorted(metrics) or 'none'}", None


def lvs_verdict(metrics):
    """Judge LVS from LVS machine metrics.

    Args:
        metrics: Merged LVS step metrics (match keys).

    Returns:
        (ok, detail, match): match None when no LVS match key is
            present; detail names the deciding key or keys seen.
    """
    seen = []
    for name in LVS_MISMATCH_KEYS:
        key, value = lookup(metrics, name)
        numeral = number(value) if key is not None else None
        if numeral is not None:
            mismatched = int(numeral)
            seen.append((key, mismatched))
            if mismatched > 0:
                return False, f"{mismatched} unmatched ({key})", False
    if seen:
        return True, f"netlists match ({seen[0][0]}=0)", True
    for name in LVS_KEYS:
        key, value = lookup(metrics, name)
        verdict = boolean(value) if key is not None else None
        if verdict is not None:
            if verdict:
                return True, f"netlists match ({key})", True
            return False, f"netlists do not match ({key})", False
    return None, f"keys present: {sorted(metrics) or 'none'}", None


def equiv_verdict(metrics):
    """Judge equivalence from EQY machine metrics.

    Args:
        metrics: Merged equivalence step metrics (proven keys).

    Returns:
        (ok, detail, proven): proven None when no equivalence key
            is present; detail names the deciding key or keys seen.
    """
    for name in EQY_KEYS:
        key, value = lookup(metrics, name)
        verdict = boolean(value) if key is not None else None
        if verdict is not None:
            if verdict:
                return True, f"equivalence proven ({key})", True
            return False, f"equivalence failure ({key})", False
    return None, f"keys present: {sorted(metrics) or 'none'}", None


def missing_reason(stage_id, label, metrics):
    """Loud missing-machine-file reason for one gated stage.

    Args:
        stage_id: Gate id (D22/D25/D26/D27).
        label: Short metric kind (STA/DRC/LVS/equivalence).
        metrics: Merged step metrics (possibly empty).

    Returns:
        Reason naming the machine files plus the keys seen.
    """
    seen = sorted(metrics) or "none"
    return (
        f"no {label} machine-file metrics "
        f"(state_out.json/metrics.csv) for {stage_id}; "
        f"keys present: {seen}"
    )


def _read_json(path):
    """Decode one JSON file, or None when absent/unparseable.

    Args:
        path: JSON file path.

    Returns:
        Decoded value, or None.
    """
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _read_csv(path):
    """Decode one Metric,Value CSV file into a flat mapping.

    Args:
        path: CSV file path with a Metric,Value header row.

    Returns:
        Key to coerced (number-or-string) value mapping.
    """
    try:
        rows = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    parsed = {}
    reader = csv.DictReader(rows)
    if reader.fieldnames != ["Metric", "Value"]:
        return {}
    for row in reader:
        try:
            key = (row["Metric"] or "").strip()
            raw = (row["Value"] or "").strip()
        except (AttributeError, KeyError):
            continue
        if not key:
            continue
        try:
            parsed[key] = float(raw)
        except ValueError:
            parsed[key] = raw
    return parsed
