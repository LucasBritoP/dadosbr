from __future__ import annotations

from dadosbr.corporate_actions import (
    apply_adjustments_to_price_history,
    calculate_adjustment_factors,
    list_corporate_action_types,
    normalize_corporate_action,
    normalize_corporate_actions,
    normalize_yfinance_actions,
)


def test_normalize_cash_event_keeps_structured_dates_and_identifiers() -> None:
    event = normalize_corporate_action(
        {
            "ticker": "PETR4",
            "isin": "BRPETRACNPR6",
            "issuer_cnpj": "33.000.167/0001-01",
            "cvm_code": "9512",
            "event_type": "dividendo",
            "declared_date": "2026-04-20",
            "ex_date": "2026-05-02",
            "payment_date": "2026-05-20",
            "amount_per_share": "1.25",
            "reference_price": "25.00",
            "status": "confirmed",
            "source_id": "manual",
            "document_id": "ata-123",
        }
    )

    assert event["action_id"] == "PETR4:DIVIDEND:2026-05-02:1.25"
    assert event["asset_id"] == "B3:PETR4"
    assert event["issuer_cnpj"] == "33000167000101"
    assert event["event_type"] == "dividend"
    assert event["event_category"] == "cash"
    assert event["amount_per_share"] == 1.25
    assert event["price_adjustment_factor"] == 0.95
    assert event["share_adjustment_factor"] == 1.0
    assert event["document_id"] == "ata-123"


def test_normalize_yfinance_actions_builds_dividend_and_split_events() -> None:
    events = normalize_yfinance_actions(
        dividends=[{"observed_at": "2026-05-02", "value": 0.5}],
        splits=[{"observed_at": "2026-06-01", "value": 2.0}],
        ticker="ABCD3",
    )

    assert [event["event_type"] for event in events] == ["dividend", "split"]
    assert events[0]["source_id"] == "yfinance"
    assert events[0]["ex_date"] == "2026-05-02"
    assert events[1]["ratio"] == 2.0
    assert events[1]["price_adjustment_factor"] == 0.5
    assert events[1]["share_adjustment_factor"] == 2.0


def test_calculate_adjustment_factors_accumulates_cash_and_share_events() -> None:
    events = [
        normalize_corporate_action(
            {"ticker": "ABCD3", "event_type": "split", "ex_date": "2026-05-10", "ratio": 2.0}
        ),
        normalize_corporate_action(
            {
                "ticker": "ABCD3",
                "event_type": "jcp",
                "ex_date": "2026-05-15",
                "amount_per_share": 1.0,
                "reference_price": 10.0,
            }
        ),
    ]

    factors = calculate_adjustment_factors(events)

    assert factors[0]["price_adjustment_factor"] == 0.5
    assert factors[0]["cumulative_price_factor"] == 0.5
    assert factors[1]["price_adjustment_factor"] == 0.9
    assert factors[1]["cumulative_price_factor"] == 0.45
    assert factors[1]["cumulative_share_factor"] == 2.0


def test_apply_adjustments_to_price_history_uses_events_after_each_price_date() -> None:
    price_history = [
        {"observed_at": "2026-05-09", "open": 18.0, "high": 21.0, "low": 17.0, "close": 20.0, "volume": 100},
        {"observed_at": "2026-05-12", "open": 9.5, "high": 10.5, "low": 9.0, "close": 10.0, "volume": 200},
        {"observed_at": "2026-05-16", "open": 9.0, "high": 9.2, "low": 8.8, "close": 9.0, "volume": 210},
    ]
    events = [
        normalize_corporate_action(
            {"ticker": "ABCD3", "event_type": "split", "ex_date": "2026-05-10", "ratio": 2.0}
        ),
        normalize_corporate_action(
            {
                "ticker": "ABCD3",
                "event_type": "dividend",
                "ex_date": "2026-05-15",
                "amount_per_share": 1.0,
                "reference_price": 10.0,
            }
        ),
    ]

    adjusted = apply_adjustments_to_price_history(price_history, events)

    assert adjusted[0]["adjusted_close"] == 9.0
    assert adjusted[0]["adjusted_volume"] == 200
    assert adjusted[1]["adjusted_close"] == 9.0
    assert adjusted[2]["adjusted_close"] == 9.0
    assert adjusted[0]["adjustment_event_count"] == 2
    assert adjusted[2]["adjustment_event_count"] == 0


def test_normalize_corporate_actions_response_and_type_catalog() -> None:
    response = normalize_corporate_actions(
        [{"ticker": "ABCD3", "event_type": "subscricao", "ex_date": "2026-05-01", "subscription_price": 12.3}]
    )
    type_response = list_corporate_action_types()

    assert response["ok"] is True
    assert response["records"][0]["event_type"] == "subscription"
    assert response["records"][0]["subscription_price"] == 12.3
    assert type_response["ok"] is True
    assert {"dividend", "jcp", "split", "reverse_split", "subscription"}.issubset(
        {record["event_type"] for record in type_response["records"]}
    )
