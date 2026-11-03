"""Marker-delimited stdout envelope extraction for the meow sim driver.

The driver contract used to be "exactly one JSON document on
stdout", but solver libraries print warnings there anyway: tidy3d
logs its unwritable-config warning to stdout on import, which
turned healthy solves into `runner_unavailable` (MEOW-STDOUT).
The driver now frames its envelope between BEGIN/END marker
lines; this module finds that frame and falls back to a tolerant
JSON scan for unmarked streams (older staged drivers, canned
test envelopes). Anything outside the envelope is solver
chatter: it is logged at warning level and never fatal.

Marker contract: the literal marker strings below are duplicated
in `src/adapters/meow/_driver.py`, which is staged standalone
into run workdirs and cannot import this module. Change both or
neither.
"""

import json
import logging

_LOGGER = logging.getLogger(__name__)

BEGIN_MARKER = "ROCKETEDA-ENVELOPE-BEGIN"
END_MARKER = "ROCKETEDA-ENVELOPE-END"
_CHATTER_PREVIEW = 500


def _log_chatter(chatter):
    """Log solver chatter at warning level, truncated, never fatal."""
    text = (chatter or "").strip()
    if text:
        _LOGGER.warning(
            "meow driver stdout chatter (%d bytes, never fatal): %s",
            len(text),
            text[:_CHATTER_PREVIEW],
        )


def _scan_candidates(stdout):
    """[(value, start, end)] for every top-level JSON value in order."""
    decoder = json.JSONDecoder()
    found = []
    index = 0
    while index < len(stdout):
        if stdout[index] not in "{[":
            index += 1
            continue
        try:
            value, end = decoder.raw_decode(stdout, index)
        except ValueError:
            index += 1
            continue
        found.append((value, index, end))
        index = end if end > index else index + 1
    return found


def extract_envelope(stdout):
    """Extract the driver's JSON envelope from possibly noisy stdout.

    Clean streams parse exactly as before; marked streams use the
    BEGIN/END frame authoritatively (a decoy JSON object in the
    chatter never wins); unmarked noisy streams fall back to a
    tolerant scan preferring the envelope-shaped value. Solver
    chatter is logged at warning level and never fatal.

    Args:
        stdout: Raw driver stdout, possibly with solver warnings
            or banners around the JSON envelope.

    Returns:
        Parsed envelope value (the adapter validates its shape),
            or None when no envelope is present.

    Caution: A corrupt marked frame returns None rather than
        scanning for a substitute — the frame is authoritative,
        so garbage inside it is a corrupt envelope, not chatter.
    """
    if not isinstance(stdout, str):
        return None
    try:
        return json.loads(stdout)
    except ValueError:
        pass
    begin = stdout.find(BEGIN_MARKER)
    if begin >= 0:
        end = stdout.find(END_MARKER, begin + len(BEGIN_MARKER))
        if end > begin:
            frame = stdout[begin + len(BEGIN_MARKER):end]
            try:
                value = json.loads(frame.strip())
            except ValueError:
                _log_chatter(stdout)
                return None
            _log_chatter(stdout[:begin] + stdout[end + len(END_MARKER):])
            return value
    candidates = _scan_candidates(stdout)
    if not candidates:
        _log_chatter(stdout)
        return None
    for value, start, end in reversed(candidates):
        if isinstance(value, dict) and "ok" in value:
            _log_chatter(stdout[:start] + stdout[end:])
            return value
    value, start, end = candidates[-1]
    _log_chatter(stdout[:start] + stdout[end:])
    return value
