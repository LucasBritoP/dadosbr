from dadosbr.core.registry import SOURCES


def test_registry_contains_alpha_sources() -> None:
    expected = {
        "bcb_sgs",
        "bcb_ptax",
        "bcb_focus",
        "cvm_dados_abertos",
        "b3_cotahist",
        "tesouro_transparente",
        "ibge_sidra",
        "ipeadata",
        "receita_cnpj",
        "mdic_comex_stat",
        "bndes_dados_abertos",
        "asset_master",
        "timeseries",
        "benchmarks",
        "fixed_income",
        "fundamentals",
        "corporate_actions",
        "b3_derivatives",
        "anbima_curves",
        "derivatives",
        "interest_curves",
    }
    assert expected.issubset(set(SOURCES))
