from fastapi.testclient import TestClient

import dadosbr.api.app as api_app


def test_corporate_action_types_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        api_app,
        "list_corporate_action_types",
        lambda: {"ok": True, "records": [{"event_type": "dividend"}]},
    )
    client = TestClient(api_app.app)

    response = client.get("/corporate-actions/types")

    assert response.status_code == 200
    assert response.json()["records"][0]["event_type"] == "dividend"


def test_corporate_actions_ticker_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        api_app,
        "get_corporate_actions",
        lambda **kwargs: {"ok": True, "records": [{"ticker": kwargs["ticker"], "event_type": "split"}]},
    )
    client = TestClient(api_app.app)

    response = client.get("/corporate-actions/PETR4?source=yfinance")

    assert response.status_code == 200
    assert response.json()["records"][0]["ticker"] == "PETR4"


def test_corporate_action_factors_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        api_app,
        "get_corporate_action_factors",
        lambda **kwargs: {"ok": True, "records": [{"cumulative_price_factor": 0.9}]},
    )
    client = TestClient(api_app.app)

    response = client.get("/corporate-actions/PETR4/adjustment-factors")

    assert response.status_code == 200
    assert response.json()["records"][0]["cumulative_price_factor"] == 0.9


def test_adjusted_history_endpoint(monkeypatch, tmp_path) -> None:
    cotahist = tmp_path / "cotahist.txt"
    cotahist.write_text("", encoding="utf-8")
    monkeypatch.setenv("DADOSBR_ENABLE_LOCAL_FILE_ENDPOINTS", "1")
    monkeypatch.setenv("DADOSBR_LOCAL_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        api_app,
        "get_corporate_action_adjusted_history",
        lambda **kwargs: {"ok": True, "records": [{"adjusted_close": 10.0}]},
    )
    client = TestClient(api_app.app)

    response = client.get(
        "/corporate-actions/PETR4/adjusted-history",
        params={"b3_file_path": str(cotahist)},
    )

    assert response.status_code == 200
    assert response.json()["records"][0]["adjusted_close"] == 10.0
