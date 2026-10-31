"""Error type for catalog violations. Carries a stable machine code."""


class LibraryError(Exception):
    """Catalog violation with a stable machine code.

    Args:
        code: Stable machine-readable error code.
        message: Human-readable detail.
        fields: Itemized fields, when the error names any.
    """

    def __init__(self, code, message, fields=None):
        super().__init__(message)
        self.code = code
        self.fields = fields or []
