import json
import os
from pathlib import Path
import time

import httpx

BASE = os.getenv("DADOSBR_API_BASE", "http://127.0.0.1:8000")
ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures"
SMOKE_DIR = Path(os.getenv("DADOSBR_SMOKE_DIR", ".dadosbr/smoke")).resolve()
COTAHIST_FILE = SMOKE_DIR / "COTAHIST_SMOKE.TXT"
DERIVATIVES_FILE = SMOKE_DIR / "derivatives_smoke.csv"
TIMESERIES_DB = SMOKE_DIR / "timeseries.sqlite"
CNPJ_DB = SMOKE_DIR.parent / "datasets" / "receita_cnpj" / "index" / "cnpj.sqlite"
REPORT_PATH = Path(os.getenv("DADOSBR_API_TEST_REPORT", ".dadosbr/reports/api-test-report.json")).resolve()
results = []

client = httpx.Client(timeout=float(os.getenv("DADOSBR_API_TEST_TIMEOUT_SECONDS", "30")))


def sample_cotahist_bytes() -> bytes:
    return b"".join(
        [
            sample_cotahist_line("20260504", open_price=29900, high_price=30400, low_price=29800, close_price=30000),
            sample_cotahist_line("20260505", open_price=30123, high_price=31000, low_price=29900, close_price=30555),
            sample_cotahist_line("20260506", open_price=30600, high_price=31200, low_price=30400, close_price=30950),
        ]
    )


def sample_cotahist_line(date_text: str, *, open_price: int, high_price: int, low_price: int, close_price: int) -> bytes:
    line = [" "] * 245
    line[0:2] = list("01")
    line[2:10] = list(date_text)
    line[12:24] = list("PETR4       ")
    line[24:27] = list("010")
    line[27:39] = list("PETROBRAS   ")
    line[39:49] = list("PN      N1")
    line[52:56] = list("R$  ")
    line[56:69] = list(f"{open_price:013d}")
    line[69:82] = list(f"{high_price:013d}")
    line[82:95] = list(f"{low_price:013d}")
    line[95:108] = list(f"{(open_price + close_price) // 2:013d}")
    line[108:121] = list(f"{close_price:013d}")
    line[121:134] = list(f"{close_price - 50:013d}")
    line[134:147] = list(f"{close_price + 50:013d}")
    line[147:152] = list("00123")
    line[152:170] = list("000000000000000500")
    line[170:188] = list("000000000000123456")
    line[230:242] = list("BRPETRACNPR6")
    line[242:245] = list("123")
    return ("".join(line) + "\n").encode("latin-1")


def prepare_local_fixtures() -> None:
    SMOKE_DIR.mkdir(parents=True, exist_ok=True)
    COTAHIST_FILE.write_bytes(sample_cotahist_bytes())
    DERIVATIVES_FILE.write_text(
        "Data Pregao;Codigo Instrumento;Preco Ajuste Atual;Preco Ajuste Anterior;"
        "Quantidade Negociada;Contratos em Aberto\n"
        "2026-05-05;WDOQ26;5.123,50;5.100,00;12000;200000\n",
        encoding="utf-8",
    )
    build_cnpj_fixture_index()
    os.environ.setdefault("DADOSBR_B3_COTAHIST_FILE", str(COTAHIST_FILE))
    os.environ.setdefault("DADOSBR_TESOURO_PACKAGE_FILE", str(FIXTURE_DIR / "tesouro_package.json"))
    os.environ.setdefault("DADOSBR_TESOURO_RATES_CSV_FILE", str(FIXTURE_DIR / "tesouro_rates.csv"))
    os.environ.setdefault("DADOSBR_COMEX_DATA_DIR", str(FIXTURE_DIR / "comex"))


def build_cnpj_fixture_index() -> None:
    from dadosbr.connectors.receita_cnpj import build_cnpj_index

    response = build_cnpj_index(FIXTURE_DIR / "receita_cnpj", db_path=CNPJ_DB)
    if not response.get("ok"):
        raise RuntimeError(f"Could not build CNPJ fixture index: {response}")


