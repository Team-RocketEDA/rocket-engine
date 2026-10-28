"""Error type for catalog violations. Carries a stable machine code."""


class LibraryError(Exception):
    def __init__(self, code, message, fields=None):
        super().__init__(message)
        self.code = code
        self.fields = fields or []
