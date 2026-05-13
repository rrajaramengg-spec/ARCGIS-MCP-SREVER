"""Logging filters for correlation and sanitization.

CorrelationFilter reads ContextVars and injects them into every LogRecord.
SanitizingFilter redacts known sensitive field names from log records.
"""

import logging
from typing import Set

from core.observability.context import request_id_var, service_name_var

_SENSITIVE_FIELDS: Set[str] = frozenset({
    "password",
    "token",
    "secret",
    "api_key",
    "authorization",
    "credential",
    "private_key",
})

_REDACTED = "[REDACTED]"


class CorrelationFilter(logging.Filter):
    """Inject ContextVar values into every LogRecord.

    Adds ``request_id`` and ``service`` attributes so formatters can
    include them without any changes to existing logger.info() calls.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.service = service_name_var.get()
        return True


class SanitizingFilter(logging.Filter):
    """Redact known sensitive field names in LogRecord extra attributes.

    Checks attribute names against a deny-list and replaces values with
    ``[REDACTED]``. Only inspects attributes added via ``extra={}`` —
    standard LogRecord fields are not touched.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        for key in vars(record):
            if key in _SENSITIVE_FIELDS:
                setattr(record, key, _REDACTED)
        return True
