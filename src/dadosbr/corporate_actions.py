from __future__ import annotations

import importlib
import json
import os
import queue
import threading
from typing import Any
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

from dadosbr.core import DataSourceError, make_failure, make_success
from dadosbr.core.cache import DiskCache
from dadosbr.core.http import http_get_bytes_cached, http_response_metadata
from dadosbr.core.utils import sha256_json
from dadosbr.core.yfinance import (
    yfinance_action_cache_ttl_seconds,
    yfinance_action_period,
    yfinance_history_kwargs,
    yfinance_timeout_seconds,
)
from dadosbr.timeseries import fetch_asset_price_history

SOURCE_ID = "corporate_actions"

EVENT_TYPES: dict[str, dict[str, str]] = {
    "dividend": {"event_type": "dividend", "event_category": "cash", "description": "Dividendo em dinheiro"},
    "jcp": {"event_type": "jcp", "event_category": "cash", "description": "Juros sobre capital proprio"},
    "amortization": {"event_type": "amortization", "event_category": "cash", "description": "Amortizacao"},
    "capital_reduction": {
        "event_type": "capital_reduction",
        "event_category": "cash",
        "description": "Reducao ou restituicao de capital",
    },
    "split": {"event_type": "split", "event_category": "share", "description": "Desdobramento"},
    "reverse_split": {"event_type": "reverse_split", "event_category": "share", "description": "Grupamento"},
    "bonus": {"event_type": "bonus", "event_category": "share", "description": "Bonificacao em acoes"},
    "subscription": {"event_type": "subscription", "event_category": "rights", "description": "Subscricao"},
    "merger": {"event_type": "merger", "event_category": "reorganization", "description": "Incorporacao/fusao"},
    "spin_off": {"event_type": "spin_off", "event_category": "reorganization", "description": "Cisao"},
}

EVENT_ALIASES = {
    "dividendo": "dividend",
    "dividendos": "dividend",
    "dividend": "dividend",
    "jcp": "jcp",
    "juros sobre capital proprio": "jcp",
    "juros sobre capital próprio": "jcp",
    "amortizacao": "amortization",
    "amortização": "amortization",
    "reducao de capital": "capital_reduction",
    "redução de capital": "capital_reduction",
    "restituicao de capital": "capital_reduction",
    "restituição de capital": "capital_reduction",
    "split": "split",
    "desdobramento": "split",
    "reverse_split": "reverse_split",
    "grupamento": "reverse_split",
    "bonificacao": "bonus",
    "bonificação": "bonus",
    "bonus": "bonus",
    "subscricao": "subscription",
    "subscrição": "subscription",
    "subscription": "subscription",
    "incorporacao": "merger",
    "incorporação": "merger",
    "fusao": "merger",
    "fusão": "merger",
    "cisao": "spin_off",
    "cisão": "spin_off",
}


def list_corporate_action_types() -> dict:
    records = [EVENT_TYPES[key] for key in sorted(EVENT_TYPES)]
    return make_success(
        source_id=SOURCE_ID,
        source_url="local://dadosbr/corporate-actions/types",
        records=records,
        raw_sha256=sha256_json(records),
    ).model_dump(mode="json")


