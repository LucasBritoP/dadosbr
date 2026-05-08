from pathlib import Path

from dadosbr.connectors import tesouro


def _fixture_bytes(name: str) -> bytes:
    root = Path(__file__).resolve().parents[1] / "fixtures"
    return (root / name).read_bytes()


def test_fetch_tesouro_rates(monkeypatch) -> None:
    package = _fixture_bytes("tesouro_package.json")
    csv_data = _fixture_bytes("tesouro_rates.csv")

    def fake_get(url: str, **_kwargs):
        if "package_show" in url:
            return package, {}
        return csv_data, {}

    monkeypatch.setattr(tesouro, "http_get_bytes", fake_get)
    response = tesouro.fetch_tesouro_rates(limit=10)
    assert response["ok"] is True
    assert len(response["records"]) == 1
    assert response["records"][0]["bond_type"] == "Tesouro Selic 2029"


def test_fetch_tesouro_rates_uses_local_fixture_files(monkeypatch, tmp_path) -> None:
    package_path = tmp_path / "tesouro_package.json"
    csv_path = tmp_path / "tesouro_rates.csv"
    package_path.write_bytes(_fixture_bytes("tesouro_package.json"))
    csv_path.write_bytes(_fixture_bytes("tesouro_rates.csv"))

    monkeypatch.setenv("DADOSBR_TESOURO_PACKAGE_FILE", str(package_path))
    monkeypatch.setenv("DADOSBR_TESOURO_RATES_CSV_FILE", str(csv_path))

    def fail_network(*_args, **_kwargs):
        raise AssertionError("Tesouro fixture mode should not call network")

    monkeypatch.setattr(tesouro, "http_get_bytes", fail_network)
    response = tesouro.fetch_tesouro_rates(limit=10)

    assert response["ok"] is True
    assert response["records"][0]["bond_type"] == "Tesouro Selic 2029"
