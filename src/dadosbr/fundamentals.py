from __future__ import annotations

import importlib
import json
import os
import queue
import threading
import unicodedata
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

from dadosbr.connectors.cvm import fetch_cvm_company_reports, fetch_cvm_company_reports_batch
from dadosbr.core import DataSourceError, make_failure, make_success
from dadosbr.core.cache import DiskCache
from dadosbr.core.http import http_get_bytes_cached, http_response_metadata
from dadosbr.core.utils import sha256_json
from dadosbr.core.yfinance import (
    yfinance_dividend_cache_ttl_seconds,
    yfinance_dividend_period,
    yfinance_history_kwargs,
    yfinance_timeout_seconds,
)
from dadosbr.timeseries import fetch_asset_price_history

SOURCE_ID = "fundamentals"

FUNDAMENTALS_CALENDAR = [
    {
        "calendar_id": "cvm_dfp",
        "name": "DFP - Demonstracoes Financeiras Padronizadas",
        "source_id": "cvm_dados_abertos",
        "frequency": "annual",
        "release_rule": "Entrega anual conforme calendario regulatorio CVM.",
        "revision_policy": "possible",
    },
    {
        "calendar_id": "cvm_itr",
        "name": "ITR - Informacoes Trimestrais",
        "source_id": "cvm_dados_abertos",
        "frequency": "quarterly",
        "release_rule": "Entrega trimestral conforme calendario regulatorio CVM.",
        "revision_policy": "possible",
    },
    {
        "calendar_id": "cvm_fre",
        "name": "FRE - Formulario de Referencia",
        "source_id": "cvm_dados_abertos",
        "frequency": "annual_or_event_driven",
        "release_rule": "Atualizacao anual e por eventos relevantes conforme CVM.",
        "revision_policy": "possible",
    },
    {
        "calendar_id": "cvm_fca",
        "name": "FCA - Formulario Cadastral",
        "source_id": "cvm_dados_abertos",
        "frequency": "event_driven",
        "release_rule": "Atualizacao cadastral conforme CVM.",
        "revision_policy": "possible",
    },
]


def canonical_statement_line(row: dict[str, Any]) -> dict[str, Any]:
    cvm_code = str(row.get("cvm_code", "")).strip()
    account_code = str(row.get("account_code", "")).strip()
    account_name = str(row.get("account_name", "")).strip()
    value = _scaled_value(row.get("value"), row.get("scale", ""))
    return {
        "company_id": f"CVM:{cvm_code}" if cvm_code else "",
        "company_name": str(row.get("company_name", "")).strip(),
        "cvm_code": cvm_code,
        "cnpj": _digits(row.get("cnpj", "")),
        "doc_type": str(row.get("doc_type", "")).strip().lower(),
        "observed_at": str(row.get("observed_at", "")).strip()[:10],
        "statement_type": _statement_type(account_code, account_name),
        "account_code": account_code,
        "account_name": account_name,
        "canonical_account": _canonical_account(account_code, account_name),
        "value": value,
        "currency": str(row.get("currency", "")).strip(),
        "scale": str(row.get("scale", "")).strip(),
        "source_id": "cvm_dados_abertos",
        "data_stage": "normalized",
    }


def build_company_identity(statement_rows: list[dict[str, Any]]) -> dict[str, Any]:
    for row in statement_rows:
        cvm_code = str(row.get("cvm_code", "")).strip()
        cnpj = _digits(row.get("cnpj", ""))
        name = str(row.get("company_name", "")).strip()
        if cvm_code or cnpj or name:
            return {
                "company_id": f"CVM:{cvm_code}" if cvm_code else (f"BR_CNPJ:{cnpj}" if cnpj else ""),
                "company_name": name,
                "cvm_code": cvm_code,
                "cnpj": cnpj,
            }
    return {"company_id": "", "company_name": "", "cvm_code": "", "cnpj": ""}