def normalize_corporate_action(row: dict[str, Any]) -> dict[str, Any]:
    ticker = str(row.get("ticker", "")).strip().upper()
    event_type = _event_type(row.get("event_type", row.get("type", "")))
    amount = _safe_float(row.get("amount_per_share", row.get("amount", row.get("value"))))
    ratio = _safe_float(row.get("ratio", row.get("split_ratio")))
    reference_price = _safe_float(row.get("reference_price", row.get("close_before")))
    ex_date = _date_value(row.get("ex_date", row.get("observed_at", row.get("date"))))
    payment_date = _date_value(row.get("payment_date"))
    declared_date = _date_value(row.get("declared_date"))
    approval_date = _date_value(row.get("approval_date"))
    record_date = _date_value(row.get("record_date"))
    price_factor, share_factor = _event_factors(event_type, amount=amount, ratio=ratio, reference_price=reference_price)
    subscription_price = _safe_float(row.get("subscription_price"))
    event_def = EVENT_TYPES.get(event_type, {"event_category": "unknown"})
    quality_flags = []
    if event_type in {"dividend", "jcp", "amortization", "capital_reduction"} and amount is None:
        quality_flags.append("missing_amount_per_share")
    if event_type in {"split", "reverse_split", "bonus"} and ratio is None:
        quality_flags.append("missing_ratio")
    if not ex_date:
        quality_flags.append("missing_ex_date")
    action_id = _action_id(ticker=ticker, event_type=event_type, ex_date=ex_date, amount=amount, ratio=ratio)
    return {
        "action_id": action_id,
        "ticker": ticker,
        "asset_id": f"B3:{ticker}" if ticker else "",
        "isin": str(row.get("isin", "")).strip(),
        "issuer_cnpj": _digits(row.get("issuer_cnpj", row.get("cnpj", ""))),
        "cvm_code": str(row.get("cvm_code", "")).strip(),
        "event_type": event_type,
        "event_category": event_def.get("event_category", "unknown"),
        "declared_date": declared_date,
        "approval_date": approval_date,
        "record_date": record_date,
        "ex_date": ex_date,
        "payment_date": payment_date,
        "amount_per_share": amount,
        "currency": str(row.get("currency", "BRL") or "BRL").strip().upper(),
        "ratio": ratio,
        "subscription_price": subscription_price,
        "reference_price": reference_price,
        "price_adjustment_factor": price_factor,
        "share_adjustment_factor": share_factor,
        "status": str(row.get("status", "unknown") or "unknown").strip().lower(),
        "source_id": str(row.get("source_id", "manual") or "manual").strip(),
        "source_url": str(row.get("source_url", "") or ""),
        "document_id": str(row.get("document_id", "") or ""),
        "data_stage": str(row.get("data_stage", "normalized") or "normalized"),
        "quality_flags": quality_flags,
    }


def normalize_corporate_actions(rows: list[dict[str, Any]]) -> dict:
    records = [normalize_corporate_action(row) for row in rows]
    return make_success(
        source_id=SOURCE_ID,
        source_url="local://dadosbr/corporate-actions/normalize",
        records=records,
        raw_sha256=sha256_json(records),
        limitations=["Manual/normalized corporate actions depend on input source quality."],
    ).model_dump(mode="json")


def normalize_yfinance_actions(
    *,
    dividends: list[dict[str, Any]] | None = None,
    splits: list[dict[str, Any]] | None = None,
    ticker: str,
    source_id: str = "yfinance",
) -> list[dict[str, Any]]:
    records = []
    for row in dividends or []:
        records.append(
            normalize_corporate_action(
                {
                    "ticker": ticker,
                    "event_type": "dividend",
                    "ex_date": row.get("observed_at", row.get("date")),
                    "amount_per_share": row.get("value", row.get("amount")),
                    "source_id": source_id,
                    "data_stage": "enriched",
                    "status": "reported",
                }
            )
        )
    for row in splits or []:
        records.append(
            normalize_corporate_action(
                {
                    "ticker": ticker,
                    "event_type": "split",
                    "ex_date": row.get("observed_at", row.get("date")),
                    "ratio": row.get("value", row.get("ratio")),
                    "source_id": source_id,
                    "data_stage": "enriched",
                    "status": "reported",
                }
            )
        )
    return sorted(records, key=lambda item: (item.get("ex_date", ""), item.get("event_type", "")))


