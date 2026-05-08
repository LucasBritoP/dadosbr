from __future__ import annotations

import json
import time
from datetime import date

import dadosbr.fundamentals as fundamentals
from dadosbr.fundamentals import (
    build_company_identity,
    build_fundamental_snapshot,
    calculate_fundamental_metrics,
    calculate_ttm,
    canonical_statement_line,
    compare_fundamental_snapshots,
    get_company_dividends,
    normalize_yfinance_dividends,
)


def _sample_statement_rows() -> list[dict]:
    return [
        {
            "doc_type": "dfp",
            "company_name": "Companhia ABCD",
            "cvm_code": "12345",
            "cnpj": "12.345.678/0001-90",
            "observed_at": "2026-12-31",
            "account_code": "3.01",
            "account_name": "Receita de Venda de Bens e/ou Serviços",
            "value": 1000.0,
        },
        {
            "doc_type": "dfp",
            "company_name": "Companhia ABCD",
            "cvm_code": "12345",
            "cnpj": "12.345.678/0001-90",
            "observed_at": "2026-12-31",
            "account_code": "3.03",
            "account_name": "Resultado Bruto",
            "value": 400.0,
        },
        {
            "doc_type": "dfp",
            "company_name": "Companhia ABCD",
            "cvm_code": "12345",
            "cnpj": "12.345.678/0001-90",
            "observed_at": "2026-12-31",
            "account_code": "3.05",
            "account_name": "Resultado Antes do Resultado Financeiro e dos Tributos",
            "value": 250.0,
        },
        {
            "doc_type": "dfp",
            "company_name": "Companhia ABCD",
            "cvm_code": "12345",
            "cnpj": "12.345.678/0001-90",
            "observed_at": "2026-12-31",
            "account_code": "3.11",
            "account_name": "Lucro/Prejuízo Consolidado do Período",
            "value": 120.0,
        },
        {
            "doc_type": "dfp",
            "company_name": "Companhia ABCD",
            "cvm_code": "12345",
            "cnpj": "12.345.678/0001-90",
            "observed_at": "2026-12-31",
            "account_code": "1",
            "account_name": "Ativo Total",
            "value": 2000.0,
        },
        {
            "doc_type": "dfp",
            "company_name": "Companhia ABCD",
            "cvm_code": "12345",
            "cnpj": "12.345.678/0001-90",
            "observed_at": "2026-12-31",
            "account_code": "2.03",
            "account_name": "Patrimônio Líquido Consolidado",
            "value": 800.0,
        },
        {
            "doc_type": "dfp",
            "company_name": "Companhia ABCD",
            "cvm_code": "12345",
            "cnpj": "12.345.678/0001-90",
            "observed_at": "2026-12-31",
            "account_code": "1.01.01",
            "account_name": "Caixa e Equivalentes de Caixa",
            "value": 90.0,
        },
        {
            "doc_type": "dfp",
            "company_name": "Companhia ABCD",
            "cvm_code": "12345",
            "cnpj": "12.345.678/0001-90",
            "observed_at": "2026-12-31",
            "account_code": "2.01.04",
            "account_name": "Empréstimos e Financiamentos",
            "value": 300.0,
        },
    ]


def test_canonical_statement_line_maps_cvm_accounts() -> None:
    row = {
        "doc_type": "dfp",
        "company_name": "Companhia ABCD",
        "cvm_code": "12345",
        "cnpj": "12.345.678/0001-90",
        "observed_at": "2026-12-31",
        "account_code": "3.11",
        "account_name": "Lucro/Prejuízo Consolidado do Período",
        "value": 120.0,
        "scale": "",
    }

    line = canonical_statement_line(row)

    assert line["company_id"] == "CVM:12345"
    assert line["cnpj"] == "12345678000190"
    assert line["statement_type"] == "income_statement"
    assert line["canonical_account"] == "net_income"
    assert line["value"] == 120.0


def test_build_fundamental_snapshot_calculates_core_facts_and_metrics() -> None:
    response = build_fundamental_snapshot(
        statement_rows=_sample_statement_rows(),
        market_data={"last_price": 20.0, "shares_outstanding": 100.0},
    )

    assert response["ok"] is True
    snapshot = response["records"][0]
    assert snapshot["identity"]["company_id"] == "CVM:12345"
    assert snapshot["facts"]["revenue"] == 1000.0
    assert snapshot["facts"]["net_debt"] == 210.0
    assert snapshot["metrics"]["net_margin"] == 0.12
    assert snapshot["metrics"]["roe"] == 0.15
    assert snapshot["metrics"]["roa"] == 0.06
    assert snapshot["metrics"]["price_to_earnings"] == 16.666667
    assert snapshot["metrics"]["price_to_book"] == 2.5
    assert snapshot["metrics"]["market_cap"] == 2000.0


