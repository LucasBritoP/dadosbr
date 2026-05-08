from fastapi.testclient import TestClient

import dadosbr.api.app as api_app


def test_benchmarks_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        api_app,
        "list_benchmarks",
        lambda: {"ok": True, "records": [{"benchmark_id": "selic"}]},
    )
    client = TestClient(api_app.app)

    response = client.get("/benchmarks")

    assert response.status_code == 200
    assert response.json()["records"][0]["benchmark_id"] == "selic"


def test_benchmark_history_endpoint(monkeypatch) -> None:
    def fake_history(**kwargs):
        assert kwargs["benchmark_id"] == "ipca"
        assert kwargs["real"] is False
        return {"ok": True, "records": [{"benchmark_id": "ipca", "value": 0.4}]}

    monkeypatch.setattr(api_app, "fetch_benchmark_history", fake_history)
    client = TestClient(api_app.app)

    response = client.get("/benchmarks/ipca/history?last=1")

    assert response.status_code == 200
    assert response.json()["records"][0]["value"] == 0.4


def test_benchmark_real_history_uses_history_endpoint(monkeypatch) -> None:
    def fake_history(**kwargs):
        assert kwargs["benchmark_id"] == "selic"
        assert kwargs["real"] is True
        assert kwargs["deflator"] == "ipca"
        return {"ok": True, "records": [{"benchmark_id": "selic", "real_value": 1.02}]}

    monkeypatch.setattr(api_app, "fetch_benchmark_history", fake_history)
    client = TestClient(api_app.app)

    response = client.get("/benchmarks/selic/history?real=true&deflator=ipca")

    assert response.status_code == 200
    assert response.json()["records"][0]["real_value"] == 1.02


def test_benchmark_compare_endpoint(monkeypatch) -> None:
    def fake_compare(**kwargs):
        assert kwargs["asset_id"] == "B3:PETR4"
        assert kwargs["benchmark_id"] == "ibov"
        return {"ok": True, "records": [{"excess_return": 0.02}]}

    monkeypatch.setattr(api_app, "compare_asset_to_benchmark", fake_compare)
    client = TestClient(api_app.app)

    response = client.get("/benchmarks/compare?asset_id=B3:PETR4&benchmark_id=ibov")

    assert response.status_code == 200
    assert response.json()["records"][0]["excess_return"] == 0.02


def test_redundant_benchmark_routes_are_not_public_contract() -> None:
    paths = api_app.app.openapi()["paths"]

    assert "/benchmarks/{benchmark_id}/real" not in paths
    assert "/benchmarks/yield-curve" not in paths


def test_macro_calendar_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        api_app,
        "list_macro_calendar",
        lambda: {"ok": True, "records": [{"calendar_id": "bcb_focus"}]},
    )
    client = TestClient(api_app.app)

    response = client.get("/macro/calendar")

    assert response.status_code == 200
    assert response.json()["records"][0]["calendar_id"] == "bcb_focus"
