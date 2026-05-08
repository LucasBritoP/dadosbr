from __future__ import annotations

from dadosbr.benchmarks import (
    _frame_value,
    build_yield_curve_from_tesouro,
    compare_series_to_benchmark,
    deflate_series,
    get_benchmark_metadata,
    list_benchmarks,
    normalize_benchmark_history,
)


def test_list_benchmarks_exposes_core_macro_and_market_aliases() -> None:
    response = list_benchmarks()

    assert response["ok"] is True
    ids = {record["benchmark_id"] for record in response["records"]}
    assert {"selic", "cdi", "ipca", "ptax_usd", "ibov", "ifix"}.issubset(ids)


def test_get_benchmark_metadata_returns_source_details() -> None:
    response = get_benchmark_metadata("selic")

    assert response["ok"] is True
    record = response["records"][0]
    assert record["benchmark_id"] == "selic"
    assert record["provider"] == "bcb_sgs"
    assert record["series_code"] == "11"
    assert record["data_kind"] == "interest_rate"


def test_normalize_benchmark_history_adds_returns_and_revision_policy() -> None:
    metadata = get_benchmark_metadata("ibov")["records"][0]

    records = normalize_benchmark_history(
        [
            {"observed_at": "2026-05-05", "value": 100000.0},
            {"observed_at": "2026-05-06", "value": 101000.0},
        ],
        metadata=metadata,
    )

    assert records[0]["series_id"] == "BENCHMARK:IBOV"
    assert records[0]["simple_return"] is None
    assert records[1]["simple_return"] == 0.01
    assert records[1]["cumulative_return"] == 0.01
    assert records[1]["revision_policy"] == "not_expected"


def test_deflate_series_uses_accumulated_inflation_percent_values() -> None:
    real = deflate_series(
        nominal_records=[
            {"observed_at": "2026-01-31", "value": 100.0},
            {"observed_at": "2026-02-28", "value": 111.0},
        ],
        inflation_records=[
            {"observed_at": "2026-01-31", "value": 0.0},
            {"observed_at": "2026-02-28", "value": 10.0},
        ],
    )

    assert real[0]["real_value"] == 100.0
    assert real[1]["real_value"] == 100.909091
    assert real[1]["deflator_factor"] == 1.1


def test_compare_series_to_benchmark_aligns_dates_and_excess_return() -> None:
    comparison = compare_series_to_benchmark(
        asset_records=[
            {"observed_at": "2026-05-05", "simple_return": None},
            {"observed_at": "2026-05-06", "simple_return": 0.03},
        ],
        benchmark_records=[
            {"observed_at": "2026-05-06", "simple_return": 0.01},
        ],
        asset_id="B3:PETR4",
        benchmark_id="ibov",
    )

    assert comparison == [
        {
            "observed_at": "2026-05-06",
            "asset_id": "B3:PETR4",
            "benchmark_id": "ibov",
            "asset_return": 0.03,
            "benchmark_return": 0.01,
            "excess_return": 0.02,
        }
    ]


def test_frame_value_returns_scalar_from_multiindex_like_yfinance_row() -> None:
    class _ScalarSeries:
        def __init__(self, value: float) -> None:
            self.iloc = [value]

        def __len__(self) -> int:
            return 1

    class _Row:
        index = [("Close", "^BVSP")]

        def __contains__(self, key: object) -> bool:
            return key == "Close"

        def __getitem__(self, key: object):
            if key == "Close":
                return _ScalarSeries(123456.0)
            if key == ("Close", "^BVSP"):
                return 123456.0
            raise KeyError(key)

    assert _frame_value(_Row(), "Close") == 123456.0


def test_build_yield_curve_from_tesouro_sorts_by_maturity_and_tenor() -> None:
    curve = build_yield_curve_from_tesouro(
        [
            {
                "bond_type": "Tesouro IPCA+",
                "maturity_date": "2030-05-15",
                "observed_at": "2026-05-05",
                "buy_rate_morning": 5.5,
                "sell_rate_morning": 5.6,
            },
            {
                "bond_type": "Tesouro Selic",
                "maturity_date": "2029-03-01",
                "observed_at": "2026-05-05",
                "buy_rate_morning": 10.0,
                "sell_rate_morning": 10.1,
            },
        ]
    )

    assert [record["maturity_date"] for record in curve] == ["2029-03-01", "2030-05-15"]
    assert curve[0]["tenor_years"] == 2.82
    assert curve[0]["rate_type"] == "post_fixed"
    assert curve[1]["rate_type"] == "inflation_linked"
