"""API contract: the one inbound port every gateway calls.

Gateways (http, mcp, ipc, cli/dispatcher, console) own only I/O
framing — parsing their wire format and serializing results. They
never build submit envelopes themselves and never subclass each
other: every gateway composes over `submit` here (composition over
inheritance), so the envelope shape, request-id minting, and error
propagation exist exactly once.

Validation stays at the boundaries: gateways reject unknown names
with their wire-appropriate error (UsageError on text wires,
AdapterError on framed wires), and Engine.submit backstops with
unsupported_operation. Engine errors propagate untouched — mapping
them to wire envelopes is framing, owned by each gateway with the
shared shapes from `adapters.errors`.
"""

import uuid


def submit(engine, project_id, operation, arguments, request_id=None):
    """Submit one call through the engine port.

    Args:
        engine: Engine (or stand-in) exposing `submit`.
        project_id: Project the call runs against.
        operation: Cataloged operation or query name.
        arguments: Operation arguments mapping.
        request_id: Envelope id; minted when omitted.

    Returns:
        Engine result for the call (ack, completion, or data).
    """
    return engine.submit({
        "project_id": project_id,
        "operation": operation,
        "arguments": dict(arguments),
        "request_id": request_id or uuid.uuid4().hex,
    })
