from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_SENSITIVE_KEY_RE = re.compile(
    r"(?:authorization|api[-_]?key|access[-_]?token|refresh[-_]?token|token|secret|password|cookie)",
    re.IGNORECASE,
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_URL_CREDENTIAL_RE = re.compile(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@")
_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(authorization|api[-_]?key|access[-_]?token|refresh[-_]?token|token|secret|password|cookie)"
    r"([\"']?\s*[:=]\s*[\"']?)([^\"'\s,;&}]+)"
)


def redact_url(value: str) -> str:
    """Remove credentials and secret-like query values from a URL."""

    try:
        parts = urlsplit(value)
    except ValueError:
        return "[invalid-url]"
    if not parts.scheme or not parts.netloc:
        return value
    hostname = parts.hostname or ""
    try:
        port = f":{parts.port}" if parts.port is not None else ""
    except ValueError:
        return "[invalid-url]"
    netloc = f"{hostname}{port}"
    query = urlencode(
        [
            (key, "[REDACTED]" if _SENSITIVE_KEY_RE.search(key) else item)
            for key, item in parse_qsl(parts.query, keep_blank_values=True)
        ]
    )
    return urlunsplit((parts.scheme, netloc, parts.path, query, ""))


def redact_sensitive(value: Any, *, max_length: int = 2000) -> str:
    """Return a log-safe error detail without credentials or bearer tokens."""

    text = str(value or "")
    text = _URL_CREDENTIAL_RE.sub(r"\1[REDACTED]@", text)
    text = _BEARER_RE.sub("Bearer [REDACTED]", text)
    text = _ASSIGNMENT_RE.sub(lambda item: f"{item.group(1)}{item.group(2)}[REDACTED]", text)
    return text[:max_length]


def redact_mapping(value: dict[str, Any]) -> dict[str, Any]:
    """Recursively redact secret-like mapping keys before diagnostics are persisted."""

    output: dict[str, Any] = {}
    for key, item in value.items():
        if _SENSITIVE_KEY_RE.search(str(key)):
            output[str(key)] = "[REDACTED]"
        elif isinstance(item, dict):
            output[str(key)] = redact_mapping(item)
        elif isinstance(item, list):
            output[str(key)] = [
                redact_mapping(entry)
                if isinstance(entry, dict)
                else redact_sensitive(entry)
                if isinstance(entry, str)
                else entry
                for entry in item
            ]
        elif isinstance(item, str):
            output[str(key)] = redact_sensitive(item)
        else:
            output[str(key)] = item
    return output
