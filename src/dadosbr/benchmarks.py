from __future__ import annotations

from datetime import date, datetime
from typing import Any

from dadosbr.core import DataSourceError, make_failure, make_success
from dadosbr.core.utils import sha256_json
from dadosbr.core.yfinance import yfinance_timeout_seconds
from dadosbr.timeseries import fetch_asset_price_history, fetch_economic_timeseries
from dadosbr.connectors.tesouro import fetch_tesouro_rates

SOURCE_ID = "benchmarks"

BENCHMARK_CATALOG: dict[str, dict[str, Any]] = {
    "selic": {
        "benchmark_id": "selic",
        "name": "SELIC efetiva diaria",
        "provider": "bcb_sgs",
        "series_code": "11",
        "data_kind": "interest_rate",
        "frequency": "daily",
        "unit": "% a.d.",
        "source_id": "bcb_sgs",
        "revision_policy": "not_expected",
        "official": True,
    },
    "cdi": {
        "benchmark_id": "cdi",
        "name": "CDI diario",
        "provider": "bcb_sgs",
        "series_code": "12",
        "data_kind": "interest_rate",
        "frequency": "daily",
        "unit": "% a.d.",
        "source_id": "bcb_sgs",
        "revision_policy": "not_expected",
        "official": True,
    },
    "ipca": {
        "benchmark_id": "ipca",
        "name": "IPCA variacao mensal",
        "provider": "bcb_sgs",
        "series_code": "433",
        "data_kind": "inflation",
        "frequency": "monthly",
        "unit": "% m/m",
        "source_id": "bcb_sgs",
        "revision_policy": "possible",
        "official": True,
    },
    "igpm": {
        "benchmark_id": "igpm",
        "name": "IGP-M variacao mensal",
        "provider": "bcb_sgs",
        "series_code": "189",
        "data_kind": "inflation",
        "frequency": "monthly",
        "unit": "% m/m",
        "source_id": "bcb_sgs",
        "revision_policy": "possible",
        "official": True,
    },
    "ptax_usd": {
        "benchmark_id": "ptax_usd",
        "name": "Dolar americano venda",
        "provider": "bcb_sgs",
        "series_code": "1",
        "data_kind": "fx_rate",
        "frequency": "daily",
        "unit": "BRL/USD",
        "source_id": "bcb_sgs",
        "revision_policy": "not_expected",
        "official": True,
    },
    "ibov": {
        "benchmark_id": "ibov",
        "name": "Ibovespa",
        "provider": "yfinance",
        "symbol": "^BVSP",
        "data_kind": "market_index",
        "frequency": "daily",
        "unit": "points",
        "source_id": "yfinance",
        "revision_policy": "not_expected",
        "official": False,
    },
    "ifix": {
        "benchmark_id": "ifix",
        "name": "IFIX",
        "provider": "yfinance",
        "symbol": "IFIX.SA",
        "data_kind": "market_index",
        "frequency": "daily",
        "unit": "points",
        "source_id": "yfinance",
        "revision_policy": "not_expected",
        "official": False,
    },
}

MACRO_CALENDAR: list[dict[str, Any]] = [
    {
        "calendar_id": "bcb_focus",
        "name": "Boletim Focus",
        "source_id": "bcb_focus",
        "frequency": "weekly",
        "release_rule": "Publicado semanalmente pelo Banco Central.",
        "revision_policy": "new_snapshot",
    },
    {
        "calendar_id": "bcb_sgs_daily",
        "name": "Series diarias SGS",
        "source_id": "bcb_sgs",
        "frequency": "daily",
        "release_rule": "Disponibilidade depende da serie SGS consultada.",
        "revision_policy": "series_dependent",
    },
    {
        "calendar_id": "ibge_ipca",
        "name": "IPCA",
        "source_id": "ibge_sidra",
        "frequency": "monthly",
        "release_rule": "Calendario oficial do IBGE; esta alfa registra a regra, nao a data futura exata.",
        "revision_policy": "possible",
    },
    {
        "calendar_id": "tesouro_direto",
        "name": "Taxas e precos do Tesouro Direto",
        "source_id": "tesouro_transparente",
        "frequency": "daily",
        "release_rule": "Atualizacao em dias uteis conforme disponibilidade do Tesouro Transparente.",
        "revision_policy": "not_expected",
    },
]


