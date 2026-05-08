from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class DataSourceError(Exception):
    code: str
    message: str
    source_id: str
    source_url: str | None = None
    retryable: bool = False
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return f"{self.source_id}:{self.code}: {self.message}"