def test_calculate_ttm_sums_last_four_periods_per_account() -> None:
    rows = [
        {"canonical_account": "revenue", "observed_at": "2026-03-31", "value": 100.0},
        {"canonical_account": "revenue", "observed_at": "2026-06-30", "value": 110.0},
        {"canonical_account": "revenue", "observed_at": "2026-09-30", "value": 120.0},
        {"canonical_account": "revenue", "observed_at": "2026-12-31", "value": 130.0},
        {"canonical_account": "revenue", "observed_at": "2025-12-31", "value": 90.0},
    ]

    assert calculate_ttm(rows)["revenue_ttm"] == 460.0


def test_calculate_fundamental_metrics_handles_enterprise_value() -> None:
    metrics = calculate_fundamental_metrics(
        {
            "revenue": 1000.0,
            "ebit": 250.0,
            "net_income": 125.0,
            "total_assets": 2000.0,
            "equity": 500.0,
            "net_debt": 200.0,
        },
        market_data={"market_cap": 1500.0},
    )

    assert metrics["ebit_margin"] == 0.25
    assert metrics["enterprise_value"] == 1700.0
    assert metrics["ev_to_ebit"] == 6.8
    assert metrics["debt_to_equity"] == 0.4


def test_build_company_identity_prefers_cvm_and_cnpj_fields() -> None:
    identity = build_company_identity(_sample_statement_rows())

    assert identity == {
        "company_id": "CVM:12345",
        "company_name": "Companhia ABCD",
        "cvm_code": "12345",
        "cnpj": "12345678000190",
    }


def test_compare_fundamental_snapshots_adds_growth_and_relative_metrics() -> None:
    rows = compare_fundamental_snapshots(
        [
            {"identity": {"company_id": "CVM:1"}, "facts": {"revenue": 100.0}, "metrics": {"roe": 0.1}},
            {"identity": {"company_id": "CVM:2"}, "facts": {"revenue": 120.0}, "metrics": {"roe": 0.15}},
        ],
        metric="roe",
    )

    assert rows[0]["rank"] == 1
    assert rows[0]["company_id"] == "CVM:2"
    assert rows[0]["metric_value"] == 0.15


