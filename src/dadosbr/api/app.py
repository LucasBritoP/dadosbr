from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, File, Header, HTTPException, UploadFile

from dadosbr.asset_master import (
    get_asset_master,
    get_cnae_taxonomy,
    get_instrument_master,
    get_issuer_master,
    get_ncm_taxonomy,
    search_asset_master,
)
from dadosbr.benchmarks import (
    compare_asset_to_benchmark,
    fetch_benchmark_history,
    get_benchmark_metadata,
    list_benchmarks,
    list_macro_calendar,
)
from dadosbr.connectors import (
    build_cnpj_index,
    download_cnpj_period,
    fetch_b3_cotahist,
    fetch_bndes_operations,
    fetch_bndes_variable_income,
    fetch_comex_municipality,
    fetch_comex_ncm,
    fetch_comex_table,
    fetch_cvm_company_reports,
    fetch_cvm_fii_monthly,
    fetch_cvm_fund_daily,
    fetch_cvm_fund_portfolio,
    fetch_focus_expectations,
    fetch_ibge_sidra,
    fetch_ipea_series,
    fetch_ptax,
    fetch_sgs_series,
    fetch_tesouro_rates,
    get_cnpj_company,
    get_cnpj_partners,
    get_cnpj_status,
    list_bndes_datasets,
    parse_b3_cotahist_bytes,
    search_cnpj_companies,
    summarize_comex_ncm,
)
from dadosbr.corporate_actions import (
    get_corporate_action_adjusted_history,
    get_corporate_action_factors,
    get_corporate_actions,
    list_corporate_action_types,
)
from dadosbr.derivatives import (
    get_derivative_futures_from_file,
    list_derivative_families,
    make_derivatives_response,
    normalize_futures_quotes,
    normalize_options_chain,
    parse_derivatives_csv_bytes,
)
from dadosbr.core.registry import SOURCES
from dadosbr.core.security import (
    SecurityPolicyError,
    validate_admin_http_access,
    validate_optional_local_path,
    validate_upload_size_bytes,
)
from dadosbr.fixed_income import (
    get_fixed_income_analytics,
    get_fixed_income_cashflows,
    get_fixed_income_credit_spread_curve,
    get_fund_fixed_income_exposure,
    get_private_credit_debentures,
    get_tesouro_fixed_income,
)
from dadosbr.fundamentals import (
    compare_companies_fundamentals,
    get_company_dividends,
    get_company_fundamentals,
    get_company_ratios,
    get_company_statement,
    list_fundamentals_calendar,
)
from dadosbr.interest_curves import (
    build_di_curve_from_futures,
    calculate_discount_factors,
    calculate_forward_rates,
    get_tesouro_interest_curve,
    interpolate_interest_curve,
    list_interest_curve_sources,
    make_interest_curve_response,
    normalize_anbima_curve_rows,
    normalize_curve_points,
)
from dadosbr.timeseries import (
    fetch_asset_price_history,
    fetch_economic_timeseries,
    read_timeseries_records,
    write_asset_history_to_store,
)

app = FastAPI(title="DadosBR API", version="0.1.0a0")

_UPLOAD_READ_CHUNK_BYTES = 1024 * 1024


def _security_error(exc: SecurityPolicyError) -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={"code": exc.code, "message": exc.message, "details": exc.details},
    )


def _safe_local_path(path: str, *, purpose: str) -> str:
    try:
        return validate_optional_local_path(path, purpose=purpose)
    except SecurityPolicyError as exc:
        raise _security_error(exc) from exc


async def _read_limited_upload(file: UploadFile, *, purpose: str) -> bytes:
    chunks: list[bytes] = []
    total_size = 0
    while True:
        chunk = await file.read(_UPLOAD_READ_CHUNK_BYTES)
        if not chunk:
            break
        total_size += len(chunk)
        try:
            validate_upload_size_bytes(total_size, purpose=purpose)
        except SecurityPolicyError as exc:
            raise _security_error(exc) from exc
        chunks.append(chunk)
    return b"".join(chunks)


def _safe_admin(token: str | None) -> None:
    try:
        validate_admin_http_access(token)
    except SecurityPolicyError as exc:
        raise _security_error(exc) from exc


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "dadosbr-api"}


@app.get("/sources")
def list_sources() -> dict:
    return {"ok": True, "sources": [source.model_dump(mode="json") for source in SOURCES.values()]}


