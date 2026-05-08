from fastapi.testclient import TestClient

import dadosbr.api.app as api_app


def test_asset_history_endpoint(monkeypatch) -> None:
    def fake_history(**kwargs):
        assert kwargs["asset_id"] == "B3:PETR4"
        assert kwargs["adjusted"] is True
        return {"ok": True, "records": [{"asset_id": "B3:PETR4", "adjusted_close": 10.5}]}

    monkeypatch.setattr(api_app, "fetch_asset_price_history", fake_history)
    client = TestClient(api_app.app)

    response = client.get("/assets/B3:PETR4/history?adjusted=true")

    assert response.status_code == 200
    assert response.json()["records"][0]["adjusted_close"] == 10.5


def test_economic_timeseries_endpoint(monkeypatch) -> None:
    def fake_series(**kwargs):
        assert kwargs["provider"] == "bcb_sgs"
        assert kwargs["series_code"] == "11"
        return {"ok": True, "records": [{"series_id": "ECON:BCB_SGS:11", "value": 14.65}]}

    monkeypatch.setattr(api_app, "fetch_economic_timeseries", fake_series)
    client = TestClient(api_app.app)

    response = client.get("/timeseries/economic/bcb_sgs/11?last=1")

    assert response.status_code == 200
    assert response.json()["records"][0]["series_id"] == "ECON:BCB_SGS:11"
