from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SourceMetadata(BaseModel):
    source_id: str
    name: str
    base_url: str
    license_name: str
    update_frequency: str
    official: bool = True
    notes: str = ""


class DataError(BaseModel):
    code: str
    message: str
    source_id: str
    source_url: str | None = None
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class DataResponse(BaseModel):
    ok: bool = True
    source_id: str
    source_url: str
    license_name: str = ""
    source_mode: str = "live"
    resilience: dict[str, Any] = Field(default_factory=dict)
    collected_at: datetime
    observed_at: datetime | None = None
    raw_sha256: str | None = None
    freshness: str = "unknown"
    limitations: list[str] = Field(default_factory=list)
    records: list[dict[str, Any]] = Field(default_factory=list)
    error: DataError | None = None

    @classmethod
    def failure(
        cls,
        *,
        source_id: str,
        source_url: str,
        collected_at: datetime,
        error: DataError,
        license_name: str = "",
        source_mode: str = "error",
        resilience: dict[str, Any] | None = None,
    ) -> "DataResponse":
        return cls(
            ok=False,
            source_id=source_id,
            source_url=source_url,
            license_name=license_name,
            source_mode=source_mode,
            resilience=resilience or {},
            collected_at=collected_at,
            records=[],
            error=error,
            freshness="error",
        )