@app.get("/sources/{source_id}")
def get_source(source_id: str) -> dict:
    source = SOURCES.get(source_id)
    if not source:
        return {"ok": False, "error": {"code": "not_found", "message": f"Unknown source: {source_id}"}}
    return {"ok": True, "source": source.model_dump(mode="json")}


@app.get("/bcb/sgs/{series_id}")
def bcb_sgs(series_id: str, last: int = 12, start_date: str = "", end_date: str = "") -> dict:
    return fetch_sgs_series(series_id, last=last, start_date=start_date or None, end_date=end_date or None)


@app.get("/bcb/ptax")
def bcb_ptax(date: str, currency: str = "USD") -> dict:
    return fetch_ptax(target_date=date, currency=currency)


@app.get("/bcb/focus")
def bcb_focus(indicator: str, top: int = 50) -> dict:
    return fetch_focus_expectations(indicator=indicator, top=top)


@app.get("/cvm/company-reports")
def cvm_reports(
    year: int,
    doc_type: str = "all",
    cvm_code: str = "",
    statement: str = "summary",
    limit: int = 200,
) -> dict:
    return fetch_cvm_company_reports(
        year=year,
        doc_type=doc_type,
        cvm_code=cvm_code,
        statement=statement,
        limit=limit,
    )


@app.get("/cvm/funds/daily")
def cvm_funds_daily(cnpj: str = "", date: str = "", limit: int = 200) -> dict:
    return fetch_cvm_fund_daily(cnpj=cnpj, date=date, limit=limit)


@app.get("/cvm/funds/portfolio")
def cvm_funds_portfolio(cnpj: str = "", date: str = "", limit: int = 200) -> dict:
    return fetch_cvm_fund_portfolio(cnpj=cnpj, date=date, limit=limit)


@app.get("/cvm/fii/monthly")
def cvm_fii(cnpj: str = "", year: int = 0, month: int = 0, limit: int = 200) -> dict:
    return fetch_cvm_fii_monthly(cnpj=cnpj, year=year, month=month, limit=limit)


@app.get("/b3/cotahist")
def b3_cotahist(year: int = 0, ticker: str = "", limit: int = 200) -> dict:
    return fetch_b3_cotahist(year=year if year > 0 else None, ticker=ticker or None, limit=limit)


@app.post("/b3/cotahist/parse")
async def b3_cotahist_parse(file: UploadFile = File(...), ticker: str = "", limit: int = 200) -> dict:  # noqa: B008
    raw = await _read_limited_upload(file, purpose="b3_cotahist_parse")
    return parse_b3_cotahist_bytes(raw, source_url=file.filename or "upload", ticker=ticker or None, limit=limit)


@app.get("/tesouro/rates")
def tesouro_rates(limit: int = 200) -> dict:
    return fetch_tesouro_rates(limit=limit)


@app.get("/ibge/sidra")
def ibge_sidra(path: str) -> dict:
    return fetch_ibge_sidra(path)


@app.get("/ipea/series/{series_code}")
def ipea_series(series_code: str, top: int = 200) -> dict:
    return fetch_ipea_series(series_code, top=top)


@app.get("/cnpj/status")
def cnpj_status() -> dict:
    return get_cnpj_status()


@app.get("/cnpj/search")
def cnpj_search(q: str = "", uf: str = "", cnae: str = "", situacao: str = "", limit: int = 50) -> dict:
    return search_cnpj_companies(q=q, uf=uf, cnae=cnae, situacao=situacao, limit=limit)


@app.get("/cnpj/{cnpj}/socios")
def cnpj_partners(cnpj: str) -> dict:
    return get_cnpj_partners(cnpj)


@app.get("/cnpj/{cnpj}")
def cnpj_company(cnpj: str) -> dict:
    return get_cnpj_company(cnpj)


@app.post("/admin/cnpj/sync")
def admin_cnpj_sync(
    period: str = "latest",
    groups: str = "empresas,estabelecimentos,socios,simples,domains",
    max_files: int = 0,
    x_dadosbr_admin_token: str | None = Header(default=None),
) -> dict:
    _safe_admin(x_dadosbr_admin_token)
    download = download_cnpj_period(
        period=period,
        groups=groups,
        max_files=max_files if max_files > 0 else None,
    )
    if not download.get("ok"):
        return download
    files = download.get("records", [])
    if not files:
        return {"ok": False, "error": {"code": "source_unavailable", "message": "No CNPJ files downloaded."}}
    return build_cnpj_index(Path(files[0]["path"]).parent)


