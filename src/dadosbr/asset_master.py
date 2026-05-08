from __future__ import annotations

from pathlib import Path
from typing import Any

from dadosbr.connectors.b3 import fetch_b3_cotahist, parse_b3_cotahist_file
from dadosbr.connectors.comex import fetch_comex_table
from dadosbr.connectors.receita_cnpj import get_cnpj_company, search_cnpj_companies
from dadosbr.core import DataSourceError, make_failure, make_success
from dadosbr.core.utils import sha256_json

SOURCE_ID = "asset_master"


def canonical_instrument_from_b3_quote(row: dict[str, Any]) -> dict[str, Any]:
    ticker = str(row.get("ticker", "")).strip().upper()
    return {
        "instrument_id": f"B3:{ticker}",
        "asset_id": f"B3:{ticker}",
        "asset_type": "b3_listed_security",
        "ticker": ticker,
        "exchange": "B3",
        "isin": str(row.get("isin", "")).strip(),
        "market_type": str(row.get("market_type", "")).strip(),
        "short_name": str(row.get("short_name", "")).strip(),
        "specification": str(row.get("specification", "")).strip(),
        "currency": str(row.get("currency_ref", "")).strip(),
        "issuer_name_hint": str(row.get("short_name", "")).strip(),
        "last_observed_at": row.get("observed_at"),
        "last_close_price": row.get("close_price"),
        "source_refs": [{"source_id": "b3_cotahist", "field": "ticker"}],
    }


def canonical_tesouro_instrument(row: dict[str, Any]) -> dict[str, Any]:
    bond_type = str(row.get("bond_type", "")).strip()
    maturity = str(row.get("maturity_date", "")).strip()
    slug = "_".join(bond_type.upper().split())
    return {
        "instrument_id": f"TESOURO:{slug}:{maturity}",
        "asset_id": f"TESOURO:{slug}:{maturity}",
        "asset_type": "public_bond",
        "issuer_id": "BR_GOV:FEDERAL_TREASURY",
        "issuer_name": "Tesouro Nacional",
        "bond_type": bond_type,
        "maturity_date": maturity,
        "last_observed_at": row.get("observed_at"),
        "source_refs": [{"source_id": "tesouro_transparente", "field": "bond_type"}],
    }


def canonical_issuer_from_cnpj(row: dict[str, Any]) -> dict[str, Any]:
    cnpj = _digits(str(row.get("cnpj", "")))
    return {
        "issuer_id": f"BR_CNPJ:{cnpj}",
        "asset_id": f"BR_CNPJ:{cnpj}",
        "asset_type": "issuer",
        "issuer_type": "company",
        "cnpj": cnpj,
        "legal_name": str(row.get("razao_social", "")).strip(),
        "trading_name": str(row.get("nome_fantasia", "")).strip(),
        "uf": str(row.get("uf", "")).strip(),
        "registration_status": str(row.get("situacao_cadastral", "")).strip(),
        "main_cnae": str(row.get("cnae_principal", "")).strip(),
        "source_refs": [{"source_id": "receita_cnpj", "field": "cnpj"}],
    }


def canonical_fund_from_cvm_record(row: dict[str, Any]) -> dict[str, Any]:
    cnpj = _digits(str(row.get("cnpj", "")))
    name = str(row.get("fund_name", "") or row.get("company_name", "")).strip()
    return {
        "instrument_id": f"CVM_FUND:{cnpj}",
        "asset_id": f"CVM_FUND:{cnpj}",
        "asset_type": "fund",
        "cnpj": cnpj,
        "name": name,
        "last_observed_at": row.get("observed_at"),
        "source_refs": [{"source_id": "cvm_dados_abertos", "field": "cnpj"}],
    }


def build_asset_master_snapshot(
    *,
    b3_quotes: list[dict[str, Any]] | None = None,
    cnpj_companies: list[dict[str, Any]] | None = None,
    cvm_funds: list[dict[str, Any]] | None = None,
    tesouro_rates: list[dict[str, Any]] | None = None,
) -> dict:
    records: list[dict[str, Any]] = []
    for row in b3_quotes or []:
        records.append(canonical_instrument_from_b3_quote(row))
    for row in cnpj_companies or []:
        records.append(canonical_issuer_from_cnpj(row))
    for row in cvm_funds or []:
        records.append(canonical_fund_from_cvm_record(row))
    for row in tesouro_rates or []:
        records.append(canonical_tesouro_instrument(row))
    return make_success(
        source_id=SOURCE_ID,
        source_url="local://dadosbr/asset-master",
        records=records,
        raw_sha256=sha256_json(records),
        limitations=["Derived master records depend on source sync freshness."],
    ).model_dump(mode="json")


