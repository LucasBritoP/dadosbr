from pathlib import Path

from dadosbr.connectors import comex
from dadosbr.connectors.comex import (
    fetch_comex_municipality,
    fetch_comex_ncm,
    fetch_comex_table,
    summarize_comex_ncm,
)


def _fixture(name: str) -> bytes:
    root = Path(__file__).resolve().parents[1] / "fixtures" / "comex"
    return (root / name).read_bytes()


def fake_fixture_fetch(url: str) -> bytes:
    if "ncm/EXP_2026.csv" in url:
        return _fixture("EXP_2026.csv")
    if "ncm/IMP_2026.csv" in url:
        return _fixture("IMP_2026.csv")
    if "mun/EXP_2026_MUN.csv" in url:
        return _fixture("EXP_2026_MUN.csv")
    if "/tabelas/NCM.csv" in url:
        return _fixture("NCM.csv")
    raise AssertionError(f"Unexpected URL in test: {url}")


def fake_fixture_fetch_with_metadata(url: str) -> tuple[bytes, str, dict, list[str]]:
    return fake_fixture_fetch(url), "live", {}, []


def test_filter_comex_ncm_from_fixture(monkeypatch) -> None:
    monkeypatch.setattr("dadosbr.connectors.comex._fetch_csv_bytes_with_metadata", fake_fixture_fetch_with_metadata)
    result = fetch_comex_ncm(flow="export", year=2026, ncm="12019000", uf="SP", limit=10)
    assert result["ok"] is True
    assert len(result["records"]) == 2


def test_summarize_comex_by_month(monkeypatch) -> None:
    monkeypatch.setattr("dadosbr.connectors.comex._fetch_csv_bytes_with_metadata", fake_fixture_fetch_with_metadata)
    result = summarize_comex_ncm(flow="export", year=2026, group_by="month", ncm="12019000")
    assert result["ok"] is True
    assert result["records"][0]["vl_fob"] == 50000
    assert result["records"][1]["vl_fob"] == 90000


def test_fetch_comex_municipality(monkeypatch) -> None:
    monkeypatch.setattr("dadosbr.connectors.comex._fetch_csv_bytes_with_metadata", fake_fixture_fetch_with_metadata)
    result = fetch_comex_municipality(flow="export", year=2026, uf="SP", municipality_code="3550308", sh4="1201")
    assert result["ok"] is True
    assert result["records"][0]["municipality_code"] == "3550308"


def test_fetch_comex_table(monkeypatch) -> None:
    monkeypatch.setattr("dadosbr.connectors.comex._fetch_csv_bytes_with_metadata", fake_fixture_fetch_with_metadata)
    result = fetch_comex_table(table_name="NCM")
    assert result["ok"] is True
    assert result["records"][0]["CO_NCM"] == "12019000"


def test_fetch_comex_table_uses_local_data_dir(monkeypatch, tmp_path) -> None:
    data_dir = tmp_path / "comex"
    table_dir = data_dir / "tabelas"
    table_dir.mkdir(parents=True)
    (table_dir / "NCM.csv").write_bytes(_fixture("NCM.csv"))

    def fail_network(*_args, **_kwargs):
        raise AssertionError("Comex local data dir should not call network")

    monkeypatch.setenv("DADOSBR_COMEX_DATA_DIR", str(data_dir))
    monkeypatch.setattr(comex, "http_get_bytes", fail_network)
    result = fetch_comex_table(table_name="NCM")

    assert result["ok"] is True
    assert result["records"][0]["CO_NCM"] == "12019000"


def test_fetch_csv_bytes_allows_md_ic_ssl_fallback(monkeypatch) -> None:
    seen: dict[str, bool | None] = {}

    def fake_cached(_url: str, **kwargs):
        seen["verify_ssl"] = kwargs.get("verify_ssl")
        return _fixture("NCM.csv"), {}

    monkeypatch.delenv("DADOSBR_COMEX_DATA_DIR", raising=False)
    monkeypatch.setenv("DADOSBR_COMEX_VERIFY_SSL", "0")
    monkeypatch.setattr(comex, "http_get_bytes_cached", fake_cached)

    raw = comex._fetch_csv_bytes("https://balanca.economia.gov.br/balanca/bd/tabelas/NCM.csv")

    assert raw.startswith(b"CO_NCM")
    assert seen["verify_ssl"] is False
