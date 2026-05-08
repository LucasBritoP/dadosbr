from __future__ import annotations

import csv
import unicodedata
from io import StringIO
from urllib.parse import urlencode

from dadosbr.core import DataSourceError, make_failure, make_success
from dadosbr.core.csv_stream import decode_text
from dadosbr.core.http import http_get_bytes, http_get_bytes_cached, http_response_metadata, parse_json_bytes
from dadosbr.core.utils import sha256_bytes, sha256_json

SOURCE_ID = "bndes_dados_abertos"
CKAN_BASE = "https://dadosabertos.bndes.gov.br/api/3/action/"
OPERACOES_PACKAGE = "operacoes-financiamento"
OPERACOES_PACKAGE_ID = "10e21ad1-568e-45e5-a8af-43f2c05ef1a2"
OPERACOES_RESOURCE_ID = "6f56b78c-510f-44b6-8274-78a5b7e931f4"
RENDA_VARIAVEL_PACKAGE = "renda-variavel"
RENDA_VARIAVEL_PACKAGE_ID = "0f87a724-3025-4e2d-a707-ea4d5cfeb9a5"


def package_show(package_id_or_name: str) -> dict:
    url = CKAN_BASE + "package_show?" + urlencode({"id": package_id_or_name})
    body, _headers = _fetch_bndes_bytes(url, timeout_seconds=60)
    payload = parse_json_bytes(body, source_id=SOURCE_ID, source_url=url)
    if not payload.get("success"):
        raise DataSourceError("invalid_response", "CKAN package_show returned success=false", SOURCE_ID, source_url=url)
    return payload


def select_csv_resource(package: dict, resource_id: str = "", name_contains: str = "") -> dict:
    resources = package.get("result", {}).get("resources", [])
    if resource_id:
        for resource in resources:
            if resource.get("id") == resource_id:
                return resource
    needle = _text_key(name_contains)
    if needle:
        for resource in resources:
            if str(resource.get("format", "")).upper() == "CSV" and needle in _resource_key(resource):
                return resource
        raise DataSourceError("invalid_response", f"CSV resource containing '{name_contains}' not found in package", SOURCE_ID)
    for resource in resources:
        if str(resource.get("format", "")).upper() == "CSV":
            return resource
    raise DataSourceError("invalid_response", "CSV resource not found in package", SOURCE_ID)


def fetch_resource_csv(resource: dict, encoding: str = "windows-1252") -> list[dict[str, str]]:
    resource_url = str(resource.get("url", "")).strip()
    if not resource_url:
        raise DataSourceError("invalid_response", "Resource URL missing", SOURCE_ID)
    raw, _headers = _fetch_bndes_bytes(resource_url, timeout_seconds=120)
    text = decode_text(raw, encodings=(encoding, "utf-8-sig", "latin-1"))
    return [dict(row) for row in csv.DictReader(StringIO(text), delimiter=";")]


def list_bndes_datasets(query: str = "", rows: int = 20) -> dict:
    safe_rows = max(1, min(int(rows or 20), 100))
    params = {"rows": safe_rows}
    if query:
        params["q"] = query
    url = CKAN_BASE + "package_search?" + urlencode(params)
    try:
        body, headers = _fetch_bndes_bytes(url, timeout_seconds=60)
        source_mode, resilience, cache_limitations = http_response_metadata(headers)
        payload = parse_json_bytes(body, source_id=SOURCE_ID, source_url=url)
        if not payload.get("success"):
            raise DataSourceError("invalid_response", "CKAN package_search returned success=false", SOURCE_ID, source_url=url)
        results = payload.get("result", {}).get("results", [])
        records = [
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "title": item.get("title"),
                "license_title": item.get("license_title"),
                "metadata_modified": item.get("metadata_modified"),
            }
            for item in results
        ]
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


