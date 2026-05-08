import io
import zipfile

import pytest

from dadosbr.connectors import cvm
from dadosbr.core import DataSourceError


def _zip_with_csv(member_name: str, csv_text: str) -> bytes:
    buff = io.BytesIO()
    with zipfile.ZipFile(buff, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(member_name, csv_text)
    return buff.getvalue()


@pytest.fixture(autouse=True)
def _isolate_cache(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DADOSBR_CACHE_DIR", str(tmp_path / "cache"))


def test_fetch_cvm_company_reports(monkeypatch) -> None:
    summary_csv = (
        "CD_CVM;DENOM_CIA;CNPJ_CIA;DT_REFER;VERSAO\n"
        "9512;ACME SA;00.000.000/0001-00;2026-03-31;1\n"
    )
    zip_body = _zip_with_csv("dfp_cia_aberta_2026.csv", summary_csv)
    monkeypatch.setattr(cvm, "http_get_bytes", lambda *_a, **_k: (zip_body, {}))
    response = cvm.fetch_cvm_company_reports(year=2026, doc_type="dfp", limit=10)
    assert response["ok"] is True
    assert response["records"][0]["cvm_code"] == "9512"


def test_fetch_cvm_company_reports_uses_api_friendly_timeout(monkeypatch) -> None:
    seen: dict[str, int | None] = {}

    def fake_http_get_bytes(*_args, **kwargs):
        seen["timeout"] = kwargs.get("timeout_seconds")
        raise DataSourceError(
            "network_error",
            "simulated timeout",
            cvm.SOURCE_ID,
            retryable=True,
        )

    monkeypatch.setenv("DADOSBR_DISABLE_HTTP_CACHE", "1")
    monkeypatch.setattr(cvm, "http_get_bytes", fake_http_get_bytes)
    response = cvm.fetch_cvm_company_reports(year=2025, doc_type="dfp", limit=1)

    assert response["ok"] is False
    assert seen["timeout"] is not None
    assert seen["timeout"] <= 15


def test_fetch_cvm_company_reports_streams_company_csv_rows(monkeypatch) -> None:
    summary_csv = (
        "CD_CVM;DENOM_CIA;CNPJ_CIA;DT_REFER;VERSAO\n"
        "9512;ACME SA;00.000.000/0001-00;2026-03-31;1\n"
    )
    zip_body = _zip_with_csv("dfp_cia_aberta_2026.csv", summary_csv)
    monkeypatch.setenv("DADOSBR_DISABLE_HTTP_CACHE", "1")
    monkeypatch.setattr(cvm, "http_get_bytes", lambda *_a, **_k: (zip_body, {}))

    def fail_full_csv_read(*_args, **_kwargs):
        raise AssertionError("company report parser should stream rows before filtering")

    monkeypatch.setattr(cvm, "_read_csv_rows", fail_full_csv_read)
    response = cvm.fetch_cvm_company_reports(year=2026, doc_type="dfp", cvm_code="9512", limit=1)

    assert response["ok"] is True
    assert response["records"][0]["cvm_code"] == "9512"


def test_fetch_cvm_company_reports_filters_cvm_code_before_normalizing(monkeypatch) -> None:
    summary_csv = (
        "CD_CVM;DENOM_CIA;CNPJ_CIA;DT_REFER;VERSAO\n"
        "1111;OTHER SA;00.000.000/0001-00;2026-03-31;1\n"
        "009512;ACME SA;00.000.000/0001-00;2026-03-31;1\n"
    )
    zip_body = _zip_with_csv("dfp_cia_aberta_2026.csv", summary_csv)
    monkeypatch.setenv("DADOSBR_DISABLE_HTTP_CACHE", "1")
    monkeypatch.setattr(cvm, "http_get_bytes", lambda *_a, **_k: (zip_body, {}))
    original_normalize = cvm._normalize_company_row
    normalized_codes: list[str] = []

    def track_normalize(row, doc_type, member):
        normalized_codes.append(str(row.get("CD_CVM", "")))
        return original_normalize(row, doc_type, member)

    monkeypatch.setattr(cvm, "_normalize_company_row", track_normalize)
    response = cvm.fetch_cvm_company_reports(year=2026, doc_type="dfp", cvm_code="9512", limit=1)

    assert response["ok"] is True
    assert normalized_codes == ["009512"]


def test_cvm_csv_reader_accepts_large_fields() -> None:
    large_value = "x" * 200_000
    zip_body = _zip_with_csv("cda_fi_BLC_1_202605.csv", f"CNPJ_FUNDO;DS_ATIVO\n00.000.000/0001-00;{large_value}\n")

    with zipfile.ZipFile(io.BytesIO(zip_body)) as zf:
        rows = list(cvm._iter_csv_rows(zf, "cda_fi_BLC_1_202605.csv"))

    assert rows[0]["DS_ATIVO"] == large_value


def test_cvm_code_aliases_cover_metadata_layouts() -> None:
    assert cvm._row_cvm_code({"COD_CVM": "9512"}) == "9512"
    assert cvm._row_cvm_code({"CD_CVM_EMISSOR": "9512"}) == "9512"
    assert cvm._row_cvm_code({"Codigo_CVM": "009512"}) == "009512"


def test_company_metadata_rows_normalize_cvm_ipe_layout() -> None:
    row = {
        "CNPJ_Companhia": "33.000.167/0001-01",
        "Nome_Companhia": "PETROLEO BRASILEIRO S.A. PETROBRAS",
        "Codigo_CVM": "009512",
        "Data_Referencia": "2024-02-26",
        "Categoria": "Comunicado ao Mercado",
        "Assunto": "Teste",
    }

    normalized = cvm._normalize_company_row(row, "ipe", "ipe_cia_aberta_2024.csv")

    assert normalized["cvm_code"] == "9512"
    assert normalized["cvm_code_raw"] == "009512"
    assert normalized["company_name"] == "PETROLEO BRASILEIRO S.A. PETROBRAS"
    assert normalized["cnpj"] == "33.000.167/0001-01"
    assert normalized["observed_at"] == "2024-02-26"
    assert normalized["document_category"] == "Comunicado ao Mercado"
    assert normalized["subject"] == "Teste"


def test_fetch_cvm_company_reports_reuses_cached_zip(monkeypatch, tmp_path) -> None:
    summary_csv = (
        "CD_CVM;DENOM_CIA;CNPJ_CIA;DT_REFER;VERSAO\n"
        "9512;ACME SA;00.000.000/0001-00;2026-03-31;1\n"
    )
    zip_body = _zip_with_csv("dfp_cia_aberta_2026.csv", summary_csv)
    calls = {"count": 0}

    def fake_http_get_bytes(*_args, **_kwargs):
        calls["count"] += 1
        return zip_body, {}

    monkeypatch.setenv("DADOSBR_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(cvm, "http_get_bytes", fake_http_get_bytes)

    first = cvm.fetch_cvm_company_reports(year=2026, doc_type="dfp", cvm_code="9512", limit=1)
    second = cvm.fetch_cvm_company_reports(year=2026, doc_type="dfp", cvm_code="9512", limit=1)

    assert first["ok"] is True
    assert second["ok"] is True
    assert calls["count"] == 1


def test_fetch_cvm_company_reports_reuses_parsed_response_cache(monkeypatch, tmp_path) -> None:
    summary_csv = (
        "CD_CVM;DENOM_CIA;CNPJ_CIA;DT_REFER;VERSAO\n"
        "9512;ACME SA;00.000.000/0001-00;2026-03-31;1\n"
    )
    zip_body = _zip_with_csv("dfp_cia_aberta_2026.csv", summary_csv)
    monkeypatch.setenv("DADOSBR_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(cvm, "http_get_bytes", lambda *_a, **_k: (zip_body, {}))

    first = cvm.fetch_cvm_company_reports(year=2026, doc_type="dfp", cvm_code="9512", limit=1)
    assert first["ok"] is True

    def fail_parser(*_args, **_kwargs):
        raise AssertionError("parsed response cache should avoid parsing the ZIP again")

    monkeypatch.setattr(cvm, "_iter_csv_rows", fail_parser)
    second = cvm.fetch_cvm_company_reports(year=2026, doc_type="dfp", cvm_code="9512", limit=1)

    assert second["ok"] is True
    assert second["records"][0]["cvm_code"] == "9512"


def test_fetch_cvm_fund_daily(monkeypatch) -> None:
    csv_text = (
        "CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;NR_COTST\n"
        "00.000.000/0001-00;2026-05-05;1000,10;10,01;900,09;10\n"
    )
    zip_body = _zip_with_csv("inf_diario_fi_202605.csv", csv_text)
    monkeypatch.setattr(cvm, "http_get_bytes", lambda *_a, **_k: (zip_body, {}))
    response = cvm.fetch_cvm_fund_daily(cnpj="00000000000100", date="2026-05", limit=10)
    assert response["ok"] is True
    assert response["records"][0]["quota_value"] == 10.01


def test_fetch_cvm_fund_portfolio(monkeypatch) -> None:
    csv_text = (
        "CNPJ_FUNDO;DT_COMPTC;DENOM_SOCIAL;TP_ATIVO;CD_ATIVO;NM_EMISSOR;VL_MERC_POS_FINAL\n"
        "00.000.000/0001-00;2026-05-05;FUND X;DEBENTURE;DEB123;EMISSOR Y;123,45\n"
    )
    zip_body = _zip_with_csv("cda_fi_BLC_1_202605.csv", csv_text)
    monkeypatch.setattr(cvm, "http_get_bytes", lambda *_a, **_k: (zip_body, {}))
    response = cvm.fetch_cvm_fund_portfolio(cnpj="00000000000100", date="2026-05", limit=10)
    assert response["ok"] is True
    assert response["records"][0]["asset_code"] == "DEB123"


def test_fetch_cvm_fii_monthly(monkeypatch) -> None:
    csv_text = (
        "CNPJ_FUNDO;DENOM_SOCIAL;DT_COMPTC;VL_PATRIM_LIQ;VL_QUOTA;NR_COTST;CAPTC_DIA;RESG_DIA\n"
        "00.000.000/0001-00;FII X;2026-05-31;10000,00;101,10;200;10,00;5,00\n"
    )
    zip_body = _zip_with_csv("inf_mensal_fii_2026.csv", csv_text)
    monkeypatch.setattr(cvm, "http_get_bytes", lambda *_a, **_k: (zip_body, {}))
    response = cvm.fetch_cvm_fii_monthly(cnpj="00000000000100", year=2026, month=5, limit=10)
    assert response["ok"] is True
    assert response["records"][0]["valor_cota"] == 101.1


def test_fetch_cvm_fii_monthly_accepts_current_split_layout(monkeypatch) -> None:
    geral_csv = (
        "CNPJ_Fundo_Classe;Nome_Fundo_Classe;Data_Referencia;Codigo_ISIN;Segmento_Atuacao;Tipo_Gestao\n"
        "00.000.000/0001-00;FII NOVO;2026-05-31;BRFIINOVO001;Lajes Corporativas;Ativa\n"
    )
    complemento_csv = (
        "CNPJ_Fundo_Classe;Data_Referencia;Patrimonio_Liquido;Valor_Patrimonial_Cotas;"
        "Total_Numero_Cotistas;Quantidade_Cotas_Emitidas;Percentual_Dividend_Yield_Mes\n"
        "00.000.000/0001-00;2026-05-31;10000,00;101,10;200;99;0,75\n"
    )
    buff = io.BytesIO()
    with zipfile.ZipFile(buff, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("inf_mensal_fii_geral_2026.csv", geral_csv)
        zf.writestr("inf_mensal_fii_complemento_2026.csv", complemento_csv)
    monkeypatch.setattr(cvm, "http_get_bytes", lambda *_a, **_k: (buff.getvalue(), {}))

    response = cvm.fetch_cvm_fii_monthly(cnpj="00000000000100", year=2026, month=5, limit=10)

    assert response["ok"] is True
    record = response["records"][0]
    assert record["cnpj"] == "00.000.000/0001-00"
    assert record["fund_name"] == "FII NOVO"
    assert record["observed_at"] == "2026-05-31"
    assert record["valor_cota"] == 101.1
    assert record["patrimonio_liquido"] == 10000.0
    assert record["cotistas"] == 200
    assert record["isin"] == "BRFIINOVO001"
    assert record["dividend_yield_month"] == 0.75