def list_benchmarks() -> dict:
    records = [BENCHMARK_CATALOG[key] for key in sorted(BENCHMARK_CATALOG)]
    return make_success(
        source_id=SOURCE_ID,
        source_url="local://dadosbr/benchmarks/catalog",
        records=records,
        raw_sha256=sha256_json(records),
    ).model_dump(mode="json")


def get_benchmark_metadata(benchmark_id: str) -> dict:
    benchmark = _metadata(benchmark_id)
    if not benchmark:
        return make_failure(
            DataSourceError("not_found", f"Unknown benchmark: {benchmark_id}", SOURCE_ID)
        ).model_dump(mode="json")
    return make_success(
        source_id=SOURCE_ID,
        source_url="local://dadosbr/benchmarks/catalog",
        records=[benchmark],
        raw_sha256=sha256_json([benchmark]),
    ).model_dump(mode="json")


def fetch_benchmark_history(
    *,
    benchmark_id: str,
    start_date: str = "",
    end_date: str = "",
    last: int = 200,
    real: bool = False,
    deflator: str = "ipca",
) -> dict:
    metadata = _metadata(benchmark_id)
    if not metadata:
        return make_failure(
            DataSourceError("not_found", f"Unknown benchmark: {benchmark_id}", SOURCE_ID)
        ).model_dump(mode="json")

    if metadata["provider"] == "bcb_sgs":
        response = fetch_economic_timeseries(
            provider="bcb_sgs",
            series_code=str(metadata["series_code"]),
            last=last,
            start_date=start_date,
            end_date=end_date,
        )
    elif metadata["provider"] == "yfinance":
        response = fetch_yfinance_benchmark_history(
            symbol=str(metadata["symbol"]),
            benchmark_id=metadata["benchmark_id"],
            start_date=start_date,
            end_date=end_date,
            limit=last,
        )
    else:
        return make_failure(
            DataSourceError(
                "validation_error",
                f"Unsupported benchmark provider: {metadata['provider']}",
                SOURCE_ID,
            )
        ).model_dump(mode="json")

    if not response.get("ok"):
        return response

    records = normalize_benchmark_history(response.get("records", []), metadata=metadata)
    limitations = list(response.get("limitations", []))
    if metadata["provider"] == "yfinance":
        limitations.append("Market index data uses optional yfinance enrichment, not official B3 redistribution.")

    if real:
        deflator_response = fetch_benchmark_history(
            benchmark_id=deflator,
            start_date=start_date,
            end_date=end_date,
            last=last,
            real=False,
        )
        if not deflator_response.get("ok"):
            return deflator_response
        records = deflate_series(
            nominal_records=records,
            inflation_records=deflator_response.get("records", []),
            deflator_id=deflator,
        )

    return make_success(
        source_id=SOURCE_ID,
        source_url=response.get("source_url", ""),
        records=records,
        raw_sha256=sha256_json(records),
        limitations=limitations,
    ).model_dump(mode="json")


def fetch_yfinance_benchmark_history(
    *,
    symbol: str,
    benchmark_id: str,
    start_date: str = "",
    end_date: str = "",
    limit: int = 200,
) -> dict:
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
            value = _frame_value(row, "Adj Close")
            if value is None:
                value = _frame_value(row, "Close")
            records.append(
                {
                    "benchmark_id": benchmark_id,
                    "observed_at": index.date().isoformat(),
                    "value": _safe_float(value),
                }
            )
        return make_success(
            source_id=SOURCE_ID,
            source_url=f"https://finance.yahoo.com/quote/{symbol}/history",
            records=records,
            raw_sha256=sha256_json(records),
        ).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        return make_failure(
            DataSourceError("source_unavailable", str(exc), SOURCE_ID, retryable=True)
        ).model_dump(mode="json")


