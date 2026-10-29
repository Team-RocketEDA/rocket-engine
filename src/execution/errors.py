"""Error type for execution violations. Carries a stable machine code."""


class ExecutionError(Exception):
    def __init__(self, code, message, fields=None):
        super().__init__(message)
        self.code = code
        self.fields = fields or []


class UsageError(Exception):
    """Op-call validation failure: unknown op or malformed args.

    Raised by the dispatch port; inbound adapters map it to a usage
    exit (CLI: exit 2). Codes reuse the stable engine vocabulary:
    `unsupported_operation` for unknown names, `invalid_command`
    for malformed calls.
    """

    def __init__(self, code, message, fields=None):
        super().__init__(message)
        self.code = code
        self.fields = fields or []