@app.get("/comex/ncm")
def comex_ncm(flow: str, year: int, ncm: str = "", uf: str = "", country: str = "", limit: int = 200) -> dict:
    return fetch_comex_ncm(flow=flow, year=year, ncm=ncm, uf=uf, country=country, limit=limit)


@app.get("/comex/ncm/summary")
def comex_ncm_summary(flow: str, year: int, group_by: str = "month", ncm: str = "", uf: str = "", country: str = "") -> dict:
    return summarize_comex_ncm(flow=flow, year=year, group_by=group_by, ncm=ncm, uf=uf, country=country)


@app.get("/comex/municipality")
def comex_municipality(flow: str, year: int, uf: str = "", municipality_code: str = "", sh4: str = "", limit: int = 200) -> dict:
    return fetch_comex_municipality(flow=flow, year=year, uf=uf, municipality_code=municipality_code, sh4=sh4, limit=limit)


@app.get("/comex/tables/{table_name}")
def comex_table(table_name: str, limit: int = 500) -> dict:
    return fetch_comex_table(table_name=table_name, limit=limit)


@app.get("/bndes/operations")
def bndes_operations(cnpj: str = "", uf: str = "", year: int = 0, setor: str = "", limit: int = 200) -> dict:
    return fetch_bndes_operations(cnpj=cnpj, uf=uf, year=year, setor=setor, limit=limit)


@app.get("/bndes/variable-income")
def bndes_variable_income(kind: str = "all", company: str = "", year: int = 0, limit: int = 200) -> dict:
    return fetch_bndes_variable_income(kind=kind, company=company, year=year, limit=limit)


@app.get("/bndes/datasets")
def bndes_datasets(query: str = "", rows: int = 20) -> dict:
    return list_bndes_datasets(query=query, rows=rows)


@app.get("/corporate-actions/types")
def corporate_action_types() -> dict:
    return list_corporate_action_types()