def normalize_benchmark_history(
    rows: list[dict[str, Any]],
    *,
    metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    accumulated_factor = 1.0
    unit = str(metadata.get("unit", ""))
    for row in sorted(rows, key=lambda item: str(item.get("observed_at", ""))):
        value = _safe_float(row.get("value"))
        quality_flags = [] if value is not None else ["missing_value"]
        if metadata.get("revision_policy") not in {"", "not_expected"}:
            quality_flags.append("revision_possible")
        period_factor = round(1 + (value / 100), 10) if value is not None and unit.startswith("%") else None
        if period_factor is not None:
            accumulated_factor *= period_factor
        record = {
            "benchmark_id": metadata["benchmark_id"],
            "series_id": f"BENCHMARK:{str(metadata['benchmark_id']).upper()}",
            "name": metadata["name"],
            "data_kind": metadata["data_kind"],
            "frequency": metadata["frequency"],
            "observed_at": str(row.get("observed_at", "")),
            "value": value,
            "unit": metadata["unit"],
            "source_id": metadata["source_id"],
            "provider": metadata["provider"],
            "data_stage": "normalized",
            "official": bool(metadata.get("official")),
            "revision_policy": metadata.get("revision_policy", ""),
            "period_factor": period_factor,
            "accumulated_factor": round(accumulated_factor, 10) if period_factor is not None else None,
            "simple_return": None,
            "cumulative_return": None,
            "quality_flags": quality_flags,
        }
        records.append(record)
    _add_returns(records)
    return records


def deflate_series(
    *,
    nominal_records: list[dict[str, Any]],
    inflation_records: list[dict[str, Any]],
    deflator_id: str = "ipca",
) -> list[dict[str, Any]]:
    inflation = sorted(inflation_records, key=lambda item: str(item.get("observed_at", "")))
    nominal = sorted(nominal_records, key=lambda item: str(item.get("observed_at", "")))
    factor = 1.0
    cursor = 0
    records: list[dict[str, Any]] = []
    for record in nominal:
        observed = _date_key(record.get("observed_at", ""))
        while cursor < len(inflation) and _date_key(inflation[cursor].get("observed_at", "")) <= observed:
            inflation_value = _safe_float(inflation[cursor].get("value"))
            if inflation_value is not None:
                factor *= 1 + (inflation_value / 100)
            cursor += 1
        value = _safe_float(record.get("value"))
        enriched = dict(record)
        enriched["deflator_id"] = deflator_id
        enriched["deflator_factor"] = round(factor, 6)
        enriched["real_value"] = round(value / factor, 6) if value is not None and factor else None
        enriched["data_stage"] = "deflated"
        records.append(enriched)
    return records


def compare_asset_to_benchmark(
    *,
    asset_id: str,
    benchmark_id: str,
    start_date: str = "",
    end_date: str = "",
    adjusted: bool = False,
    b3_file_path: str = "",
    last: int = 5000,
) -> dict:
    asset_response = fetch_asset_price_history(
        asset_id=asset_id,
        start_date=start_date,
        end_date=end_date,
        adjusted=adjusted,
        b3_file_path=b3_file_path,
        limit=last,
    )
    if not asset_response.get("ok"):
        return asset_response
    benchmark_response = fetch_benchmark_history(
        benchmark_id=benchmark_id,
        start_date=start_date,
        end_date=end_date,
        last=last,
    )
    if not benchmark_response.get("ok"):
        return benchmark_response
    records = compare_series_to_benchmark(
        asset_records=asset_response.get("records", []),
        benchmark_records=benchmark_response.get("records", []),
        asset_id=asset_id,
        benchmark_id=benchmark_id,
        adjusted=adjusted,
    )
    return make_success(
        source_id=SOURCE_ID,
        source_url="local://dadosbr/benchmarks/compare",
        records=records,
        raw_sha256=sha256_json(records),
    ).model_dump(mode="json")


def compare_series_to_benchmark(
    *,
    asset_records: list[dict[str, Any]],
    benchmark_records: list[dict[str, Any]],
    asset_id: str,
    benchmark_id: str,
    adjusted: bool = False,
) -> list[dict[str, Any]]:
    asset_field = "adjusted_return" if adjusted else "simple_return"
    benchmark_by_date = {_date_key(row.get("observed_at", "")): row for row in benchmark_records}
    records: list[dict[str, Any]] = []
    for asset in asset_records:
        observed = _date_key(asset.get("observed_at", ""))
        benchmark = benchmark_by_date.get(observed)
        if not benchmark:
            continue
        asset_return = _safe_float(asset.get(asset_field))
        benchmark_return = _safe_float(benchmark.get("simple_return"))
        if asset_return is None or benchmark_return is None:
            continue
        records.append(
            {
                "observed_at": observed,
                "asset_id": asset_id,
                "benchmark_id": benchmark_id,
                "asset_return": asset_return,
                "benchmark_return": benchmark_return,
                "excess_return": round(asset_return - benchmark_return, 10),
            }
        )
    return records


def fetch_yield_curve(*, limit: int = 200) -> dict:
    response = fetch_tesouro_rates(limit=limit)
    if not response.get("ok"):
        return response
    records = build_yield_curve_from_tesouro(response.get("records", []))
    return make_success(
        source_id=SOURCE_ID,
        source_url=response.get("source_url", ""),
        records=records,
        raw_sha256=sha256_json(records),
        limitations=["Curva derivada dos titulos ofertados no Tesouro Direto; nao e curva ANBIMA."],
    ).model_dump(mode="json")


def build_yield_curve_from_tesouro(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rows:
        observed = _parse_date(row.get("observed_at"))
        maturity = _parse_date(row.get("maturity_date"))
        if observed is None or maturity is None:
            continue
        bond_type = str(row.get("bond_type", ""))
        tenor_years = round((maturity - observed).days / 365.25, 2)
        records.append(
            {
                "benchmark_id": "tesouro_yield_curve",
                "observed_at": observed.isoformat(),
                "bond_type": bond_type,
                "maturity_date": maturity.isoformat(),
                "tenor_years": tenor_years,
                "buy_rate": _safe_float(row.get("buy_rate_morning")),
                "sell_rate": _safe_float(row.get("sell_rate_morning")),
                "rate_type": _tesouro_rate_type(bond_type),
                "source_id": "tesouro_transparente",
                "data_stage": "derived",
            }
        )
    return sorted(records, key=lambda item: (item["maturity_date"], item["bond_type"]))


def list_macro_calendar() -> dict:
    return make_success(
        source_id=SOURCE_ID,
        source_url="local://dadosbr/macro/calendar",
        records=MACRO_CALENDAR,
        raw_sha256=sha256_json(MACRO_CALENDAR),
        limitations=["Calendario alfa descreve frequencias/regras, nao datas futuras oficiais dinamicas."],
    ).model_dump(mode="json")


def _metadata(benchmark_id: str) -> dict[str, Any] | None:
    return BENCHMARK_CATALOG.get(str(benchmark_id or "").strip().lower())


def _add_returns(records: list[dict[str, Any]]) -> None:
    first: float | None = None
    previous: float | None = None
    for record in records:
        value = _safe_float(record.get("value"))
        if value is not None and previous not in (None, 0):
            record["simple_return"] = round((value / previous) - 1, 10)
        if value is not None and first not in (None, 0):
            record["cumulative_return"] = round((value / first) - 1, 10)
        elif value is not None and first is None:
            first = value
        if value is not None:
            previous = value


def _tesouro_rate_type(bond_type: str) -> str:
    text = bond_type.upper()
    if "IPCA" in text:
        return "inflation_linked"
    if "SELIC" in text:
        return "post_fixed"
    if "PREFIX" in text:
        return "fixed_rate"
    return "unknown"


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()[:10]
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _date_key(value: Any) -> str:
    return str(value or "")[:10]


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_limit(limit: int) -> int:
    return max(1, min(int(limit or 200), 20000))


def _frame_value(row: Any, column: str) -> Any:
    for key in row.index:
        if isinstance(key, tuple) and key[0] == column:
            return _scalar_value(row[key])
    if column in row:
        return _scalar_value(row[column])
    return None


def _scalar_value(value: Any) -> Any:
    if hasattr(value, "iloc") and hasattr(value, "__len__"):
        try:
            if len(value) == 0:
                return None
            return value.iloc[0]
        except Exception:  # noqa: BLE001
            return value
    return value
