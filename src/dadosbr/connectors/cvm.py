from __future__ import annotations

import csv
import json
import os
import zipfile
from datetime import UTC, datetime
from io import BytesIO, TextIOWrapper
from pathlib import Path
from typing import Any

from dadosbr.core import DataSourceError, make_failure, make_success
from dadosbr.core.cache import DiskCache
from dadosbr.core.http import http_get_bytes, http_get_bytes_cached, http_response_metadata
from dadosbr.core.utils import parse_maybe_br_decimal, sha256_json

SOURCE_ID = "cvm_dados_abertos"

_DOC_URLS = {
    "ipe": "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{year}.zip",
    "dfp": "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_{year}.zip",
    "itr": "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/itr_cia_aberta_{year}.zip",
    "fre": "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FRE/DADOS/fre_cia_aberta_{year}.zip",
    "fca": "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FCA/DADOS/fca_cia_aberta_{year}.zip",
}
_DEFAULT_COMPANY_REPORT_TIMEOUT_SECONDS = 10
_DEFAULT_CSV_FIELD_SIZE_LIMIT = 100 * 1024 * 1024
_COMPANY_REPORT_RESPONSE_CACHE_VERSION = 2


def fetch_cvm_company_reports(
    *,
    year: int,
    doc_type: str = "all",
    cvm_code: str = "",
    statement: str = "summary",
    limit: int = 200,
) -> dict:
    safe_limit = max(1, min(int(limit or 200), 2000))
    safe_doc = str(doc_type or "all").lower()
    safe_statement = str(statement or "summary").lower()
    valid_docs = {"all", "ipe", "dfp", "itr", "fre", "fca"}
    if safe_doc not in valid_docs:
        return make_failure(
            DataSourceError(
                "validation_error",
                f"Invalid doc_type '{doc_type}'. Expected one of {sorted(valid_docs)}",
                SOURCE_ID,
            )
        ).model_dump(mode="json")

    doc_list = ["ipe", "dfp", "itr", "fre", "fca"] if safe_doc == "all" else [safe_doc]
    records: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    source_urls: list[str] = []
    source_mode = "live"
    resilience: dict[str, Any] = {}
    cache_limitations: list[str] = []
    cache_key = _company_report_response_cache_key(
        year=int(year),
        doc_type=safe_doc,
        cvm_code=cvm_code,
        statement=safe_statement,
        limit=safe_limit,
    )
    cached_response = _cached_company_report_response(cache_key)
    if cached_response is not None:
        return cached_response

    for doc in doc_list:
        url = _DOC_URLS[doc].format(year=int(year))
        source_urls.append(url)
        try:
            body, headers = _fetch_company_report_zip(url)
            source_mode = _accumulate_http_metadata(
                headers,
                source_url=url,
                source_mode=source_mode,
                resilience=resilience,
                limitations=cache_limitations,
            )
            with zipfile.ZipFile(BytesIO(body)) as zf:
                members = [m for m in zf.namelist() if m.lower().endswith(".csv")]
                selected_members = _select_company_members(members, doc, safe_statement)
                for member in selected_members:
                    for row in _iter_csv_rows(zf, member):
                        if cvm_code and _cvm_code_key(_row_cvm_code(row)) != _cvm_code_key(cvm_code):
                            continue
                        normalized = _normalize_company_row(row, doc, member)
                        records.append(normalized)
                        if len(records) >= safe_limit:
                            break
                    if len(records) >= safe_limit:
                        break
        except DataSourceError as exc:
            failures.append({"source": url, "error": exc.message})
        except Exception as exc:  # noqa: BLE001
            failures.append({"source": url, "error": str(exc)})
        if len(records) >= safe_limit:
            break

    if not records and failures:
        return make_failure(
            DataSourceError(
                "source_unavailable",
                "No company report data could be retrieved from CVM datasets.",
                SOURCE_ID,
                source_url=source_urls[0] if source_urls else None,
                details={"failures": failures},
            )
        ).model_dump(mode="json")

    limitations = list(cache_limitations)
    if safe_statement != "summary":
        limitations.append(
            "Detailed statements are most complete for DFP/ITR; FRE/FCA/IPE are metadata-oriented."
        )
    response = make_success(
        source_id=SOURCE_ID,
        source_url=";".join(source_urls),
        records=records[:safe_limit],
        raw_sha256=sha256_json(records),
        limitations=limitations,
        source_mode=source_mode,
        resilience=resilience,
    ).model_dump(mode="json")
    response["failures"] = failures
    _set_cached_company_report_response(cache_key, response)
    return response


