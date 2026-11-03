"""Shared marker-delimited envelope extraction for solver drivers.

Solver stdout is untrusted: warnings, banners, and progress lines may
surround the one JSON envelope the driver prints. Drivers frame the
envelope with ``ROCKETEDA_ENVELOPE_BEGIN``/``ROCKETEDA_ENVELOPE_END``
markers (one marker per line, JSON between); this helper extracts the
framed document and tolerates any chatter outside it. Legacy clean
stdout (exactly one JSON document, no markers) still parses, and
unmarked chatter falls back to a best-effort envelope scan so old
drivers degrade gracefully. Chatter is never fatal: the native stdout
(with warnings) stays intact for the Engine run log, which stores it
verbatim (see ``Engine._run_operation``); only the envelope is parsed.
"""

import json

from .errors import AdapterError

ENVELOPE_BEGIN = "ROCKETEDA_ENVELOPE_BEGIN"
ENVELOPE_END = "ROCKETEDA_ENVELOPE_END"


def emit_envelope(payload):
    """Emit one marker-delimited envelope document.

    Args:
        payload: Envelope mapping with an ``ok`` boolean.

    Returns:
        Marker-framed envelope text (begin line, JSON line, end line).
    """
    return "\n".join(
        [ENVELOPE_BEGIN, json.dumps(payload), ENVELOPE_END]
    ) + "\n"


def _scan(text):
    """Last envelope-shaped JSON object in text, or None when absent."""
    decoder = json.JSONDecoder()
    found = None
    start = 0
    while True:
        index = text.find("{", start)
        if index == -1:
            return found
        try:
            data, _ = decoder.raw_decode(text[index:])
        except ValueError:
            start = index + 1
            continue
        if isinstance(data, dict) and isinstance(data.get("ok"), bool):
            found = data
        start = index + 1


def extract_envelope(stdout, *, tool):
    """Extract one driver envelope from possibly chattered stdout.

    Markers first, then the legacy whole-stdout document, then a
    best-effort envelope scan for unmarked chatter. The native stdout
    is never mutated: warnings stay in it for the Engine run log.

    Args:
        stdout: Driver stdout text (bytes are decoded as UTF-8).
        tool: Driver label for the no-envelope message (sax,
            circulax, views, meow).

    Returns:
        Envelope mapping with an ``ok`` boolean.

    Raises:
        AdapterError: runner_unavailable when no JSON envelope is
            found or the framed document is not an envelope.
    """
    if isinstance(stdout, (bytes, bytearray)):
        text = bytes(stdout).decode("utf-8", errors="replace")
    elif isinstance(stdout, str):
        text = stdout
    elif stdout is None:
        text = ""
    else:
        raise AdapterError(
            "runner_unavailable",
            f"{tool} driver printed no JSON envelope.",
        )
    message = f"{tool} driver printed no JSON envelope."
    begin = text.rfind(ENVELOPE_BEGIN)
    if begin != -1:
        end = text.find(ENVELOPE_END, begin + len(ENVELOPE_BEGIN))
        if end == -1:
            raise AdapterError("runner_unavailable", message)
        candidate = text[begin + len(ENVELOPE_BEGIN):end].strip()
        try:
            data = json.loads(candidate)
        except (TypeError, ValueError):
            data = _scan(candidate)
            if data is None:
                raise AdapterError(
                    "runner_unavailable", message
                ) from None
            return data
        if not isinstance(data, dict) or not isinstance(
            data.get("ok"), bool
        ):
            raise AdapterError("runner_unavailable", message)
        return data
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        pass
    else:
        if not isinstance(data, dict) or not isinstance(
            data.get("ok"), bool
        ):
            raise AdapterError("runner_unavailable", message)
        return data
    found = _scan(text)
    if found is None:
        raise AdapterError("runner_unavailable", message)
    return found