def build_statement_facts(statement_lines: list[dict[str, Any]]) -> dict[str, float]:
    facts: dict[str, float] = {}
    for line in sorted(statement_lines, key=lambda item: str(item.get("observed_at", ""))):
        account = str(line.get("canonical_account", ""))
        value = _safe_float(line.get("value"))
        if not account or account == "unknown" or value is None:
            continue
        if account == "gross_debt":
            facts[account] = facts.get(account, 0.0) + value
        else:
            facts[account] = value
    if "gross_debt" in facts or "cash_and_equivalents" in facts:
        facts["net_debt"] = round(facts.get("gross_debt", 0.0) - facts.get("cash_and_equivalents", 0.0), 6)
    return facts


def calculate_ttm(statement_lines: list[dict[str, Any]]) -> dict[str, float]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for line in statement_lines:
        account = str(line.get("canonical_account", ""))
        if not account or account == "unknown":
            continue
        grouped.setdefault(account, []).append(line)
    result: dict[str, float] = {}
    for account, rows in grouped.items():
        values = [
            _safe_float(row.get("value"))
            for row in sorted(rows, key=lambda item: str(item.get("observed_at", "")))[-4:]
        ]
        clean = [value for value in values if value is not None]
        if clean:
            result[f"{account}_ttm"] = round(sum(clean), 6)
    return result


def calculate_fundamental_metrics(
    facts: dict[str, float],
    market_data: dict[str, Any] | None = None,
) -> dict[str, float | None]:
    market = market_data or {}
    shares = _safe_float(market.get("shares_outstanding"))
    last_price = _safe_float(market.get("last_price"))
    market_cap = _safe_float(market.get("market_cap"))
    if market_cap is None and shares is not None and last_price is not None:
        market_cap = shares * last_price

    net_debt = _safe_float(facts.get("net_debt"))
    enterprise_value = None
    if market_cap is not None:
        enterprise_value = market_cap + (net_debt or 0.0)

    metrics = {
        "gross_margin": _ratio(facts.get("gross_profit"), facts.get("revenue")),
        "ebit_margin": _ratio(facts.get("ebit"), facts.get("revenue")),
        "net_margin": _ratio(facts.get("net_income"), facts.get("revenue")),
        "roe": _ratio(facts.get("net_income"), facts.get("equity")),
        "roa": _ratio(facts.get("net_income"), facts.get("total_assets")),
        "debt_to_equity": _ratio(facts.get("net_debt"), facts.get("equity")),
        "eps": _ratio(facts.get("net_income"), shares),
        "book_value_per_share": _ratio(facts.get("equity"), shares),
        "market_cap": _round_or_none(market_cap),
        "enterprise_value": _round_or_none(enterprise_value),
        "price_to_earnings": _ratio(market_cap, facts.get("net_income")),
        "price_to_book": _ratio(market_cap, facts.get("equity")),
        "ev_to_ebit": _ratio(enterprise_value, facts.get("ebit")),
        "ev_to_ebitda": _ratio(enterprise_value, facts.get("ebitda")),
    }
    return metrics


def build_fundamental_snapshot(
    *,
    statement_rows: list[dict[str, Any]],
    market_data: dict[str, Any] | None = None,
) -> dict:
    lines = [canonical_statement_line(row) for row in statement_rows]
    facts = build_statement_facts(lines)
    metrics = calculate_fundamental_metrics(facts, market_data=market_data)
    ttm = calculate_ttm(lines)
    identity = build_company_identity(statement_rows)
    quality_flags: list[str] = []
    for required in ("revenue", "net_income", "equity", "total_assets"):
        if required not in facts:
            quality_flags.append(f"missing_{required}")
    record = {
        "identity": identity,
        "periods": sorted({line["observed_at"] for line in lines if line.get("observed_at")}),
        "facts": facts,
        "ttm": ttm,
        "metrics": metrics,
        "statement_lines": lines,
        "quality_flags": quality_flags,
        "source_refs": [{"source_id": "cvm_dados_abertos", "field": "account_code"}],
    }
    return make_success(
        source_id=SOURCE_ID,
        source_url="local://dadosbr/fundamentals/snapshot",
        records=[record],
        raw_sha256=sha256_json([record]),
        limitations=["Derived from CVM standardized account lines; account mapping is heuristic."],
    ).model_dump(mode="json")