def fetch_cvm_company_reports_batch(
    *,
    year: int,
    doc_type: str = "dfp",
    cvm_codes: str | list[str],
    statement: str = "financials",
    limit_per_code: int = 2000,
) -> dict:
    safe_limit = max(1, min(int(limit_per_code or 2000), 2000))
    safe_doc = str(doc_type or "dfp").lower()
    safe_statement = str(statement or "financials").lower()
    valid_docs = {"all", "ipe", "dfp", "itr", "fre", "fca"}
    if safe_doc not in valid_docs:
        return make_failure(
            DataSourceError(
                "validation_error",
                f"Invalid doc_type '{doc_type}'. Expected one of {sorted(valid_docs)}",
                SOURCE_ID,
            )
        ).model_dump(mode="json")

    codes = _normalize_cvm_code_list(cvm_codes)
    if not codes:
        return make_failure(
            DataSourceError(
                "validation_error",
                "At least one CVM code is required.",
                SOURCE_ID,
            )
        ).model_dump(mode="json")

    doc_list = ["ipe", "dfp", "itr", "fre", "fca"] if safe_doc == "all" else [safe_doc]
    records: list[dict[str, Any]] = []
    counts_by_code = dict.fromkeys(codes, 0)
    failures: list[dict[str, str]] = []
    source_urls: list[str] = []
    source_mode = "live"
    resilience: dict[str, Any] = {}
    cache_limitations: list[str] = []
    cache_key = _company_report_response_cache_key(
        year=int(year),
        doc_type=safe_doc,
        cvm_code="batch:" + ",".join(codes),
        statement=safe_statement,
        limit=safe_limit,
    )
    cached_response = _cached_company_report_response(cache_key)
    if cached_response is not None:
        return cached_response

    for doc in doc_list:
        url = _DOC_URLS[doc].format(year=int(year))
        source_urls.append(url)
        try:
            body, headers = _fetch_company_report_zip(url)
            source_mode = _accumulate_http_metadata(
                headers,
                source_url=url,
                source_mode=source_mode,
                resilience=resilience,
                limitations=cache_limitations,
            )
            with zipfile.ZipFile(BytesIO(body)) as zf:
                members = [m for m in zf.namelist() if m.lower().endswith(".csv")]
                selected_members = _select_company_members(members, doc, safe_statement)
                for member in selected_members:
                    for row in _iter_csv_rows(zf, member):
                        row_code = _cvm_code_key(_row_cvm_code(row))
                        if row_code not in counts_by_code or counts_by_code[row_code] >= safe_limit:
                            continue
                        records.append(_normalize_company_row(row, doc, member))
                        counts_by_code[row_code] += 1
                    if all(count >= safe_limit for count in counts_by_code.values()):
                        break
        except DataSourceError as exc:
            failures.append({"source": url, "error": exc.message})
        except Exception as exc:  # noqa: BLE001
            failures.append({"source": url, "error": str(exc)})
        if all(count >= safe_limit for count in counts_by_code.values()):
            break

    if not records and failures:
        return make_failure(
            DataSourceError(
                "source_unavailable",
                "No company report data could be retrieved from CVM datasets.",
                SOURCE_ID,
                source_url=source_urls[0] if source_urls else None,
                details={"failures": failures},
            )
        ).model_dump(mode="json")

    limitations = list(cache_limitations)
    if safe_statement != "summary":
        limitations.append(
            "Detailed statements are most complete for DFP/ITR; FRE/FCA/IPE are metadata-oriented."
        )
    response = make_success(
        source_id=SOURCE_ID,
        source_url=";".join(source_urls),
        records=records,
        raw_sha256=sha256_json(records),
        limitations=limitations,
        source_mode=source_mode,
        resilience=resilience,
    ).model_dump(mode="json")
    response["failures"] = failures
    response["record_counts_by_cvm_code"] = counts_by_code
    _set_cached_company_report_response(cache_key, response)
    return response


