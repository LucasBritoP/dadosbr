from pathlib import Path

from dadosbr.connectors import bcb


def _fixture(name: str) -> bytes:
    root = Path(__file__).resolve().parents[1] / "fixtures"
    return (root / name).read_bytes()


def test_fetch_sgs_series(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DADOSBR_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(bcb, "http_get_bytes", lambda *_a, **_k: (_fixture("bcb_sgs.json"), {}))
    response = bcb.fetch_sgs_series("432", last=2)
    assert response["ok"] is True
    assert response["source_mode"] == "live"
    assert response["resilience"]["cache_status"] == "miss"
    assert response["records"][0]["series_id"] == "432"


def test_fetch_ptax(monkeypatch) -> None:
    monkeypatch.setattr(bcb, "http_get_bytes", lambda *_a, **_k: (_fixture("bcb_ptax.json"), {}))
    response = bcb.fetch_ptax(target_date="2026-05-05")
    assert response["ok"] is True
    assert response["records"][0]["buy_rate"] == 5.12


def test_fetch_focus(monkeypatch) -> None:
    monkeypatch.setattr(bcb, "http_get_bytes", lambda *_a, **_k: (_fixture("bcb_focus.json"), {}))
    response = bcb.fetch_focus_expectations(indicator="IPCA", top=1)
    assert response["ok"] is True
    assert response["records"][0]["indicator"] == "IPCA"
    assert response["raw_sha256"]
