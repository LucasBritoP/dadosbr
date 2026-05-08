from __future__ import annotations

from math import isclose

from dadosbr.interest_curves import (
    build_di_curve_from_futures,
    calculate_discount_factors,
    calculate_forward_rates,
    interpolate_interest_curve,
    list_interest_curve_sources,
    normalize_anbima_curve_rows,
    normalize_curve_points,
)


def test_list_interest_curve_sources_exposes_tesouro_anbima_and_b3_di() -> None:
    response = list_interest_curve_sources()

    assert response["ok"] is True
    curve_ids = {record["curve_id"] for record in response["records"]}
    assert {"tesouro_direto", "anbima_prefixado", "anbima_ipca", "b3_di_pre"}.issubset(curve_ids)


def test_build_di_curve_from_futures_uses_di1_pu_formula() -> None:
    records = build_di_curve_from_futures(
        [
            {
                "symbol": "DI1F27",
                "contract_family": "DI1",
                "observed_at": "2026-05-05",
                "maturity_date": "2027-01-04",
                "business_days": 170,
                "settlement_price": 93500.0,
            }
        ]
    )

    expected_rate = (100000 / 93500) ** (252 / 170) - 1
    assert len(records) == 1
    assert records[0]["curve_id"] == "b3_di_pre"
    assert records[0]["vertex_symbol"] == "DI1F27"
    assert records[0]["discount_factor"] == 0.935
    assert isclose(records[0]["annual_rate"], expected_rate, rel_tol=1e-10)
    assert records[0]["annual_rate_pct"] == round(expected_rate * 100, 6)


def test_normalize_anbima_curve_rows_expands_prefixado_ipca_and_implicita_vertices() -> None:
    records = normalize_anbima_curve_rows(
        [
            {
                "data_referencia": "2026-05-05",
                "vertice_du": "252",
                "taxa_prefixadas": "10,25",
                "taxa_ipca": "5,50",
                "taxa_implicita": "4,50",
            }
        ]
    )

    by_curve = {record["curve_id"]: record for record in records}
    assert set(by_curve) == {"anbima_prefixado", "anbima_ipca", "anbima_inflacao_implicita"}
    assert by_curve["anbima_prefixado"]["annual_rate_pct"] == 10.25
    assert by_curve["anbima_prefixado"]["annual_rate"] == 0.1025
    assert by_curve["anbima_prefixado"]["business_days"] == 252
    assert by_curve["anbima_prefixado"]["tenor_years"] == 1.0


def test_interpolate_interest_curve_linearly_between_tenors() -> None:
    point = interpolate_interest_curve(
        [
            {"curve_id": "b3_di_pre", "tenor_years": 1.0, "annual_rate": 0.10},
            {"curve_id": "b3_di_pre", "tenor_years": 3.0, "annual_rate": 0.12},
        ],
        target_tenor_years=2.0,
    )

    assert point["curve_id"] == "b3_di_pre"
    assert point["tenor_years"] == 2.0
    assert point["annual_rate"] == 0.11
    assert point["annual_rate_pct"] == 11.0
    assert point["interpolated"] is True


def test_calculate_discount_factors_and_forward_rates() -> None:
    points = normalize_curve_points(
        [
            {"curve_id": "test_curve", "observed_at": "2026-05-05", "business_days": 252, "annual_rate_pct": 10.0},
            {"curve_id": "test_curve", "observed_at": "2026-05-05", "business_days": 504, "annual_rate_pct": 12.0},
        ],
        source_id="unit_test",
    )

    discounted = calculate_discount_factors(points)
    forwards = calculate_forward_rates(discounted)

    assert discounted[0]["discount_factor"] == round(1 / 1.1, 10)
    assert len(forwards) == 1
    expected_forward = ((1.12**2) / 1.10) - 1
    assert isclose(forwards[0]["forward_rate"], expected_forward, rel_tol=1e-10)
    assert forwards[0]["forward_rate_pct"] == round(expected_forward * 100, 6)
