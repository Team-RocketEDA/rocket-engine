"""Error type for project-service violations. Carries a stable machine code."""


class ProjectError(Exception):
    def __init__(self, code, message, fields=None):
        super().__init__(message)
        self.code = code
        self.fields = fields or []
