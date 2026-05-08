from __future__ import annotations

from urllib.parse import quote

from dadosbr.core import DataSourceError, make_failure, make_success
from dadosbr.core.http import http_get_bytes, http_get_bytes_cached, http_response_metadata, parse_json_bytes
from dadosbr.core.utils import parse_iso_datetime, sha256_bytes

SOURCE_ID = "ipeadata"


def fetch_ipea_series(series_code: str, *, top: int = 200) -> dict:
    code = str(series_code or "").strip()
    if not code:
        return make_failure(
            DataSourceError("validation_error", "series_code is required", SOURCE_ID)
        ).model_dump(mode="json")

    safe_top = max(1, min(int(top or 200), 2000))
    endpoint = f"ValoresSerie(SERCODIGO='{code}')"
    url = (
        "http://www.ipeadata.gov.br/api/odata4/"
        + quote(endpoint, safe="()='")
        + f"?$top={safe_top}&$orderby=VALDATA%20desc"
    )
    try:
        body, headers = http_get_bytes_cached(
            url,
            source_id=SOURCE_ID,
            timeout_seconds=30,
            cache_namespace="ipea",
            fetcher=http_get_bytes,
            max_stale_seconds=30 * 24 * 60 * 60,
        )
        source_mode, resilience, cache_limitations = http_response_metadata(headers)
        doc = parse_json_bytes(body, source_id=SOURCE_ID, source_url=url)
        rows = doc.get("value", []) if isinstance(doc, dict) else []
        records: list[dict] = []
        for row in rows:
            dt = str(row.get("VALDATA") or row.get("VALDATAFIXA") or "")
            observed = parse_iso_datetime(dt.replace(" ", "T"), "VALDATA")
            value = row.get("VALVALOR")
            records.append(
                {
                    "series_code": code,
                    "observed_at": observed.isoformat(),
                    "value": float(value) if value is not None else None,
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
