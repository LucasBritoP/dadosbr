from __future__ import annotations

from pathlib import Path
from typing import Any

from dadosbr.core import DataSourceError, make_failure
from dadosbr.asset_master import (
    get_asset_master as asset_get_master,
    get_cnae_taxonomy as asset_get_cnae_taxonomy,
    get_instrument_master as asset_get_instrument_master,
    get_issuer_master as asset_get_issuer_master,
    get_ncm_taxonomy as asset_get_ncm_taxonomy,
    search_asset_master as asset_search_master,
)
from dadosbr.benchmarks import (
    compare_asset_to_benchmark as benchmark_compare_asset_to_benchmark,
    fetch_benchmark_history as benchmark_fetch_history,
    fetch_yield_curve as benchmark_fetch_yield_curve,
    get_benchmark_metadata as benchmark_get_metadata,
    list_benchmarks as benchmark_list,
    list_macro_calendar as benchmark_list_macro_calendar,
)
from dadosbr.connectors import (
    build_cnpj_index as cnpj_build_index,
    download_cnpj_period as cnpj_download_period,
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
    get_cnpj_company as cnpj_get_company,
    get_cnpj_partners as cnpj_get_partners,
    get_cnpj_status as cnpj_get_status,
    list_bndes_datasets as bndes_list_datasets,
    parse_b3_cotahist_bytes,
    search_cnpj_companies as cnpj_search_companies,
    summarize_comex_ncm as comex_summarize_ncm,
)
from dadosbr.corporate_actions import (
    get_corporate_action_adjusted_history as ca_get_adjusted_history,
    get_corporate_action_factors as ca_get_factors,
    get_corporate_actions as ca_get_actions,
    list_corporate_action_types as ca_list_types,
    normalize_corporate_actions as ca_normalize_actions,
)
from dadosbr.derivatives import (
    get_derivative_futures_from_file as deriv_get_futures_from_file,
    list_derivative_families as deriv_list_families,
    make_derivatives_response as deriv_make_response,
    normalize_futures_quotes as deriv_normalize_futures_quotes,
    normalize_options_chain as deriv_normalize_options_chain,
    parse_derivatives_csv_bytes as deriv_parse_csv_bytes,
)
from dadosbr.core.registry import SOURCES
from dadosbr.core.security import (
    SecurityPolicyError,
    validate_admin_mcp_access,
    validate_optional_local_path,
    validate_upload_size,
)
from dadosbr.fixed_income import (
    get_fixed_income_analytics as fi_get_analytics,
    get_fixed_income_cashflows as fi_get_cashflows,
    get_fixed_income_credit_spread_curve as fi_get_credit_spread_curve,
    get_fund_fixed_income_exposure as fi_get_fund_exposure,
    get_private_credit_debentures as fi_get_private_credit_debentures,
    get_tesouro_fixed_income as fi_get_tesouro,
)
from dadosbr.fundamentals import (
    compare_companies_fundamentals as fundamentals_compare_companies,
    get_company_dividends as fundamentals_get_company_dividends,
    get_company_fundamentals as fundamentals_get_company,
    get_company_ratios as fundamentals_get_company_ratios,
    get_company_statement as fundamentals_get_company_statement,
    list_fundamentals_calendar as fundamentals_list_calendar,
)
from dadosbr.interest_curves import (
    build_di_curve_from_futures as curves_build_di_curve_from_futures,
    calculate_discount_factors as curves_calculate_discount_factors,
    calculate_forward_rates as curves_calculate_forward_rates,
    get_tesouro_interest_curve as curves_get_tesouro_interest_curve,
    interpolate_interest_curve as curves_interpolate_interest_curve,
    list_interest_curve_sources as curves_list_sources,
    make_interest_curve_response as curves_make_response,
    normalize_anbima_curve_rows as curves_normalize_anbima_curve_rows,
    normalize_curve_points as curves_normalize_curve_points,
)
from dadosbr.timeseries import (
    fetch_asset_price_history as ts_fetch_asset_price_history,
    fetch_economic_timeseries as ts_fetch_economic_timeseries,
    read_timeseries_records as ts_read_timeseries_records,
    write_asset_history_to_store as ts_write_asset_history_to_store,
)

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover
    FastMCP = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None

EXPANSION_TOOL_NAMES = {
    "get_cnpj_status",
    "get_cnpj_company",
    "search_cnpj_companies",
    "get_cnpj_partners",
    "get_comex_ncm",
    "summarize_comex_ncm",
    "get_comex_municipality",
    "get_comex_table",
    "get_bndes_operations",
    "get_bndes_variable_income",
    "list_bndes_datasets",
}