def test(name, method, path, *, expected_ok: bool = True, **kwargs):
    url = f"{BASE}{path}"
    display_path = path
    if kwargs.get("params"):
        display_path = f"{path}?{httpx.QueryParams(kwargs['params'])}"
    start = time.time()
    print(f"[TEST] {method} {display_path}", end=" ", flush=True)
    try:
        if method == "GET":
            r = client.get(url, **kwargs)
        elif method == "POST":
            r = client.post(url, **kwargs)
        else:
            r = client.request(method, url, **kwargs)
        elapsed = round(time.time() - start, 2)
        ok = False
        try:
            parsed = r.json()
            ok = parsed.get("ok", True) if isinstance(parsed, dict) else True
        except Exception:
            ok = r.status_code < 400
        ok = ok and r.status_code < 400
        expected = ok is expected_ok
        status = "OK" if expected else f"FAIL({r.status_code})"
        print(f"-> {status} ({elapsed}s)")
        results.append(
            {
                "name": name,
                "method": method,
                "path": display_path,
                "status": r.status_code,
                "ok": ok,
                "expected_ok": expected_ok,
                "passed": expected,
                "elapsed": elapsed,
                "body_preview": r.text[:300],
                "error": None,
            }
        )
    except Exception as e:
        elapsed = round(time.time() - start, 2)
        print(f"-> ERROR ({elapsed}s): {e}")
        results.append(
            {
                "name": name,
                "method": method,
                "path": display_path,
                "status": None,
                "ok": False,
                "expected_ok": expected_ok,
                "passed": expected_ok is False,
                "elapsed": elapsed,
                "body_preview": "",
                "error": str(e),
            }
        )

prepare_local_fixtures()

# 1. Health & Sources
test("Health", "GET", "/health")
test("Sources", "GET", "/sources")
test("Source BCB SGS", "GET", "/sources/bcb_sgs")
test("Source Unknown", "GET", "/sources/unknown", expected_ok=False)

# 2. BCB
test("BCB SGS Serie 11", "GET", "/bcb/sgs/11?last=5")
test("BCB PTAX", "GET", "/bcb/ptax?date=2026-05-05")
test("BCB Focus", "GET", "/bcb/focus?indicator=IPCA")

# 3. CVM
test("CVM Company Reports", "GET", "/cvm/company-reports?year=2025&limit=5")
test("CVM Funds Daily", "GET", "/cvm/funds/daily?limit=5")
test("CVM Funds Portfolio", "GET", "/cvm/funds/portfolio?limit=5")
test("CVM FII Monthly", "GET", "/cvm/fii/monthly?year=2025&month=1&limit=5")

# 4. B3
test("B3 Cotahist", "GET", "/b3/cotahist?year=2025&limit=5")
test(
    "B3 Cotahist Parse",
    "POST",
    "/b3/cotahist/parse",
    files={"file": ("COTAHIST_SMOKE.TXT", sample_cotahist_bytes(), "text/plain")},
)

# 5. Tesouro
test("Tesouro Rates", "GET", "/tesouro/rates?limit=5")

# 6. IBGE
test("IBGE SIDRA", "GET", "/ibge/sidra?path=t/1737/n1/all/v/63/p/last%203")

# 7. IPEA
test("IPEA Series", "GET", "/ipea/series/BM12_PIB12?top=5")

# 8. CNPJ
test("CNPJ Status", "GET", "/cnpj/status")
test("CNPJ Search", "GET", "/cnpj/search?q=ACME&limit=5")
test("CNPJ Company", "GET", "/cnpj/12345678000190")
test("CNPJ Partners", "GET", "/cnpj/12345678000190/socios")

