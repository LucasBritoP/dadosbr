from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_json(data: Any) -> str:
    payload = json.dumps(data, ensure_ascii=False, default=str, sort_keys=True).encode("utf-8")
    return sha256_bytes(payload)


def parse_iso_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid {field_name}: {value}") from exc


def parse_iso_datetime(value: str, field_name: str) -> datetime:
    raw = str(value).strip().replace("Z", "+00:00")
    try:
        result = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"invalid {field_name}: {value}") from exc
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def parse_br_decimal(value: Any) -> float:
    raw = str(value).strip()
    if raw == "":
        raise ValueError("empty numeric value")
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    return float(raw)


def parse_maybe_br_decimal(value: Any) -> float | None:
    raw = str(value).strip()
    if raw in {"", "-", "...", "None", "nan"}:
        return None
    return parse_br_decimal(raw)


def freshest_observed(records: list[dict[str, Any]], field: str = "observed_at") -> datetime | None:
    values: list[datetime] = []
    for row in records:
        v = row.get(field)
        if isinstance(v, datetime):
            values.append(v.astimezone(UTC))
        elif isinstance(v, str) and v:
            try:
                values.append(parse_iso_datetime(v, field))
            except ValueError:
                continue
    return max(values) if values else None


def compute_freshness(observed_at: datetime | None, collected_at: datetime) -> str:
    if observed_at is None:
        return "no_data"
    age_hours = (collected_at - observed_at).total_seconds() / 3600.0
    if age_hours <= 26:
        return "fresh"
    if age_hours <= 24 * 7:
        return "stale"
    return "old"