ASSET_MASTER_TOOL_NAMES = {
    "get_asset_master",
    "search_asset_master",
    "get_issuer_master",
    "get_instrument_master",
    "get_cnae_taxonomy",
    "get_ncm_taxonomy",
}

TIMESERIES_TOOL_NAMES = {
    "get_asset_price_history",
    "get_economic_timeseries",
    "read_timeseries_store",
    "write_asset_history_to_store",
}

BENCHMARK_TOOL_NAMES = {
    "list_benchmarks",
    "get_benchmark_metadata",
    "get_benchmark_history",
    "get_real_benchmark_history",
    "compare_asset_to_benchmark",
    "get_yield_curve",
    "list_macro_calendar",
}

FIXED_INCOME_TOOL_NAMES = {
    "get_tesouro_fixed_income",
    "get_private_credit_debentures",
    "get_fund_fixed_income_exposure",
    "get_fixed_income_cashflows",
    "get_fixed_income_analytics",
    "get_fixed_income_credit_spread_curve",
}

FUNDAMENTALS_TOOL_NAMES = {
    "get_company_fundamentals",
    "get_company_statement",
    "get_company_ratios",
    "get_company_dividends",
    "compare_companies_fundamentals",
    "list_fundamentals_calendar",
}

CORPORATE_ACTION_TOOL_NAMES = {
    "list_corporate_action_types",
    "get_corporate_actions",
    "get_corporate_action_factors",
    "get_corporate_action_adjusted_history",
    "normalize_corporate_actions",
}

DERIVATIVES_TOOL_NAMES = {
    "list_derivative_families",
    "normalize_futures_quotes",
    "get_derivative_futures_from_file",
    "parse_derivatives_futures_text",
    "normalize_options_chain",
}

INTEREST_CURVE_TOOL_NAMES = {
    "list_interest_curve_sources",
    "get_tesouro_interest_curve",
    "normalize_interest_curve_points",
    "normalize_anbima_curve_rows",
    "build_di_curve_from_futures",
    "interpolate_interest_curve",
    "calculate_discount_factors",
    "calculate_forward_rates",
}

_DEFAULT_TIMESERIES_STORE_PATH = Path(".dadosbr") / "datasets" / "timeseries" / "timeseries.sqlite"


def _mcp_security_failure(exc: SecurityPolicyError, *, source_id: str, purpose: str) -> dict:
    return make_failure(
        DataSourceError(
            exc.code,
            exc.message,
            source_id,
            source_url=f"mcp://dadosbr/{purpose}",
            details=exc.details,
        )
    ).model_dump(mode="json")


def _validate_mcp_local_path(raw_path: str, *, purpose: str, source_id: str) -> tuple[str, dict | None]:
    try:
        return validate_optional_local_path(raw_path, purpose=purpose), None
    except SecurityPolicyError as exc:
        return "", _mcp_security_failure(exc, source_id=source_id, purpose=purpose)


def _validate_mcp_admin(raw_token: str, *, purpose: str, source_id: str) -> dict | None:
    try:
        validate_admin_mcp_access(raw_token)
    except SecurityPolicyError as exc:
        return _mcp_security_failure(exc, source_id=source_id, purpose=purpose)
    return None


def _encode_mcp_text_payload(
    raw_text: str,
    *,
    encoding: str,
    purpose: str,
    source_id: str,
) -> tuple[bytes | None, dict | None]:
    selected_encoding = (encoding or "utf-8").strip() or "utf-8"
    try:
        raw_bytes = str(raw_text or "").encode(selected_encoding, errors="replace")
    except LookupError:
        return (
            None,
            make_failure(
                DataSourceError(
                    "validation_error",
                    f"Unknown encoding: {selected_encoding}",
                    source_id,
                    source_url=f"mcp://dadosbr/{purpose}",
                )
            ).model_dump(mode="json"),
        )
    try:
        validate_upload_size(raw_bytes, purpose=purpose)
    except SecurityPolicyError as exc:
        return None, _mcp_security_failure(exc, source_id=source_id, purpose=purpose)
    return raw_bytes, None