def fetch_cvm_fund_daily(*, cnpj: str = "", date: str = "", limit: int = 200) -> dict:
    safe_limit = max(1, min(int(limit or 200), 5000))
    candidates = _month_candidates(date)
    failures: list[dict[str, str]] = []
    records: list[dict] = []
    source_url = ""
    source_mode = "live"
    resilience: dict[str, Any] = {}
    cache_limitations: list[str] = []
    for ym in candidates:
        source_url = f"https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_{ym}.zip"
        try:
            body, headers = _fetch_cvm_zip(source_url, cache_namespace="cvm_fund_daily")
            source_mode = _accumulate_http_metadata(
                headers,
                source_url=source_url,
                source_mode=source_mode,
                resilience=resilience,
                limitations=cache_limitations,
            )
            with zipfile.ZipFile(BytesIO(body)) as zf:
                members = [m for m in zf.namelist() if m.lower().endswith(".csv")]
                for member in members:
                    for row in _iter_csv_rows(zf, member):
                        row_cnpj = str(row.get("CNPJ_FUNDO_CLASSE", row.get("CNPJ_FUNDO", "")))
                        if cnpj and _digits(row_cnpj) != _digits(cnpj):
                            continue
                        records.append(
                            {
                                "cnpj": row_cnpj,
                                "observed_at": _csv_date_to_iso(row.get("DT_COMPTC", "")),
                                "total_value": parse_maybe_br_decimal(row.get("VL_TOTAL")),
                                "quota_value": parse_maybe_br_decimal(row.get("VL_QUOTA")),
                                "net_worth": parse_maybe_br_decimal(row.get("VL_PATRIM_LIQ")),
                                "investors": _safe_int(row.get("NR_COTST")),
                            }
                        )
                        if len(records) >= safe_limit:
                            break
                    if len(records) >= safe_limit:
                        break
        except Exception as exc:  # noqa: BLE001
            failures.append({"source": source_url, "error": str(exc)})
        if records:
            break
    if not records and failures:
        return make_failure(
            DataSourceError(
                "source_unavailable",
                "No CVM fund daily records were retrieved.",
                SOURCE_ID,
                source_url=source_url,
                details={"failures": failures},
            )
        ).model_dump(mode="json")
    response = make_success(
        source_id=SOURCE_ID,
        source_url=source_url,
        records=records[:safe_limit],
        raw_sha256=sha256_json(records),
        limitations=cache_limitations,
        source_mode=source_mode,
        resilience=resilience,
    ).model_dump(mode="json")
    response["failures"] = failures
    return response


