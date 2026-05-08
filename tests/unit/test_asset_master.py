from pathlib import Path

from dadosbr.connectors.receita_cnpj import build_cnpj_index


def _sample_b3_quote() -> dict:
    return {
        "ticker": "PETR4",
        "observed_at": "2026-05-05T00:00:00+00:00",
        "market_type": "010",
        "short_name": "PETROBRAS",
        "specification": "PN      N1",
        "currency_ref": "R$",
        "isin": "BRPETRACNPR6",
        "close_price": 30.55,
    }


def _fixture_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "fixtures" / "receita_cnpj"


def test_canonical_instrument_from_b3_quote() -> None:
    from dadosbr.asset_master import canonical_instrument_from_b3_quote

    instrument = canonical_instrument_from_b3_quote(_sample_b3_quote())
    assert instrument["instrument_id"] == "B3:PETR4"
    assert instrument["asset_type"] == "b3_listed_security"
    assert instrument["ticker"] == "PETR4"
    assert instrument["isin"] == "BRPETRACNPR6"
    assert instrument["issuer_name_hint"] == "PETROBRAS"


def test_get_issuer_master_from_cnpj_index(tmp_path) -> None:
    from dadosbr.asset_master import get_issuer_master

    db_path = tmp_path / "cnpj.sqlite"
    assert build_cnpj_index(_fixture_dir(), db_path=db_path)["ok"] is True

    response = get_issuer_master("12345678000190", db_path=db_path)
    assert response["ok"] is True
    issuer = response["records"][0]
    assert issuer["issuer_id"] == "BR_CNPJ:12345678000190"
    assert issuer["legal_name"] == "ACME DADOS LTDA"
    assert issuer["main_cnae"] == "6201501"


def test_get_cnae_taxonomy_from_cnpj_index(tmp_path) -> None:
    from dadosbr.asset_master import get_cnae_taxonomy

    db_path = tmp_path / "cnpj.sqlite"
    assert build_cnpj_index(_fixture_dir(), db_path=db_path)["ok"] is True

    response = get_cnae_taxonomy("6201501", db_path=db_path)
    assert response["ok"] is True
    assert response["records"][0]["code"] == "6201501"
    assert "Desenvolvimento" in response["records"][0]["description"]


def test_build_asset_master_snapshot() -> None:
    from dadosbr.asset_master import build_asset_master_snapshot

    response = build_asset_master_snapshot(
        b3_quotes=[_sample_b3_quote()],
        tesouro_rates=[
            {
                "bond_type": "Tesouro Selic 2029",
                "maturity_date": "2029-03-01",
                "observed_at": "2026-05-05",
            }
        ],
    )
    assert response["ok"] is True
    ids = {record["instrument_id"] for record in response["records"]}
    assert "B3:PETR4" in ids
    assert "TESOURO:TESOURO_SELIC_2029:2029-03-01" in ids
