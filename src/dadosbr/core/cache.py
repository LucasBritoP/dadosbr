from __future__ import annotations

import json
import uuid
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Any

from .utils import sha256_bytes, utc_now


class DiskCache:
    def __init__(self, cache_dir: str | Path, ttl_seconds: int = 3600) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = timedelta(seconds=max(0, int(ttl_seconds)))

    def _key_path(self, key: str) -> Path:
        return self.cache_dir / f"{self._key_digest(key)}.json"

    def _key_digest(self, key: str) -> str:
        return sha256_bytes(key.encode("utf-8"))

    def get(self, key: str) -> dict[str, Any] | None:
        entry = self.get_with_metadata(key)
        return entry[0] if entry else None

    def get_with_metadata(
        self,
        key: str,
        *,
        allow_expired: bool = False,
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        path = self._key_path(key)
        if not path.exists():
            return None
        try:
            content = json.loads(path.read_text(encoding="utf-8"))
            created_at = content.get("created_at")
            if not created_at:
                return None
            created = datetime.fromisoformat(created_at)
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            age = utc_now() - created
            expired = self.ttl.total_seconds() > 0 and age > self.ttl
            if expired and not allow_expired:
                return None
            value = content.get("value")
            if not isinstance(value, dict):
                return None
            return value, {
                "created_at": created.isoformat(),
                "age_seconds": max(0, int(age.total_seconds())),
                "expired": expired,
            }
        except Exception:  # noqa: BLE001
            return None

    def set(self, key: str, value: dict[str, Any]) -> None:
        path = self._key_path(key)
        payload = {"created_at": utc_now().isoformat(), "value": value}
        _atomic_write_text(path, json.dumps(payload, ensure_ascii=False, default=str))

    def set_bytes(self, key: str, value: bytes) -> str:
        path = self.cache_dir / f"{self._key_digest(key)}.{uuid.uuid4().hex}.body"
        _atomic_write_bytes(path, value)
        return path.name

    def get_bytes(self, filename: str) -> bytes:
        safe_name = Path(str(filename or "")).name
        if not safe_name:
            raise FileNotFoundError("Empty cache blob name.")
        return (self.cache_dir / safe_name).read_bytes()

    def delete_bytes(self, filename: str) -> bool:
        safe_name = Path(str(filename or "")).name
        if not safe_name:
            return False
        try:
            (self.cache_dir / safe_name).unlink()
        except FileNotFoundError:
            return False
        return True


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_bytes(content)
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()