def get_issuer_master(cnpj: str, db_path: str | Path | None = None) -> dict:
    response = get_cnpj_company(cnpj, db_path=db_path)
    if not response.get("ok"):
        return response
    records = [canonical_issuer_from_cnpj(row) for row in response.get("records", [])]
    return make_success(
        source_id=SOURCE_ID,
        source_url=str(db_path or "local://receita-cnpj-index"),
        records=records,
        raw_sha256=sha256_json(records),
    ).model_dump(mode="json")


def get_instrument_master(ticker: str, b3_file_path: str = "", limit: int = 1) -> dict:
    if b3_file_path:
        response = parse_b3_cotahist_file(b3_file_path, ticker=ticker, limit=limit)
    else:
        response = fetch_b3_cotahist(ticker=ticker, limit=limit)
    if not response.get("ok"):
        return response
    records = [canonical_instrument_from_b3_quote(row) for row in response.get("records", [])]
    return make_success(
        source_id=SOURCE_ID,
        source_url=response.get("source_url", ""),
        records=records,
        raw_sha256=sha256_json(records),
    ).model_dump(mode="json")


def search_asset_master(
    q: str = "",
    asset_type: str = "all",
    issuer_cnpj: str = "",
    limit: int = 50,
    db_path: str | Path | None = None,
    b3_file_path: str = "",
) -> dict:
    records: list[dict[str, Any]] = []
    normalized_type = str(asset_type or "all").strip().lower()

    if normalized_type in {"all", "issuer"}:
        if issuer_cnpj:
            issuer = get_issuer_master(issuer_cnpj, db_path=db_path)
            if issuer.get("ok"):
                records.extend(issuer.get("records", []))
        else:
            response = search_cnpj_companies(q=q, limit=limit, db_path=db_path)
            if response.get("ok"):
                records.extend(canonical_issuer_from_cnpj(row) for row in response.get("records", []))

    if normalized_type in {"all", "instrument"} and q and b3_file_path:
        instrument = get_instrument_master(q, b3_file_path=b3_file_path, limit=limit)
        if instrument.get("ok"):
            records.extend(instrument.get("records", []))

    return make_success(
        source_id=SOURCE_ID,
        source_url="local://dadosbr/asset-master/search",
        records=records[: max(1, min(int(limit or 50), 1000))],
        raw_sha256=sha256_json(records),
    ).model_dump(mode="json")


def get_asset_master(asset_id: str, db_path: str | Path | None = None, b3_file_path: str = "") -> dict:
    raw = str(asset_id or "").strip()
    if not raw:
        return make_failure(DataSourceError("validation_error", "asset_id is required", SOURCE_ID)).model_dump(mode="json")
    digits = _digits(raw)
    if len(digits) == 14:
        return get_issuer_master(digits, db_path=db_path)
    ticker = raw.split(":", 1)[1] if raw.upper().startswith("B3:") else raw
    return get_instrument_master(ticker, b3_file_path=b3_file_path)


def get_cnae_taxonomy(code: str, db_path: str | Path | None = None) -> dict:
    import sqlite3

    db_file = Path(db_path) if db_path else Path(".dadosbr") / "datasets" / "receita_cnpj" / "index" / "cnpj.sqlite"
    if not db_file.exists():
        return make_failure(
            DataSourceError("index_missing", "CNPJ index not found for CNAE taxonomy.", SOURCE_ID, source_url=str(db_file))
        ).model_dump(mode="json")
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT code, description FROM cnaes WHERE code = ?", (str(code),)).fetchone()
        records = [dict(row)] if row else []
        return make_success(
            source_id=SOURCE_ID,
            source_url=str(db_file),
            records=records,
            raw_sha256=sha256_json(records),
        ).model_dump(mode="json")
    finally:
        conn.close()


def get_ncm_taxonomy(code: str) -> dict:
    response = fetch_comex_table("NCM", limit=10000)
    if not response.get("ok"):
        return response
    records = [
        {"code": row.get("CO_NCM", ""), "description": row.get("NO_NCM_POR", "")}
        for row in response.get("records", [])
        if row.get("CO_NCM", "") == str(code)
    ]
    return make_success(
        source_id=SOURCE_ID,
        source_url=response.get("source_url", ""),
        records=records,
        raw_sha256=sha256_json(records),
    ).model_dump(mode="json")


def _digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())