def fetch_bndes_operations(
    cnpj: str = "",
    uf: str = "",
    year: int = 0,
    setor: str = "",
    limit: int = 200,
) -> dict:
    safe_limit = max(1, min(int(limit or 200), 5000))
    try:
        package = _load_package_with_fallback(OPERACOES_PACKAGE, OPERACOES_PACKAGE_ID)
        resource = select_csv_resource(package, resource_id=OPERACOES_RESOURCE_ID)
        rows = fetch_resource_csv(resource)
        records: list[dict] = []
        cnpj_digits = _digits(cnpj)
        for row in rows:
            row_cnpj = _digits(row.get("cnpj", ""))
            if cnpj_digits and row_cnpj != cnpj_digits:
                continue
            if uf and str(row.get("uf", "")).upper() != uf.upper():
                continue
            if year:
                row_year = _extract_year(row.get("data_da_contratacao", ""))
                if row_year != int(year):
                    continue
            if setor and setor.lower() not in str(row.get("setor_bndes", "")).lower() and setor.lower() not in str(row.get("setor_cnae", "")).lower():
                continue
            records.append(
                {
                    "cliente": row.get("cliente", ""),
                    "cnpj": row_cnpj,
                    "uf": row.get("uf", ""),
                    "municipio": row.get("municipio", ""),
                    "data_da_contratacao": _normalize_date(row.get("data_da_contratacao", "")),
                    "valor_contratado_reais": _to_float(row.get("valor_contratado_reais")),
                    "valor_desembolsado_reais": _to_float(row.get("valor_desembolsado_reais")),
                    "setor_cnae": row.get("setor_cnae", ""),
                    "setor_bndes": row.get("setor_bndes", ""),
                    "porte_do_cliente": row.get("porte_do_cliente", ""),
                    "situacao_do_contrato": row.get("situacao_do_contrato", ""),
                }
            )
            if len(records) >= safe_limit:
                break
        return make_success(
            source_id=SOURCE_ID,
            source_url=str(resource.get("url", "")),
            records=records,
            raw_sha256=sha256_json(records),
        ).model_dump(mode="json")
    except DataSourceError as exc:
        return make_failure(exc).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        return make_failure(DataSourceError("parse_error", str(exc), SOURCE_ID)).model_dump(mode="json")


def fetch_bndes_variable_income(
    kind: str = "all",
    company: str = "",
    year: int = 0,
    limit: int = 200,
) -> dict:
    safe_limit = max(1, min(int(limit or 200), 5000))
    normalized_kind = str(kind or "all").lower()
    if normalized_kind not in {"all", "debentures", "funds"}:
        return make_failure(
            DataSourceError("validation_error", "kind must be one of all|debentures|funds", SOURCE_ID)
        ).model_dump(mode="json")
    try:
        package = _load_package_with_fallback(RENDA_VARIAVEL_PACKAGE, RENDA_VARIAVEL_PACKAGE_ID)
        selected_resources = []
        if normalized_kind in {"all", "debentures"}:
            selected_resources.append(select_csv_resource(package, name_contains="debent"))
        if normalized_kind in {"all", "funds"}:
            selected_resources.append(select_csv_resource(package, name_contains="fund"))

        records: list[dict] = []
        for resource in selected_resources:
            resource_key = _resource_key(resource)
            rows = fetch_resource_csv(resource)
            current_kind = "debentures" if "debent" in resource_key else "funds"
            for row in rows:
                normalized = _normalize_variable_income_row(row, current_kind)
                if company and company.lower() not in str(normalized.get("company", "")).lower():
                    continue
                if year and normalized.get("year") != int(year):
                    continue
                records.append(normalized)
                if len(records) >= safe_limit:
                    break
            if len(records) >= safe_limit:
                break

        source_url = ";".join(str(resource.get("url", "")) for resource in selected_resources)
        limitations = []
        if normalized_kind in {"all", "debentures"}:
            limitations.append(
                "BNDES debenture CSV usually provides issuer, CNPJ, sector and quantity, not market yield, maturity or indexer."
            )
        return make_success(
            source_id=SOURCE_ID,
            source_url=source_url,
            records=records,
            raw_sha256=sha256_json(records),
            limitations=limitations,
        ).model_dump(mode="json")
    except DataSourceError as exc:
        return make_failure(exc).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        return make_failure(DataSourceError("parse_error", str(exc), SOURCE_ID)).model_dump(mode="json")


