from __future__ import annotations

from fastapi.testclient import TestClient

import dadosbr.api.app as api_app


def test_local_file_endpoint_blocks_paths_by_default(monkeypatch, tmp_path) -> None:
    marker = tmp_path / "derivatives.csv"
    marker.write_text("symbol\nDI1F27\n", encoding="utf-8")

    def fail_if_called(**_kwargs):
        raise AssertionError("local parser should not be called when local file access is disabled")

    monkeypatch.delenv("DADOSBR_ENABLE_LOCAL_FILE_ENDPOINTS", raising=False)
    monkeypatch.setattr(api_app, "get_derivative_futures_from_file", fail_if_called)
    client = TestClient(api_app.app)

    response = client.get("/derivatives/futures", params={"file_path": str(marker)})

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "local_file_access_disabled"


def test_local_file_endpoint_allows_paths_inside_configured_root(monkeypatch, tmp_path) -> None:
    marker = tmp_path / "derivatives.csv"
    marker.write_text("symbol\nDI1F27\n", encoding="utf-8")

    def fake_parse(**kwargs):
        assert kwargs["file_path"] == str(marker.resolve())
        return {"ok": True, "records": [{"symbol": "DI1F27"}]}

    monkeypatch.setenv("DADOSBR_ENABLE_LOCAL_FILE_ENDPOINTS", "1")
    monkeypatch.setenv("DADOSBR_LOCAL_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(api_app, "get_derivative_futures_from_file", fake_parse)
    client = TestClient(api_app.app)

    response = client.get("/derivatives/futures", params={"file_path": str(marker)})

    assert response.status_code == 200
    assert response.json()["records"][0]["symbol"] == "DI1F27"


def test_local_file_endpoint_rejects_paths_outside_configured_root(monkeypatch, tmp_path) -> None:
    root = tmp_path / "allowed"
    outside = tmp_path / "outside.csv"
    root.mkdir()
    outside.write_text("symbol\nDI1F27\n", encoding="utf-8")

    monkeypatch.setenv("DADOSBR_ENABLE_LOCAL_FILE_ENDPOINTS", "1")
    monkeypatch.setenv("DADOSBR_LOCAL_DATA_DIR", str(root))
    client = TestClient(api_app.app)

    response = client.get("/derivatives/futures", params={"file_path": str(outside)})

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "local_file_outside_allowed_root"


def test_admin_sync_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("DADOSBR_ENABLE_ADMIN_HTTP", raising=False)
    client = TestClient(api_app.app)

    response = client.post("/admin/cnpj/sync")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "admin_http_disabled"


def test_admin_sync_requires_configured_token(monkeypatch) -> None:
    monkeypatch.setenv("DADOSBR_ENABLE_ADMIN_HTTP", "1")
    monkeypatch.setenv("DADOSBR_ADMIN_TOKEN", "secret-token")
    client = TestClient(api_app.app)

    response = client.post("/admin/cnpj/sync")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "admin_token_invalid"


def test_admin_sync_requires_token_configuration_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("DADOSBR_ENABLE_ADMIN_HTTP", "1")
    monkeypatch.delenv("DADOSBR_ADMIN_TOKEN", raising=False)
    client = TestClient(api_app.app)

    response = client.post("/admin/cnpj/sync")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "admin_token_required"


def test_admin_sync_allows_valid_token(monkeypatch, tmp_path) -> None:
    downloaded = tmp_path / "Empresas0.zip"
    downloaded.write_bytes(b"zip")

    monkeypatch.setenv("DADOSBR_ENABLE_ADMIN_HTTP", "1")
    monkeypatch.setenv("DADOSBR_ADMIN_TOKEN", "secret-token")
    monkeypatch.setattr(
        api_app,
        "download_cnpj_period",
        lambda **_kwargs: {"ok": True, "records": [{"path": str(downloaded)}]},
    )
    monkeypatch.setattr(
        api_app,
        "build_cnpj_index",
        lambda *_args, **_kwargs: {"ok": True, "records": [{"inserted": 1}]},
    )
    client = TestClient(api_app.app)

    response = client.post("/admin/cnpj/sync", headers={"X-DadosBR-Admin-Token": "secret-token"})

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_b3_upload_rejects_oversized_body_before_parser(monkeypatch) -> None:
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("parser should not be called for oversized uploads")

    monkeypatch.setenv("DADOSBR_MAX_UPLOAD_BYTES", "4")
    monkeypatch.setattr(api_app, "parse_b3_cotahist_bytes", fail_if_called)
    client = TestClient(api_app.app)

    response = client.post(
        "/b3/cotahist/parse",
        files={"file": ("cotahist.txt", b"12345", "text/plain")},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "upload_too_large"
    assert response.json()["detail"]["details"]["size_bytes"] == 5


def test_derivatives_upload_rejects_oversized_body_before_parser(monkeypatch) -> None:
    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("parser should not be called for oversized uploads")

    monkeypatch.setenv("DADOSBR_MAX_UPLOAD_BYTES", "4")
    monkeypatch.setattr(api_app, "parse_derivatives_csv_bytes", fail_if_called)
    client = TestClient(api_app.app)

    response = client.post(
        "/derivatives/futures/parse",
        files={"file": ("derivatives.csv", b"12345", "text/csv")},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "upload_too_large"
    assert response.json()["detail"]["details"]["size_bytes"] == 5
