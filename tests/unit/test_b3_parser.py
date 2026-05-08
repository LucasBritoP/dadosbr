from dadosbr.connectors.b3 import fetch_b3_cotahist, parse_b3_cotahist_bytes


def _sample_cotahist_line() -> bytes:
    line = [" "] * 245
    line[0:2] = list("01")
    line[2:10] = list("20260505")
    line[12:24] = list("PETR4       ")
    line[24:27] = list("010")
    line[27:39] = list("PETROBRAS   ")
    line[39:49] = list("PN      N1")
    line[52:56] = list("R$  ")
    line[56:69] = list("0000000030123")
    line[69:82] = list("0000000031000")
    line[82:95] = list("0000000029900")
    line[95:108] = list("0000000030400")
    line[108:121] = list("0000000030555")
    line[121:134] = list("0000000030500")
    line[134:147] = list("0000000030600")
    line[147:152] = list("00123")
    line[152:170] = list("000000000000000500")
    line[170:188] = list("000000000000123456")
    line[230:242] = list("BRPETRACNPR6")
    line[242:245] = list("123")
    return ("".join(line) + "\n").encode("latin-1")


def test_parse_b3_cotahist_bytes_returns_quote() -> None:
    response = parse_b3_cotahist_bytes(_sample_cotahist_line(), source_url="fixture://cotahist")
    assert response["ok"] is True
    assert response["source_id"] == "b3_cotahist"
    assert len(response["records"]) == 1
    quote = response["records"][0]
    assert quote["ticker"] == "PETR4"
    assert quote["open_price"] == 301.23
    assert quote["high_price"] == 310.0
    assert quote["low_price"] == 299.0
    assert quote["average_price"] == 304.0
    assert quote["close_price"] == 305.55
    assert quote["best_bid_price"] == 305.0
    assert quote["best_ask_price"] == 306.0
    assert quote["market_type"] == "010"
    assert quote["short_name"] == "PETROBRAS"
    assert quote["specification"] == "PN      N1"
    assert quote["currency_ref"] == "R$"
    assert quote["isin"] == "BRPETRACNPR6"
    assert quote["quantity_traded"] == 500
    assert quote["financial_volume"] == 1234.56


def test_fetch_b3_cotahist_uses_local_fixture_file(monkeypatch, tmp_path) -> None:
    fixture_path = tmp_path / "COTAHIST_SMOKE.TXT"
    fixture_path.write_bytes(_sample_cotahist_line())

    monkeypatch.setenv("DADOSBR_B3_COTAHIST_FILE", str(fixture_path))

    response = fetch_b3_cotahist(year=2025, ticker="PETR4", limit=1)

    assert response["ok"] is True
    assert response["source_mode"] == "local_snapshot"
    assert response["resilience"]["local_file"] == str(fixture_path)
    assert response["records"][0]["ticker"] == "PETR4"
