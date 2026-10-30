"""Error type for adapter violations. Carries a stable machine code."""


class AdapterError(Exception):
    """Adapter violation with a stable machine code.

    Args:
        code: Stable machine-readable error code.
        message: Human-readable detail.
        fields: Itemized fields, when the error names any.
    """

    def __init__(self, code, message, fields=None):
        super().__init__(message)
        self.code = code
        self.fields = fields or []