def _build_server() -> Any:
    if FastMCP is None:
        raise RuntimeError(
            "MCP dependency is not installed. Install with: python -m pip install -e ."
        ) from _IMPORT_ERROR

    mcp = FastMCP("dadosbr-mcp")

    @mcp.tool()
    def list_sources() -> dict:
        """List all registered DadosBR data sources and their metadata."""
        return {"ok": True, "sources": [source.model_dump(mode="json") for source in SOURCES.values()]}

    @mcp.tool()
    def get_source_metadata(source_id: str) -> dict:
        """Get metadata, license notes and limitations for one data source."""
        source = SOURCES.get(source_id)
        if not source:
            return {"ok": False, "error": {"code": "not_found", "message": f"Unknown source: {source_id}"}}
        return {"ok": True, "source": source.model_dump(mode="json")}

    @mcp.tool()
    def get_bcb_sgs_series(series_id: str, last: int = 12, start_date: str = "", end_date: str = "") -> dict:
        """Fetch a Banco Central SGS time series by numeric series id."""
        return fetch_sgs_series(series_id, last=last, start_date=start_date or None, end_date=end_date or None)

    @mcp.tool()
    def get_bcb_ptax(date: str, currency: str = "USD") -> dict:
        """Fetch PTAX exchange rates from Banco Central for a reference date."""
        return fetch_ptax(target_date=date, currency=currency)

    @mcp.tool()
    def get_bcb_focus(indicator: str, top: int = 50) -> dict:
        """Fetch Focus market expectations for an economic indicator."""
        return fetch_focus_expectations(indicator=indicator, top=top)

    @mcp.tool()
    def get_cvm_company_reports(
        year: int,
        doc_type: str = "all",
        cvm_code: str = "",
        statement: str = "summary",
        limit: int = 200,
    ) -> dict:
        """Fetch CVM company financial report rows for a year and statement type."""
        return fetch_cvm_company_reports(
            year=year,
            doc_type=doc_type,
            cvm_code=cvm_code,
            statement=statement,
            limit=limit,
        )

    @mcp.tool()
    def get_cvm_fund_daily_info(cnpj: str = "", date: str = "", limit: int = 200) -> dict:
        """Fetch daily CVM investment fund information."""
        return fetch_cvm_fund_daily(cnpj=cnpj, date=date, limit=limit)

    @mcp.tool()
    def get_cvm_fund_portfolio(cnpj: str = "", date: str = "", limit: int = 200) -> dict:
        """Fetch CVM fund portfolio holdings."""
        return fetch_cvm_fund_portfolio(cnpj=cnpj, date=date, limit=limit)

    @mcp.tool()
    def get_cvm_fii_monthly_report(cnpj: str = "", year: int = 0, month: int = 0, limit: int = 200) -> dict:
        """Fetch monthly CVM real estate fund reports."""
        return fetch_cvm_fii_monthly(cnpj=cnpj, year=year, month=month, limit=limit)

    @mcp.tool()
    def get_b3_cotahist_quotes(year: int = 0, ticker: str = "", limit: int = 200) -> dict:
        """Fetch or parse B3 COTAHIST end-of-day quotes."""
        return fetch_b3_cotahist(year=year if year > 0 else None, ticker=ticker or None, limit=limit)

    @mcp.tool()
    def parse_b3_cotahist_text(
        raw_text: str,
        ticker: str = "",
        limit: int = 200,
        encoding: str = "latin-1",
    ) -> dict:
        """Parse B3 COTAHIST text content sent through MCP JSON."""
        raw_bytes, error = _encode_mcp_text_payload(
            raw_text,
            encoding=encoding,
            purpose="b3/cotahist/text",
            source_id="b3_cotahist",
        )
        if error is not None:
            return error
        return parse_b3_cotahist_bytes(
            raw_bytes or b"",
            source_url="mcp://dadosbr/b3/cotahist/text",
            ticker=ticker or None,
            limit=limit,
        )

    @mcp.tool()
    def get_tesouro_rates(limit: int = 200) -> dict:
        """Fetch current Tesouro Direto public bond rates."""
        return fetch_tesouro_rates(limit=limit)

    @mcp.tool()
    def get_ibge_sidra(path: str) -> dict:
        """Fetch an IBGE SIDRA path and return normalized response records."""
        return fetch_ibge_sidra(path)

    @mcp.tool()
    def get_ipeadata_series(series_code: str, top: int = 200) -> dict:
        """Fetch an IPEADATA economic series by code."""
        return fetch_ipea_series(series_code, top=top)

    @mcp.tool()
    def get_cnpj_status() -> dict:
        """Show local Receita Federal CNPJ index status."""
        return cnpj_get_status()

    @mcp.tool()
    def get_cnpj_company(cnpj: str) -> dict:
        """Look up one company in the local Receita Federal CNPJ index."""
        return cnpj_get_company(cnpj)

    @mcp.tool()
    def search_cnpj_companies(q: str = "", uf: str = "", cnae: str = "", situacao: str = "", limit: int = 50) -> dict:
        """Search companies in the local Receita Federal CNPJ index."""
        return cnpj_search_companies(q=q, uf=uf, cnae=cnae, situacao=situacao, limit=limit)

    @mcp.tool()
    def get_cnpj_partners(cnpj: str) -> dict:
        """List QSA partners for a company CNPJ from the local index."""
        return cnpj_get_partners(cnpj)

    @mcp.tool()
    def admin_sync_cnpj(
        period: str = "latest",
        groups: str = "empresas,estabelecimentos,socios,simples,domains",
        max_files: int = 0,
        admin_token: str = "",
    ) -> dict:
        """Download and build a local Receita Federal CNPJ index."""
        error = _validate_mcp_admin(admin_token, purpose="admin/cnpj/sync", source_id="receita_cnpj")
        if error:
            return error
        download = cnpj_download_period(period=period, groups=groups, max_files=max_files if max_files > 0 else None)
        if not download.get("ok"):
            return download
        files = download.get("records", [])
        if not files:
            return {"ok": False, "error": {"code": "source_unavailable", "message": "No files downloaded."}}
        from pathlib import Path as _Path

        return cnpj_build_index(_Path(files[0]["path"]).parent)

    @mcp.tool()
    def get_comex_ncm(flow: str, year: int, ncm: str = "", uf: str = "", country: str = "", limit: int = 200) -> dict:
        """Fetch Comex Stat import or export rows grouped by NCM."""
        return fetch_comex_ncm(flow=flow, year=year, ncm=ncm, uf=uf, country=country, limit=limit)

    @mcp.tool()
    def summarize_comex_ncm(flow: str, year: int, group_by: str = "month", ncm: str = "", uf: str = "", country: str = "") -> dict:
        """Summarize Comex Stat NCM trade data by month, country, UF or NCM."""
        return comex_summarize_ncm(flow=flow, year=year, group_by=group_by, ncm=ncm, uf=uf, country=country)

    @mcp.tool()
    def get_comex_municipality(flow: str, year: int, uf: str = "", municipality_code: str = "", sh4: str = "", limit: int = 200) -> dict:
        """Fetch Comex Stat import or export rows by municipality."""
        return fetch_comex_municipality(flow=flow, year=year, uf=uf, municipality_code=municipality_code, sh4=sh4, limit=limit)

    @mcp.tool()
    def get_comex_table(table_name: str, limit: int = 500) -> dict:
        """Fetch a Comex Stat auxiliary table such as NCM."""
        return fetch_comex_table(table_name=table_name, limit=limit)

    @mcp.tool()
    def get_bndes_operations(cnpj: str = "", uf: str = "", year: int = 0, setor: str = "", limit: int = 200) -> dict:
        """Fetch BNDES financing operations with optional filters."""
        return fetch_bndes_operations(cnpj=cnpj, uf=uf, year=year, setor=setor, limit=limit)

    @mcp.tool()
    def get_bndes_variable_income(kind: str = "all", company: str = "", year: int = 0, limit: int = 200) -> dict:
        """Fetch BNDES variable income, funds, debentures or participation data."""
        return fetch_bndes_variable_income(kind=kind, company=company, year=year, limit=limit)

    @mcp.tool()
    def list_bndes_datasets(query: str = "", rows: int = 20) -> dict:
        """List BNDES open data datasets from the CKAN catalog."""
        return bndes_list_datasets(query=query, rows=rows)

    @mcp.tool()
    def get_asset_master(asset_id: str, db_path: str = "", b3_file_path: str = "") -> dict:
        """Get a unified asset master record by CNPJ, ticker or prefixed asset id."""
        db_path, error = _validate_mcp_local_path(db_path, purpose="cnpj_index", source_id="asset_master")
        if error:
            return error
        b3_file_path, error = _validate_mcp_local_path(
            b3_file_path, purpose="b3_cotahist_file", source_id="asset_master"
        )
        if error:
            return error
        return asset_get_master(asset_id, db_path=db_path or None, b3_file_path=b3_file_path)

    @mcp.tool()
    def search_asset_master(
        q: str = "",
        asset_type: str = "all",
        issuer_cnpj: str = "",
        limit: int = 50,
        db_path: str = "",
        b3_file_path: str = "",
    ) -> dict:
        """Search the asset master across issuers, instruments and taxonomies."""
        db_path, error = _validate_mcp_local_path(db_path, purpose="cnpj_index", source_id="asset_master")
        if error:
            return error
        b3_file_path, error = _validate_mcp_local_path(
            b3_file_path, purpose="b3_cotahist_file", source_id="asset_master"
        )
        if error:
            return error
        return asset_search_master(
            q=q,
            asset_type=asset_type,
            issuer_cnpj=issuer_cnpj,
            limit=limit,
            db_path=db_path or None,
            b3_file_path=b3_file_path,
        )

    @mcp.tool()
    def get_issuer_master(cnpj: str, db_path: str = "") -> dict:
        """Get issuer master data for a company CNPJ."""
        db_path, error = _validate_mcp_local_path(db_path, purpose="cnpj_index", source_id="asset_master")
        if error:
            return error
        return asset_get_issuer_master(cnpj, db_path=db_path or None)

    @mcp.tool()
    def get_instrument_master(ticker: str, b3_file_path: str = "") -> dict:
        """Get instrument master data for a B3 ticker."""
        b3_file_path, error = _validate_mcp_local_path(
            b3_file_path, purpose="b3_cotahist_file", source_id="asset_master"
        )
        if error:
            return error
        return asset_get_instrument_master(ticker, b3_file_path=b3_file_path)

    @mcp.tool()
    def get_cnae_taxonomy(code: str, db_path: str = "") -> dict:
        """Get CNAE taxonomy metadata by code."""
        db_path, error = _validate_mcp_local_path(db_path, purpose="cnpj_index", source_id="asset_master")
        if error:
            return error
        return asset_get_cnae_taxonomy(code, db_path=db_path or None)

    @mcp.tool()
    def get_ncm_taxonomy(code: str) -> dict:
        """Get NCM taxonomy metadata by code."""
        return asset_get_ncm_taxonomy(code)

    @mcp.tool()
    def get_asset_price_history(
        asset_id: str,
        start_date: str = "",
        end_date: str = "",
        adjusted: bool = False,
        b3_file_path: str = "",
        limit: int = 5000,
        store: bool = False,
        db_path: str = "",
    ) -> dict:
        """Fetch canonical asset OHLCV history with optional adjusted prices."""
        b3_file_path, error = _validate_mcp_local_path(
            b3_file_path, purpose="b3_cotahist_file", source_id="timeseries"
        )
        if error:
            return error
        db_path, error = _validate_mcp_local_path(db_path, purpose="timeseries_store", source_id="timeseries")
        if error:
            return error
        if store and not db_path:
            _default_store, error = _validate_mcp_local_path(
                str(_DEFAULT_TIMESERIES_STORE_PATH), purpose="timeseries_store", source_id="timeseries"
            )
            if error:
                return error
        return ts_fetch_asset_price_history(
            asset_id=asset_id,
            start_date=start_date,
            end_date=end_date,
            adjusted=adjusted,
            b3_file_path=b3_file_path,
            limit=limit,
            store=store,
            db_path=db_path or None,
        )

    @mcp.tool()
    def get_economic_timeseries(
        provider: str,
        series_code: str,
        last: int = 200,
        start_date: str = "",
        end_date: str = "",
    ) -> dict:
        """Fetch a canonical economic time series from BCB, IPEA or IBGE."""
        return ts_fetch_economic_timeseries(
            provider=provider,
            series_code=series_code,
            last=last,
            start_date=start_date,
            end_date=end_date,
        )

    @mcp.tool()
    def read_timeseries_store(
        db_path: str = "",
        asset_id: str = "",
        series_id: str = "",
        start_date: str = "",
        end_date: str = "",
        limit: int = 5000,
    ) -> dict:
        """Read records from the local DadosBR time series SQLite store."""
        db_path, error = _validate_mcp_local_path(db_path, purpose="timeseries_store", source_id="timeseries")
        if error:
            return error
        return ts_read_timeseries_records(
            db_path=db_path or None,
            asset_id=asset_id,
            series_id=series_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

    @mcp.tool()
    def write_asset_history_to_store(
        asset_id: str,
        start_date: str = "",
        end_date: str = "",
        adjusted: bool = False,
        b3_file_path: str = "",
        limit: int = 5000,
        db_path: str = "",
    ) -> dict:
        """Fetch an asset history and persist it to the local time series store."""
        b3_file_path, error = _validate_mcp_local_path(
            b3_file_path, purpose="b3_cotahist_file", source_id="timeseries"
        )
        if error:
            return error
        db_path, error = _validate_mcp_local_path(db_path, purpose="timeseries_store", source_id="timeseries")
        if error:
            return error
        if not db_path:
            _default_store, error = _validate_mcp_local_path(
                str(_DEFAULT_TIMESERIES_STORE_PATH), purpose="timeseries_store", source_id="timeseries"
            )
            if error:
                return error
        return ts_write_asset_history_to_store(
            asset_id=asset_id,
            start_date=start_date,
            end_date=end_date,
            adjusted=adjusted,
            b3_file_path=b3_file_path,
            limit=limit,
            db_path=db_path or None,
        )

    @mcp.tool()
    def list_benchmarks() -> dict:
        """List benchmark aliases such as SELIC, CDI, IPCA, IBOV and IFIX."""
        return benchmark_list()

    @mcp.tool()
    def get_benchmark_metadata(benchmark_id: str) -> dict:
        """Get metadata for one benchmark alias."""
        return benchmark_get_metadata(benchmark_id)

    @mcp.tool()
    def get_benchmark_history(
        benchmark_id: str,
        start_date: str = "",
        end_date: str = "",
        last: int = 200,
        real: bool = False,
        deflator: str = "ipca",
    ) -> dict:
        """Fetch benchmark history and optionally return real deflated values."""
        return benchmark_fetch_history(
            benchmark_id=benchmark_id,
            start_date=start_date,
            end_date=end_date,
            last=last,
            real=real,
            deflator=deflator,
        )

    @mcp.tool()
    def get_real_benchmark_history(
        benchmark_id: str,
        start_date: str = "",
        end_date: str = "",
        last: int = 200,
        deflator: str = "ipca",
    ) -> dict:
        """Fetch real benchmark history deflated by IPCA or another deflator."""
        return benchmark_fetch_history(
            benchmark_id=benchmark_id,
            start_date=start_date,
            end_date=end_date,
            last=last,
            real=True,
            deflator=deflator,
        )

    @mcp.tool()
    def compare_asset_to_benchmark(
        asset_id: str,
        benchmark_id: str,
        start_date: str = "",
        end_date: str = "",
        adjusted: bool = False,
        b3_file_path: str = "",
        last: int = 5000,
    ) -> dict:
        """Compare an asset return series against a benchmark return series."""
        b3_file_path, error = _validate_mcp_local_path(
            b3_file_path, purpose="b3_cotahist_file", source_id="benchmarks"
        )
        if error:
            return error
        return benchmark_compare_asset_to_benchmark(
            asset_id=asset_id,
            benchmark_id=benchmark_id,
            start_date=start_date,
            end_date=end_date,
            adjusted=adjusted,
            b3_file_path=b3_file_path,
            last=last,
        )

    @mcp.tool()
    def get_yield_curve(limit: int = 200) -> dict:
        """Return raw Tesouro-derived maturity and rate points."""
        return benchmark_fetch_yield_curve(limit=limit)

    @mcp.tool()
    def list_macro_calendar() -> dict:
        """List macroeconomic release calendar rules and frequencies."""
        return benchmark_list_macro_calendar()

    @mcp.tool()
    def get_tesouro_fixed_income(limit: int = 200) -> dict:
        """Return Tesouro Direto bonds as canonical fixed income instruments."""
        return fi_get_tesouro(limit=limit)

    @mcp.tool()
    def get_private_credit_debentures(company: str = "", year: int = 0, limit: int = 200) -> dict:
        """Return private credit debenture records from public BNDES/CVM data."""
        return fi_get_private_credit_debentures(company=company, year=year, limit=limit)

    @mcp.tool()
    def get_fund_fixed_income_exposure(cnpj: str = "", date: str = "", limit: int = 5000) -> dict:
        """Return fixed income exposure records for CVM investment funds."""
        return fi_get_fund_exposure(cnpj=cnpj, date=date, limit=limit)

    @mcp.tool()
    def get_fixed_income_cashflows(
        settlement_date: str,
        maturity_date: str,
        principal: float,
        annual_coupon_rate: float,
        payments_per_year: int = 1,
    ) -> dict:
        """Generate projected fixed income cashflows for a coupon bond."""
        return fi_get_cashflows(
            settlement_date=settlement_date,
            maturity_date=maturity_date,
            principal=principal,
            annual_coupon_rate=annual_coupon_rate,
            payments_per_year=payments_per_year,
        )

    @mcp.tool()
    def get_fixed_income_analytics(
        price: float,
        settlement_date: str,
        maturity_date: str,
        principal: float,
        annual_coupon_rate: float,
        payments_per_year: int = 1,
    ) -> dict:
        """Calculate fixed income analytics such as yield and duration."""
        return fi_get_analytics(
            price=price,
            settlement_date=settlement_date,
            maturity_date=maturity_date,
            principal=principal,
            annual_coupon_rate=annual_coupon_rate,
            payments_per_year=payments_per_year,
        )

    @mcp.tool()
    def get_fixed_income_credit_spread_curve(
        benchmark_rate: float,
        observed_at: str = "",
        company: str = "",
        year: int = 0,
        limit: int = 200,
    ) -> dict:
        """Build a credit spread curve over a benchmark annual rate."""
        return fi_get_credit_spread_curve(
            benchmark_rate=benchmark_rate,
            observed_at=observed_at,
            company=company,
            year=year,
            limit=limit,
        )

    @mcp.tool()
    def get_company_fundamentals(
        cvm_code: str,
        year: int,
        doc_type: str = "dfp",
        ticker: str = "",
        b3_file_path: str = "",
        shares_outstanding: float = 0,
        market_cap: float = 0,
        limit: int = 5000,
    ) -> dict:
        """Build a canonical fundamentals snapshot for a CVM company."""
        b3_file_path, error = _validate_mcp_local_path(
            b3_file_path, purpose="b3_cotahist_file", source_id="fundamentals"
        )
        if error:
            return error
        return fundamentals_get_company(
            cvm_code=cvm_code,
            year=year,
            doc_type=doc_type,
            ticker=ticker,
            b3_file_path=b3_file_path,
            shares_outstanding=shares_outstanding,
            market_cap=market_cap,
            limit=limit,
        )

    @mcp.tool()
    def get_company_statement(
        cvm_code: str,
        year: int,
        doc_type: str = "dfp",
        statement: str = "all",
        limit: int = 5000,
    ) -> dict:
        """Fetch canonical CVM financial statement lines for a company."""
        return fundamentals_get_company_statement(
            cvm_code=cvm_code,
            year=year,
            doc_type=doc_type,
            statement=statement,
            limit=limit,
        )

    @mcp.tool()
    def get_company_ratios(
        cvm_code: str,
        year: int,
        doc_type: str = "dfp",
        ticker: str = "",
        b3_file_path: str = "",
        shares_outstanding: float = 0,
        market_cap: float = 0,
    ) -> dict:
        """Calculate financial ratios for a CVM company."""
        b3_file_path, error = _validate_mcp_local_path(
            b3_file_path, purpose="b3_cotahist_file", source_id="fundamentals"
        )
        if error:
            return error
        return fundamentals_get_company_ratios(
            cvm_code=cvm_code,
            year=year,
            doc_type=doc_type,
            ticker=ticker,
            b3_file_path=b3_file_path,
            shares_outstanding=shares_outstanding,
            market_cap=market_cap,
        )

    @mcp.tool()
    def get_company_dividends(ticker: str, start_date: str = "", end_date: str = "", limit: int = 500) -> dict:
        """Fetch dividend and distribution events for a listed ticker."""
        return fundamentals_get_company_dividends(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

    @mcp.tool()
    def compare_companies_fundamentals(
        cvm_codes: str,
        year: int,
        metric: str = "roe",
        doc_type: str = "dfp",
        limit_per_company: int = 2000,
    ) -> dict:
        """Compare fundamentals metrics across CVM companies."""
        return fundamentals_compare_companies(
            cvm_codes=cvm_codes,
            year=year,
            metric=metric,
            doc_type=doc_type,
            limit_per_company=limit_per_company,
        )

    @mcp.tool()
    def list_fundamentals_calendar() -> dict:
        """List fundamentals reporting calendar rules and frequencies."""
        return fundamentals_list_calendar()

    @mcp.tool()
    def list_corporate_action_types() -> dict:
        """List supported corporate action and provento event types."""
        return ca_list_types()

    @mcp.tool()
    def get_corporate_actions(
        ticker: str,
        source: str = "yfinance",
        start_date: str = "",
        end_date: str = "",
        limit: int = 500,
    ) -> dict:
        """Fetch corporate actions and proventos for a ticker."""
        return ca_get_actions(
            ticker=ticker,
            source=source,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

    @mcp.tool()
    def get_corporate_action_factors(
        ticker: str,
        source: str = "yfinance",
        start_date: str = "",
        end_date: str = "",
        limit: int = 500,
    ) -> dict:
        """Calculate cumulative adjustment factors from corporate actions."""
        return ca_get_factors(
            ticker=ticker,
            source=source,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

    @mcp.tool()
    def get_corporate_action_adjusted_history(
        ticker: str,
        b3_file_path: str = "",
        source: str = "yfinance",
        start_date: str = "",
        end_date: str = "",
        limit: int = 5000,
    ) -> dict:
        """Fetch price history adjusted by corporate action factors."""
        b3_file_path, error = _validate_mcp_local_path(
            b3_file_path, purpose="b3_cotahist_file", source_id="corporate_actions"
        )
        if error:
            return error
        return ca_get_adjusted_history(
            ticker=ticker,
            b3_file_path=b3_file_path,
            source=source,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

    @mcp.tool()
    def normalize_corporate_actions(rows: list[dict[str, Any]]) -> dict:
        """Normalize local corporate action rows to the DadosBR schema."""
        return ca_normalize_actions(rows)

    @mcp.tool()
    def list_derivative_families() -> dict:
        """List supported B3 derivative families such as DI1, DOL and WIN."""
        return deriv_list_families()

    @mcp.tool()
    def normalize_futures_quotes(rows: list[dict[str, Any]], family: str = "", limit: int = 5000) -> dict:
        """Normalize futures quote rows to the DadosBR derivative schema."""
        records = deriv_normalize_futures_quotes(rows, family=family, limit=limit)
        return deriv_make_response(records, source_url="local://dadosbr/mcp/derivatives/futures/normalize")

    @mcp.tool()
    def get_derivative_futures_from_file(file_path: str, family: str = "", limit: int = 5000) -> dict:
        """Parse derivative futures quotes from an authorized local CSV file."""
        file_path, error = _validate_mcp_local_path(file_path, purpose="derivatives_file", source_id="derivatives")
        if error:
            return error
        return deriv_get_futures_from_file(file_path=file_path, family=family, limit=limit)

    @mcp.tool()
    def parse_derivatives_futures_text(
        raw_text: str,
        family: str = "",
        limit: int = 5000,
        encoding: str = "utf-8",
    ) -> dict:
        """Parse derivative futures CSV text content sent through MCP JSON."""
        raw_bytes, error = _encode_mcp_text_payload(
            raw_text,
            encoding=encoding,
            purpose="derivatives/futures/text",
            source_id="derivatives",
        )
        if error is not None:
            return error
        return deriv_parse_csv_bytes(
            raw_bytes or b"",
            source_url="mcp://dadosbr/derivatives/futures/text",
            family=family,
            limit=limit,
        )

    @mcp.tool()
    def normalize_options_chain(rows: list[dict[str, Any]], limit: int = 5000) -> dict:
        """Normalize listed options chain rows to the DadosBR schema."""
        records = deriv_normalize_options_chain(rows, limit=limit)
        return deriv_make_response(records, source_url="local://dadosbr/mcp/derivatives/options/normalize")

    @mcp.tool()
    def list_interest_curve_sources() -> dict:
        """List supported interest curve sources and curve identifiers."""
        return curves_list_sources()

    @mcp.tool()
    def get_tesouro_interest_curve(limit: int = 200) -> dict:
        """Return normalized Tesouro Direto interest curve points."""
        return curves_get_tesouro_interest_curve(limit=limit)

    @mcp.tool()
    def normalize_interest_curve_points(
        rows: list[dict[str, Any]],
        source_id: str = "manual",
        curve_id: str = "",
    ) -> dict:
        """Normalize generic interest curve point rows."""
        records = curves_normalize_curve_points(rows, source_id=source_id, curve_id=curve_id)
        return curves_make_response(records, source_url="local://dadosbr/mcp/curves/normalize")

    @mcp.tool()
    def normalize_anbima_curve_rows(rows: list[dict[str, Any]]) -> dict:
        """Normalize ANBIMA curve feed rows into prefix, IPCA and implied inflation curves."""
        records = curves_normalize_anbima_curve_rows(rows)
        return curves_make_response(records, source_url="local://dadosbr/mcp/curves/anbima/normalize")

    @mcp.tool()
    def build_di_curve_from_futures(rows: list[dict[str, Any]]) -> dict:
        """Build a DI x Pre curve from normalized DI1 futures rows."""
        records = curves_build_di_curve_from_futures(rows)
        return curves_make_response(records, source_url="local://dadosbr/mcp/curves/di-futures")

    @mcp.tool()
    def interpolate_interest_curve(rows: list[dict[str, Any]], target_tenor_years: float) -> dict:
        """Interpolate an interest curve at a target tenor in years."""
        record = curves_interpolate_interest_curve(rows, target_tenor_years=target_tenor_years)
        return curves_make_response([record], source_url="local://dadosbr/mcp/curves/interpolate")

    @mcp.tool()
    def calculate_discount_factors(rows: list[dict[str, Any]]) -> dict:
        """Calculate discount factors and zero prices for curve points."""
        records = curves_calculate_discount_factors(rows)
        return curves_make_response(records, source_url="local://dadosbr/mcp/curves/discount-factors")

    @mcp.tool()
    def calculate_forward_rates(rows: list[dict[str, Any]]) -> dict:
        """Calculate forward rates between ordered interest curve points."""
        records = curves_calculate_forward_rates(rows)
        return curves_make_response(records, source_url="local://dadosbr/mcp/curves/forward-rates")

    return mcp


def main() -> None:
    server = _build_server()
    server.run()


if __name__ == "__main__":
    main()
