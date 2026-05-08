from __future__ import annotations

import csv
import os
from collections import defaultdict
from io import StringIO
from pathlib import Path
from urllib.parse import urlparse

from dadosbr.core import DataSourceError, make_failure, make_success
from dadosbr.core.csv_stream import decode_text
from dadosbr.core.http import http_get_bytes, http_get_bytes_cached, http_response_metadata
from dadosbr.core.utils import sha256_bytes, sha256_json

SOURCE_ID = "mdic_comex_stat"
VALID_TABLES = {"NCM", "UF_MUN", "PAIS", "VIA", "URF"}


def fetch_comex_ncm(
    flow: str,
    year: int,
    ncm: str = "",
    uf: str = "",
    country: str = "",
    limit: int = 200,
) -> dict:
    prefix = _flow_prefix(flow)
    safe_year = _validate_year(year)
    safe_limit = max(1, min(int(limit or 200), 5000))
    url = f"https://balanca.economia.gov.br/balanca/bd/comexstat-bd/ncm/{prefix}_{safe_year}.csv"
    try:
        raw, source_mode, resilience, cache_limitations = _fetch_csv_bytes_with_metadata(url)
        reader = csv.DictReader(StringIO(decode_text(raw)), delimiter=";")
        records: list[dict] = []
        for row in reader:
            if ncm and row.get("CO_NCM", "") != ncm:
                continue
            if uf and row.get("SG_UF_NCM", "").upper() != uf.upper():
                continue
            if country and row.get("CO_PAIS", "") != country:
                continue
            records.append(_normalize_ncm_row(row))
            if len(records) >= safe_limit:
                break
        return make_success(
            source_id=SOURCE_ID,
            source_url=url,
            records=records,
            raw_sha256=sha256_bytes(raw),
            limitations=cache_limitations,
            source_mode=source_mode,
            resilience=resilience,
        ).model_dump(mode="json")
    except DataSourceError as exc:
        return make_failure(exc).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        return make_failure(DataSourceError("parse_error", str(exc), SOURCE_ID, source_url=url)).model_dump(mode="json")


def summarize_comex_ncm(
    flow: str,
    year: int,
    group_by: str = "month",
    ncm: str = "",
    uf: str = "",
    country: str = "",
) -> dict:
    prefix = _flow_prefix(flow)
    safe_year = _validate_year(year)
    key_type = group_by.strip().lower()
    valid = {"month", "ncm", "country", "uf", "sh4", "municipality"}
    if key_type not in valid:
        return make_failure(
            DataSourceError(
                "validation_error",
                f"Invalid group_by '{group_by}'. Expected one of {sorted(valid)}",
                SOURCE_ID,
            )
        ).model_dump(mode="json")
    url = f"https://balanca.economia.gov.br/balanca/bd/comexstat-bd/ncm/{prefix}_{safe_year}.csv"
    try:
        raw, source_mode, resilience, cache_limitations = _fetch_csv_bytes_with_metadata(url)
        reader = csv.DictReader(StringIO(decode_text(raw)), delimiter=";")
        totals: dict[str, dict[str, int | str]] = defaultdict(
            lambda: {"qt_estat": 0, "kg_liquido": 0, "vl_fob": 0, "vl_frete": 0, "vl_seguro": 0}
        )
        for row in reader:
            if ncm and row.get("CO_NCM", "") != ncm:
                continue
            if uf and row.get("SG_UF_NCM", "").upper() != uf.upper():
                continue
            if country and row.get("CO_PAIS", "") != country:
                continue
            key = _summary_key(row, key_type)
            bucket = totals[key]
            bucket["key"] = key
            bucket["qt_estat"] += _to_int(row.get("QT_ESTAT"))
            bucket["kg_liquido"] += _to_int(row.get("KG_LIQUIDO"))
            bucket["vl_fob"] += _to_int(row.get("VL_FOB"))
            bucket["vl_frete"] += _to_int(row.get("VL_FRETE"))
            bucket["vl_seguro"] += _to_int(row.get("VL_SEGURO"))
        records = [totals[key] for key in sorted(totals)]
        return make_success(
            source_id=SOURCE_ID,
            source_url=url,
            records=records,
            raw_sha256=sha256_json(records),
            limitations=cache_limitations,
            source_mode=source_mode,
            resilience=resilience,
        ).model_dump(mode="json")
    except DataSourceError as exc:
        return make_failure(exc).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        return make_failure(DataSourceError("parse_error", str(exc), SOURCE_ID, source_url=url)).model_dump(mode="json")


def fetch_comex_municipality(
    flow: str,
    year: int,
    uf: str = "",
    municipality_code: str = "",
    sh4: str = "",
    limit: int = 200,
) -> dict:
    prefix = _flow_prefix(flow)
    safe_year = _validate_year(year)
    safe_limit = max(1, min(int(limit or 200), 5000))
    url = f"https://balanca.economia.gov.br/balanca/bd/comexstat-bd/mun/{prefix}_{safe_year}_MUN.csv"
    try:
        raw, source_mode, resilience, cache_limitations = _fetch_csv_bytes_with_metadata(url)
        reader = csv.DictReader(StringIO(decode_text(raw)), delimiter=";")
        records: list[dict] = []
        for row in reader:
            if uf and row.get("SG_UF_MUN", "").upper() != uf.upper():
                continue
            if municipality_code and row.get("CO_MUN", "") != municipality_code:
                continue
            if sh4 and row.get("SH4", "") != sh4:
                continue
            records.append(
                {
                    "year": _to_int(row.get("CO_ANO")),
                    "month": _to_int(row.get("CO_MES")),
                    "sh4": row.get("SH4", ""),
                    "country": row.get("CO_PAIS", ""),
                    "uf": row.get("SG_UF_MUN", ""),
                    "municipality_code": row.get("CO_MUN", ""),
                    "kg_liquido": _to_int(row.get("KG_LIQUIDO")),
                    "vl_fob": _to_int(row.get("VL_FOB")),
                }
            )
            if len(records) >= safe_limit:
                break
        return make_success(
            source_id=SOURCE_ID,
            source_url=url,
            records=records,
            raw_sha256=sha256_bytes(raw),
            limitations=cache_limitations,
            source_mode=source_mode,
            resilience=resilience,
        ).model_dump(mode="json")
    except DataSourceError as exc:
        return make_failure(exc).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        return make_failure(DataSourceError("parse_error", str(exc), SOURCE_ID, source_url=url)).model_dump(mode="json")