def fetch_cvm_fund_portfolio(*, cnpj: str = "", date: str = "", limit: int = 200) -> dict:
    safe_limit = max(1, min(int(limit or 200), 5000))
    candidates = _month_candidates(date)
    failures: list[dict[str, str]] = []
    records: list[dict] = []
    source_url = ""
    source_mode = "live"
    resilience: dict[str, Any] = {}
    cache_limitations: list[str] = []
    for ym in candidates:
        source_url = f"https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/cda_fi_{ym}.zip"
        try:
            body, headers = _fetch_cvm_zip(source_url, cache_namespace="cvm_fund_portfolio")
            source_mode = _accumulate_http_metadata(
                headers,
                source_url=source_url,
                source_mode=source_mode,
                resilience=resilience,
                limitations=cache_limitations,
            )
            with zipfile.ZipFile(BytesIO(body)) as zf:
                members = [m for m in zf.namelist() if m.lower().endswith(".csv")]
                for member in members:
                    for row in _iter_csv_rows(zf, member):
                        row_cnpj = str(row.get("CNPJ_FUNDO_CLASSE", row.get("CNPJ_FUNDO", "")))
                        if cnpj and _digits(row_cnpj) != _digits(cnpj):
                            continue
                        records.append(
                            {
                                "cnpj": row_cnpj,
                                "observed_at": _csv_date_to_iso(row.get("DT_COMPTC", "")),
                                "fund_name": row.get("DENOM_SOCIAL", ""),
                                "asset_type": row.get("TP_ATIVO", row.get("TP_APLIC", "")),
                                "asset_code": row.get("CD_ATIVO", row.get("CD_APLIC", "")),
                                "issuer": row.get("NM_EMISSOR", row.get("EMISSOR", "")),
                                "market_value": parse_maybe_br_decimal(row.get("VL_MERC_POS_FINAL")),
                                "is_confidential_member": "confid" in member.lower(),
                            }
                        )
                        if len(records) >= safe_limit:
                            break
                    if len(records) >= safe_limit:
                        break
        except Exception as exc:  # noqa: BLE001
            failures.append({"source": source_url, "error": str(exc)})
        if records:
            break
    if not records and failures:
        return make_failure(
            DataSourceError(
                "source_unavailable",
                "No CVM fund portfolio records were retrieved.",
                SOURCE_ID,
                source_url=source_url,
                details={"failures": failures},
            )
        ).model_dump(mode="json")
    response = make_success(
        source_id=SOURCE_ID,
        source_url=source_url,
        records=records[:safe_limit],
        raw_sha256=sha256_json(records),
        limitations=cache_limitations,
        source_mode=source_mode,
        resilience=resilience,
    ).model_dump(mode="json")
    response["failures"] = failures
    return response


def fetch_cvm_fii_monthly(
    *,
    cnpj: str = "",
    year: int = 0,
    month: int = 0,
    limit: int = 200,
) -> dict:
    safe_limit = max(1, min(int(limit or 200), 5000))
    years = [year] if year else [datetime.now(UTC).year, datetime.now(UTC).year - 1]
    failures: list[dict[str, str]] = []
    records: list[dict] = []
    source_url = ""
    source_mode = "live"
    resilience: dict[str, Any] = {}
    cache_limitations: list[str] = []
    for current_year in years:
        source_url = f"https://dados.cvm.gov.br/dados/FII/DOC/INF_MENSAL/DADOS/inf_mensal_fii_{int(current_year)}.zip"
        try:
            body, headers = _fetch_cvm_zip(source_url, cache_namespace="cvm_fii_monthly")
            source_mode = _accumulate_http_metadata(
                headers,
                source_url=source_url,
                source_mode=source_mode,
                resilience=resilience,
                limitations=cache_limitations,
            )
            with zipfile.ZipFile(BytesIO(body)) as zf:
                merged: dict[tuple[str, str], dict[str, Any]] = {}
                for member in sorted(m for m in zf.namelist() if m.lower().endswith(".csv")):
                    for row in _iter_csv_rows(zf, member):
                        row_cnpj = _first_value(row, "CNPJ_FUNDO", "CNPJ_FUNDO_CLASSE", "CNPJ_Fundo_Classe")
                        if cnpj and _digits(row_cnpj) != _digits(cnpj):
                            continue
                        dt = _first_value(row, "DT_COMPTC", "DATA_REFERENCIA", "Data_Referencia")
                        if month and dt and _safe_month(dt) != month:
                            continue
                        observed_at = _csv_date_to_iso(dt)
                        key = (_digits(row_cnpj), observed_at)
                        record = merged.setdefault(
                            key,
                            {
                                "cnpj": row_cnpj,
                                "fund_name": "",
                                "observed_at": observed_at,
                                "patrimonio_liquido": None,
                                "valor_cota": None,
                                "cotistas": None,
                                "captacao_no_mes": None,
                                "resgate_no_mes": None,
                                "cotas_emitidas": None,
                                "valor_ativo": None,
                                "isin": "",
                                "segmento_atuacao": "",
                                "tipo_gestao": "",
                                "dividend_yield_month": None,
                                "source_members": [],
                            },
                        )
                        _merge_fii_monthly_record(record, row, member)
                records.extend(sorted(merged.values(), key=lambda item: str(item.get("observed_at", "")))[:safe_limit])
        except Exception as exc:  # noqa: BLE001
            failures.append({"source": source_url, "error": str(exc)})
        if records:
            break
    if not records and failures:
        return make_failure(
            DataSourceError(
                "source_unavailable",
                "No CVM FII monthly records were retrieved.",
                SOURCE_ID,
                source_url=source_url,
                details={"failures": failures},
            )
        ).model_dump(mode="json")
    response = make_success(
        source_id=SOURCE_ID,
        source_url=source_url,
        records=records[:safe_limit],
        raw_sha256=sha256_json(records),
        limitations=cache_limitations,
        source_mode=source_mode,
        resilience=resilience,
    ).model_dump(mode="json")
    response["failures"] = failures
    return response