def _load_package_with_fallback(name: str, package_id: str) -> dict:
    try:
        return package_show(name)
    except DataSourceError:
        return package_show(package_id)


def _fetch_bndes_bytes(url: str, *, timeout_seconds: int) -> tuple[bytes, dict[str, str]]:
    return http_get_bytes_cached(
        url,
        source_id=SOURCE_ID,
        timeout_seconds=timeout_seconds,
        cache_namespace="bndes",
        fetcher=http_get_bytes,
        max_stale_seconds=30 * 24 * 60 * 60,
    )


def _normalize_variable_income_row(row: dict[str, str], kind: str) -> dict:
    if kind == "debentures":
        company = _row_value(row, "empresa", "razao_social", "razao social", "companhia", "emissor")
        return {
            "kind": "debentures",
            "ticker": _row_value(row, "sigla", "ticker", "codigo_ativo"),
            "company": company,
            "issuer_name": company,
            "cnpj": _digits(_row_value(row, "cnpj", "cnpj_emissor")),
            "year": _to_int(_row_value(row, "ano", "ano_posicao")),
            "asset_type": _row_value(row, "tipo_de_ativo", "tipo_ativo"),
            "sector": _row_value(row, "setor_de_atividade", "setor"),
            "quantity_final": _to_float(_row_value(row, "quantidade_final")),
            "valor_investido": _to_float(_row_value(row, "valor_investido", "invested_value", "valor")),
            "indexer": _row_value(row, "indexer", "indexador"),
            "maturity_date": _normalize_date(_row_value(row, "maturity_date", "data_vencimento", "vencimento")),
            "open_closed": _row_value(row, "aberta_fechada"),
        }
    fund_name = _row_value(row, "nome_do_fundo", "razao_social", "nome_fundo", "fundo")
    return {
        "kind": "funds",
        "ticker": _row_value(row, "sigla", "ticker"),
        "fund_name": fund_name,
        "company": fund_name,
        "issuer_name": fund_name,
        "cnpj": _digits(_row_value(row, "cnpj")),
        "year": _to_int(_row_value(row, "ano", "ano_posicao")),
        "asset_type": _row_value(row, "tipo_de_ativo", "tipo_ativo"),
        "sector": _row_value(row, "setor_de_atividade", "setor"),
        "participacao_total": _to_float(_row_value(row, "participacao_total", "participacao_pp_final", "total_pp")),
    }


def _resource_key(resource: dict) -> str:
    return _text_key(" ".join(str(resource.get(field, "")) for field in ("name", "url", "description")))


def _row_value(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    folded = {_text_key(key): value for key, value in row.items()}
    for key in keys:
        value = folded.get(_text_key(key))
        if value not in (None, ""):
            return str(value)
    return ""


def _text_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return normalized.encode("ascii", "ignore").decode("ascii").lower()


def _digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _to_float(value: str | float | int | None) -> float | None:
    raw = str(value or "").strip()
    if raw == "":
        return None
    raw = raw.replace(".", "").replace(",", ".") if "," in raw and "." in raw else raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def _to_int(value: str | int | None) -> int:
    raw = str(value or "").strip()
    if raw == "":
        return 0
    try:
        return int(float(raw))
    except ValueError:
        return 0


def _extract_year(value: str) -> int:
    text = str(value or "").strip()
    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])
    return 0


def _normalize_date(value: str) -> str:
    text = str(value or "").strip()
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return text
    if "/" in text and len(text) >= 10:
        day, month, year = text[:10].split("/")
        return f"{year}-{month}-{day}"
    return text