def compare_fundamental_snapshots(
    snapshots: list[dict[str, Any]],
    *,
    metric: str = "roe",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for snapshot in snapshots:
        value = _safe_float(snapshot.get("metrics", {}).get(metric))
        if value is None:
            value = _safe_float(snapshot.get("facts", {}).get(metric))
        if value is None:
            continue
        identity = snapshot.get("identity", {})
        rows.append(
            {
                "company_id": identity.get("company_id", ""),
                "company_name": identity.get("company_name", ""),
                "metric": metric,
                "metric_value": value,
            }
        )
    rows.sort(key=lambda item: item["metric_value"], reverse=True)
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows


def normalize_yfinance_dividends(rows: list[dict[str, Any]], *, ticker: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    cumulative = 0.0
    for row in sorted(rows, key=lambda item: str(item.get("observed_at", ""))):
        amount = _safe_float(row.get("value")) or 0.0
        cumulative += amount
        records.append(
            {
                "ticker": str(ticker).strip().upper(),
                "observed_at": str(row.get("observed_at", ""))[:10],
                "amount": round(amount, 6),
                "cumulative_amount": round(cumulative, 6),
                "source_id": "yfinance",
                "data_stage": "enriched",
            }
        )
    return records


def get_company_statement(
    *,
    cvm_code: str,
    year: int,
    doc_type: str = "dfp",
    statement: str = "all",
    limit: int = 5000,
) -> dict:
    response = fetch_cvm_company_reports(
        year=year,
        doc_type=doc_type,
        cvm_code=cvm_code,
        statement=statement,
        limit=limit,
    )
    if not response.get("ok"):
        return response
    records = [canonical_statement_line(row) for row in response.get("records", [])]
    return make_success(
        source_id=SOURCE_ID,
        source_url=response.get("source_url", ""),
        records=records,
        raw_sha256=sha256_json(records),
        limitations=response.get("limitations", []) + ["Account mapping is heuristic and should be validated."],
    ).model_dump(mode="json")


def get_company_fundamentals(
    *,
    cvm_code: str,
    year: int,
    doc_type: str = "dfp",
    ticker: str = "",
    b3_file_path: str = "",
    shares_outstanding: float = 0,
    market_cap: float = 0,
    limit: int = 5000,
) -> dict:
    response = fetch_cvm_company_reports(
        year=year,
        doc_type=doc_type,
        cvm_code=cvm_code,
        statement="financials",
        limit=limit,
    )
    if not response.get("ok"):
        return response
    market_data = _market_data(
        ticker=ticker,
        b3_file_path=b3_file_path,
        shares_outstanding=shares_outstanding,
        market_cap=market_cap,
    )
    snapshot = build_fundamental_snapshot(statement_rows=response.get("records", []), market_data=market_data)
    snapshot["source_url"] = response.get("source_url", "")
    snapshot["limitations"] = snapshot.get("limitations", []) + response.get("limitations", [])
    return snapshot


def get_company_ratios(
    *,
    cvm_code: str,
    year: int,
    doc_type: str = "dfp",
    ticker: str = "",
    b3_file_path: str = "",
    shares_outstanding: float = 0,
    market_cap: float = 0,
) -> dict:
    response = get_company_fundamentals(
        cvm_code=cvm_code,
        year=year,
        doc_type=doc_type,
        ticker=ticker,
        b3_file_path=b3_file_path,
        shares_outstanding=shares_outstanding,
        market_cap=market_cap,
    )
    if not response.get("ok"):
        return response
    snapshot = response.get("records", [{}])[0]
    record = {
        **snapshot.get("metrics", {}),
        "company_id": snapshot.get("identity", {}).get("company_id", ""),
        "cvm_code": snapshot.get("identity", {}).get("cvm_code", ""),
    }
    return make_success(
        source_id=SOURCE_ID,
        source_url=response.get("source_url", ""),
        records=[record],
        raw_sha256=sha256_json([record]),
        limitations=response.get("limitations", []),
    ).model_dump(mode="json")


def get_company_dividends(
    *,
    ticker: str,
    start_date: str = "",
    end_date: str = "",
    limit: int = 500,
) -> dict:
    symbol = _yfinance_symbol(ticker)
    source_url = f"https://finance.yahoo.com/quote/{symbol}/history?filter=div"
    safe_limit = max(1, min(int(limit or 500), 5000))
    cached_entry = _get_cached_yfinance_dividend_rows(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
    )
    if cached_entry is not None:
        cached_rows, cached_provider = cached_entry
        records = normalize_yfinance_dividends(cached_rows[-safe_limit:], ticker=ticker)
        return make_success(
            source_id=SOURCE_ID,
            source_url=source_url,
            records=records,
            raw_sha256=sha256_json(records),
            limitations=["Dividend/JCP data uses optional yfinance enrichment, not official CVM event files."],
            source_mode="cache_hit",
            resilience={"cache_status": "hit", "provider": cached_provider},
        ).model_dump(mode="json")
    try:
        rows, headers = _fetch_yahoo_chart_dividend_rows(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )
        _set_cached_yfinance_dividend_rows(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            rows=rows,
            provider="yahoo_chart",
        )
        records = normalize_yfinance_dividends(rows[-safe_limit:], ticker=ticker)
        source_mode, resilience, cache_limitations = http_response_metadata(headers)
        return make_success(
            source_id=SOURCE_ID,
            source_url=source_url,
            records=records,
            raw_sha256=sha256_json(records),
            limitations=[
                "Dividend/JCP data uses optional Yahoo Finance enrichment, not official CVM event files."
            ]
            + cache_limitations,
            source_mode=source_mode,
            resilience={**resilience, "provider": "yahoo_chart"},
        ).model_dump(mode="json")
    except DataSourceError:
        pass
    try:
        frame = _run_yfinance_history_with_timeout(
            lambda: _fetch_yfinance_dividend_history(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
            ),
            timeout_seconds=yfinance_timeout_seconds(),
            source_url=source_url,
        )
        if frame is None or getattr(frame, "empty", False):
            return make_failure(
                DataSourceError("source_unavailable", f"No yfinance dividend data for {symbol}.", SOURCE_ID)
            ).model_dump(mode="json")
        rows = []
        for index, row in frame.iterrows():
            observed_at = index.date().isoformat()
            if start_date and observed_at < start_date:
                continue
            if end_date and observed_at > end_date:
                continue
            value = _frame_value(row, "Dividends")
            if _safe_float(value) in (None, 0):
                continue
            rows.append({"observed_at": observed_at, "value": float(value)})
        _set_cached_yfinance_dividend_rows(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            rows=rows,
            provider="yfinance",
        )
        records = normalize_yfinance_dividends(rows[-safe_limit:], ticker=ticker)
        return make_success(
            source_id=SOURCE_ID,
            source_url=source_url,
            records=records,
            raw_sha256=sha256_json(records),
            limitations=["Dividend/JCP data uses optional yfinance enrichment, not official CVM event files."],
        ).model_dump(mode="json")
    except ImportError:
        return make_failure(
            DataSourceError(
                "dependency_missing",
                "Install optional dependency with: python -m pip install -e .[enriched]",
                SOURCE_ID,
            )
        ).model_dump(mode="json")
    except DataSourceError as exc:
        return make_failure(exc).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        return make_failure(
            DataSourceError("source_unavailable", str(exc), SOURCE_ID, retryable=True)
        ).model_dump(mode="json")


def compare_companies_fundamentals(
    *,
    cvm_codes: str,
    year: int,
    metric: str = "roe",
    doc_type: str = "dfp",
    limit_per_company: int = 2000,
) -> dict:
    codes = _cvm_code_list(cvm_codes)
    snapshots: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    response = fetch_cvm_company_reports_batch(
        year=year,
        doc_type=doc_type,
        cvm_codes=codes,
        statement="financials",
        limit_per_code=limit_per_company,
    )
    if not response.get("ok"):
        return response

    rows_by_code: dict[str, list[dict[str, Any]]] = {code: [] for code in codes}
    for row in response.get("records", []):
        row_code = _cvm_code_key(row.get("cvm_code", ""))
        if row_code in rows_by_code:
            rows_by_code[row_code].append(row)

    for cvm_code in codes:
        rows = rows_by_code.get(cvm_code, [])
        if rows:
            snapshot = build_fundamental_snapshot(statement_rows=rows)
            if snapshot.get("ok") and snapshot.get("records"):
                snapshots.append(snapshot["records"][0])
            else:
                failures.append({"cvm_code": cvm_code, "error": snapshot.get("error", {})})
        else:
            failures.append({"cvm_code": cvm_code, "error": {"code": "not_found", "message": "No CVM rows found."}})
    records = compare_fundamental_snapshots(snapshots, metric=metric)
    payload = make_success(
        source_id=SOURCE_ID,
        source_url=response.get("source_url", "local://dadosbr/fundamentals/compare"),
        records=records,
        raw_sha256=sha256_json(records),
        limitations=[
            "Comparison depends on comparable CVM account mappings and reporting periods.",
            *response.get("limitations", []),
        ],
        source_mode=response.get("source_mode", "live"),
        resilience=response.get("resilience", {}),
    ).model_dump(mode="json")
    payload["failures"] = failures + response.get("failures", [])
    payload["record_counts_by_cvm_code"] = response.get("record_counts_by_cvm_code", {})
    return payload


def list_fundamentals_calendar() -> dict:
    return make_success(
        source_id=SOURCE_ID,
        source_url="local://dadosbr/fundamentals/calendar",
        records=FUNDAMENTALS_CALENDAR,
        raw_sha256=sha256_json(FUNDAMENTALS_CALENDAR),
        limitations=["Calendar describes filing families and frequency, not dynamic future due dates."],
    ).model_dump(mode="json")


def _cvm_code_list(cvm_codes: str) -> list[str]:
    seen: set[str] = set()
    codes: list[str] = []
    for part in str(cvm_codes or "").split(","):
        code = _cvm_code_key(part)
        if code and code not in seen:
            seen.add(code)
            codes.append(code)
    return codes


def _cvm_code_key(value: Any) -> str:
    digits = _digits(value)
    if not digits:
        return ""
    return digits.lstrip("0") or "0"


def _market_data(
    *,
    ticker: str = "",
    b3_file_path: str = "",
    shares_outstanding: float = 0,
    market_cap: float = 0,
) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if shares_outstanding:
        data["shares_outstanding"] = float(shares_outstanding)
    if market_cap:
        data["market_cap"] = float(market_cap)
    if ticker and b3_file_path:
        response = fetch_asset_price_history(asset_id=f"B3:{ticker}", b3_file_path=b3_file_path, limit=1)
        if response.get("ok") and response.get("records"):
            data["last_price"] = response["records"][-1].get("close")
    return data


def _fetch_yfinance_dividend_history(*, symbol: str, start_date: str = "", end_date: str = "") -> Any:
    yf = importlib.import_module("yfinance")
    kwargs = yfinance_history_kwargs(start_date=start_date, end_date=end_date)
    if not start_date and not end_date:
        kwargs["period"] = yfinance_dividend_period()
    return yf.Ticker(symbol).history(
        auto_adjust=False,
        actions=True,
        **kwargs,
    )


def _fetch_yahoo_chart_dividend_rows(
    *,
    symbol: str,
    start_date: str = "",
    end_date: str = "",
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    params: dict[str, str] = {"interval": "1d", "events": "div"}
    if start_date or end_date:
        params["period1"] = str(_date_to_unix(start_date or "1970-01-01"))
        params["period2"] = str(_date_to_unix(end_date, plus_one_day=True) if end_date else int(datetime.now(UTC).timestamp()))
    else:
        params["range"] = yfinance_dividend_period()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{urlencode(params)}"
    body, headers = http_get_bytes_cached(
        url,
        source_id=SOURCE_ID,
        timeout_seconds=yfinance_timeout_seconds(),
        cache_namespace="yahoo_chart_dividends",
        max_stale_seconds=yfinance_dividend_cache_ttl_seconds(),
    )
    try:
        payload = json.loads(body.decode("utf-8"))
        result = payload.get("chart", {}).get("result", [])
        if not result:
            raise ValueError("missing chart result")
        dividends = result[0].get("events", {}).get("dividends", {})
        rows = [
            {
                "observed_at": datetime.fromtimestamp(int(item["date"]), UTC).date().isoformat(),
                "value": float(item["amount"]),
            }
            for item in dividends.values()
            if item.get("date") is not None and item.get("amount") is not None
        ]
    except Exception as exc:  # noqa: BLE001
        raise DataSourceError(
            "parse_error",
            f"Could not parse Yahoo chart dividend response: {exc}",
            SOURCE_ID,
            source_url=url,
            retryable=True,
        ) from exc
    rows.sort(key=lambda item: item["observed_at"])
    if start_date:
        rows = [row for row in rows if str(row.get("observed_at", "")) >= start_date]
    if end_date:
        rows = [row for row in rows if str(row.get("observed_at", "")) <= end_date]
    if not rows:
        raise DataSourceError("source_unavailable", f"No Yahoo chart dividend data for {symbol}.", SOURCE_ID, source_url=url)
    return rows, headers


def _get_cached_yfinance_dividend_rows(
    *,
    symbol: str,
    start_date: str = "",
    end_date: str = "",
) -> tuple[list[dict[str, Any]], str] | None:
    if _yfinance_dividend_cache_disabled():
        return None
    cached = _yfinance_dividend_cache().get(_yfinance_dividend_cache_key(symbol=symbol, start_date=start_date, end_date=end_date))
    if not cached or not isinstance(cached.get("rows"), list):
        return None
    provider = str(cached.get("provider") or "yahoo_finance")
    return [row for row in cached["rows"] if isinstance(row, dict)], provider


def _set_cached_yfinance_dividend_rows(
    *,
    symbol: str,
    start_date: str = "",
    end_date: str = "",
    rows: list[dict[str, Any]],
    provider: str,
) -> None:
    if _yfinance_dividend_cache_disabled():
        return
    _yfinance_dividend_cache().set(
        _yfinance_dividend_cache_key(symbol=symbol, start_date=start_date, end_date=end_date),
        {"rows": rows, "provider": provider},
    )


def _yfinance_dividend_cache() -> DiskCache:
    root = Path(os.getenv("DADOSBR_CACHE_DIR", ".dadosbr/cache"))
    return DiskCache(root / "yfinance" / "dividends", ttl_seconds=yfinance_dividend_cache_ttl_seconds())


def _yfinance_dividend_cache_key(*, symbol: str, start_date: str = "", end_date: str = "") -> str:
    return json.dumps(
        {
            "kind": "dividends",
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "period": "" if start_date or end_date else yfinance_dividend_period(),
        },
        sort_keys=True,
    )


def _yfinance_dividend_cache_disabled() -> bool:
    return os.getenv("DADOSBR_DISABLE_HTTP_CACHE", "").strip().lower() in {"1", "true", "yes", "on"}


def _date_to_unix(value: str, *, plus_one_day: bool = False) -> int:
    day = datetime.fromisoformat(value).replace(tzinfo=UTC)
    if plus_one_day:
        day += timedelta(days=1)
    return int(day.timestamp())


def _run_yfinance_history_with_timeout(
    call: Callable[[], Any],
    *,
    timeout_seconds: int,
    source_url: str,
) -> Any:
    result_queue: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

    def run() -> None:
        try:
            result_queue.put((True, call()))
        except Exception as exc:  # noqa: BLE001
            result_queue.put((False, exc))

    worker = threading.Thread(target=run, name="dadosbr-yfinance-history", daemon=True)
    worker.start()
    worker.join(timeout_seconds)
    if worker.is_alive():
        raise DataSourceError(
            "timeout",
            f"yfinance history request timed out after {timeout_seconds} seconds.",
            SOURCE_ID,
            source_url=source_url,
            retryable=True,
        )
    try:
        ok, value = result_queue.get_nowait()
    except queue.Empty as exc:
        raise DataSourceError(
            "timeout",
            "yfinance history request finished without a result.",
            SOURCE_ID,
            source_url=source_url,
            retryable=True,
        ) from exc
    if ok:
        return value
    raise value


def _canonical_account(account_code: str, account_name: str) -> str:
    code = str(account_code or "").strip()
    name = _ascii(account_name)
    exact = {
        "1": "total_assets",
        "1.01": "current_assets",
        "1.01.01": "cash_and_equivalents",
        "2.01": "current_liabilities",
        "2.02": "non_current_liabilities",
        "2.03": "equity",
        "2.01.04": "gross_debt",
        "2.02.01": "gross_debt",
        "3.01": "revenue",
        "3.03": "gross_profit",
        "3.05": "ebit",
        "3.11": "net_income",
        "6.01": "operating_cash_flow",
        "6.02": "investing_cash_flow",
        "6.03": "financing_cash_flow",
    }
    if code in exact:
        return exact[code]
    if "receita" in name and ("venda" in name or "servico" in name):
        return "revenue"
    if "resultado bruto" in name:
        return "gross_profit"
    if "lucro" in name and "periodo" in name:
        return "net_income"
    if "patrimonio liquido" in name and (code.startswith("2") or not code):
        return "equity"
    if "ativo total" in name:
        return "total_assets"
    if "caixa" in name and "equivalente" in name:
        return "cash_and_equivalents"
    if "emprestimo" in name or "financiamento" in name:
        return "gross_debt"
    return "unknown"


def _statement_type(account_code: str, account_name: str) -> str:
    code = str(account_code or "")
    name = _ascii(account_name)
    if code.startswith("3"):
        return "income_statement"
    if code.startswith(("1", "2")):
        return "balance_sheet"
    if code.startswith("6") or "caixa" in name:
        return "cash_flow"
    return "unknown"


def _scaled_value(value: Any, scale: Any) -> float | None:
    parsed = _safe_float(value)
    if parsed is None:
        return None
    normalized_scale = _ascii(scale)
    if "mil" in normalized_scale:
        return parsed * 1000
    return parsed


def _ratio(numerator: Any, denominator: Any) -> float | None:
    num = _safe_float(numerator)
    den = _safe_float(denominator)
    if num is None or den in (None, 0):
        return None
    return round(num / den, 6)


def _round_or_none(value: Any) -> float | None:
    parsed = _safe_float(value)
    return round(parsed, 6) if parsed is not None else None


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _frame_value(row: Any, column: str) -> Any:
    if column in row:
        return row[column]
    if hasattr(row, "get"):
        return row.get(column)
    return None


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _ascii(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    return normalized.encode("ascii", "ignore").decode("ascii").lower()


def _yfinance_symbol(ticker: str) -> str:
    raw = str(ticker or "").strip().upper()
    return raw if "." in raw or raw.startswith("^") else f"{raw}.SA"
