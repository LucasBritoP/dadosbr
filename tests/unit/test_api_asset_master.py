from fastapi.testclient import TestClient

from dadosbr.api.app import app


def test_asset_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        "dadosbr.api.app.get_asset_master",
        lambda asset_id, **_kwargs: {"ok": True, "records": [{"asset_id": asset_id}]},
    )
    client = TestClient(app)
    response = client.get("/assets/B3:PETR4")
    assert response.status_code == 200
    assert response.json()["records"][0]["asset_id"] == "B3:PETR4"


def test_issuer_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        "dadosbr.api.app.get_issuer_master",
        lambda cnpj, **_kwargs: {"ok": True, "records": [{"issuer_id": f"BR_CNPJ:{cnpj}"}]},
    )
    client = TestClient(app)
    response = client.get("/issuers/12345678000190")
    assert response.status_code == 200
    assert response.json()["records"][0]["issuer_id"] == "BR_CNPJ:12345678000190"


def test_instrument_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        "dadosbr.api.app.get_instrument_master",
        lambda ticker, **_kwargs: {"ok": True, "records": [{"instrument_id": f"B3:{ticker}"}]},
    )
    client = TestClient(app)
    response = client.get("/instruments/PETR4")
    assert response.status_code == 200
    assert response.json()["records"][0]["instrument_id"] == "B3:PETR4"


def test_cnae_taxonomy_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        "dadosbr.api.app.get_cnae_taxonomy",
        lambda code, **_kwargs: {"ok": True, "records": [{"code": code}]},
    )
    client = TestClient(app)
    response = client.get("/taxonomies/cnae/6201501")
    assert response.status_code == 200
    assert response.json()["records"][0]["code"] == "6201501"


def test_ncm_taxonomy_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        "dadosbr.api.app.get_ncm_taxonomy",
        lambda code: {"ok": True, "records": [{"code": code}]},
    )
    client = TestClient(app)
    response = client.get("/taxonomies/ncm/12019000")
    assert response.status_code == 200
    assert response.json()["records"][0]["code"] == "12019000"
