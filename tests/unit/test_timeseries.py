from __future__ import annotations

from dadosbr.timeseries import (
    canonical_b3_price_history,
    canonical_economic_series,
    fetch_yfinance_adjusted_history,
    read_timeseries_records,
    write_timeseries_records,
)


def test_canonical_b3_price_history_adds_returns_and_adjustment_flags() -> None:
    rows = [
        {
            "ticker": "PETR4",
            "observed_at": "2026-05-05T00:00:00+00:00",
            "open_price": 10.0,
            "high_price": 11.0,
            "low_price": 9.5,
            "close_price": 10.0,
            "quantity_traded": 100,
            "financial_volume": 1000.0,
            "currency_ref": "R$",
            "isin": "BRPETRACNPR6",
        },
        {
            "ticker": "PETR4",
            "observed_at": "2026-05-06T00:00:00+00:00",
            "open_price": 10.2,
            "high_price": 11.5,
            "low_price": 10.0,
            "close_price": 11.0,
            "quantity_traded": 150,
            "financial_volume": 1650.0,
            "currency_ref": "R$",
            "isin": "BRPETRACNPR6",
        },
    ]

    records = canonical_b3_price_history(
        rows,
        adjusted_by_date={"2026-05-06": {"adjusted_close": 10.5}},
        adjusted=True,
    )

    assert records[0]["series_id"] == "PRICE:B3:PETR4:1D"
    assert records[0]["asset_id"] == "B3:PETR4"
    assert records[0]["data_stage"] == "normalized"
    assert records[0]["is_business_day"] is True
    assert records[0]["simple_return"] is None
    assert records[1]["simple_return"] == 0.1
    assert records[1]["cumulative_return"] == 0.1
    assert records[1]["adjusted_close"] == 10.5
    assert records[1]["is_adjusted"] is True
    assert records[1]["adjustment_method"] == "yfinance_adj_close"
    assert "missing_adjusted_close" in records[0]["quality_flags"]


def test_timeseries_store_roundtrip_deduplicates_records(tmp_path) -> None:
    db_path = tmp_path / "timeseries.sqlite"
    records = canonical_b3_price_history(
        [
            {"ticker": "VALE3", "observed_at": "2026-05-05T00:00:00+00:00", "close_price": 60.0},
            {"ticker": "VALE3", "observed_at": "2026-05-06T00:00:00+00:00", "close_price": 61.0},
        ]
    )

    first = write_timeseries_records(records, db_path=db_path)
    second = write_timeseries_records(records, db_path=db_path)
    read = read_timeseries_records(db_path=db_path, asset_id="B3:VALE3")

    assert first["ok"] is True
    assert second["ok"] is True
    assert read["ok"] is True
    assert len(read["records"]) == 2
    assert read["records"][0]["observed_at"].startswith("2026-05-05")
    assert read["records"][1]["close"] == 61.0

    unprefixed = read_timeseries_records(db_path=db_path, asset_id="VALE3")
    lowercase = read_timeseries_records(db_path=db_path, asset_id="b3:vale3")

    assert len(unprefixed["records"]) == 2
    assert len(lowercase["records"]) == 2


def test_canonical_economic_series_marks_provider_and_stage() -> None:
    records = canonical_economic_series(
        [{"series_id": "11", "observed_at": "2026-05-05T00:00:00+00:00", "value": 14.65}],
        provider="bcb_sgs",
        series_code="11",
    )

    assert records == [
        {
            "series_id": "ECON:BCB_SGS:11",
            "asset_id": "",
            "data_kind": "economic_indicator",
            "frequency": "unknown",
            "observed_at": "2026-05-05T00:00:00+00:00",
            "value": 14.65,
            "source_id": "bcb_sgs",
            "data_stage": "normalized",
            "quality_flags": [],
        }
    ]


def test_yfinance_adjusted_history_uses_timeout(monkeypatch) -> None:
    import sys

    seen: dict[str, int | None] = {}

    class FakeYFinance:
        @staticmethod
        def download(*_args, **kwargs):
            seen["timeout"] = kwargs.get("timeout")
            return None

    monkeypatch.setitem(sys.modules, "yfinance", FakeYFinance)

    response = fetch_yfinance_adjusted_history(ticker="PETR4", limit=1)

    assert response["ok"] is False
    assert seen["timeout"] == 30
