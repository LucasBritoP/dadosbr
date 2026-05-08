from pathlib import Path

import pytest

from dadosbr.connectors import ibge, ipea


def _fixture_bytes(name: str) -> bytes:
    root = Path(__file__).resolve().parents[1] / "fixtures"
    return (root / name).read_bytes()


@pytest.fixture(autouse=True)
def _isolate_cache(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DADOSBR_CACHE_DIR", str(tmp_path / "cache"))


def test_fetch_ibge_sidra(monkeypatch) -> None:
    monkeypatch.setattr(ibge, "http_get_bytes", lambda *_a, **_k: (_fixture_bytes("ibge_sidra.json"), {}))
    response = ibge.fetch_ibge_sidra("t/1737/n1/all/v/63/p/202604")
    assert response["ok"] is True
    assert response["records"][0]["value"] == 0.21


def test_fetch_ibge_sidra_quotes_path_spaces(monkeypatch) -> None:
    seen: dict[str, str] = {}

    def fake_http_get_bytes(url: str, **_kwargs):
        seen["url"] = url
        return _fixture_bytes("ibge_sidra.json"), {}

    monkeypatch.setattr(ibge, "http_get_bytes", fake_http_get_bytes)
    response = ibge.fetch_ibge_sidra("t/1737/n1/all/v/63/p/last 3")

    assert response["ok"] is True
    assert " " not in seen["url"]
    assert seen["url"].endswith("/values/t/1737/n1/all/v/63/p/last%203")


def test_fetch_ipea_series(monkeypatch) -> None:
    monkeypatch.setattr(ipea, "http_get_bytes", lambda *_a, **_k: (_fixture_bytes("ipea_series.json"), {}))
    response = ipea.fetch_ipea_series("PRECOS12_IPCA12")
    assert response["ok"] is True
    assert response["records"][0]["value"] == 10.5


def test_fetch_ipea_series_quotes_orderby_space(monkeypatch) -> None:
    seen: dict[str, str] = {}

    def fake_http_get_bytes(url: str, **_kwargs):
        seen["url"] = url
        return _fixture_bytes("ipea_series.json"), {}

    monkeypatch.setattr(ipea, "http_get_bytes", fake_http_get_bytes)
    response = ipea.fetch_ipea_series("BM12_PIB12", top=5)

    assert response["ok"] is True
    assert " " not in seen["url"]
    assert "$orderby=VALDATA%20desc" in seen["url"]