def calculate_adjustment_factors(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cumulative_price = 1.0
    cumulative_share = 1.0
    records = []
    for event in sorted(events, key=lambda item: (str(item.get("ex_date", "")), str(item.get("action_id", "")))):
        price_factor = _safe_float(event.get("price_adjustment_factor")) or 1.0
        share_factor = _safe_float(event.get("share_adjustment_factor")) or 1.0
        cumulative_price *= price_factor
        cumulative_share *= share_factor
        records.append(
            {
                "action_id": event.get("action_id", ""),
                "ticker": event.get("ticker", ""),
                "asset_id": event.get("asset_id", ""),
                "event_type": event.get("event_type", ""),
                "ex_date": event.get("ex_date", ""),
                "amount_per_share": event.get("amount_per_share"),
                "ratio": event.get("ratio"),
                "price_adjustment_factor": round(price_factor, 10),
                "share_adjustment_factor": round(share_factor, 10),
                "cumulative_price_factor": round(cumulative_price, 10),
                "cumulative_share_factor": round(cumulative_share, 10),
                "source_id": event.get("source_id", ""),
            }
        )
    return records


def apply_adjustments_to_price_history(
    price_history: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized_events = [event if "price_adjustment_factor" in event else normalize_corporate_action(event) for event in events]
    records = []
    for row in sorted(price_history, key=lambda item: str(item.get("observed_at", ""))):
        observed = _date_value(row.get("observed_at"))
        future_events = [event for event in normalized_events if str(event.get("ex_date", "")) > observed]
        price_factor = 1.0
        share_factor = 1.0
        applied_ids = []
        for event in future_events:
            price_factor *= _safe_float(event.get("price_adjustment_factor")) or 1.0
            share_factor *= _safe_float(event.get("share_adjustment_factor")) or 1.0
            applied_ids.append(event.get("action_id", ""))
        enriched = dict(row)
        for field in ("open", "high", "low", "close"):
            if _safe_float(row.get(field)) is not None:
                enriched[f"adjusted_{field}"] = round(float(row[field]) * price_factor, 6)
        volume = _safe_float(row.get("volume"))
        if volume is not None:
            adjusted_volume = volume * share_factor
            enriched["adjusted_volume"] = int(adjusted_volume) if adjusted_volume.is_integer() else round(adjusted_volume, 6)
        enriched["corporate_action_price_factor"] = round(price_factor, 10)
        enriched["corporate_action_share_factor"] = round(share_factor, 10)
        enriched["adjustment_event_count"] = len(future_events)
        enriched["adjustment_action_ids"] = applied_ids
        enriched["data_stage"] = "corporate_action_adjusted" if future_events else row.get("data_stage", "normalized")
        records.append(enriched)
    return records


def get_corporate_actions(
    *,
    ticker: str,
    source: str = "yfinance",
    start_date: str = "",
    end_date: str = "",
    limit: int = 500,
) -> dict:
    normalized_source = str(source or "yfinance").strip().lower()
    if normalized_source != "yfinance":
        return make_failure(
            DataSourceError(
                "validation_error",
                "Only source='yfinance' is currently implemented for automatic corporate actions.",
                SOURCE_ID,
            )
        ).model_dump(mode="json")
    response = fetch_yfinance_corporate_actions(ticker=ticker, start_date=start_date, end_date=end_date, limit=limit)
    return response


def fetch_yfinance_corporate_actions(
    *,
    ticker: str,
    start_date: str = "",
    end_date: str = "",
    limit: int = 500,
) -> dict:
    symbol = _yfinance_symbol(ticker)
    source_url = f"https://finance.yahoo.com/quote/{symbol}/history"
    safe_limit = max(1, min(int(limit or 500), 5000))
    cached_entry = _get_cached_yahoo_action_rows(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
    )
    if cached_entry is not None:
        cached_records, cached_provider = cached_entry
        records = cached_records[-safe_limit:]
        return make_success(
            source_id=SOURCE_ID,
            source_url=source_url,
            records=records,
            raw_sha256=sha256_json(records),
            limitations=[
                "Corporate actions use optional Yahoo Finance enrichment, not official B3/CVM structured event files."
            ],
            source_mode="cache_hit",
            resilience={"cache_status": "hit", "provider": cached_provider},
        ).model_dump(mode="json")
    try:
        records, headers = _fetch_yahoo_chart_action_records(
            symbol=symbol,
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
        )
        records = records[-safe_limit:]
        _set_cached_yahoo_action_rows(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            rows=records,
            provider="yahoo_chart",
        )
        source_mode, resilience, cache_limitations = http_response_metadata(headers)
        return make_success(
            source_id=SOURCE_ID,
            source_url=source_url,
            records=records,
            raw_sha256=sha256_json(records),
            limitations=[
                "Corporate actions use optional Yahoo Finance enrichment, not official B3/CVM structured event files."
            ]
            + cache_limitations,
            source_mode=source_mode,
            resilience={**resilience, "provider": "yahoo_chart"},
        ).model_dump(mode="json")
    except DataSourceError:
        pass
    try:
        frame = _run_yfinance_history_with_timeout(
            lambda: _fetch_yfinance_action_history(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
            ),
            timeout_seconds=yfinance_timeout_seconds(),
            source_url=source_url,
        )
        dividends = _frame_to_action_rows(frame, column="Dividends")
        splits = _frame_to_action_rows(frame, column="Stock Splits")
        records = normalize_yfinance_actions(dividends=dividends, splits=splits, ticker=ticker)
        records = [
            record
            for record in records
            if (not start_date or record.get("ex_date", "") >= start_date)
            and (not end_date or record.get("ex_date", "") <= end_date)
        ][-safe_limit:]
        _set_cached_yahoo_action_rows(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            rows=records,
            provider="yfinance",
        )
        return make_success(
            source_id=SOURCE_ID,
            source_url=source_url,
            records=records,
            raw_sha256=sha256_json(records),
            limitations=[
                "Corporate actions use optional yfinance enrichment, not official B3/CVM structured event files."
            ],
            source_mode="live",
            resilience={"provider": "yfinance"},
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
        return make_failure(DataSourceError("source_unavailable", str(exc), SOURCE_ID, retryable=True)).model_dump(
            mode="json"
        )


def get_corporate_action_factors(
    *,
    ticker: str,
    source: str = "yfinance",
    start_date: str = "",
    end_date: str = "",
    limit: int = 500,
) -> dict:
    response = get_corporate_actions(
        ticker=ticker,
        source=source,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    if not response.get("ok"):
        return response
    records = calculate_adjustment_factors(response.get("records", []))
    return make_success(
        source_id=SOURCE_ID,
        source_url=response.get("source_url", ""),
        records=records,
        raw_sha256=sha256_json(records),
        limitations=response.get("limitations", []),
    ).model_dump(mode="json")


def get_corporate_action_adjusted_history(
    *,
    ticker: str,
    b3_file_path: str = "",
    source: str = "yfinance",
    start_date: str = "",
    end_date: str = "",
    limit: int = 5000,
) -> dict:
    price_response = fetch_asset_price_history(
        asset_id=f"B3:{ticker}",
        start_date=start_date,
        end_date=end_date,
        adjusted=False,
        b3_file_path=b3_file_path,
        limit=limit,
    )
    if not price_response.get("ok"):
        return price_response
    action_response = get_corporate_actions(
        ticker=ticker,
        source=source,
        start_date="",
        end_date=end_date,
        limit=limit,
    )
    if not action_response.get("ok"):
        return action_response
    records = apply_adjustments_to_price_history(price_response.get("records", []), action_response.get("records", []))
    return make_success(
        source_id=SOURCE_ID,
        source_url=price_response.get("source_url", ""),
        records=records,
        raw_sha256=sha256_json(records),
        limitations=price_response.get("limitations", [])
        + action_response.get("limitations", [])
        + ["Adjusted OHLCV is derived from available corporate actions and should be validated."],
    ).model_dump(mode="json")


def _event_type(value: Any) -> str:
    raw = str(value or "").strip().lower()
    return EVENT_ALIASES.get(raw, raw or "unknown")


def _event_factors(
    event_type: str,
    *,
    amount: float | None,
    ratio: float | None,
    reference_price: float | None,
) -> tuple[float | None, float]:
    if event_type in {"dividend", "jcp", "amortization", "capital_reduction"}:
        if amount is not None and reference_price not in (None, 0):
            return round((reference_price - amount) / reference_price, 10), 1.0
        return None, 1.0
    if event_type == "split":
        if ratio not in (None, 0):
            return round(1 / ratio, 10), ratio
        return None, 1.0
    if event_type == "reverse_split":
        if ratio not in (None, 0):
            return round(1 / ratio, 10), ratio
        return None, 1.0
    if event_type == "bonus":
        if ratio is not None:
            share_factor = 1 + ratio
            return round(1 / share_factor, 10), share_factor
        return None, 1.0
    return None, 1.0


def _action_id(
    *,
    ticker: str,
    event_type: str,
    ex_date: str,
    amount: float | None,
    ratio: float | None,
) -> str:
    suffix_value = amount if amount is not None else ratio
    suffix = f":{suffix_value:g}" if suffix_value is not None else ""
    return f"{ticker}:{event_type.upper()}:{ex_date or 'NO_DATE'}{suffix}"


def _series_to_rows(series: Any, *, value_name: str) -> list[dict[str, Any]]:
    rows = []
    if series is None:
        return rows
    for index, value in series.items():
        rows.append({"observed_at": index.date().isoformat(), value_name: float(value)})
    return rows


def _frame_to_action_rows(frame: Any, *, column: str) -> list[dict[str, Any]]:
    rows = []
    if frame is None or getattr(frame, "empty", False):
        return rows
    for index, row in frame.iterrows():
        value = _frame_value(row, column)
        parsed = _safe_float(value)
        if parsed in (None, 0):
            continue
        rows.append({"observed_at": index.date().isoformat(), "value": parsed})
    return rows


def _frame_value(row: Any, column: str) -> Any:
    if column in row:
        return row[column]
    if hasattr(row, "get"):
        return row.get(column)
    return None


def _fetch_yfinance_action_history(*, symbol: str, start_date: str = "", end_date: str = "") -> Any:
    yf = importlib.import_module("yfinance")
    return yf.Ticker(symbol).history(
        auto_adjust=False,
        actions=True,
        **yfinance_history_kwargs(start_date=start_date, end_date=end_date),
    )


def _fetch_yahoo_chart_action_records(
    *,
    symbol: str,
    ticker: str,
    start_date: str = "",
    end_date: str = "",
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    params: dict[str, str] = {"interval": "1d", "events": "div,splits"}
    if start_date or end_date:
        params["period1"] = str(_date_to_unix(start_date or "1970-01-01"))
        params["period2"] = str(_date_to_unix(end_date, plus_one_day=True) if end_date else int(datetime.now(UTC).timestamp()))
    else:
        params["range"] = yfinance_action_period()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{urlencode(params)}"
    body, headers = http_get_bytes_cached(
        url,
        source_id=SOURCE_ID,
        timeout_seconds=yfinance_timeout_seconds(),
        cache_namespace="yahoo_chart_actions",
        max_stale_seconds=yfinance_action_cache_ttl_seconds(),
    )
    try:
        payload = json.loads(body.decode("utf-8"))
        result = payload.get("chart", {}).get("result", [])
        if not result:
            raise ValueError("missing chart result")
        events = result[0].get("events", {})
        dividends = [
            {
                "observed_at": datetime.fromtimestamp(int(item["date"]), UTC).date().isoformat(),
                "value": float(item["amount"]),
            }
            for item in events.get("dividends", {}).values()
            if item.get("date") is not None and item.get("amount") is not None
        ]
        splits = [
            {
                "observed_at": datetime.fromtimestamp(int(item["date"]), UTC).date().isoformat(),
                "value": _split_ratio(item),
            }
            for item in events.get("splits", {}).values()
            if item.get("date") is not None and _split_ratio(item) is not None
        ]
    except Exception as exc:  # noqa: BLE001
        raise DataSourceError(
            "parse_error",
            f"Could not parse Yahoo chart corporate actions response: {exc}",
            SOURCE_ID,
            source_url=url,
            retryable=True,
        ) from exc
    records = normalize_yfinance_actions(dividends=dividends, splits=splits, ticker=ticker, source_id="yahoo_chart")
    records = [
        record
        for record in records
        if (not start_date or record.get("ex_date", "") >= start_date)
        and (not end_date or record.get("ex_date", "") <= end_date)
    ]
    return records, headers


def _split_ratio(item: dict[str, Any]) -> float | None:
    numerator = _safe_float(item.get("numerator"))
    denominator = _safe_float(item.get("denominator"))
    if numerator not in (None, 0) and denominator not in (None, 0):
        return numerator / denominator
    raw_ratio = str(item.get("splitRatio", "") or "").strip()
    if ":" in raw_ratio:
        left, right = raw_ratio.split(":", 1)
        left_value = _safe_float(left)
        right_value = _safe_float(right)
        if left_value not in (None, 0) and right_value not in (None, 0):
            return left_value / right_value
    return None


def _get_cached_yahoo_action_rows(
    *,
    symbol: str,
    start_date: str = "",
    end_date: str = "",
) -> tuple[list[dict[str, Any]], str] | None:
    if _yahoo_action_cache_disabled():
        return None
    cached = _yahoo_action_cache().get(_yahoo_action_cache_key(symbol=symbol, start_date=start_date, end_date=end_date))
    if not cached or not isinstance(cached.get("rows"), list):
        return None
    provider = str(cached.get("provider") or "yahoo_finance")
    return [row for row in cached["rows"] if isinstance(row, dict)], provider


def _set_cached_yahoo_action_rows(
    *,
    symbol: str,
    start_date: str = "",
    end_date: str = "",
    rows: list[dict[str, Any]],
    provider: str,
) -> None:
    if _yahoo_action_cache_disabled():
        return
    _yahoo_action_cache().set(
        _yahoo_action_cache_key(symbol=symbol, start_date=start_date, end_date=end_date),
        {"rows": rows, "provider": provider},
    )


def _yahoo_action_cache() -> DiskCache:
    root = Path(os.getenv("DADOSBR_CACHE_DIR", ".dadosbr/cache"))
    return DiskCache(root / "yfinance" / "corporate_actions", ttl_seconds=yfinance_action_cache_ttl_seconds())


def _yahoo_action_cache_key(*, symbol: str, start_date: str = "", end_date: str = "") -> str:
    return json.dumps(
        {
            "kind": "corporate_actions",
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "period": "" if start_date or end_date else yfinance_action_period(),
        },
        sort_keys=True,
    )


def _yahoo_action_cache_disabled() -> bool:
    return os.getenv("DADOSBR_DISABLE_HTTP_CACHE", "").strip().lower() in {"1", "true", "yes", "on"}


def _date_to_unix(value: str, *, plus_one_day: bool = False) -> int:
    day = datetime.fromisoformat(value).replace(tzinfo=UTC)
    if plus_one_day:
        day += timedelta(days=1)
    return int(day.timestamp())


def _run_yfinance_history_with_timeout(
    call: Any,
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

    worker = threading.Thread(target=run, name="dadosbr-yfinance-actions", daemon=True)
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


def _date_value(value: Any) -> str:
    return str(value or "").strip()[:10]


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _yfinance_symbol(ticker: str) -> str:
    raw = str(ticker or "").strip().upper()
    return raw if "." in raw or raw.startswith("^") else f"{raw}.SA"
