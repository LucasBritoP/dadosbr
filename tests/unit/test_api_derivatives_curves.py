from __future__ import annotations

from fastapi.testclient import TestClient

import dadosbr.api.app as api_app


def test_derivative_families_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        api_app,
        "list_derivative_families",
        lambda: {"ok": True, "records": [{"family_id": "DI1"}]},
    )
    client = TestClient(api_app.app)

    response = client.get("/derivatives/families")

    assert response.status_code == 200
    assert response.json()["records"][0]["family_id"] == "DI1"


def test_derivative_futures_normalize_endpoint(monkeypatch) -> None:
    def fake_normalize(rows):
        assert rows[0]["symbol"] == "DI1F27"
        return [{"symbol": "DI1F27", "contract_family": "DI1"}]

    monkeypatch.setattr(api_app, "normalize_futures_quotes", fake_normalize)
    client = TestClient(api_app.app)

    response = client.post("/derivatives/futures/normalize", json=[{"symbol": "DI1F27"}])

    assert response.status_code == 200
    assert response.json()["records"][0]["contract_family"] == "DI1"


def test_options_normalize_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        api_app,
        "normalize_options_chain",
        lambda rows: [{"symbol": rows[0]["symbol"], "option_type": "call"}],
    )
    client = TestClient(api_app.app)

    response = client.post("/derivatives/options/normalize", json=[{"symbol": "PETRF260"}])

    assert response.status_code == 200
    assert response.json()["records"][0]["option_type"] == "call"


def test_interest_curve_sources_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        api_app,
        "list_interest_curve_sources",
        lambda: {"ok": True, "records": [{"curve_id": "b3_di_pre"}]},
    )
    client = TestClient(api_app.app)

    response = client.get("/curves/sources")

    assert response.status_code == 200
    assert response.json()["records"][0]["curve_id"] == "b3_di_pre"


def test_di_curve_from_futures_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        api_app,
        "build_di_curve_from_futures",
        lambda rows: [{"curve_id": "b3_di_pre", "vertex_symbol": rows[0]["symbol"]}],
    )
    client = TestClient(api_app.app)

    response = client.post("/curves/di-futures", json=[{"symbol": "DI1F27"}])

    assert response.status_code == 200
    assert response.json()["records"][0]["vertex_symbol"] == "DI1F27"


def test_curve_interpolate_endpoint(monkeypatch) -> None:
    def fake_interpolate(rows, *, target_tenor_years):
        assert target_tenor_years == 2.0
        return {"curve_id": rows[0]["curve_id"], "annual_rate": 0.11}

    monkeypatch.setattr(api_app, "interpolate_interest_curve", fake_interpolate)
    client = TestClient(api_app.app)

    response = client.post(
        "/curves/interpolate?target_tenor_years=2",
        json=[{"curve_id": "b3_di_pre", "tenor_years": 1, "annual_rate": 0.1}],
    )

    assert response.status_code == 200
    assert response.json()["records"][0]["annual_rate"] == 0.11