def test_compare_companies_fundamentals_uses_batch_cvm_fetch(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_batch(**kwargs):
        seen.update(kwargs)
        records = []
        for code, company, net_income, equity in (
            ("9512", "Petrobras", 20.0, 100.0),
            ("4170", "Banco Alfa", 10.0, 100.0),
        ):
            records.extend(
                [
                    {
                        "doc_type": "dfp",
                        "company_name": company,
                        "cvm_code": code,
                        "cnpj": "",
                        "observed_at": "2025-12-31",
                        "account_code": "3.11",
                        "account_name": "Lucro Consolidado do Periodo",
                        "value": net_income,
                    },
                    {
                        "doc_type": "dfp",
                        "company_name": company,
                        "cvm_code": code,
                        "cnpj": "",
                        "observed_at": "2025-12-31",
                        "account_code": "2.03",
                        "account_name": "Patrimonio Liquido",
                        "value": equity,
                    },
                ]
            )
        return {
            "ok": True,
            "source_url": "fixture://cvm",
            "records": records,
            "limitations": [],
            "source_mode": "local_snapshot",
            "resilience": {},
            "failures": [],
            "record_counts_by_cvm_code": {"9512": 2, "4170": 2},
        }

    def fail_company_fetch(**_kwargs):
        raise AssertionError("comparison should not fetch fundamentals one company at a time")

    monkeypatch.setattr(fundamentals, "fetch_cvm_company_reports_batch", fake_batch)
    monkeypatch.setattr(fundamentals, "get_company_fundamentals", fail_company_fetch)

    response = fundamentals.compare_companies_fundamentals(
        cvm_codes="009512,004170",
        year=2025,
        metric="roe",
        doc_type="dfp",
        limit_per_company=777,
    )

    assert response["ok"] is True
    assert seen["cvm_codes"] == ["9512", "4170"]
    assert seen["statement"] == "financials"
    assert seen["limit_per_code"] == 777
    assert response["records"][0]["company_id"] == "CVM:9512"
    assert response["records"][0]["metric_value"] == 0.2


def test_statement_facts_ignore_equity_movement_rows() -> None:
    response = build_fundamental_snapshot(
        statement_rows=[
            {
                "company_name": "Companhia ABCD",
                "cvm_code": "12345",
                "cnpj": "12.345.678/0001-90",
                "observed_at": "2026-12-31",
                "account_code": "3.11",
                "account_name": "Lucro/Prejuizo Consolidado do Periodo",
                "value": 120.0,
            },
            {
                "company_name": "Companhia ABCD",
                "cvm_code": "12345",
                "cnpj": "12.345.678/0001-90",
                "observed_at": "2026-12-31",
                "account_code": "2.03",
                "account_name": "Patrimonio Liquido",
                "value": 800.0,
            },
            {
                "company_name": "Companhia ABCD",
                "cvm_code": "12345",
                "cnpj": "12.345.678/0001-90",
                "observed_at": "2026-12-31",
                "account_code": "5.06",
                "account_name": "Mutacoes Internas do Patrimonio Liquido",
                "value": 0.0,
            },
        ]
    )

    snapshot = response["records"][0]
    assert snapshot["facts"]["equity"] == 800.0
    assert snapshot["metrics"]["roe"] == 0.15


def test_get_company_dividends_uses_limited_yfinance_history(monkeypatch) -> None:
    import sys

    seen: dict[str, object] = {}

    class FakeIndex:
        def __init__(self, value: str):
            self._value = date.fromisoformat(value)

        def date(self):
            return self._value

    class FakeFrame:
        empty = False

        def tail(self, _limit):
            return self

        def iterrows(self):
            yield FakeIndex("2026-05-01"), {"Dividends": 0.5, "Stock Splits": 0.0}

    class FakeTicker:
        def __init__(self, symbol: str):
            seen["symbol"] = symbol

        def history(self, **kwargs):
            seen.update(kwargs)
            return FakeFrame()

    class FakeYFinance:
        Ticker = FakeTicker

    monkeypatch.setenv("DADOSBR_DISABLE_HTTP_CACHE", "1")
    monkeypatch.setattr(
        fundamentals,
        "_fetch_yahoo_chart_dividend_rows",
        lambda **_kwargs: (_ for _ in ()).throw(
            fundamentals.DataSourceError("source_unavailable", "chart unavailable", "fundamentals", retryable=True)
        ),
    )
    monkeypatch.setitem(sys.modules, "yfinance", FakeYFinance)

    response = get_company_dividends(ticker="PETR4", limit=10)

    assert response["ok"] is True
    assert seen["symbol"] == "PETR4.SA"
    assert seen["period"] == "2y"
    assert seen["timeout"] == 30
    assert response["records"][0]["amount"] == 0.5


def test_get_company_dividends_limits_after_filtering_zero_price_rows(monkeypatch) -> None:
    import sys

    class FakeIndex:
        def __init__(self, value: str):
            self._value = date.fromisoformat(value)

        def date(self):
            return self._value

    class FakeFrame:
        empty = False

        def tail(self, _limit):
            raise AssertionError("Dividend limit must be applied after filtering non-zero dividend rows")

        def iterrows(self):
            yield FakeIndex("2026-05-01"), {"Dividends": 0.5}
            yield FakeIndex("2026-05-02"), {"Dividends": 0.0}
            yield FakeIndex("2026-05-03"), {"Dividends": 0.0}

    class FakeTicker:
        def __init__(self, _symbol: str):
            pass

        def history(self, **_kwargs):
            return FakeFrame()

    class FakeYFinance:
        Ticker = FakeTicker

    monkeypatch.setenv("DADOSBR_DISABLE_HTTP_CACHE", "1")
    monkeypatch.setattr(
        fundamentals,
        "_fetch_yahoo_chart_dividend_rows",
        lambda **_kwargs: (_ for _ in ()).throw(
            fundamentals.DataSourceError("source_unavailable", "chart unavailable", "fundamentals", retryable=True)
        ),
    )
    monkeypatch.setitem(sys.modules, "yfinance", FakeYFinance)

    response = get_company_dividends(ticker="PETR4", limit=1)

    assert response["ok"] is True
    assert response["records"] == [
        {
            "ticker": "PETR4",
            "observed_at": "2026-05-01",
            "amount": 0.5,
            "cumulative_amount": 0.5,
            "source_id": "yfinance",
            "data_stage": "enriched",
        }
    ]


def test_get_company_dividends_reuses_disk_cache(monkeypatch, tmp_path) -> None:
    import sys

    calls = {"history": 0}

    class FakeIndex:
        def __init__(self, value: str):
            self._value = date.fromisoformat(value)

        def date(self):
            return self._value

    class FakeFrame:
        empty = False

        def iterrows(self):
            yield FakeIndex("2026-05-01"), {"Dividends": 0.5}
            yield FakeIndex("2026-06-01"), {"Dividends": 0.7}

    class FakeTicker:
        def __init__(self, _symbol: str):
            pass

        def history(self, **_kwargs):
            calls["history"] += 1
            return FakeFrame()

    class FakeYFinance:
        Ticker = FakeTicker

    monkeypatch.setattr(
        fundamentals,
        "_fetch_yahoo_chart_dividend_rows",
        lambda **_kwargs: (_ for _ in ()).throw(
            fundamentals.DataSourceError("source_unavailable", "chart unavailable", "fundamentals", retryable=True)
        ),
    )
    monkeypatch.setenv("DADOSBR_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setitem(sys.modules, "yfinance", FakeYFinance)

    first = get_company_dividends(ticker="PETR4", limit=2)
    second = get_company_dividends(ticker="PETR4", limit=1)

    assert first["ok"] is True
    assert second["ok"] is True
    assert calls["history"] == 1
    assert second["source_mode"] == "cache_hit"
    assert second["resilience"]["provider"] == "yfinance"
    assert second["records"] == [
        {
            "ticker": "PETR4",
            "observed_at": "2026-06-01",
            "amount": 0.7,
            "cumulative_amount": 0.7,
            "source_id": "yfinance",
            "data_stage": "enriched",
        }
    ]


def test_get_company_dividends_uses_yahoo_chart_before_yfinance(monkeypatch) -> None:
    import sys

    body = {
        "chart": {
            "result": [
                {
                    "events": {
                        "dividends": {
                            "a": {"date": 1776949200, "amount": 0.626229},
                            "b": {"date": 1766494800, "amount": 0.952128},
                        }
                    }
                }
            ],
            "error": None,
        }
    }
    seen: dict[str, str] = {}

    def fake_get(url: str, **_kwargs):
        seen["url"] = url
        return json.dumps(body).encode(), {"x-dadosbr-cache": "miss"}

    class FailYFinance:
        def __getattr__(self, _name):
            raise AssertionError("yfinance should not be imported for chart fast path")

    monkeypatch.setenv("DADOSBR_DISABLE_HTTP_CACHE", "1")
    monkeypatch.setattr(fundamentals, "http_get_bytes_cached", fake_get)
    monkeypatch.setitem(sys.modules, "yfinance", FailYFinance())

    response = get_company_dividends(ticker="PETR4", limit=1)

    assert response["ok"] is True
    assert "query1.finance.yahoo.com" in seen["url"]
    assert response["records"] == [
        {
            "ticker": "PETR4",
            "observed_at": "2026-04-23",
            "amount": 0.626229,
            "cumulative_amount": 0.626229,
            "source_id": "yfinance",
            "data_stage": "enriched",
        }
    ]


def test_get_company_dividends_returns_timeout_when_yfinance_hangs(monkeypatch) -> None:
    import sys

    class FakeTicker:
        def __init__(self, _symbol: str):
            pass

        def history(self, **_kwargs):
            time.sleep(2)
            raise AssertionError("slow yfinance call should be cut off before completion")

    class FakeYFinance:
        Ticker = FakeTicker

    monkeypatch.setenv("DADOSBR_DISABLE_HTTP_CACHE", "1")
    monkeypatch.setenv("DADOSBR_YFINANCE_TIMEOUT_SECONDS", "1")
    monkeypatch.setattr(
        fundamentals,
        "_fetch_yahoo_chart_dividend_rows",
        lambda **_kwargs: (_ for _ in ()).throw(
            fundamentals.DataSourceError("source_unavailable", "chart unavailable", "fundamentals", retryable=True)
        ),
    )
    monkeypatch.setitem(sys.modules, "yfinance", FakeYFinance)

    start = time.monotonic()
    response = get_company_dividends(ticker="PETR4", limit=3)
    elapsed = time.monotonic() - start

    assert elapsed < 1.6
    assert response["ok"] is False
    assert response["error"]["code"] == "timeout"
    assert response["error"]["retryable"] is True


def test_get_company_dividends_timeout_includes_yfinance_import(monkeypatch) -> None:
    def slow_import(_name: str):
        time.sleep(2)
        raise AssertionError("slow yfinance import should be cut off before completion")

    monkeypatch.setenv("DADOSBR_DISABLE_HTTP_CACHE", "1")
    monkeypatch.setenv("DADOSBR_YFINANCE_TIMEOUT_SECONDS", "1")
    monkeypatch.setattr(
        fundamentals,
        "_fetch_yahoo_chart_dividend_rows",
        lambda **_kwargs: (_ for _ in ()).throw(
            fundamentals.DataSourceError("source_unavailable", "chart unavailable", "fundamentals", retryable=True)
        ),
    )
    monkeypatch.setattr(fundamentals.importlib, "import_module", slow_import)

    start = time.monotonic()
    response = get_company_dividends(ticker="PETR4", limit=3)
    elapsed = time.monotonic() - start

    assert elapsed < 1.6
    assert response["ok"] is False
    assert response["error"]["code"] == "timeout"


def test_normalize_yfinance_dividends() -> None:
    records = normalize_yfinance_dividends(
        [{"observed_at": "2026-05-01", "value": 0.5}, {"observed_at": "2026-08-01", "value": 0.7}],
        ticker="ABCD3",
    )

    assert records[-1]["ticker"] == "ABCD3"
    assert records[-1]["amount"] == 0.7
    assert records[-1]["cumulative_amount"] == 1.2
