"""可分享输出的敏感值检查。"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from urllib.parse import parse_qsl, urlsplit


class OutputSafetyError(ValueError):
    """输出包含不应被分享的字段。"""

    def __init__(self, field_path: str, reason: str) -> None:
        self.field_path = field_path
        self.reason = reason
        super().__init__(f"输出安全检查失败：{field_path}（{reason}）")


_ABSOLUTE_PATH = re.compile(
    r"(?<![A-Za-z0-9])/(?:Users|home|private|var|tmp)(?:/|$)"
    r"|(?<![A-Za-z0-9])[A-Za-z]:[\\/]Users[\\/]",
    re.IGNORECASE,
)
_SECRET_ASSIGNMENT = re.compile(
    r"\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|secret|password|"
    r"signature|token)\s*[:=]\s*[^\s,;&)]+",
    re.IGNORECASE,
)
_SENSITIVE_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth_token",
    "key",
    "password",
    "secret",
    "signature",
    "token",
}


def ensure_safe_output(payload: object, *, root: str) -> None:
    """递归检查可分享 payload，只报告字段路径，不回显字段值。"""

    _check_value(payload, root)


def _check_value(value: object, path: str) -> None:
    if isinstance(value, str):
        if _ABSOLUTE_PATH.search(value):
            raise OutputSafetyError(path, "personal_absolute_path")
        if _SECRET_ASSIGNMENT.search(value):
            raise OutputSafetyError(path, "secret_assignment")
        if _has_sensitive_query(value):
            raise OutputSafetyError(path, "sensitive_url_query")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            _check_value(child, f"{path}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        for index, child in enumerate(value):
            _check_value(child, f"{path}[{index}]")


def _has_sensitive_query(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.query:
        return False
    return any(
        key.casefold() in _SENSITIVE_QUERY_KEYS
        or key.casefold().endswith(("_token", "_signature"))
        for key, _ in parse_qsl(parsed.query, keep_blank_values=True)
    )


__all__ = ["OutputSafetyError", "ensure_safe_output"]
