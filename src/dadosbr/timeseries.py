from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dadosbr.connectors.b3 import fetch_b3_cotahist, parse_b3_cotahist_file
from dadosbr.connectors.bcb import fetch_sgs_series
from dadosbr.connectors.ibge import fetch_ibge_sidra
from dadosbr.connectors.ipea import fetch_ipea_series
from dadosbr.core import DataSourceError, make_failure, make_success
from dadosbr.core.utils import sha256_json
from dadosbr.core.yfinance import yfinance_timeout_seconds

SOURCE_ID = "timeseries"
DEFAULT_STORE_PATH = Path(".dadosbr") / "datasets" / "timeseries" / "timeseries.sqlite"


def canonical_b3_price_history(
    rows: list[dict[str, Any]],
    *,
    adjusted_by_date: dict[str, dict[str, Any]] | None = None,
    adjusted: bool = False,
) -> list[dict[str, Any]]:
    adjustment_map = adjusted_by_date or {}
    records: list[dict[str, Any]] = []

    for row in sorted(rows, key=lambda item: (str(item.get("ticker", "")), str(item.get("observed_at", "")))):
        ticker = str(row.get("ticker", "")).strip().upper()
        observed_at = str(row.get("observed_at", "")).strip()
        date_key = _date_key(observed_at)
        adjustment = adjustment_map.get(date_key, {})
        adjusted_close = _safe_float(adjustment.get("adjusted_close"))
        quality_flags: list[str] = []

        if _safe_float(row.get("close_price")) is None:
            quality_flags.append("missing_close")
        if adjusted and adjusted_close is None:
            quality_flags.append("missing_adjusted_close")

        record = {
            "series_id": f"PRICE:B3:{ticker}:1D",
            "asset_id": f"B3:{ticker}",
            "data_kind": "market_price",
            "frequency": "daily",
            "observed_at": observed_at,
            "open": _safe_float(row.get("open_price")),
            "high": _safe_float(row.get("high_price")),
            "low": _safe_float(row.get("low_price")),
            "close": _safe_float(row.get("close_price")),
            "adjusted_close": adjusted_close,
            "volume": _safe_int(row.get("quantity_traded")),
            "financial_volume": _safe_float(row.get("financial_volume")),
            "currency": _normalize_currency(row.get("currency_ref")),
            "isin": str(row.get("isin", "")).strip(),
            "source_id": "b3_cotahist",
            "data_stage": "adjusted" if adjusted_close is not None else "normalized",
            "is_adjusted": adjusted_close is not None,
            "is_business_day": _is_business_day(observed_at),
            "adjustment_method": "yfinance_adj_close" if adjusted_close is not None else "",
            "simple_return": None,
            "adjusted_return": None,
            "cumulative_return": None,
            "adjusted_cumulative_return": None,
            "quality_flags": quality_flags,
        }
        records.append(record)

    _add_returns(records, "close", "simple_return")
    _add_returns(records, "adjusted_close", "adjusted_return")
    _add_cumulative_returns(records, "close", "cumulative_return")
    _add_cumulative_returns(records, "adjusted_close", "adjusted_cumulative_return")
    return records


def canonical_economic_series(
    rows: list[dict[str, Any]],
    *,
    provider: str,
    series_code: str,
    frequency: str = "unknown",
) -> list[dict[str, Any]]:
    normalized_provider = str(provider).strip().upper()
    source_id = str(provider).strip().lower()
    records: list[dict[str, Any]] = []
    for row in rows:
        records.append(
            {
                "series_id": f"ECON:{normalized_provider}:{series_code}",
                "asset_id": "",
                "data_kind": "economic_indicator",
                "frequency": frequency,
                "observed_at": str(row.get("observed_at", "")),
                "value": _safe_float(row.get("value")),
                "source_id": source_id,
                "data_stage": "normalized",
                "quality_flags": [] if _safe_float(row.get("value")) is not None else ["missing_value"],
            }
        )
    return records


