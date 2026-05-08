from __future__ import annotations

import csv
import os
from io import StringIO
from pathlib import Path
from urllib.parse import urlencode

from dadosbr.core import DataSourceError, make_failure, make_success
from dadosbr.core.http import http_get_bytes, http_get_bytes_cached, http_response_metadata, parse_json_bytes
from dadosbr.core.utils import parse_br_decimal, parse_iso_date, sha256_bytes

SOURCE_ID = "tesouro_transparente"
PACKAGE_ID = "taxas-dos-titulos-ofertados-pelo-tesouro-direto"
RESOURCE_ID = "796d2059-14e9-44e3-80c9-2d9e30b405c1"


def fetch_tesouro_rates(*, limit: int = 200) -> dict:
    safe_limit = max(1, min(int(limit or 200), 2000))
    package_url = (
        "https://www.tesourotransparente.gov.br/ckan/api/3/action/package_show?"
        + urlencode({"id": PACKAGE_ID})
    )
    try:
        package_headers: dict[str, str] = {}
        csv_headers: dict[str, str] = {}
        local_files: list[str] = []
        package_body = _local_file_bytes("DADOSBR_TESOURO_PACKAGE_FILE")
        if package_body is None:
            package_body, package_headers = _fetch_bytes(package_url, timeout_seconds=60)
        else:
            local_files.append(os.getenv("DADOSBR_TESOURO_PACKAGE_FILE", "").strip())
        package = parse_json_bytes(package_body, source_id=SOURCE_ID, source_url=package_url)
        resource = _find_resource(package)
        csv_url = str(resource.get("url", ""))
        if not csv_url:
            raise DataSourceError(
                "invalid_response",
                "CKAN resource URL not found",
                SOURCE_ID,
                source_url=package_url,
            )
        csv_body = _local_file_bytes("DADOSBR_TESOURO_RATES_CSV_FILE")
        if csv_body is None:
            csv_body, csv_headers = _fetch_bytes(csv_url, timeout_seconds=60)
        else:
            local_files.append(os.getenv("DADOSBR_TESOURO_RATES_CSV_FILE", "").strip())
        source_mode, resilience, cache_limitations = http_response_metadata(csv_headers or package_headers)
        if local_files:
            source_mode = "local_snapshot"
            resilience["local_files"] = local_files
        text = _decode_csv(csv_body)
        reader = csv.DictReader(StringIO(text), delimiter=";")
        records: list[dict] = []
        for row in reader:
            if len(records) >= safe_limit:
                break
            records.append(
                {
                    "bond_type": row.get("Tipo Titulo"),
                    "maturity_date": parse_iso_date(
                        _to_iso_br_date(row.get("Data Vencimento", "")), "Data Vencimento"
                    ).isoformat(),
                    "observed_at": parse_iso_date(
                        _to_iso_br_date(row.get("Data Base", "")), "Data Base"
                    ).isoformat(),
                    "buy_rate_morning": parse_br_decimal(row.get("Taxa Compra Manha")),
                    "sell_rate_morning": parse_br_decimal(row.get("Taxa Venda Manha")),
                    "buy_price_morning": parse_br_decimal(row.get("PU Compra Manha")),
                    "sell_price_morning": parse_br_decimal(row.get("PU Venda Manha")),
                }
            )
        return make_success(
            source_id=SOURCE_ID,
            source_url=csv_url,
            records=records,
            raw_sha256=sha256_bytes(csv_body),
            limitations=cache_limitations,
            source_mode=source_mode,
            resilience=resilience,
        ).model_dump(mode="json")
    except DataSourceError as exc:
        return make_failure(exc).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        return make_failure(
            DataSourceError("parse_error", str(exc), SOURCE_ID, source_url=package_url)
        ).model_dump(mode="json")


def _find_resource(package: dict) -> dict:
    if not package.get("success"):
        raise DataSourceError("invalid_response", "CKAN package request failed", SOURCE_ID)
    resources = package.get("result", {}).get("resources", [])
    for resource in resources:
        if resource.get("id") == RESOURCE_ID:
            return resource
    for resource in resources:
        if str(resource.get("format", "")).upper() == "CSV":
            return resource
    raise DataSourceError("invalid_response", "CSV resource not found", SOURCE_ID)


def _fetch_bytes(url: str, *, timeout_seconds: int) -> tuple[bytes, dict[str, str]]:
    return http_get_bytes_cached(
        url,
        source_id=SOURCE_ID,
        timeout_seconds=timeout_seconds,
        cache_namespace="tesouro",
        fetcher=http_get_bytes,
    )


def _local_file_bytes(env_name: str) -> bytes | None:
    configured = os.getenv(env_name, "").strip()
    if not configured:
        return None
    path = Path(configured)
    if not path.exists():
        raise DataSourceError(
            "validation_error",
            f"{env_name} points to a missing file: {path}",
            SOURCE_ID,
        )
    return path.read_bytes()


def _to_iso_br_date(value: str) -> str:
    raw = str(value).strip()
    if "-" in raw:
        return raw
    day, month, year = raw.split("/")
    return f"{year}-{month}-{day}"


def _decode_csv(data: bytes) -> str:
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DataSourceError("parse_error", "Unable to decode Tesouro CSV", SOURCE_ID)
