from fastapi.testclient import TestClient

import dadosbr.api.app as api_app


def test_fundamentals_company_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        api_app,
        "get_company_fundamentals",
        lambda **kwargs: {"ok": True, "records": [{"identity": {"company_id": "CVM:12345"}}]},
    )
    client = TestClient(api_app.app)

    response = client.get("/fundamentals/companies/12345?year=2026")

    assert response.status_code == 200
    assert response.json()["records"][0]["identity"]["company_id"] == "CVM:12345"


def test_fundamentals_statement_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        api_app,
        "get_company_statement",
        lambda **kwargs: {"ok": True, "records": [{"canonical_account": "revenue"}]},
    )
    client = TestClient(api_app.app)

    response = client.get("/fundamentals/companies/12345/statements?year=2026")

    assert response.status_code == 200
    assert response.json()["records"][0]["canonical_account"] == "revenue"


def test_fundamentals_ratios_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        api_app,
        "get_company_ratios",
        lambda **kwargs: {"ok": True, "records": [{"roe": 0.15}]},
    )
    client = TestClient(api_app.app)

    response = client.get("/fundamentals/companies/12345/ratios?year=2026")

    assert response.status_code == 200
    assert response.json()["records"][0]["roe"] == 0.15


def test_fundamentals_dividends_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        api_app,
        "get_company_dividends",
        lambda **kwargs: {"ok": True, "records": [{"amount": 0.5}]},
    )
    client = TestClient(api_app.app)

    response = client.get("/fundamentals/companies/ABCD3/dividends")

    assert response.status_code == 200
    assert response.json()["records"][0]["amount"] == 0.5


def test_fundamentals_compare_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        api_app,
        "compare_companies_fundamentals",
        lambda **kwargs: {"ok": True, "records": [{"rank": 1}]},
    )
    client = TestClient(api_app.app)

    response = client.get("/fundamentals/compare?cvm_codes=1,2&year=2026&metric=roe")

    assert response.status_code == 200
    assert response.json()["records"][0]["rank"] == 1


def test_fundamentals_calendar_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        api_app,
        "list_fundamentals_calendar",
        lambda: {"ok": True, "records": [{"calendar_id": "cvm_dfp"}]},
    )
    client = TestClient(api_app.app)

    response = client.get("/fundamentals/calendar")

    assert response.status_code == 200
    assert response.json()["records"][0]["calendar_id"] == "cvm_dfp"