def fetch_asset_price_history(
    *,
    asset_id: str,
    start_date: str = "",
    end_date: str = "",
    adjusted: bool = False,
    b3_file_path: str = "",
    limit: int = 5000,
    store: bool = False,
    db_path: str | Path | None = None,
) -> dict:
    ticker = _ticker_from_asset_id(asset_id)
    if not ticker:
        return make_failure(
            DataSourceError("validation_error", "asset_id must identify a B3 ticker.", SOURCE_ID)
        ).model_dump(mode="json")

    source_response = (
        parse_b3_cotahist_file(b3_file_path, ticker=ticker, limit=limit)
        if b3_file_path
        else fetch_b3_cotahist(ticker=ticker, limit=limit)
    )
    if not source_response.get("ok"):
        return source_response

    adjusted_by_date: dict[str, dict[str, Any]] = {}
    limitations = list(source_response.get("limitations", []))
    if adjusted:
        adjusted_response = fetch_yfinance_adjusted_history(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
        if adjusted_response.get("ok"):
            adjusted_by_date = {
                str(row.get("observed_at", ""))[:10]: row for row in adjusted_response.get("records", [])
            }
        else:
            message = adjusted_response.get("error", {}).get("message", "Adjusted close unavailable.")
            limitations.append(f"Adjusted close unavailable: {message}")

    records = canonical_b3_price_history(
        list(source_response.get("records", [])),
        adjusted_by_date=adjusted_by_date,
        adjusted=adjusted,
    )
    records = _filter_dates(records, start_date=start_date, end_date=end_date)[: _safe_limit(limit)]

    if store:
        write_timeseries_records(records, db_path=db_path)

    limitations.append(
        "Adjusted close uses optional yfinance data and is not an official B3 corporate-actions adjustment."
        if adjusted
        else "Raw close is not adjusted for dividends, JCP, splits or other corporate actions."
    )
    return make_success(
        source_id=SOURCE_ID,
        source_url=str(source_response.get("source_url", "")),
        records=records,
        raw_sha256=sha256_json(records),
        limitations=limitations,
    ).model_dump(mode="json")


def fetch_yfinance_adjusted_history(
    *,
    ticker: str,
    start_date: str = "",
    end_date: str = "",
    limit: int = 5000,
) -> dict:
    symbol = _yfinance_symbol(ticker)
    try:
        import yfinance as yf  # type: ignore[import-not-found]
    except ImportError:
        return make_failure(
            DataSourceError(
                "dependency_missing",
                "Install optional dependency with: python -m pip install -e .[enriched]",
                SOURCE_ID,
            )
        ).model_dump(mode="json")

    try:
        frame = yf.download(
            symbol,
            start=start_date or None,
            end=end_date or None,
            auto_adjust=False,
            progress=False,
            actions=False,
            timeout=yfinance_timeout_seconds(),
        )
        if frame is None or frame.empty:
            return make_failure(
                DataSourceError("source_unavailable", f"No yfinance data for {symbol}.", SOURCE_ID)
            ).model_dump(mode="json")

        records: list[dict[str, Any]] = []
        for index, row in frame.tail(_safe_limit(limit)).iterrows():
            observed_at = index.date().isoformat()
            records.append(
                {
                    "ticker": str(ticker).strip().upper(),
                    "observed_at": observed_at,
                    "close": _safe_float(_frame_value(row, "Close")),
                    "adjusted_close": _safe_float(_frame_value(row, "Adj Close")),
                    "source_id": "yfinance",
                }
            )
        return make_success(
            source_id=SOURCE_ID,
            source_url=f"https://finance.yahoo.com/quote/{symbol}/history",
            records=records,
            raw_sha256=sha256_json(records),
            limitations=["Unofficial adjusted close source. Validate before production use."],
        ).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        return make_failure(
            DataSourceError("source_unavailable", str(exc), SOURCE_ID, retryable=True)
        ).model_dump(mode="json")


def fetch_economic_timeseries(
    *,
    provider: str,
    series_code: str,
    last: int = 200,
    start_date: str = "",
    end_date: str = "",
) -> dict:
    normalized_provider = str(provider or "").strip().lower()
    if normalized_provider == "bcb_sgs":
        response = fetch_sgs_series(
            series_code,
            last=None if start_date or end_date else last,
            start_date=start_date or None,
            end_date=end_date or None,
        )
    elif normalized_provider == "ipeadata":
        response = fetch_ipea_series(series_code, top=last)
    elif normalized_provider == "ibge_sidra":
        response = fetch_ibge_sidra(series_code)
    else:
        return make_failure(
            DataSourceError(
                "validation_error",
                "provider must be one of: bcb_sgs, ipeadata, ibge_sidra.",
                SOURCE_ID,
            )
        ).model_dump(mode="json")

    if not response.get("ok"):
        return response
    records = canonical_economic_series(
        response.get("records", []),
        provider=normalized_provider,
        series_code=series_code,
    )
    return make_success(
        source_id=SOURCE_ID,
        source_url=response.get("source_url", ""),
        records=records,
        raw_sha256=sha256_json(records),
        limitations=response.get("limitations", []),
    ).model_dump(mode="json")


def write_asset_history_to_store(
    *,
    asset_id: str,
    start_date: str = "",
    end_date: str = "",
    adjusted: bool = False,
    b3_file_path: str = "",
    limit: int = 5000,
    db_path: str | Path | None = None,
) -> dict:
    response = fetch_asset_price_history(
        asset_id=asset_id,
        start_date=start_date,
        end_date=end_date,
        adjusted=adjusted,
        b3_file_path=b3_file_path,
        limit=limit,
    )
    if not response.get("ok"):
        return response
    return write_timeseries_records(response.get("records", []), db_path=db_path)


def write_timeseries_records(records: list[dict[str, Any]], *, db_path: str | Path | None = None) -> dict:
    db_file = _store_path(db_path)
    conn = _connect_store(db_file)
    try:
        now = datetime.now(UTC).isoformat()
        for record in records:
            stored_record = {**record, "asset_id": _store_asset_id(record.get("asset_id", ""))}
            conn.execute(
                """
                INSERT OR REPLACE INTO timeseries_records (
                    series_id, asset_id, observed_at, data_kind, frequency, value,
                    open, high, low, close, adjusted_close, volume, financial_volume,
                    currency, source_id, data_stage, is_adjusted, adjustment_method,
                    simple_return, adjusted_return, quality_flags, payload_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stored_record.get("series_id", ""),
                    stored_record.get("asset_id", ""),
                    stored_record.get("observed_at", ""),
                    stored_record.get("data_kind", ""),
                    stored_record.get("frequency", ""),
                    _safe_float(stored_record.get("value")),
                    _safe_float(stored_record.get("open")),
                    _safe_float(stored_record.get("high")),
                    _safe_float(stored_record.get("low")),
                    _safe_float(stored_record.get("close")),
                    _safe_float(stored_record.get("adjusted_close")),
                    _safe_int(stored_record.get("volume")),
                    _safe_float(stored_record.get("financial_volume")),
                    stored_record.get("currency", ""),
                    stored_record.get("source_id", ""),
                    stored_record.get("data_stage", ""),
                    1 if stored_record.get("is_adjusted") else 0,
                    stored_record.get("adjustment_method", ""),
                    _safe_float(stored_record.get("simple_return")),
                    _safe_float(stored_record.get("adjusted_return")),
                    json.dumps(stored_record.get("quality_flags", []), ensure_ascii=True),
                    json.dumps(stored_record, ensure_ascii=True, sort_keys=True),
                    now,
                ),
            )
        conn.commit()
    finally:
        conn.close()

    payload = [{"db_path": str(db_file), "written": len(records)}]
    return make_success(
        source_id=SOURCE_ID,
        source_url=str(db_file),
        records=payload,
        raw_sha256=sha256_json(payload),
    ).model_dump(mode="json")


def read_timeseries_records(
    *,
    db_path: str | Path | None = None,
    asset_id: str = "",
    series_id: str = "",
    start_date: str = "",
    end_date: str = "",
    limit: int = 5000,
) -> dict:
    db_file = _store_path(db_path)
    if not db_file.exists():
        return make_failure(
            DataSourceError("index_missing", "Timeseries store not found.", SOURCE_ID, source_url=str(db_file))
        ).model_dump(mode="json")

    where = []
    params: list[Any] = []
    if asset_id:
        where.append("UPPER(asset_id) = ?")
        params.append(_store_asset_id(asset_id).upper())
    if series_id:
        where.append("series_id = ?")
        params.append(series_id)
    if start_date:
        where.append("observed_at >= ?")
        params.append(start_date)
    if end_date:
        where.append("observed_at <= ?")
        params.append(end_date)
    sql = "SELECT payload_json FROM timeseries_records"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY observed_at ASC LIMIT ?"
    params.append(_safe_limit(limit))

    conn = _connect_store(db_file)
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    records = [json.loads(row[0]) for row in rows]
    return make_success(
        source_id=SOURCE_ID,
        source_url=str(db_file),
        records=records,
        raw_sha256=sha256_json(records),
    ).model_dump(mode="json")


def _connect_store(db_file: Path) -> sqlite3.Connection:
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS timeseries_records (
            series_id TEXT NOT NULL,
            asset_id TEXT NOT NULL DEFAULT '',
            observed_at TEXT NOT NULL,
            data_kind TEXT,
            frequency TEXT,
            value REAL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            adjusted_close REAL,
            volume INTEGER,
            financial_volume REAL,
            currency TEXT,
            source_id TEXT,
            data_stage TEXT,
            is_adjusted INTEGER,
            adjustment_method TEXT,
            simple_return REAL,
            adjusted_return REAL,
            quality_flags TEXT,
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (series_id, asset_id, observed_at)
        )
        """
    )
    return conn


def _add_returns(records: list[dict[str, Any]], price_field: str, output_field: str) -> None:
    previous_by_series: dict[str, float] = {}
    for record in records:
        price = _safe_float(record.get(price_field))
        series_id = str(record.get("series_id", ""))
        previous = previous_by_series.get(series_id)
        if price is not None and previous not in (None, 0):
            record[output_field] = round((price / previous) - 1, 10)
        if price is not None:
            previous_by_series[series_id] = price


def _add_cumulative_returns(records: list[dict[str, Any]], price_field: str, output_field: str) -> None:
    first_by_series: dict[str, float] = {}
    for record in records:
        price = _safe_float(record.get(price_field))
        series_id = str(record.get("series_id", ""))
        first = first_by_series.get(series_id)
        if price is not None and first not in (None, 0):
            record[output_field] = round((price / first) - 1, 10)
        elif price is not None and first is None:
            first_by_series[series_id] = price


def _filter_dates(records: list[dict[str, Any]], *, start_date: str = "", end_date: str = "") -> list[dict[str, Any]]:
    filtered = []
    for record in records:
        observed = str(record.get("observed_at", ""))
        date_key = _date_key(observed)
        if start_date and date_key < start_date:
            continue
        if end_date and date_key > end_date:
            continue
        filtered.append(record)
    return filtered


def _store_path(db_path: str | Path | None) -> Path:
    return Path(db_path) if db_path else DEFAULT_STORE_PATH


def _ticker_from_asset_id(asset_id: str) -> str:
    raw = str(asset_id or "").strip().upper()
    if raw.startswith("B3:"):
        return raw.split(":", 1)[1]
    return raw


def _store_asset_id(asset_id: Any) -> str:
    raw = str(asset_id or "").strip()
    if not raw:
        return ""
    upper = raw.upper()
    if upper.startswith("B3:"):
        return f"B3:{upper.split(':', 1)[1]}"
    if ":" not in upper:
        return f"B3:{upper}"
    return upper


def _yfinance_symbol(ticker: str) -> str:
    raw = str(ticker or "").strip().upper()
    return raw if "." in raw else f"{raw}.SA"


def _date_key(observed_at: str) -> str:
    return str(observed_at or "")[:10]


def _is_business_day(observed_at: str) -> bool:
    try:
        return datetime.fromisoformat(_date_key(observed_at)).weekday() < 5
    except ValueError:
        return False


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _safe_limit(limit: int) -> int:
    return max(1, min(int(limit or 5000), 20000))


def _normalize_currency(value: Any) -> str:
    raw = str(value or "").strip().upper()
    if raw in {"R$", "BRL"}:
        return "BRL"
    return raw


def _frame_value(row: Any, column: str) -> Any:
    if column in row:
        return row[column]
    for key in row.index:
        if isinstance(key, tuple) and key[0] == column:
            return row[key]
    return None
