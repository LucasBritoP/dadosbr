from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@dataclass(frozen=True)
class McpCase:
    name: str
    arguments: dict[str, Any]
    timeout_seconds: int = 30
    expected_error_code: str = ""


@dataclass(frozen=True)
class SmokeContext:
    repo_root: Path
    workspace: Path
    b3_file: Path
    cnpj_db: Path
    derivatives_file: Path
    timeseries_db: Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a real MCP fire test against every DadosBR tool.")
    parser.add_argument(
        "--output",
        default="",
        help="Optional Markdown report path. Defaults to .dadosbr/reports/mcp-fire-test-<timestamp>.md.",
    )
    parser.add_argument(
        "--keep-workspace",
        action="store_true",
        help="Do not remove the temporary smoke-test workspace.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    workspace = Path(tempfile.mkdtemp(prefix="dadosbr-mcp-fire-"))
    context = prepare_workspace(repo_root=repo_root, workspace=workspace)
    report_path = Path(args.output) if args.output else default_report_path(repo_root)

    started = datetime.now(UTC)
    try:
        results = asyncio.run(run_fire_test(context))
        ended = datetime.now(UTC)
        report = build_report(results, context=context, started=started, ended=ended)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
        print(report)
        print(f"\nReport written to: {report_path}")
        failures = [
            item
            for item in results["cases"]
            if item["status"] not in {"pass", "expected_error"}
        ]
        return 1 if failures else 0
    finally:
        if args.keep_workspace:
            print(f"Temporary workspace kept at: {workspace}")
        else:
            shutil.rmtree(workspace, ignore_errors=True)


def default_report_path(repo_root: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return repo_root / ".dadosbr" / "reports" / f"mcp-fire-test-{timestamp}.md"


def prepare_workspace(*, repo_root: Path, workspace: Path) -> SmokeContext:
    b3_file = workspace / "COTAHIST_SMOKE.TXT"
    b3_file.write_text(sample_cotahist_text(), encoding="latin-1")

    derivatives_file = workspace / "derivatives.csv"
    derivatives_file.write_text(sample_derivatives_csv(), encoding="utf-8")

    cnpj_input = workspace / "cnpj_input"
    cnpj_input.mkdir(parents=True, exist_ok=True)
    for path in (repo_root / "tests" / "fixtures" / "receita_cnpj").glob("*.zip"):
        shutil.copy2(path, cnpj_input / path.name)

    cnpj_db = workspace / ".dadosbr" / "datasets" / "receita_cnpj" / "index" / "cnpj.sqlite"
    from dadosbr.connectors.receita_cnpj import build_cnpj_index

    response = build_cnpj_index(cnpj_input, db_path=cnpj_db)
    if not response.get("ok"):
        raise RuntimeError(f"Could not build CNPJ fixture index: {response}")

    timeseries_db = workspace / ".dadosbr" / "datasets" / "timeseries" / "timeseries.sqlite"
    timeseries_db.parent.mkdir(parents=True, exist_ok=True)

    return SmokeContext(
        repo_root=repo_root,
        workspace=workspace,
        b3_file=b3_file,
        cnpj_db=cnpj_db,
        derivatives_file=derivatives_file,
        timeseries_db=timeseries_db,
    )


async def run_fire_test(context: SmokeContext) -> dict[str, Any]:
    cases = build_cases(context)
    listed_tools = await list_mcp_tools(context)
    listed_names = {tool["name"] for tool in listed_tools}
    case_names = {case.name for case in cases}

    results: dict[str, Any] = {
        "listed_tools": listed_tools,
        "missing_cases": sorted(listed_names - case_names),
        "extra_cases": sorted(case_names - listed_names),
        "cases": [],
    }
    for index, case in enumerate(cases, start=1):
        print(f"[{index:02d}/{len(cases):02d}] {case.name}")
        result = await run_case(context, case)
        results["cases"].append(result)
        status = result["status"]
        elapsed = result.get("elapsed_seconds")
        print(f"  -> {status} in {elapsed}s")
    return results


async def list_mcp_tools(context: SmokeContext) -> list[dict[str, Any]]:
    params = server_params(context)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await asyncio.wait_for(session.initialize(), timeout=15)
            response = await asyncio.wait_for(session.list_tools(), timeout=15)
            return [
                {
                    "name": tool.name,
                    "description": tool.description or "",
                }
                for tool in response.tools
            ]


async def run_case(context: SmokeContext, case: McpCase) -> dict[str, Any]:
    started = time.perf_counter()
    params = server_params(context)
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=15)
                response = await asyncio.wait_for(
                    session.call_tool(case.name, case.arguments),
                    timeout=case.timeout_seconds,
                )
    except TimeoutError:
        return case_result(case, started, status="timeout", error={"code": "timeout"})
    except Exception as exc:  # noqa: BLE001
        return case_result(
            case,
            started,
            status="transport_error",
            error={"code": exc.__class__.__name__, "message": str(exc)},
        )

    payload = parse_tool_payload(response)
    ok = payload.get("ok") is True
    error = payload.get("error") or {}
    error_code = str(error.get("code", "")) if isinstance(error, dict) else ""
    if ok:
        status = "pass"
    elif case.expected_error_code and error_code == case.expected_error_code:
        status = "expected_error"
    else:
        status = "fail"
    return case_result(case, started, status=status, payload=payload)


def case_result(
    case: McpCase,
    started: float,
    *,
    status: str,
    payload: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = payload or {}
    records = payload.get("records")
    sample = records[0] if isinstance(records, list) and records else None
    return {
        "tool": case.name,
        "arguments": case.arguments,
        "status": status,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "ok": payload.get("ok"),
        "source_id": payload.get("source_id"),
        "source_mode": payload.get("source_mode"),
        "records_count": len(records) if isinstance(records, list) else None,
        "error": error or payload.get("error"),
        "sample_record": compact_sample(sample),
    }


def parse_tool_payload(response: Any) -> dict[str, Any]:
    if not getattr(response, "content", None):
        return {"ok": False, "error": {"code": "empty_response", "message": "No content"}}
    text = response.content[0].text
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "error": {"code": "non_json_response", "message": text[:500]},
        }
    if isinstance(payload, dict):
        return payload
    return {"ok": False, "error": {"code": "non_object_response", "message": type(payload).__name__}}


def compact_sample(sample: Any) -> dict[str, Any] | None:
    if not isinstance(sample, dict):
        return None
    compact: dict[str, Any] = {}
    for key, value in sample.items():
        if len(compact) >= 8:
            break
        if isinstance(value, (dict, list)):
            compact[key] = f"<{type(value).__name__}:{len(value)}>"
        else:
            compact[key] = value
    return compact


def server_params(context: SmokeContext) -> StdioServerParameters:
    env = os.environ.copy()
    env.update(smoke_env(context))
    return StdioServerParameters(
        command=os.environ.get("PYTHON", "python"),
        args=["-m", "dadosbr.mcp.server"],
        env=env,
        cwd=str(context.workspace),
    )


def smoke_env(context: SmokeContext) -> dict[str, str]:
    fixture_root = context.repo_root / "tests" / "fixtures"
    src_path = str(context.repo_root / "src")
    current_pythonpath = os.environ.get("PYTHONPATH", "")
    pythonpath = src_path if not current_pythonpath else src_path + os.pathsep + current_pythonpath
    return {
        "PYTHONPATH": pythonpath,
        "DADOSBR_CACHE_DIR": str(context.workspace / ".dadosbr" / "cache"),
        "DADOSBR_CACHE_TTL_SECONDS": "86400",
        "DADOSBR_HTTP_RETRIES": "1",
        "DADOSBR_HTTP_RETRY_BACKOFF_SECONDS": "0.05",
        "DADOSBR_ALLOW_B3_DOWNLOAD": "0",
        "DADOSBR_B3_COTAHIST_FILE": str(context.b3_file),
        "DADOSBR_ENABLE_LOCAL_FILE_ENDPOINTS": "1",
        "DADOSBR_LOCAL_DATA_DIR": str(context.workspace),
        "DADOSBR_MAX_UPLOAD_BYTES": "52428800",
        "DADOSBR_ENABLE_ADMIN_MCP": "0",
        "DADOSBR_ADMIN_TOKEN": "fire-test-token",
        "DADOSBR_CVM_COMPANY_REPORT_TIMEOUT_SECONDS": "12",
        "DADOSBR_YFINANCE_TIMEOUT_SECONDS": "8",
        "DADOSBR_YFINANCE_HISTORY_PERIOD": "2y",
        "DADOSBR_YFINANCE_DIVIDEND_PERIOD": "2y",
        "DADOSBR_YFINANCE_DIVIDEND_CACHE_TTL_SECONDS": "86400",
        "DADOSBR_YFINANCE_ACTION_PERIOD": "2y",
        "DADOSBR_YFINANCE_ACTION_CACHE_TTL_SECONDS": "86400",
        "DADOSBR_TESOURO_PACKAGE_FILE": str(fixture_root / "tesouro_package.json"),
        "DADOSBR_TESOURO_RATES_CSV_FILE": str(fixture_root / "tesouro_rates.csv"),
        "DADOSBR_COMEX_DATA_DIR": str(fixture_root / "comex"),
    }


def build_cases(context: SmokeContext) -> list[McpCase]:
    b3_text = sample_cotahist_text()
    derivative_rows = [
        {
            "symbol": "DI1F27",
            "observed_at": "2026-05-05",
            "maturity_date": "2027-01-04",
            "business_days": 170,
            "settlement_price": 93500,
            "previous_settlement_price": 93400,
        }
    ]
    curve_rows = [
        {
            "curve_id": "test_curve",
            "observed_at": "2026-05-05",
            "business_days": 252,
            "tenor_years": 1.0,
            "annual_rate": 0.10,
            "annual_rate_pct": 10.0,
        },
        {
            "curve_id": "test_curve",
            "observed_at": "2026-05-05",
            "business_days": 504,
            "tenor_years": 2.0,
            "annual_rate": 0.12,
            "annual_rate_pct": 12.0,
        },
    ]
    return [
        McpCase("list_sources", {}),
        McpCase("get_source_metadata", {"source_id": "bcb_sgs"}),
        McpCase("get_bcb_sgs_series", {"series_id": "11", "last": 3}),
        McpCase("get_bcb_ptax", {"date": "2026-05-07", "currency": "USD"}),
        McpCase("get_bcb_focus", {"indicator": "IPCA", "top": 3}),
        McpCase("get_cvm_company_reports", {"year": 2024, "doc_type": "dfp", "cvm_code": "9512", "limit": 3}, 45),
        McpCase("get_cvm_fund_daily_info", {"cnpj": "26673556000132", "limit": 2}, 45),
        McpCase("get_cvm_fund_portfolio", {"cnpj": "26673556000132", "limit": 2}, 45),
        McpCase("get_cvm_fii_monthly_report", {"year": 2024, "month": 12, "limit": 2}, 45),
        McpCase("get_b3_cotahist_quotes", {"year": 2026, "ticker": "PETR4", "limit": 2}),
        McpCase("parse_b3_cotahist_text", {"raw_text": b3_text, "ticker": "PETR4", "limit": 1, "encoding": "latin-1"}),
        McpCase("get_tesouro_rates", {"limit": 3}),
        McpCase("get_ibge_sidra", {"path": "t/1737/n1/all/v/63/p/last 1"}),
        McpCase("get_ipeadata_series", {"series_code": "PRECOS12_IPCA12", "top": 3}),
        McpCase("get_cnpj_status", {}),
        McpCase("get_cnpj_company", {"cnpj": "12345678000190"}),
        McpCase("search_cnpj_companies", {"q": "ACME", "uf": "SP", "limit": 3}),
        McpCase("get_cnpj_partners", {"cnpj": "12345678000190"}),
        McpCase("admin_sync_cnpj", {"period": "latest", "max_files": 1}, 20, "admin_mcp_disabled"),
        McpCase("get_comex_ncm", {"flow": "export", "year": 2026, "ncm": "12019000", "uf": "SP", "limit": 3}),
        McpCase("summarize_comex_ncm", {"flow": "export", "year": 2026, "group_by": "month", "ncm": "12019000"}),
        McpCase("get_comex_municipality", {"flow": "export", "year": 2026, "uf": "SP", "municipality_code": "3550308", "limit": 3}),
        McpCase("get_comex_table", {"table_name": "NCM", "limit": 3}),
        McpCase("get_bndes_operations", {"uf": "SP", "year": 2024, "limit": 2}, 45),
        McpCase("get_bndes_variable_income", {"kind": "debentures", "limit": 2}, 45),
        McpCase("list_bndes_datasets", {"query": "operacoes financiamento", "rows": 2}, 30),
        McpCase("get_asset_master", {"asset_id": "B3:PETR4", "b3_file_path": str(context.b3_file)}),
        McpCase("search_asset_master", {"q": "ACME", "db_path": str(context.cnpj_db), "b3_file_path": str(context.b3_file), "limit": 3}),
        McpCase("get_issuer_master", {"cnpj": "12345678000190", "db_path": str(context.cnpj_db)}),
        McpCase("get_instrument_master", {"ticker": "PETR4", "b3_file_path": str(context.b3_file)}),
        McpCase("get_cnae_taxonomy", {"code": "6201501", "db_path": str(context.cnpj_db)}),
        McpCase("get_ncm_taxonomy", {"code": "12019000"}),
        McpCase("get_asset_price_history", {"asset_id": "B3:PETR4", "b3_file_path": str(context.b3_file), "limit": 2}),
        McpCase("write_asset_history_to_store", {"asset_id": "B3:PETR4", "b3_file_path": str(context.b3_file), "db_path": str(context.timeseries_db), "limit": 2}),
        McpCase("read_timeseries_store", {"db_path": str(context.timeseries_db), "asset_id": "B3:PETR4", "limit": 2}),
        McpCase("get_economic_timeseries", {"provider": "bcb_sgs", "series_code": "11", "last": 3}),
        McpCase("list_benchmarks", {}),
        McpCase("get_benchmark_metadata", {"benchmark_id": "selic"}),
        McpCase("get_benchmark_history", {"benchmark_id": "selic", "last": 3}),
        McpCase("get_real_benchmark_history", {"benchmark_id": "selic", "last": 3, "deflator": "ipca"}),
        McpCase("compare_asset_to_benchmark", {"asset_id": "B3:PETR4", "benchmark_id": "selic", "b3_file_path": str(context.b3_file), "last": 3}),
        McpCase("get_yield_curve", {"limit": 3}),
        McpCase("list_macro_calendar", {}),
        McpCase("get_tesouro_fixed_income", {"limit": 3}),
        McpCase("get_private_credit_debentures", {"limit": 2}, 45),
        McpCase("get_fund_fixed_income_exposure", {"cnpj": "26673556000132", "limit": 3}, 45),
        McpCase("get_fixed_income_cashflows", {"settlement_date": "2026-01-01", "maturity_date": "2028-01-01", "principal": 1000.0, "annual_coupon_rate": 0.1, "payments_per_year": 1}),
        McpCase("get_fixed_income_analytics", {"price": 1000.0, "settlement_date": "2026-01-01", "maturity_date": "2028-01-01", "principal": 1000.0, "annual_coupon_rate": 0.1, "payments_per_year": 1}),
        McpCase("get_fixed_income_credit_spread_curve", {"benchmark_rate": 0.11, "limit": 2}, 45),
        McpCase("get_company_fundamentals", {"cvm_code": "9512", "year": 2024, "doc_type": "dfp", "ticker": "PETR4", "shares_outstanding": 13044496000, "limit": 20}, 45),
        McpCase("get_company_statement", {"cvm_code": "9512", "year": 2024, "doc_type": "dfp", "statement": "all", "limit": 20}, 45),
        McpCase("get_company_ratios", {"cvm_code": "9512", "year": 2024, "doc_type": "dfp", "ticker": "PETR4", "shares_outstanding": 13044496000}, 45),
        McpCase("get_company_dividends", {"ticker": "PETR4", "limit": 5}, 25),
        McpCase("compare_companies_fundamentals", {"cvm_codes": "9512,4170", "year": 2024, "metric": "roe"}, 60),
        McpCase("list_fundamentals_calendar", {}),
        McpCase("list_corporate_action_types", {}),
        McpCase("get_corporate_actions", {"ticker": "PETR4", "limit": 5}, 25),
        McpCase("get_corporate_action_factors", {"ticker": "PETR4", "limit": 5}, 25),
        McpCase("get_corporate_action_adjusted_history", {"ticker": "PETR4", "b3_file_path": str(context.b3_file), "limit": 2}, 25),
        McpCase("normalize_corporate_actions", {"rows": [{"ticker": "PETR4", "event_type": "dividend", "ex_date": "2026-01-02", "amount_per_share": 1.23, "reference_price": 30.0}]}),
        McpCase("list_derivative_families", {}),
        McpCase("normalize_futures_quotes", {"rows": derivative_rows, "family": "DI1", "limit": 2}),
        McpCase("get_derivative_futures_from_file", {"file_path": str(context.derivatives_file), "family": "DI1", "limit": 2}),
        McpCase("parse_derivatives_futures_text", {"raw_text": sample_derivatives_csv(), "family": "WDO", "limit": 2}),
        McpCase("normalize_options_chain", {"rows": [{"symbol": "PETRF260", "underlying_ticker": "PETR4", "option_type": "CALL", "expiration_date": "2026-06-19", "strike_price": "26,00", "last_price": "1,25", "observed_at": "2026-05-05"}], "limit": 2}),
        McpCase("list_interest_curve_sources", {}),
        McpCase("get_tesouro_interest_curve", {"limit": 3}),
        McpCase("normalize_interest_curve_points", {"rows": curve_rows, "source_id": "manual", "curve_id": "test_curve"}),
        McpCase("normalize_anbima_curve_rows", {"rows": [{"data_referencia": "2026-05-05", "vertice_du": "252", "taxa_prefixadas": "10,25", "taxa_ipca": "5,50", "taxa_implicita": "4,50"}]}),
        McpCase("build_di_curve_from_futures", {"rows": derivative_rows}),
        McpCase("interpolate_interest_curve", {"rows": curve_rows, "target_tenor_years": 1.5}),
        McpCase("calculate_discount_factors", {"rows": curve_rows}),
        McpCase("calculate_forward_rates", {"rows": curve_rows}),
    ]


def build_report(
    results: dict[str, Any],
    *,
    context: SmokeContext,
    started: datetime,
    ended: datetime,
) -> str:
    cases = results["cases"]
    counts: dict[str, int] = {}
    for item in cases:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    elapsed_total = (ended - started).total_seconds()
    lines = [
        "# MCP Fire Test Report",
        "",
        f"- Started UTC: `{started.isoformat()}`",
        f"- Finished UTC: `{ended.isoformat()}`",
        f"- Total elapsed seconds: `{elapsed_total:.1f}`",
        f"- Tools listed by MCP: `{len(results['listed_tools'])}`",
        f"- Cases executed: `{len(cases)}`",
        f"- Status counts: `{json.dumps(counts, sort_keys=True)}`",
        f"- Temporary workspace: `{context.workspace}`",
        "",
    ]
    if results["missing_cases"] or results["extra_cases"]:
        lines.extend(
            [
                "## Inventory Drift",
                "",
                f"- Missing cases: `{', '.join(results['missing_cases']) or 'none'}`",
                f"- Extra cases: `{', '.join(results['extra_cases']) or 'none'}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Results",
            "",
            "| # | Tool | Status | Seconds | OK | Records | Source Mode | Error |",
            "|---:|---|---|---:|---|---:|---|---|",
        ]
    )
    for index, item in enumerate(cases, start=1):
        error = item.get("error") or {}
        error_text = error.get("code", "") if isinstance(error, dict) else str(error)
        lines.append(
            "| {idx} | `{tool}` | `{status}` | {seconds} | `{ok}` | {records} | `{mode}` | `{error}` |".format(
                idx=index,
                tool=item["tool"],
                status=item["status"],
                seconds=item["elapsed_seconds"],
                ok=item.get("ok"),
                records="" if item.get("records_count") is None else item["records_count"],
                mode=item.get("source_mode") or "",
                error=error_text,
            )
        )
    lines.extend(["", "## Calls And Samples", ""])
    for item in cases:
        lines.extend(
            [
                f"### `{item['tool']}`",
                "",
                "Arguments:",
                "",
                "```json",
                json.dumps(item["arguments"], ensure_ascii=False, indent=2),
                "```",
                "",
                "Result summary:",
                "",
                "```json",
                json.dumps(
                    {
                        "status": item["status"],
                        "elapsed_seconds": item["elapsed_seconds"],
                        "ok": item.get("ok"),
                        "source_id": item.get("source_id"),
                        "source_mode": item.get("source_mode"),
                        "records_count": item.get("records_count"),
                        "error": item.get("error"),
                        "sample_record": item.get("sample_record"),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def sample_cotahist_text() -> str:
    return "".join(
        [
            cotahist_line("20260504", open_price=29900, high_price=30400, low_price=29800, close_price=30000),
            cotahist_line("20260505", open_price=30123, high_price=31000, low_price=29900, close_price=30555),
            cotahist_line("20260506", open_price=30600, high_price=31200, low_price=30400, close_price=30950),
        ]
    )


def cotahist_line(
    date_text: str,
    *,
    open_price: int,
    high_price: int,
    low_price: int,
    close_price: int,
) -> str:
    line = [" "] * 245
    line[0:2] = list("01")
    line[2:10] = list(date_text)
    line[12:24] = list("PETR4       ")
    line[24:27] = list("010")
    line[27:39] = list("PETROBRAS   ")
    line[39:49] = list("PN      N1")
    line[52:56] = list("R$  ")
    line[56:69] = list(f"{open_price:013d}")
    line[69:82] = list(f"{high_price:013d}")
    line[82:95] = list(f"{low_price:013d}")
    line[95:108] = list(f"{(open_price + close_price) // 2:013d}")
    line[108:121] = list(f"{close_price:013d}")
    line[121:134] = list(f"{close_price - 50:013d}")
    line[134:147] = list(f"{close_price + 50:013d}")
    line[147:152] = list("00123")
    line[152:170] = list("000000000000000500")
    line[170:188] = list("000000000000123456")
    line[230:242] = list("BRPETRACNPR6")
    line[242:245] = list("123")
    return "".join(line) + "\n"


def sample_derivatives_csv() -> str:
    return (
        "Data Pregao;Codigo Instrumento;Preco Ajuste Atual;Preco Ajuste Anterior;"
        "Quantidade Negociada;Contratos em Aberto\n"
        "2026-05-05;WDOQ26;5.123,50;5.100,00;12000;200000\n"
        "2026-05-05;DI1F27;93500;93400;1500;25000\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
