import inspect
from pathlib import Path

from dadosbr.connectors import receita_cnpj
from dadosbr.connectors.receita_cnpj import (
    _filter_zip_names,
    _table_from_filename,
    build_cnpj_index,
    discover_latest_cnpj_period,
    get_cnpj_company,
    get_cnpj_partners,
    search_cnpj_companies,
)
from dadosbr.core import DataSourceError


def test_build_and_query_cnpj_index(tmp_path) -> None:
    db_path = tmp_path / "cnpj.sqlite"
    fixture_dir = Path(__file__).resolve().parents[1] / "fixtures" / "receita_cnpj"

    build_result = build_cnpj_index(fixture_dir, db_path=db_path)
    assert build_result["ok"] is True

    company = get_cnpj_company("12345678000190", db_path=db_path)
    assert company["ok"] is True
    assert company["records"][0]["cnpj"] == "12345678000190"
    assert company["records"][0]["razao_social"] == "ACME DADOS LTDA"

    partners = get_cnpj_partners("12345678000190", db_path=db_path)
    assert partners["ok"] is True
    assert partners["records"][0]["nome_socio"] == "SOCIO TESTE"

    results = search_cnpj_companies(q="ACME", uf="SP", cnae="6201501", db_path=db_path)
    assert results["ok"] is True
    assert results["records"][0]["cnpj"] == "12345678000190"


def test_receita_zip_matching_is_case_insensitive_and_url_safe() -> None:
    hrefs = [
        "Empresas0.ZIP",
        "subdir/Estabelecimentos0.zip",
        "Socios0.zip?download=1",
        "Simples.zip",
        "Cnaes.zip",
        "readme.txt",
    ]

    assert _filter_zip_names(hrefs, ["empresas", "estabelecimentos", "socios"]) == [
        "Empresas0.ZIP",
        "Estabelecimentos0.zip",
        "Socios0.zip",
    ]


def test_receita_table_detection_accepts_common_rfb_zip_names() -> None:
    assert _table_from_filename("Empresas0.ZIP") == "empresas"
    assert _table_from_filename("Estabelecimentos0.zip") == "estabelecimentos"
    assert _table_from_filename("Socios0.zip") == "socios"
    assert _table_from_filename("Simples.zip") == "simples"
    assert _table_from_filename("Municipios.zip") == "municipios"


def test_discover_latest_cnpj_period_uses_configured_fallback_base(monkeypatch, tmp_path) -> None:
    fallback_base = "https://mirror.example/arquivos/"

    def fake_http_get_bytes(url, **_kwargs):
        if url == receita_cnpj.DEFAULT_BASE_URL:
            raise DataSourceError("http_error", "official unavailable", receita_cnpj.SOURCE_ID, source_url=url)
        if url == fallback_base:
            return b'<a href="2026-03-16/">2026-03-16/</a><a href="2026-04-12/">2026-04-12/</a>', {}
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setenv("DADOSBR_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DADOSBR_RECEITA_CNPJ_FALLBACK_BASE_URLS", fallback_base)
    monkeypatch.setattr(receita_cnpj, "http_get_bytes", fake_http_get_bytes)

    response = discover_latest_cnpj_period()

    assert response["ok"] is True
    assert response["source_mode"] == "fallback_source"
    assert response["resilience"]["fallback_source"] is True
    assert response["source_url"] == fallback_base
    assert response["records"][0]["period"] == "2026-04-12"
    assert response["records"][0]["base_url"] == fallback_base


def test_download_cnpj_period_streams_zip_to_dataset_store(monkeypatch, tmp_path) -> None:
    period_url = "https://rfb.example/2026-04/"
    downloaded: list[tuple[str, Path]] = []

    def fake_fetch_page(url, **_kwargs):
        assert url == period_url
        return b'<a href="Empresas0.zip">Empresas0.zip</a>', {}

    def fake_download_to_file(url, output_path, **_kwargs):
        downloaded.append((url, Path(output_path)))
        Path(output_path).write_bytes(b"zip-content")
        return 11, {"content-type": "application/zip"}

    monkeypatch.setenv("DADOSBR_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(receita_cnpj, "_base_urls", lambda: ["https://rfb.example/"])
    monkeypatch.setattr(receita_cnpj, "http_get_bytes", fake_fetch_page)
    monkeypatch.setattr(receita_cnpj, "http_download_to_file", fake_download_to_file)

    response = receita_cnpj.download_cnpj_period(
        period="2026-04",
        groups="empresas",
        max_files=1,
        store=tmp_path / "datasets",
    )

    assert response["ok"] is True
    assert downloaded[0][0] == "https://rfb.example/2026-04/Empresas0.zip"
    assert downloaded[0][1].exists()
    assert response["records"][0]["size_bytes"] == 11
    assert response["records"][0]["path"] == str(downloaded[0][1])


def test_cnpj_index_loader_uses_streaming_text_wrapper() -> None:
    source = inspect.getsource(receita_cnpj._load_zip_into_db)

    assert "TextIOWrapper" in source
    assert ".read().decode" not in source
    assert ".splitlines()" not in source
