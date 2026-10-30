"""Error type for project-service violations. Carries a stable machine code."""


class ProjectError(Exception):
    """Project-service violation with a stable machine code.

    Args:
        code: Stable machine-readable error code.
        message: Human-readable detail.
        fields: Itemized fields, when the error names any.
    """

    def __init__(self, code, message, fields=None):
        super().__init__(message)
        self.code = code
        self.fields = fields or []
