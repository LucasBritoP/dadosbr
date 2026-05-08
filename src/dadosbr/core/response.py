from __future__ import annotations

from datetime import datetime

from .errors import DataSourceError
from .models import DataError, DataResponse
from .registry import SOURCES
from .utils import compute_freshness, freshest_observed, utc_now


def make_success(
    *,
    source_id: str,
    source_url: str,
    records: list[dict],
    observed_at: datetime | None = None,
    raw_sha256: str | None = None,
    limitations: list[str] | None = None,
    source_mode: str = "live",
    resilience: dict | None = None,
) -> DataResponse:
    collected_at = utc_now()
    resolved_observed = observed_at or freshest_observed(records)
    return DataResponse(
        ok=True,
        source_id=source_id,
        source_url=source_url,
        license_name=SOURCES[source_id].license_name,
        source_mode=source_mode,
        resilience=resilience or {},
        collected_at=collected_at,
        observed_at=resolved_observed,
        raw_sha256=raw_sha256,
        freshness=compute_freshness(resolved_observed, collected_at),
        limitations=limitations or [],
        records=records,
    )


def make_failure(error: DataSourceError) -> DataResponse:
    source_url = error.source_url or ""
    source_id = error.source_id
    license_name = SOURCES[source_id].license_name if source_id in SOURCES else ""
    return DataResponse.failure(
        source_id=source_id,
        source_url=source_url,
        collected_at=utc_now(),
        license_name=license_name,
        source_mode="error",
        error=DataError(
            code=error.code,
            message=error.message,
            source_id=error.source_id,
            source_url=source_url,
            retryable=error.retryable,
            details=error.details or {},
        ),
    )
