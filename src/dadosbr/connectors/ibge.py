from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import quote

from dadosbr.core import DataSourceError, make_failure, make_success
from dadosbr.core.http import http_get_bytes, http_get_bytes_cached, http_response_metadata, parse_json_bytes
from dadosbr.core.utils import parse_br_decimal, sha256_bytes

SOURCE_ID = "ibge_sidra"


def fetch_ibge_sidra(path: str) -> dict:
    cleaned_path = str(path or "").strip().strip("/")
    if not cleaned_path:
        return make_failure(
            DataSourceError("validation_error", "path is required", SOURCE_ID)
        ).model_dump(mode="json")
    quoted_path = quote(cleaned_path, safe="/")
    url = f"https://apisidra.ibge.gov.br/values/{quoted_path}"
    try:
        body, headers = http_get_bytes_cached(
            url,
            source_id=SOURCE_ID,
            timeout_seconds=30,
            cache_namespace="ibge",
            fetcher=http_get_bytes,
            max_stale_seconds=30 * 24 * 60 * 60,
        )
        source_mode, resilience, cache_limitations = http_response_metadata(headers)
        rows = parse_json_bytes(body, source_id=SOURCE_ID, source_url=url)
        data_rows = rows[1:] if rows and rows[0].get("V") == "Valor" else rows
        records: list[dict] = []
        for row in data_rows:
            period = str(row.get("D3C", ""))
            records.append(
                {
                    "territory_code": row.get("D1C"),
                    "territory_name": row.get("D1N"),
                    "variable_code": row.get("D2C"),
                    "variable_name": row.get("D2N"),
                    "period": period,
                    "observed_at": _period_to_iso(period),
                    "value": parse_br_decimal(row.get("V")),
                    "unit": row.get("MN"),
                }
            )
        return make_success(
            source_id=SOURCE_ID,
            source_url=url,
            records=records,
            raw_sha256=sha256_bytes(body),
            limitations=cache_limitations,
            source_mode=source_mode,
            resilience=resilience,
        ).model_dump(mode="json")
    except DataSourceError as exc:
        return make_failure(exc).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        return make_failure(
            DataSourceError("parse_error", str(exc), SOURCE_ID, source_url=url)
        ).model_dump(mode="json")


def _period_to_iso(value: str) -> str:
    text = value.strip()
    if len(text) == 6 and text.isdigit():
        return datetime(int(text[:4]), int(text[4:6]), 1, tzinfo=UTC).isoformat()
    if len(text) == 4 and text.isdigit():
        return datetime(int(text), 1, 1, tzinfo=UTC).isoformat()
    raise ValueError(f"invalid SIDRA period code: {value}")
