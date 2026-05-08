from __future__ import annotations

from dadosbr.fixed_income import (
    build_credit_spread_curve,
    build_fixed_income_master,
    calculate_fixed_income_metrics,
    canonical_tesouro_instrument,
    classify_fixed_income_asset,
    generate_fixed_rate_cashflows,
    normalize_bndes_debenture,
    summarize_fund_fixed_income_exposure,
)


def test_canonical_tesouro_instrument_classifies_indexer_and_duration_bucket() -> None:
    record = canonical_tesouro_instrument(
        {
            "bond_type": "Tesouro IPCA+",
            "maturity_date": "2035-05-15",
            "observed_at": "2026-05-06",
            "buy_rate_morning": 5.7,
            "sell_rate_morning": 5.8,
            "buy_price_morning": 1020.5,
            "sell_price_morning": 1019.2,
        }
    )

    assert record["instrument_id"] == "TESOURO:TESOURO_IPCA:2035-05-15"
    assert record["asset_class"] == "government_bond"
    assert record["indexer"] == "IPCA"
    assert record["rate_type"] == "inflation_linked"
    assert record["duration_bucket"] == "long"
    assert record["source_id"] == "tesouro_transparente"


def test_normalize_bndes_debenture_builds_private_credit_master_record() -> None:
    record = normalize_bndes_debenture(
        {
            "ticker": "ABCD11",
            "company": "Companhia ABCD",
            "cnpj": "12.345.678/0001-90",
            "year": 2026,
            "valor_investido": 1500000.0,
            "indexer": "IPCA",
            "maturity_date": "2030-01-01",
            "quantity_final": 1000.0,
        }
    )

    assert record["instrument_id"] == "DEBENTURE:ABCD11"
    assert record["asset_class"] == "debenture"
    assert record["issuer_cnpj"] == "12345678000190"
    assert record["issuer_name"] == "Companhia ABCD"
    assert record["indexer"] == "IPCA"
    assert record["maturity_date"] == "2030-01-01"
    assert record["quantity_final"] == 1000.0
    assert record["source_id"] == "bndes_dados_abertos"


def test_classify_fixed_income_asset_detects_common_credit_types() -> None:
    assert classify_fixed_income_asset("Debentures", "ABCD11", "Companhia ABCD") == "debenture"
    assert classify_fixed_income_asset("CRI", "CRI123", "Securitizadora") == "cri"
    assert classify_fixed_income_asset("Titulo Publico", "LFT", "Tesouro Nacional") == "government_bond"
    assert classify_fixed_income_asset("Cotas", "XPTO", "Fundo Acoes") == "not_fixed_income"


def test_summarize_fund_fixed_income_exposure_groups_market_value() -> None:
    response = summarize_fund_fixed_income_exposure(
        [
            {"asset_type": "Debentures", "asset_code": "ABCD11", "issuer": "Companhia ABCD", "market_value": 100.0},
            {"asset_type": "Titulo Publico", "asset_code": "LFT", "issuer": "Tesouro Nacional", "market_value": 200.0},
            {"asset_type": "Acoes", "asset_code": "PETR4", "issuer": "Petrobras", "market_value": 50.0},
        ]
    )

    assert response["total_fixed_income_market_value"] == 300.0
    assert response["total_market_value"] == 350.0
    assert response["fixed_income_share"] == 0.857143
    assert response["by_class"]["debenture"] == 100.0
    assert response["by_class"]["government_bond"] == 200.0


def test_generate_fixed_rate_cashflows_and_metrics() -> None:
    cashflows = generate_fixed_rate_cashflows(
        settlement_date="2026-01-01",
        maturity_date="2028-01-01",
        principal=1000.0,
        annual_coupon_rate=0.1,
        payments_per_year=1,
    )
    metrics = calculate_fixed_income_metrics(
        price=1000.0,
        settlement_date="2026-01-01",
        cashflows=cashflows,
    )

    assert cashflows == [
        {"payment_date": "2027-01-01", "cashflow": 100.0, "principal": 0.0, "interest": 100.0},
        {"payment_date": "2028-01-01", "cashflow": 1100.0, "principal": 1000.0, "interest": 100.0},
    ]
    assert round(metrics["yield_to_maturity"], 4) == 0.1
    assert metrics["macaulay_duration_years"] == 1.91
    assert metrics["modified_duration_years"] == 1.74


def test_build_credit_spread_curve_uses_benchmark_rate() -> None:
    curve = build_credit_spread_curve(
        [
            {"instrument_id": "DEBENTURE:ABCD11", "issuer_name": "ABCD", "maturity_date": "2030-01-01", "yield_rate": 0.145},
            {"instrument_id": "DEBENTURE:EFGH11", "issuer_name": "EFGH", "maturity_date": "2028-01-01", "yield_rate": 0.13},
        ],
        benchmark_rate=0.11,
        observed_at="2026-05-06",
    )

    assert [row["instrument_id"] for row in curve] == ["DEBENTURE:EFGH11", "DEBENTURE:ABCD11"]
    assert curve[0]["spread_bps"] == 200.0
    assert curve[1]["spread_bps"] == 350.0


def test_build_fixed_income_master_combines_sources() -> None:
    response = build_fixed_income_master(
        tesouro_rates=[
            {"bond_type": "Tesouro Selic", "maturity_date": "2029-03-01", "observed_at": "2026-05-06"}
        ],
        debentures=[{"ticker": "ABCD11", "company": "ABCD", "cnpj": "12345678000190"}],
        fund_portfolio=[{"asset_type": "CRI", "asset_code": "CRI123", "issuer": "Securitizadora", "market_value": 10.0}],
    )

    assert response["ok"] is True
    classes = {record["asset_class"] for record in response["records"]}
    assert {"government_bond", "debenture", "cri"}.issubset(classes)
