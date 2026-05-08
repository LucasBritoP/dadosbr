import json
from pathlib import Path

from dadosbr.connectors.bndes import (
    fetch_bndes_operations,
    fetch_bndes_variable_income,
    list_bndes_datasets,
)


def _fixture(name: str) -> bytes:
    root = Path(__file__).resolve().parents[1] / "fixtures" / "bndes"
    return (root / name).read_bytes()


def fake_bndes_get(url: str, **_kwargs):
    if "package_show" in url and "operacoes-financiamento" in url:
        return _fixture("package_operacoes_financiamento.json"), {}
    if "package_show" in url and "renda-variavel" in url:
        return _fixture("package_renda_variavel.json"), {}
    if "package_search" in url:
        body = json.dumps(
            {
                "success": True,
                "result": {
                    "results": [
                        {"id": "abc", "name": "operacoes-financiamento", "title": "Operacoes", "license_title": "ODbL", "metadata_modified": "2026-05-05T00:00:00"},
                    ]
                },
            }
        ).encode("utf-8")
        return body, {}
    if url.endswith("/operacoes.csv"):
        return _fixture("operacoes.csv"), {}
    if url.endswith("/debentures.csv"):
        return _fixture("debentures.csv"), {}
    if url.endswith("/fundos.csv"):
        return _fixture("fundos.csv"), {}
    raise AssertionError(f"Unexpected URL in test: {url}")


def _isolate_cache(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DADOSBR_CACHE_DIR", str(tmp_path / "cache"))


def test_fetch_bndes_operations_filters_by_cnpj(monkeypatch, tmp_path) -> None:
    _isolate_cache(monkeypatch, tmp_path)
    monkeypatch.setattr("dadosbr.connectors.bndes.http_get_bytes", fake_bndes_get)
    result = fetch_bndes_operations(cnpj="12345678000190", limit=10)
    assert result["ok"] is True
    assert result["records"][0]["cliente"] == "ACME DADOS LTDA"


def test_fetch_bndes_variable_income_debentures(monkeypatch, tmp_path) -> None:
    _isolate_cache(monkeypatch, tmp_path)
    monkeypatch.setattr("dadosbr.connectors.bndes.http_get_bytes", fake_bndes_get)
    result = fetch_bndes_variable_income(kind="debentures", company="ACME", limit=10)
    assert result["ok"] is True
    assert result["records"][0]["kind"] == "debentures"


def test_fetch_bndes_variable_income_selects_debentures_by_normalized_url(monkeypatch, tmp_path) -> None:
    _isolate_cache(monkeypatch, tmp_path)
    package_body = json.dumps(
        {
            "success": True,
            "result": {
                "resources": [
                    {
                        "id": "fund-id",
                        "name": "Fundos de Investimentos - Historico da Carteira",
                        "format": "CSV",
                        "url": "https://example.test/renda-variavel-fundos-de-investimentos-historico-da-carteira.csv",
                    },
                    {
                        "id": "deb-id",
                        "name": "Debentures - Historico da Carteira",
                        "format": "CSV",
                        "url": "https://example.test/renda-variavel-debentures-historico-da-carteira.csv",
                    },
                ]
            },
        }
    ).encode("utf-8")
    debentures_csv = (
        "sigla;razao_social;cnpj;tipo_de_ativo;ano;setor_de_atividade;quantidade_final\n"
        "ABCD11;ACME ENERGIA S.A.;12.345.678/0001-90;DEBENTURES;2025;ENERGIA;1000\n"
    ).encode("windows-1252")
    funds_csv = (
        "sigla;razao_social;cnpj;tipo_de_ativo;ano;setor_de_atividade;participacao_pp_final\n"
        "FD TESTE;FUNDO TESTE;11.111.111/0001-11;COTAS DE FUNDO;2025;N/A;25,0\n"
    ).encode("windows-1252")

    def fake_get(url: str, **_kwargs):
        if "package_show" in url:
            return package_body, {}
        if url.endswith("debentures-historico-da-carteira.csv"):
            return debentures_csv, {}
        if url.endswith("fundos-de-investimentos-historico-da-carteira.csv"):
            return funds_csv, {}
        raise AssertionError(f"Unexpected URL in test: {url}")

    monkeypatch.setattr("dadosbr.connectors.bndes.http_get_bytes", fake_get)

    result = fetch_bndes_variable_income(kind="debentures", limit=10)

    assert result["ok"] is True
    assert len(result["records"]) == 1
    record = result["records"][0]
    assert record["kind"] == "debentures"
    assert record["company"] == "ACME ENERGIA S.A."
    assert record["issuer_name"] == "ACME ENERGIA S.A."
    assert record["quantity_final"] == 1000.0
    assert "fundos-de-investimentos" not in result["source_url"]


def test_fetch_bndes_variable_income_normalizes_current_fund_fields(monkeypatch, tmp_path) -> None:
    _isolate_cache(monkeypatch, tmp_path)
    package_body = json.dumps(
        {
            "success": True,
            "result": {
                "resources": [
                    {
                        "id": "fund-id",
                        "name": "Fundos de Investimentos - Historico da Carteira",
                        "format": "CSV",
                        "url": "https://example.test/renda-variavel-fundos-de-investimentos-historico-da-carteira.csv",
                    }
                ]
            },
        }
    ).encode("utf-8")
    funds_csv = (
        "sigla;razao_social;cnpj;tipo_de_ativo;ano;setor_de_atividade;participacao_pp_final\n"
        "FD ABF FIP;AMAZON BIODIVERSITY FUND BRAZIL FUNDO DE INVESTIMENTO E;"
        "34.525.886/0001-09;COTAS DE FUNDO;2025;N/A;25,0\n"
    ).encode("windows-1252")

    def fake_get(url: str, **_kwargs):
        if "package_show" in url:
            return package_body, {}
        if url.endswith("fundos-de-investimentos-historico-da-carteira.csv"):
            return funds_csv, {}
        raise AssertionError(f"Unexpected URL in test: {url}")

    monkeypatch.setattr("dadosbr.connectors.bndes.http_get_bytes", fake_get)

    result = fetch_bndes_variable_income(kind="funds", limit=10)

    assert result["ok"] is True
    record = result["records"][0]
    assert record["fund_name"] == "AMAZON BIODIVERSITY FUND BRAZIL FUNDO DE INVESTIMENTO E"
    assert record["participacao_total"] == 25.0
    assert record["asset_type"] == "COTAS DE FUNDO"


def test_list_bndes_datasets(monkeypatch, tmp_path) -> None:
    _isolate_cache(monkeypatch, tmp_path)
    monkeypatch.setattr("dadosbr.connectors.bndes.http_get_bytes", fake_bndes_get)
    result = list_bndes_datasets(query="operacoes", rows=10)
    assert result["ok"] is True
    assert result["records"][0]["name"] == "operacoes-financiamento"