# 9. Comex
test("Comex NCM", "GET", "/comex/ncm?flow=export&year=2026&limit=5")
test("Comex NCM Summary", "GET", "/comex/ncm/summary?flow=export&year=2026")
test("Comex Municipality", "GET", "/comex/municipality?flow=export&year=2026&limit=5")
test("Comex Tables", "GET", "/comex/tables/ncm?limit=5")

# 10. BNDES
test("BNDES Operations", "GET", "/bndes/operations?uf=SP&year=2025&limit=5")
test("BNDES Variable Income", "GET", "/bndes/variable-income?year=2025&limit=5")
test("BNDES Datasets", "GET", "/bndes/datasets?rows=5")

# 11. Corporate Actions
test("Corporate Actions Types", "GET", "/corporate-actions/types")
test("Corporate Actions Factors", "GET", "/corporate-actions/PETR4/adjustment-factors?limit=5")
test("Corporate Actions Ticker", "GET", "/corporate-actions/PETR4?limit=5")
test(
    "Corporate Actions Adjusted History",
    "GET",
    "/corporate-actions/PETR4/adjusted-history",
    params={"limit": 5, "b3_file_path": str(COTAHIST_FILE)},
)

# 12. Derivatives
test("Derivatives Families", "GET", "/derivatives/families")
test("Derivatives Futures", "GET", "/derivatives/futures", params={"file_path": str(DERIVATIVES_FILE), "limit": 5})
test(
    "Derivatives Futures Parse",
    "POST",
    "/derivatives/futures/parse",
    files={"file": ("derivatives_smoke.csv", DERIVATIVES_FILE.read_bytes(), "text/csv")},
)
test(
    "Derivatives Futures Normalize",
    "POST",
    "/derivatives/futures/normalize",
    json=[
        {
            "symbol": "DI1F27",
            "observed_at": "2026-05-05",
            "business_days": 170,
            "settlement_price": 93500,
            "previous_settlement_price": 93400,
        }
    ],
)
test(
    "Derivatives Options Normalize",
    "POST",
    "/derivatives/options/normalize",
    json=[
        {
            "symbol": "PETRF260",
            "underlying_ticker": "PETR4",
            "option_type": "CALL",
            "expiration_date": "2026-06-19",
            "strike_price": "26,00",
            "last_price": "1,25",
            "observed_at": "2026-05-05",
        }
    ],
)

# 13. Curves
test("Curves Sources", "GET", "/curves/sources")
test("Curves Tesouro", "GET", "/curves/tesouro?limit=5")

test("Curves Normalize", "POST", "/curves/normalize", json=[
    {"tenor_days": 30, "rate": 0.10},
    {"tenor_days": 60, "rate": 0.11}
])

test("Curves ANBIMA Normalize", "POST", "/curves/anbima/normalize", json=[
    {"tipo": "prefixado", "prazo_dias": 252, "taxa": 10.5}
])

test("Curves DI Futures", "POST", "/curves/di-futures", json=[
    {"symbol": "DI1F26", "settlement_price": 100000, "business_days": 252}
])

test("Curves Interpolate", "POST", "/curves/interpolate?target_tenor_years=1", json=[
    {"tenor_years": 0.5, "rate": 0.10},
    {"tenor_years": 2.0, "rate": 0.12}
])

test("Curves Discount Factors", "POST", "/curves/discount-factors", json=[
    {"tenor_years": 1, "rate": 0.10}
])

test("Curves Forward Rates", "POST", "/curves/forward-rates", json=[
    {"tenor_years": 1, "rate": 0.10},
    {"tenor_years": 2, "rate": 0.12}
])