def fetch_comex_table(table_name: str, limit: int = 500) -> dict:
    normalized_table = str(table_name or "").strip().upper()
    if normalized_table not in VALID_TABLES:
        return make_failure(
            DataSourceError(
                "validation_error",
                f"Invalid table_name '{table_name}'. Expected one of {sorted(VALID_TABLES)}",
                SOURCE_ID,
            )
        ).model_dump(mode="json")
    safe_limit = max(1, min(int(limit or 500), 5000))
    url = f"https://balanca.economia.gov.br/balanca/bd/tabelas/{normalized_table}.csv"
    try:
        raw, source_mode, resilience, cache_limitations = _fetch_csv_bytes_with_metadata(url)
        reader = csv.DictReader(StringIO(decode_text(raw)), delimiter=";")
        rows = []
        for row in reader:
            rows.append(dict(row))
            if len(rows) >= safe_limit:
                break
        return make_success(
            source_id=SOURCE_ID,
            source_url=url,
            records=rows,
            raw_sha256=sha256_bytes(raw),
            limitations=cache_limitations,
            source_mode=source_mode,
            resilience=resilience,
        ).model_dump(mode="json")
    except DataSourceError as exc:
        return make_failure(exc).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        return make_failure(DataSourceError("parse_error", str(exc), SOURCE_ID, source_url=url)).model_dump(mode="json")


def _fetch_csv_bytes(url: str) -> bytes:
    return _fetch_csv_bytes_with_metadata(url)[0]


def _fetch_csv_bytes_with_metadata(url: str) -> tuple[bytes, str, dict, list[str]]:
    local_file = _local_comex_file(url)
    if local_file:
        return local_file.read_bytes(), "local_snapshot", {"local_file": str(local_file)}, []
    body, headers = http_get_bytes_cached(
        url,
        source_id=SOURCE_ID,
        timeout_seconds=120,
        cache_namespace="comex",
        verify_ssl=_verify_ssl(),
        fetcher=http_get_bytes,
    )
    source_mode, resilience, limitations = http_response_metadata(headers)
    return body, source_mode, resilience, limitations


def _verify_ssl() -> bool:
    raw = os.getenv("DADOSBR_COMEX_VERIFY_SSL", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _local_comex_file(url: str) -> Path | None:
    root = os.getenv("DADOSBR_COMEX_DATA_DIR", "").strip()
    if not root:
        return None
    parsed_path = Path(urlparse(url).path)
    filename = parsed_path.name
    section = parsed_path.parent.name
    base = Path(root)
    for candidate in (base / section / filename, base / filename):
        if candidate.exists():
            return candidate
    return None


def _flow_prefix(flow: str) -> str:
    value = str(flow or "").strip().lower()
    if value == "export":
        return "EXP"
    if value == "import":
        return "IMP"
    raise DataSourceError("validation_error", "flow must be 'export' or 'import'.", SOURCE_ID)


def _validate_year(year: int) -> int:
    value = int(year or 0)
    if value < 1997 or value > 2100:
        raise DataSourceError("validation_error", "year must be between 1997 and 2100.", SOURCE_ID)
    return value


def _to_int(value: str | int | None) -> int:
    raw = str(value or "").strip()
    if raw == "":
        return 0
    try:
        return int(float(raw))
    except ValueError:
        return 0


def _normalize_ncm_row(row: dict[str, str]) -> dict:
    return {
        "year": _to_int(row.get("CO_ANO")),
        "month": _to_int(row.get("CO_MES")),
        "ncm": row.get("CO_NCM", ""),
        "unit_code": row.get("CO_UNID", ""),
        "country": row.get("CO_PAIS", ""),
        "uf": row.get("SG_UF_NCM", ""),
        "via": row.get("CO_VIA", ""),
        "urf": row.get("CO_URF", ""),
        "qt_estat": _to_int(row.get("QT_ESTAT")),
        "kg_liquido": _to_int(row.get("KG_LIQUIDO")),
        "vl_fob": _to_int(row.get("VL_FOB")),
        "vl_frete": _to_int(row.get("VL_FRETE")),
        "vl_seguro": _to_int(row.get("VL_SEGURO")),
    }


def _summary_key(row: dict[str, str], group_by: str) -> str:
    if group_by == "month":
        return f"{row.get('CO_ANO', '')}-{str(row.get('CO_MES', '')).zfill(2)}"
    if group_by == "ncm":
        return row.get("CO_NCM", "")
    if group_by == "country":
        return row.get("CO_PAIS", "")
    if group_by == "uf":
        return row.get("SG_UF_NCM", "")
    if group_by == "sh4":
        return str(row.get("CO_NCM", ""))[:4]
    if group_by == "municipality":
        return row.get("CO_MUN", "")
    return "unknown"
