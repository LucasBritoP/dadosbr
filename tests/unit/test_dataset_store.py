from dadosbr.core.dataset_store import DatasetStore


def test_dataset_store_creates_source_period_paths(tmp_path) -> None:
    store = DatasetStore(tmp_path)
    path = store.dataset_dir("receita_cnpj", "2026-01")
    assert path == tmp_path / "receita_cnpj" / "2026-01"
    assert path.exists()


def test_manifest_round_trip(tmp_path) -> None:
    store = DatasetStore(tmp_path)
    store.write_manifest("comex_stat", "2026", {"files": [{"url": "https://example/EXP_2026.csv"}]})
    manifest = store.read_manifest("comex_stat", "2026")
    assert manifest["files"][0]["url"] == "https://example/EXP_2026.csv"