# 14. Assets
test("Assets Search", "GET", "/assets/search", params={"q": "PETR", "limit": 5, "b3_file_path": str(COTAHIST_FILE)})
test("Assets By ID", "GET", "/assets/B3:PETR4", params={"b3_file_path": str(COTAHIST_FILE)})
test("Assets History", "GET", "/assets/B3:PETR4/history", params={"limit": 5, "b3_file_path": str(COTAHIST_FILE)})
test("Issuers By CNPJ", "GET", "/issuers/12345678000190", params={"db_path": str(CNPJ_DB)})
test("Instruments By Ticker", "GET", "/instruments/PETR4", params={"b3_file_path": str(COTAHIST_FILE)})
test("Taxonomies CNAE", "GET", "/taxonomies/cnae/6201501", params={"db_path": str(CNPJ_DB)})
test("Taxonomies NCM", "GET", "/taxonomies/ncm/12019000")

# 15. Timeseries
test("Timeseries Economic BCB SGS", "GET", "/timeseries/economic/bcb_sgs/11?last=5")
test(
    "Timeseries Store Write",
    "POST",
    "/timeseries/store/assets/B3:PETR4/history",
    params={"limit": 5, "b3_file_path": str(COTAHIST_FILE), "db_path": str(TIMESERIES_DB)},
)
test("Timeseries Store Read", "GET", "/timeseries/store", params={"asset_id": "B3:PETR4", "db_path": str(TIMESERIES_DB)})

# 16. Benchmarks
test("Benchmarks List", "GET", "/benchmarks")
test("Benchmarks Metadata SELIC", "GET", "/benchmarks/selic")
test("Benchmarks History SELIC", "GET", "/benchmarks/selic/history?last=5")
test("Benchmarks Real SELIC", "GET", "/benchmarks/selic/history?last=5&real=true")
test(
    "Benchmarks Compare",
    "GET",
    "/benchmarks/compare",
    params={"asset_id": "B3:PETR4", "benchmark_id": "ibov", "last": 5, "b3_file_path": str(COTAHIST_FILE)},
)

# 17. Macro
test("Macro Calendar", "GET", "/macro/calendar")

# 18. Fixed Income
test("Fixed Income Tesouro", "GET", "/fixed-income/tesouro?limit=5")
test("Fixed Income Debentures", "GET", "/fixed-income/debentures?company=ABCD&limit=5")
test("Fixed Income Funds Exposure", "GET", "/fixed-income/funds/exposure?limit=5")
test("Fixed Income Cashflows", "GET", "/fixed-income/cashflows?settlement_date=2026-01-01&maturity_date=2028-01-01&principal=1000&annual_coupon_rate=0.1")
test("Fixed Income Analytics", "GET", "/fixed-income/analytics?price=1000&settlement_date=2026-01-01&maturity_date=2028-01-01&principal=1000&annual_coupon_rate=0.1")
test("Fixed Income Credit Spread", "GET", "/fixed-income/curves/credit-spread?benchmark_rate=0.11&limit=5")

# 19. Fundamentals
test("Fundamentals Calendar", "GET", "/fundamentals/calendar")
test("Fundamentals Compare", "GET", "/fundamentals/compare?cvm_codes=9512,4170&year=2025&metric=roe")
test("Fundamentals Company", "GET", "/fundamentals/companies/9512?year=2025")
test("Fundamentals Statements", "GET", "/fundamentals/companies/9512/statements?year=2025")
test("Fundamentals Ratios", "GET", "/fundamentals/companies/9512/ratios?year=2025")
test("Fundamentals Dividends", "GET", "/fundamentals/companies/PETR4/dividends?limit=5")

# 20. Admin
test("Admin CNPJ Sync (no token)", "POST", "/admin/cnpj/sync", expected_ok=False)

REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
with REPORT_PATH.open("w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print("\n=== RESUMO ===")
print(f"Total: {len(results)}")
print(f"Passou: {sum(1 for r in results if r['passed'])}")
print(f"Falhas inesperadas: {sum(1 for r in results if not r['passed'])}")
print(f"Relatorio: {REPORT_PATH}")
for r in results:
    if not r["passed"]:
        print(f"  FAIL {r['method']} {r['path']} -> {r['status']} {r['error'] or r['body_preview'][:100]}")

raise SystemExit(0 if all(r["passed"] for r in results) else 1)
