from __future__ import annotations

import os
from pathlib import Path
from typing import Any


TRUE_VALUES = {"1", "true", "yes", "on"}
DEFAULT_LOCAL_DATA_DIR = Path(".dadosbr")
DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024


class SecurityPolicyError(ValueError):
    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in TRUE_VALUES


def local_file_access_enabled() -> bool:
    return env_flag("DADOSBR_ENABLE_LOCAL_FILE_ENDPOINTS", default=False)


def admin_http_enabled() -> bool:
    return env_flag("DADOSBR_ENABLE_ADMIN_HTTP", default=False)


def admin_mcp_enabled() -> bool:
    return env_flag("DADOSBR_ENABLE_ADMIN_MCP", default=False)


def local_data_root() -> Path:
    configured = os.getenv("DADOSBR_LOCAL_DATA_DIR", "")
    return Path(configured or DEFAULT_LOCAL_DATA_DIR).expanduser().resolve()


def validate_local_path(raw_path: str | Path, *, purpose: str = "file") -> str:
    if not local_file_access_enabled():
        raise SecurityPolicyError(
            "local_file_access_disabled",
            "Local file path endpoints are disabled. Set DADOSBR_ENABLE_LOCAL_FILE_ENDPOINTS=1 for trusted local use.",
            purpose=purpose,
        )

    root = local_data_root()
    candidate = Path(raw_path).expanduser().resolve(strict=False)
    if candidate != root and not _is_relative_to(candidate, root):
        raise SecurityPolicyError(
            "local_file_outside_allowed_root",
            "Local path is outside DADOSBR_LOCAL_DATA_DIR.",
            path=str(candidate),
            allowed_root=str(root),
            purpose=purpose,
        )
    return str(candidate)


def validate_optional_local_path(raw_path: str | Path | None, *, purpose: str = "file") -> str:
    if raw_path in (None, ""):
        return ""
    return validate_local_path(raw_path, purpose=purpose)


def validate_admin_http_access(provided_token: str | None = None) -> None:
    if not admin_http_enabled():
        raise SecurityPolicyError(
            "admin_http_disabled",
            "HTTP admin endpoints are disabled. Use the CLI or set DADOSBR_ENABLE_ADMIN_HTTP=1 in a trusted environment.",
        )

    _validate_admin_token(provided_token, channel="HTTP")


def validate_admin_mcp_access(provided_token: str | None = None) -> None:
    if not admin_mcp_enabled():
        raise SecurityPolicyError(
            "admin_mcp_disabled",
            "MCP admin tools are disabled. Use the CLI or set DADOSBR_ENABLE_ADMIN_MCP=1 in a trusted environment.",
        )

    _validate_admin_token(provided_token, channel="MCP")


def _validate_admin_token(provided_token: str | None, *, channel: str) -> None:
    expected_token = os.getenv("DADOSBR_ADMIN_TOKEN", "").strip()
    if not expected_token:
        raise SecurityPolicyError(
            "admin_token_required",
            f"{channel} admin access requires DADOSBR_ADMIN_TOKEN when enabled.",
        )
    if provided_token != expected_token:
        raise SecurityPolicyError(
            "admin_token_invalid",
            "Invalid or missing admin token.",
        )


def validate_upload_size(raw_bytes: bytes, *, purpose: str = "upload") -> None:
    validate_upload_size_bytes(len(raw_bytes), purpose=purpose)


def validate_upload_size_bytes(size_bytes: int, *, purpose: str = "upload") -> None:
    max_bytes = _max_upload_bytes()
    if size_bytes > max_bytes:
        raise SecurityPolicyError(
            "upload_too_large",
            "Uploaded file exceeds DADOSBR_MAX_UPLOAD_BYTES.",
            size_bytes=size_bytes,
            max_bytes=max_bytes,
            purpose=purpose,
        )


def _max_upload_bytes() -> int:
    raw = os.getenv("DADOSBR_MAX_UPLOAD_BYTES", "")
    if not raw:
        return DEFAULT_MAX_UPLOAD_BYTES
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_MAX_UPLOAD_BYTES


def _is_relative_to(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False
