"""Custom project template errors (TEMPLATE-RUNTIME)."""

from __future__ import annotations


class TemplateError(Exception):
    """Typed custom-template failure; `code` names the verdict.

    Codes: invalid_template for a non-mapping, bad YAML, unknown
    key, or malformed area/config entry; future_format for a
    template newer than this engine; missing_migration for a
    version step with no registered link; invalid_migration for
    a skipped step, a conflicting link, or a migrator that does
    not return a mapping.
    """

    def __init__(self, code, message):
        """Bind one machine-readable verdict code to its message.

        Args:
            code: Verdict code naming the failure.
            message: Human-readable detail naming the violation.
        """
        super().__init__(message)
        self.code = code