def _read_csv_rows(zf: zipfile.ZipFile, member: str) -> list[dict[str, str]]:
    return list(_iter_csv_rows(zf, member))


def _merge_fii_monthly_record(record: dict[str, Any], row: dict[str, str], member: str) -> None:
    members = record.setdefault("source_members", [])
    if member not in members:
        members.append(member)
    _set_if_text(record, "cnpj", _first_value(row, "CNPJ_FUNDO", "CNPJ_FUNDO_CLASSE", "CNPJ_Fundo_Classe"))
    _set_if_text(record, "fund_name", _first_value(row, "DENOM_SOCIAL", "NOME_FUNDO_CLASSE", "Nome_Fundo_Classe"))
    _set_if_text(record, "isin", _first_value(row, "CD_ISIN", "CODIGO_ISIN", "Codigo_ISIN"))
    _set_if_text(record, "segmento_atuacao", _first_value(row, "SEGMENTO_ATUACAO", "Segmento_Atuacao"))
    _set_if_text(record, "tipo_gestao", _first_value(row, "TIPO_GESTAO", "Tipo_Gestao"))
    _set_if_number(record, "patrimonio_liquido", _first_decimal(row, "VL_PATRIM_LIQ", "PATRIMONIO_LIQUIDO", "Patrimonio_Liquido"))
    _set_if_number(record, "valor_cota", _first_decimal(row, "VL_QUOTA", "VALOR_PATRIMONIAL_COTAS", "Valor_Patrimonial_Cotas"))
    _set_if_number(record, "cotistas", _safe_int(_first_value(row, "NR_COTST", "TOTAL_NUMERO_COTISTAS", "Total_Numero_Cotistas")))
    _set_if_number(record, "captacao_no_mes", _first_decimal(row, "CAPTC_DIA", "CAPTACAO_MES", "Captacao_Mes"))
    _set_if_number(record, "resgate_no_mes", _first_decimal(row, "RESG_DIA", "RESGATE_MES", "Resgate_Mes"))
    _set_if_number(record, "cotas_emitidas", _first_decimal(row, "QT_COTAS", "QUANTIDADE_COTAS_EMITIDAS", "Quantidade_Cotas_Emitidas"))
    _set_if_number(record, "valor_ativo", _first_decimal(row, "VL_TOTAL", "VALOR_ATIVO", "Valor_Ativo"))
    _set_if_number(record, "dividend_yield_month", _first_decimal(row, "PERCENTUAL_DIVIDEND_YIELD_MES", "Percentual_Dividend_Yield_Mes"))


def _set_if_text(record: dict[str, Any], field: str, value: str) -> None:
    if value and not record.get(field):
        record[field] = value


def _set_if_number(record: dict[str, Any], field: str, value: Any) -> None:
    if value is not None and record.get(field) is None:
        record[field] = value


def _first_decimal(row: dict[str, str], *keys: str) -> float | None:
    return parse_maybe_br_decimal(_first_value(row, *keys))


def _fetch_company_report_zip(url: str) -> tuple[bytes, dict[str, str]]:
    return _fetch_cvm_zip(url, cache_namespace="cvm_company_reports", timeout_seconds=_company_report_timeout_seconds())


