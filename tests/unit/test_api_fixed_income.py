from fastapi.testclient import TestClient

import dadosbr.api.app as api_app


def test_fixed_income_tesouro_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        api_app,
        "get_tesouro_fixed_income",
        lambda **kwargs: {"ok": True, "records": [{"asset_class": "government_bond"}]},
    )
    client = TestClient(api_app.app)

    response = client.get("/fixed-income/tesouro?limit=1")

    assert response.status_code == 200
    assert response.json()["records"][0]["asset_class"] == "government_bond"


def test_fixed_income_debentures_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        api_app,
        "get_private_credit_debentures",
        lambda **kwargs: {"ok": True, "records": [{"asset_class": "debenture"}]},
    )
    client = TestClient(api_app.app)

    response = client.get("/fixed-income/debentures?company=ABCD")

    assert response.status_code == 200
    assert response.json()["records"][0]["asset_class"] == "debenture"


def test_fixed_income_fund_exposure_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        api_app,
        "get_fund_fixed_income_exposure",
        lambda **kwargs: {"ok": True, "records": [{"fixed_income_share": 0.8}]},
    )
    client = TestClient(api_app.app)

    response = client.get("/fixed-income/funds/exposure?cnpj=123")

    assert response.status_code == 200
    assert response.json()["records"][0]["fixed_income_share"] == 0.8


def test_fixed_income_cashflows_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        api_app,
        "get_fixed_income_cashflows",
        lambda **kwargs: {"ok": True, "records": [{"cashflow": 100.0}]},
    )
    client = TestClient(api_app.app)

    response = client.get(
        "/fixed-income/cashflows?settlement_date=2026-01-01&maturity_date=2028-01-01&principal=1000&annual_coupon_rate=0.1"
    )

    assert response.status_code == 200
    assert response.json()["records"][0]["cashflow"] == 100.0


def test_fixed_income_analytics_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        api_app,
        "get_fixed_income_analytics",
        lambda **kwargs: {"ok": True, "records": [{"yield_to_maturity": 0.1}]},
    )
    client = TestClient(api_app.app)

    response = client.get(
        "/fixed-income/analytics?price=1000&settlement_date=2026-01-01&maturity_date=2028-01-01&principal=1000&annual_coupon_rate=0.1"
    )

    assert response.status_code == 200
    assert response.json()["records"][0]["yield_to_maturity"] == 0.1