@app.get("/corporate-actions/{ticker}/adjustment-factors")
def corporate_action_factors(
    ticker: str,
    source: str = "yfinance",
    start_date: str = "",
    end_date: str = "",
    limit: int = 500,
) -> dict:
    return get_corporate_action_factors(
        ticker=ticker,
        source=source,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


@app.get("/corporate-actions/{ticker}/adjusted-history")
def corporate_action_adjusted_history(
    ticker: str,
    b3_file_path: str = "",
    source: str = "yfinance",
    start_date: str = "",
    end_date: str = "",
    limit: int = 5000,
) -> dict:
    b3_file_path = _safe_local_path(b3_file_path, purpose="b3_cotahist_file")
    return get_corporate_action_adjusted_history(
        ticker=ticker,
        b3_file_path=b3_file_path,
        source=source,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


@app.get("/corporate-actions/{ticker}")
def corporate_actions_ticker(
    ticker: str,
    source: str = "yfinance",
    start_date: str = "",
    end_date: str = "",
    limit: int = 500,
) -> dict:
    return get_corporate_actions(
        ticker=ticker,
        source=source,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


@app.get("/derivatives/families")
def derivative_families() -> dict:
    return list_derivative_families()


@app.get("/derivatives/futures")
def derivative_futures(file_path: str, family: str = "", limit: int = 5000) -> dict:
    file_path = _safe_local_path(file_path, purpose="derivatives_file")
    return get_derivative_futures_from_file(file_path=file_path, family=family, limit=limit)


@app.post("/derivatives/futures/parse")
async def derivative_futures_parse(file: UploadFile = File(...), family: str = "", limit: int = 5000) -> dict:  # noqa: B008
    raw = await _read_limited_upload(file, purpose="derivatives_parse")
    return parse_derivatives_csv_bytes(
        raw,
        source_url=file.filename or "upload",
        family=family,
        limit=limit,
    )


@app.post("/derivatives/futures/normalize")
def derivative_futures_normalize(rows: list[dict[str, Any]], family: str = "", limit: int = 5000) -> dict:
    if family or limit != 5000:
        records = normalize_futures_quotes(rows, family=family, limit=limit)
    else:
        records = normalize_futures_quotes(rows)
    return make_derivatives_response(records, source_url="local://dadosbr/derivatives/futures/normalize")


@app.post("/derivatives/options/normalize")
def derivative_options_normalize(rows: list[dict[str, Any]], limit: int = 5000) -> dict:
    records = normalize_options_chain(rows, limit=limit) if limit != 5000 else normalize_options_chain(rows)
    return make_derivatives_response(records, source_url="local://dadosbr/derivatives/options/normalize")


@app.get("/curves/sources")
def interest_curve_sources() -> dict:
    return list_interest_curve_sources()


@app.get("/curves/tesouro")
def tesouro_interest_curve(limit: int = 200) -> dict:
    return get_tesouro_interest_curve(limit=limit)


@app.post("/curves/normalize")
def interest_curve_normalize(
    rows: list[dict[str, Any]],
    source_id: str = "manual",
    curve_id: str = "",
) -> dict:
    records = normalize_curve_points(rows, source_id=source_id, curve_id=curve_id)
    return make_interest_curve_response(records, source_url="local://dadosbr/curves/normalize")


@app.post("/curves/anbima/normalize")
def anbima_curve_normalize(rows: list[dict[str, Any]]) -> dict:
    records = normalize_anbima_curve_rows(rows)
    return make_interest_curve_response(records, source_url="local://dadosbr/curves/anbima/normalize")


@app.post("/curves/di-futures")
def di_curve_from_futures(rows: list[dict[str, Any]]) -> dict:
    records = build_di_curve_from_futures(rows)
    return make_interest_curve_response(records, source_url="local://dadosbr/curves/di-futures")


@app.post("/curves/interpolate")
def curve_interpolate(rows: list[dict[str, Any]], target_tenor_years: float) -> dict:
    record = interpolate_interest_curve(rows, target_tenor_years=target_tenor_years)
    return make_interest_curve_response([record], source_url="local://dadosbr/curves/interpolate")


@app.post("/curves/discount-factors")
def curve_discount_factors(rows: list[dict[str, Any]]) -> dict:
    records = calculate_discount_factors(rows)
    return make_interest_curve_response(records, source_url="local://dadosbr/curves/discount-factors")


@app.post("/curves/forward-rates")
def curve_forward_rates(rows: list[dict[str, Any]]) -> dict:
    records = calculate_forward_rates(rows)
    return make_interest_curve_response(records, source_url="local://dadosbr/curves/forward-rates")


@app.get("/assets/{asset_id}/history")
def asset_history(
    asset_id: str,
    start_date: str = "",
    end_date: str = "",
    adjusted: bool = False,
    b3_file_path: str = "",
    limit: int = 5000,
    store: bool = False,
    db_path: str = "",
) -> dict:
    b3_file_path = _safe_local_path(b3_file_path, purpose="b3_cotahist_file")
    db_path = _safe_local_path(db_path, purpose="timeseries_store") if db_path else ""
    if store and not db_path:
        _safe_local_path(str(Path(".dadosbr") / "datasets" / "timeseries"), purpose="timeseries_store")
    return fetch_asset_price_history(
        asset_id=asset_id,
        start_date=start_date,
        end_date=end_date,
        adjusted=adjusted,
        b3_file_path=b3_file_path,
        limit=limit,
        store=store,
        db_path=db_path or None,
    )


@app.get("/timeseries/economic/{provider}/{series_code}")
def economic_timeseries(
    provider: str,
    series_code: str,
    last: int = 200,
    start_date: str = "",
    end_date: str = "",
) -> dict:
    return fetch_economic_timeseries(
        provider=provider,
        series_code=series_code,
        last=last,
        start_date=start_date,
        end_date=end_date,
    )


@app.get("/timeseries/store")
def timeseries_store_read(
    db_path: str = "",
    asset_id: str = "",
    series_id: str = "",
    start_date: str = "",
    end_date: str = "",
    limit: int = 5000,
) -> dict:
    db_path = _safe_local_path(db_path, purpose="timeseries_store") if db_path else ""
    return read_timeseries_records(
        db_path=db_path or None,
        asset_id=asset_id,
        series_id=series_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


@app.get("/benchmarks")
def benchmarks_list() -> dict:
    return list_benchmarks()


@app.get("/benchmarks/compare")
def benchmark_compare(
    asset_id: str,
    benchmark_id: str,
    start_date: str = "",
    end_date: str = "",
    adjusted: bool = False,
    b3_file_path: str = "",
    last: int = 5000,
) -> dict:
    b3_file_path = _safe_local_path(b3_file_path, purpose="b3_cotahist_file")
    return compare_asset_to_benchmark(
        asset_id=asset_id,
        benchmark_id=benchmark_id,
        start_date=start_date,
        end_date=end_date,
        adjusted=adjusted,
        b3_file_path=b3_file_path,
        last=last,
    )


@app.get("/fixed-income/tesouro")
def fixed_income_tesouro(limit: int = 200) -> dict:
    return get_tesouro_fixed_income(limit=limit)


@app.get("/fixed-income/debentures")
def fixed_income_debentures(company: str = "", year: int = 0, limit: int = 200) -> dict:
    return get_private_credit_debentures(company=company, year=year, limit=limit)


@app.get("/fixed-income/funds/exposure")
def fixed_income_funds_exposure(cnpj: str = "", date: str = "", limit: int = 5000) -> dict:
    return get_fund_fixed_income_exposure(cnpj=cnpj, date=date, limit=limit)


@app.get("/fixed-income/cashflows")
def fixed_income_cashflows(
    settlement_date: str,
    maturity_date: str,
    principal: float,
    annual_coupon_rate: float,
    payments_per_year: int = 1,
) -> dict:
    return get_fixed_income_cashflows(
        settlement_date=settlement_date,
        maturity_date=maturity_date,
        principal=principal,
        annual_coupon_rate=annual_coupon_rate,
        payments_per_year=payments_per_year,
    )


@app.get("/fixed-income/analytics")
def fixed_income_analytics(
    price: float,
    settlement_date: str,
    maturity_date: str,
    principal: float,
    annual_coupon_rate: float,
    payments_per_year: int = 1,
) -> dict:
    return get_fixed_income_analytics(
        price=price,
        settlement_date=settlement_date,
        maturity_date=maturity_date,
        principal=principal,
        annual_coupon_rate=annual_coupon_rate,
        payments_per_year=payments_per_year,
    )


@app.get("/fixed-income/curves/credit-spread")
def fixed_income_credit_spread_curve(
    benchmark_rate: float,
    observed_at: str = "",
    company: str = "",
    year: int = 0,
    limit: int = 200,
) -> dict:
    return get_fixed_income_credit_spread_curve(
        benchmark_rate=benchmark_rate,
        observed_at=observed_at,
        company=company,
        year=year,
        limit=limit,
    )


@app.get("/benchmarks/{benchmark_id}")
def benchmark_metadata(benchmark_id: str) -> dict:
    return get_benchmark_metadata(benchmark_id)


@app.get("/benchmarks/{benchmark_id}/history")
def benchmark_history(
    benchmark_id: str,
    start_date: str = "",
    end_date: str = "",
    last: int = 200,
    real: bool = False,
    deflator: str = "ipca",
) -> dict:
    return fetch_benchmark_history(
        benchmark_id=benchmark_id,
        start_date=start_date,
        end_date=end_date,
        last=last,
        real=real,
        deflator=deflator,
    )


@app.get("/macro/calendar")
def macro_calendar() -> dict:
    return list_macro_calendar()


@app.get("/fundamentals/calendar")
def fundamentals_calendar() -> dict:
    return list_fundamentals_calendar()


@app.get("/fundamentals/compare")
def fundamentals_compare(
    cvm_codes: str,
    year: int,
    metric: str = "roe",
    doc_type: str = "dfp",
    limit_per_company: int = 2000,
) -> dict:
    return compare_companies_fundamentals(
        cvm_codes=cvm_codes,
        year=year,
        metric=metric,
        doc_type=doc_type,
        limit_per_company=limit_per_company,
    )


@app.get("/fundamentals/companies/{cvm_code}")
def fundamentals_company(
    cvm_code: str,
    year: int,
    doc_type: str = "dfp",
    ticker: str = "",
    b3_file_path: str = "",
    shares_outstanding: float = 0,
    market_cap: float = 0,
    limit: int = 5000,
) -> dict:
    b3_file_path = _safe_local_path(b3_file_path, purpose="b3_cotahist_file")
    return get_company_fundamentals(
        cvm_code=cvm_code,
        year=year,
        doc_type=doc_type,
        ticker=ticker,
        b3_file_path=b3_file_path,
        shares_outstanding=shares_outstanding,
        market_cap=market_cap,
        limit=limit,
    )


@app.get("/fundamentals/companies/{cvm_code}/statements")
def fundamentals_company_statement(
    cvm_code: str,
    year: int,
    doc_type: str = "dfp",
    statement: str = "all",
    limit: int = 5000,
) -> dict:
    return get_company_statement(
        cvm_code=cvm_code,
        year=year,
        doc_type=doc_type,
        statement=statement,
        limit=limit,
    )


@app.get("/fundamentals/companies/{cvm_code}/ratios")
def fundamentals_company_ratios(
    cvm_code: str,
    year: int,
    doc_type: str = "dfp",
    ticker: str = "",
    b3_file_path: str = "",
    shares_outstanding: float = 0,
    market_cap: float = 0,
) -> dict:
    b3_file_path = _safe_local_path(b3_file_path, purpose="b3_cotahist_file")
    return get_company_ratios(
        cvm_code=cvm_code,
        year=year,
        doc_type=doc_type,
        ticker=ticker,
        b3_file_path=b3_file_path,
        shares_outstanding=shares_outstanding,
        market_cap=market_cap,
    )


@app.get("/fundamentals/companies/{ticker}/dividends")
def fundamentals_company_dividends(
    ticker: str,
    start_date: str = "",
    end_date: str = "",
    limit: int = 500,
) -> dict:
    return get_company_dividends(
        ticker=ticker,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


@app.post("/timeseries/store/assets/{asset_id}/history")
def timeseries_store_write_asset_history(
    asset_id: str,
    start_date: str = "",
    end_date: str = "",
    adjusted: bool = False,
    b3_file_path: str = "",
    limit: int = 5000,
    db_path: str = "",
) -> dict:
    b3_file_path = _safe_local_path(b3_file_path, purpose="b3_cotahist_file")
    db_path = _safe_local_path(db_path, purpose="timeseries_store") if db_path else ""
    if not db_path:
        _safe_local_path(str(Path(".dadosbr") / "datasets" / "timeseries"), purpose="timeseries_store")
    return write_asset_history_to_store(
        asset_id=asset_id,
        start_date=start_date,
        end_date=end_date,
        adjusted=adjusted,
        b3_file_path=b3_file_path,
        limit=limit,
        db_path=db_path or None,
    )


@app.get("/assets/search")
def assets_search(
    q: str = "",
    type: str = "all",  # noqa: A002
    issuer_cnpj: str = "",
    limit: int = 50,
    db_path: str = "",
    b3_file_path: str = "",
) -> dict:
    db_path = _safe_local_path(db_path, purpose="cnpj_index") if db_path else ""
    b3_file_path = _safe_local_path(b3_file_path, purpose="b3_cotahist_file")
    return search_asset_master(
        q=q,
        asset_type=type,
        issuer_cnpj=issuer_cnpj,
        limit=limit,
        db_path=db_path or None,
        b3_file_path=b3_file_path,
    )


@app.get("/assets/{asset_id}")
def asset_by_id(asset_id: str, db_path: str = "", b3_file_path: str = "") -> dict:
    db_path = _safe_local_path(db_path, purpose="cnpj_index") if db_path else ""
    b3_file_path = _safe_local_path(b3_file_path, purpose="b3_cotahist_file")
    return get_asset_master(asset_id, db_path=db_path or None, b3_file_path=b3_file_path)


@app.get("/issuers/{cnpj}")
def issuer_by_cnpj(cnpj: str, db_path: str = "") -> dict:
    db_path = _safe_local_path(db_path, purpose="cnpj_index") if db_path else ""
    return get_issuer_master(cnpj, db_path=db_path or None)


@app.get("/instruments/{ticker}")
def instrument_by_ticker(ticker: str, b3_file_path: str = "") -> dict:
    b3_file_path = _safe_local_path(b3_file_path, purpose="b3_cotahist_file")
    return get_instrument_master(ticker, b3_file_path=b3_file_path)


@app.get("/taxonomies/cnae/{code}")
def cnae_taxonomy(code: str, db_path: str = "") -> dict:
    db_path = _safe_local_path(db_path, purpose="cnpj_index") if db_path else ""
    return get_cnae_taxonomy(code, db_path=db_path or None)


@app.get("/taxonomies/ncm/{code}")
def ncm_taxonomy(code: str) -> dict:
    return get_ncm_taxonomy(code)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DadosBR HTTP API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    uvicorn.run("dadosbr.api.app:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