def _fetch_cvm_zip(
    url: str,
    *,
    cache_namespace: str,
    timeout_seconds: int = 90,
) -> tuple[bytes, dict[str, str]]:
    return http_get_bytes_cached(
        url,
        source_id=SOURCE_ID,
        timeout_seconds=timeout_seconds,
        cache_namespace=cache_namespace,
        fetcher=http_get_bytes,
    )


def _accumulate_http_metadata(
    headers: dict[str, str],
    *,
    source_url: str,
    source_mode: str,
    resilience: dict[str, Any],
    limitations: list[str],
) -> str:
    current_mode, current_resilience, current_limitations = http_response_metadata(headers)
    if current_resilience:
        entries = resilience.setdefault("http", [])
        entries.append({"source_url": source_url, **current_resilience})
    limitations.extend(current_limitations)
    if current_mode == "stale_cache":
        return "stale_cache"
    if source_mode == "live" and current_mode == "cache_hit":
        return "cache_hit"
    return source_mode


def _company_report_response_cache_key(
    *,
    year: int,
    doc_type: str,
    cvm_code: str,
    statement: str,
    limit: int,
) -> str:
    return json.dumps(
        {
            "year": year,
            "doc_type": doc_type,
            "cvm_code": _cvm_code_key(cvm_code),
            "statement": statement,
            "limit": limit,
            "parser_version": _COMPANY_REPORT_RESPONSE_CACHE_VERSION,
        },
        sort_keys=True,
    )


def _cached_company_report_response(cache_key: str) -> dict[str, Any] | None:
    if _http_cache_disabled():
        return None
    cached = _company_report_response_cache().get(cache_key)
    return cached if isinstance(cached, dict) else None


def _set_cached_company_report_response(cache_key: str, response: dict[str, Any]) -> None:
    if _http_cache_disabled():
        return
    _company_report_response_cache().set(cache_key, response)


def _company_report_response_cache() -> DiskCache:
    root = Path(os.getenv("DADOSBR_CACHE_DIR", ".dadosbr/cache"))
    return DiskCache(root / "cvm_company_report_responses", ttl_seconds=_cache_ttl_seconds())


def _cache_ttl_seconds() -> int:
    raw = os.getenv("DADOSBR_CACHE_TTL_SECONDS", "3600")
    try:
        return max(0, int(raw))
    except ValueError:
        return 3600


def _http_cache_disabled() -> bool:
    return os.getenv("DADOSBR_DISABLE_HTTP_CACHE", "").strip().lower() in {"1", "true", "yes", "on"}


def _iter_csv_rows(zf: zipfile.ZipFile, member: str):
    _configure_csv_field_size_limit()
    with zf.open(member) as file:
        wrapper = TextIOWrapper(file, encoding="latin-1")
        reader = csv.DictReader(wrapper, delimiter=";")
        for row in reader:
            yield dict(row)


def _configure_csv_field_size_limit() -> None:
    raw = os.getenv("DADOSBR_CSV_FIELD_SIZE_LIMIT", str(_DEFAULT_CSV_FIELD_SIZE_LIMIT))
    try:
        requested = max(csv.field_size_limit(), int(raw))
    except ValueError:
        requested = _DEFAULT_CSV_FIELD_SIZE_LIMIT
    while requested > 0:
        try:
            csv.field_size_limit(requested)
            return
        except OverflowError:
            requested //= 10


def _select_company_members(members: list[str], doc_type: str, statement: str) -> list[str]:
    if statement == "summary":
        exact = f"{doc_type}_cia_aberta_"
        selected = [m for m in members if m.lower().startswith(exact) and m.lower().count("_") <= 3]
        if selected:
            return selected
    if statement in {"financial", "financials"}:
        markers = ("_bpa_", "_bpp_", "_dre_", "_dfc_", "_dmpl_", "_dva_")
        selected = [m for m in members if any(marker in m.lower() for marker in markers)]
        if selected:
            return selected
    if statement == "all":
        return members
    if statement == "capital":
        return [m for m in members if "composicao_capital" in m.lower()]
    return [m for m in members if f"_{statement}_" in m.lower()]


