from __future__ import annotations

from dadosbr.derivatives import (
    list_derivative_families,
    normalize_futures_quote,
    normalize_futures_quotes,
    normalize_options_chain,
    parse_derivatives_csv_bytes,
)


def test_list_derivative_families_exposes_core_b3_contracts() -> None:
    response = list_derivative_families()

    assert response["ok"] is True
    family_ids = {record["family_id"] for record in response["records"]}
    assert {"DI1", "DAP", "DOL", "WDO", "IND", "WIN", "equity_options"}.issubset(family_ids)


def test_normalize_di1_future_quote_derives_contract_metadata() -> None:
    record = normalize_futures_quote(
        {
            "symbol": "DI1F27",
            "observed_at": "2026-05-05",
            "maturity_date": "2027-01-04",
            "business_days": "170",
            "settlement_price": "93500",
            "previous_settlement_price": "93400",
            "volume": "1500",
            "open_interest": "25000",
        }
    )

    assert record["contract_id"] == "B3_DERIV:DI1F27"
    assert record["instrument_type"] == "future"
    assert record["contract_family"] == "DI1"
    assert record["underlying_asset"] == "one_day_interbank_deposit"
    assert record["maturity_code"] == "F27"
    assert record["maturity_month"] == 1
    assert record["maturity_year"] == 2027
    assert record["settlement_price"] == 93500.0
    assert record["settlement_variation"] == 100.0
    assert record["business_days"] == 170
    assert record["quality_flags"] == []


def test_parse_derivatives_csv_bytes_supports_b3_like_aliases_and_br_decimals() -> None:
    payload = (
        "Data Pregao;Codigo Instrumento;Preco Ajuste Atual;Preco Ajuste Anterior;"
        "Quantidade Negociada;Contratos em Aberto\n"
        "2026-05-05;WDOQ26;5.123,50;5.100,00;12000;200000\n"
    ).encode()

    response = parse_derivatives_csv_bytes(payload, source_url="upload.csv")

    assert response["ok"] is True
    record = response["records"][0]
    assert record["symbol"] == "WDOQ26"
    assert record["contract_family"] == "WDO"
    assert record["instrument_type"] == "future"
    assert record["settlement_price"] == 5123.5
    assert record["settlement_variation"] == 23.5
    assert record["quantity_traded"] == 12000
    assert record["open_interest"] == 200000


def test_normalize_options_chain_structures_equity_options() -> None:
    records = normalize_options_chain(
        [
            {
                "symbol": "PETRF260",
                "underlying_ticker": "PETR4",
                "option_type": "CALL",
                "expiration_date": "2026-06-19",
                "strike_price": "26,00",
                "last_price": "1,25",
                "bid_price": "1,20",
                "ask_price": "1,30",
                "implied_volatility": "0,32",
                "delta": "0,55",
                "observed_at": "2026-05-05",
            }
        ]
    )

    assert records == [
        {
            "option_id": "B3_OPT:PETRF260",
            "symbol": "PETRF260",
            "underlying_ticker": "PETR4",
            "instrument_type": "option",
            "option_style": "unknown",
            "option_type": "call",
            "expiration_date": "2026-06-19",
            "strike_price": 26.0,
            "last_price": 1.25,
            "bid_price": 1.2,
            "ask_price": 1.3,
            "implied_volatility": 0.32,
            "delta": 0.55,
            "observed_at": "2026-05-05",
            "source_id": "b3_derivatives",
            "data_stage": "normalized",
            "quality_flags": [],
        }
    ]


def test_normalize_futures_quotes_filters_empty_symbols() -> None:
    records = normalize_futures_quotes(
        [
            {"symbol": "", "settlement_price": "1"},
            {"symbol": "INDM26", "settlement_price": "125000", "observed_at": "2026-05-05"},
        ]
    )

    assert len(records) == 1
    assert records[0]["contract_family"] == "IND"
