from fastapi.testclient import TestClient

from dadosbr.api.app import app


def test_cnpj_status_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        "dadosbr.api.app.get_cnpj_status",
        lambda: {"ok": True, "records": [{"db_path": "x"}]},
    )
    client = TestClient(app)
    response = client.get("/cnpj/status")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_cnpj_company_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        "dadosbr.api.app.get_cnpj_company",
        lambda cnpj: {"ok": True, "records": [{"cnpj": cnpj}]},
    )
    client = TestClient(app)
    response = client.get("/cnpj/12345678000190")
    assert response.status_code == 200
    assert response.json()["records"][0]["cnpj"] == "12345678000190"


def test_comex_ncm_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        "dadosbr.api.app.fetch_comex_ncm",
        lambda **_kwargs: {"ok": True, "records": [{"ncm": "12019000"}]},
    )
    client = TestClient(app)
    response = client.get("/comex/ncm?flow=export&year=2026")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_bndes_operations_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        "dadosbr.api.app.fetch_bndes_operations",
        lambda **_kwargs: {"ok": True, "records": [{"cliente": "ACME"}]},
    )
    client = TestClient(app)
    response = client.get("/bndes/operations?cnpj=12345678000190")
    assert response.status_code == 200
    assert response.json()["records"][0]["cliente"] == "ACME"