def _company_report_timeout_seconds() -> int:
    raw = os.getenv(
        "DADOSBR_CVM_COMPANY_REPORT_TIMEOUT_SECONDS",
        str(_DEFAULT_COMPANY_REPORT_TIMEOUT_SECONDS),
    )
    try:
        return max(1, min(int(raw), 90))
    except ValueError:
        return _DEFAULT_COMPANY_REPORT_TIMEOUT_SECONDS


def _normalize_company_row(row: dict[str, str], doc_type: str, member: str) -> dict[str, Any]:
    cvm_code_raw = _row_cvm_code(row)
    ref_date = _first_value(row, "DT_REFER", "DT_REFERENCIA", "DATA_REFERENCIA")
    value = parse_maybe_br_decimal(row.get("VL_CONTA"))
    return {
        "doc_type": doc_type,
        "member": member,
        "record_type": "statement" if value is not None else "summary",
        "company_name": _first_value(
            row,
            "DENOM_CIA",
            "DENOM_SOCIAL",
            "NOME_CIA",
            "NOME_EMPRESARIAL",
            "NOME_COMPANHIA",
        ),
        "cvm_code": _cvm_code_key(cvm_code_raw),
        "cvm_code_raw": cvm_code_raw,
        "cnpj": _first_value(row, "CNPJ_CIA", "CNPJ", "CNPJ_EMISSOR", "CNPJ_COMPANHIA"),
        "observed_at": _csv_date_to_iso(ref_date),
        "account_code": row.get("CD_CONTA", ""),
        "account_name": row.get("DS_CONTA", ""),
        "value": value,
        "currency": row.get("MOEDA", ""),
        "scale": row.get("ESCALA_MOEDA", ""),
        "document_category": _first_value(row, "CATEG_DOC", "CATEGORIA"),
        "document_type": _first_value(row, "TIPO"),
        "document_species": _first_value(row, "ESPECIE"),
        "subject": _first_value(row, "ASSUNTO"),
        "delivered_at": _csv_date_to_iso(_first_value(row, "DT_RECEB", "DATA_ENTREGA")),
        "protocol": _first_value(row, "ID_DOC", "PROTOCOLO_ENTREGA"),
        "download_url": _first_value(row, "LINK_DOC", "LINK_DOWNLOAD"),
    }


def _row_cvm_code(row: dict[str, str]) -> str:
    return _first_value(row, "CD_CVM", "CD_CVM_CIA", "COD_CVM", "CD_CVM_EMISSOR", "CODIGO_CVM")


def _cvm_code_key(value: str) -> str:
    digits = _digits(value)
    if not digits:
        return ""
    return digits.lstrip("0") or "0"


def _normalize_cvm_code_list(cvm_codes: str | list[str]) -> list[str]:
    parts = str(cvm_codes or "").split(",") if isinstance(cvm_codes, str) else cvm_codes
    seen: set[str] = set()
    codes: list[str] = []
    for part in parts:
        code = _cvm_code_key(str(part))
        if code and code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


def _first_value(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    folded = {key.upper(): value for key, value in row.items()}
    for key in keys:
        value = folded.get(key.upper())
        if value not in (None, ""):
            return str(value)
    return ""


def _digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _month_candidates(date: str, months_back: int = 6) -> list[str]:
    raw = str(date or "").strip()
    if raw and raw != "latest":
        if len(raw) == 7:
            return [raw.replace("-", "")]
        if len(raw) == 10:
            return [raw[:7].replace("-", "")]
        if len(raw) == 6 and raw.isdigit():
            return [raw]
        return []
    values: list[str] = []
    now = datetime.now(UTC)
    y = now.year
    m = now.month
    for _ in range(months_back):
        values.append(f"{y}{m:02d}")
        m -= 1
        if m == 0:
            y -= 1
            m = 12
    return values


def _csv_date_to_iso(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "-" in raw and len(raw) >= 10:
        return raw[:10]
    if "/" in raw:
        day, month, year = raw.split("/")
        return f"{year}-{month}-{day}"
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return raw


def _safe_int(value: Any) -> int | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def _safe_month(date_text: str) -> int:
    iso = _csv_date_to_iso(date_text)
    if len(iso) >= 7:
        return int(iso[5:7])
    return 0
