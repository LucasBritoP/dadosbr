from __future__ import annotations

from datetime import date, datetime
from math import pow
from typing import Any

from dadosbr.connectors.bndes import fetch_bndes_variable_income
from dadosbr.connectors.cvm import fetch_cvm_fund_portfolio
from dadosbr.connectors.tesouro import fetch_tesouro_rates
from dadosbr.core import make_success
from dadosbr.core.utils import sha256_json

SOURCE_ID = "fixed_income"


def canonical_tesouro_instrument(row: dict[str, Any]) -> dict[str, Any]:
    bond_type = str(row.get("bond_type", "")).strip()
    maturity_date = str(row.get("maturity_date", "")).strip()[:10]
    observed_at = str(row.get("observed_at", "")).strip()[:10]
    tenor_years = _tenor_years(observed_at, maturity_date)
    return {
        "instrument_id": f"TESOURO:{_slug(bond_type)}:{maturity_date}",
        "asset_class": "government_bond",
        "issuer_id": "BR_GOV:FEDERAL_TREASURY",
        "issuer_name": "Tesouro Nacional",
        "issuer_cnpj": "",
        "bond_type": bond_type,
        "ticker": "",
        "isin": "",
        "indexer": _tesouro_indexer(bond_type),
        "rate_type": _tesouro_rate_type(bond_type),
        "maturity_date": maturity_date,
        "observed_at": observed_at,
        "tenor_years": tenor_years,
        "duration_bucket": _duration_bucket(tenor_years),
        "buy_rate": _safe_float(row.get("buy_rate_morning")),
        "sell_rate": _safe_float(row.get("sell_rate_morning")),
        "buy_price": _safe_float(row.get("buy_price_morning")),
        "sell_price": _safe_float(row.get("sell_price_morning")),
        "source_id": "tesouro_transparente",
        "data_stage": "normalized",
        "source_refs": [{"source_id": "tesouro_transparente", "field": "bond_type"}],
    }


def normalize_bndes_debenture(row: dict[str, Any]) -> dict[str, Any]:
    ticker = str(row.get("ticker", "")).strip().upper()
    issuer_name = str(row.get("issuer_name") or row.get("company") or "").strip()
    return {
        "instrument_id": f"DEBENTURE:{ticker}" if ticker else f"DEBENTURE:{_digits(row.get('cnpj', ''))}",
        "asset_class": "debenture",
        "issuer_id": f"BR_CNPJ:{_digits(row.get('cnpj', ''))}" if _digits(row.get("cnpj", "")) else "",
        "issuer_cnpj": _digits(row.get("cnpj", "")),
        "issuer_name": issuer_name,
        "ticker": ticker,
        "isin": "",
        "indexer": str(row.get("indexer", "") or "").strip().upper(),
        "rate_type": "private_credit",
        "maturity_date": str(row.get("maturity_date", "") or "").strip()[:10],
        "year": _safe_int(row.get("year")),
        "invested_value": _safe_float(row.get("valor_investido", row.get("invested_value"))),
        "quantity_final": _safe_float(row.get("quantity_final")),
        "asset_type": str(row.get("asset_type", "") or "").strip(),
        "sector": str(row.get("sector", "") or "").strip(),
        "yield_rate": _safe_float(row.get("yield_rate")),
        "source_id": "bndes_dados_abertos",
        "data_stage": "normalized",
        "source_refs": [{"source_id": "bndes_dados_abertos", "field": "ticker"}],
    }


def classify_fixed_income_asset(asset_type: str = "", asset_code: str = "", issuer: str = "") -> str:
    text = " ".join([str(asset_type or ""), str(asset_code or ""), str(issuer or "")]).upper()
    if any(token in text for token in ("TESOURO", "TITULO PUBLICO", "TÍTULO PÚBLICO", "LFT", "LTN", "NTN")):
        return "government_bond"
    if "DEB" in text or "DEBENT" in text:
        return "debenture"
    if "CRI" in text:
        return "cri"
    if "CRA" in text:
        return "cra"
    if "CDB" in text:
        return "cdb"
    if "LCI" in text:
        return "lci"
    if "LCA" in text:
        return "lca"
    if "FIDC" in text:
        return "fidc"
    if "LETRA FINANCEIRA" in text or text.strip() == "LF":
        return "financial_bill"
    if "COMPROMISS" in text:
        return "repo"
    return "not_fixed_income"


def summarize_fund_fixed_income_exposure(portfolio_rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_market_value = 0.0
    total_fixed_income = 0.0
    by_class: dict[str, float] = {}
    holdings: list[dict[str, Any]] = []

    for row in portfolio_rows:
        market_value = _safe_float(row.get("market_value")) or 0.0
        total_market_value += market_value
        asset_class = classify_fixed_income_asset(
            str(row.get("asset_type", "")),
            str(row.get("asset_code", "")),
            str(row.get("issuer", "")),
        )
        if asset_class == "not_fixed_income":
            continue
        total_fixed_income += market_value
        by_class[asset_class] = round(by_class.get(asset_class, 0.0) + market_value, 6)
        holdings.append(
            {
                "asset_class": asset_class,
                "asset_code": row.get("asset_code", ""),
                "issuer": row.get("issuer", ""),
                "market_value": market_value,
            }
        )

    return {
        "total_market_value": round(total_market_value, 6),
        "total_fixed_income_market_value": round(total_fixed_income, 6),
        "fixed_income_share": round(total_fixed_income / total_market_value, 6) if total_market_value else 0.0,
        "by_class": dict(sorted(by_class.items())),
        "holdings": holdings,
    }


def generate_fixed_rate_cashflows(
    *,
    settlement_date: str,
    maturity_date: str,
    principal: float,
    annual_coupon_rate: float,
    payments_per_year: int = 1,
) -> list[dict[str, Any]]:
    settlement = _parse_date(settlement_date)
    maturity = _parse_date(maturity_date)
    if settlement is None or maturity is None or maturity <= settlement:
        return []
    frequency = max(1, int(payments_per_year or 1))
    years = max(1, round((maturity - settlement).days / 365.25 * frequency))
    coupon = float(principal) * float(annual_coupon_rate) / frequency
    records: list[dict[str, Any]] = []
    for step in range(1, years + 1):
        payment_date = _add_months(settlement, int(12 / frequency) * step)
        if step == years:
            payment_date = maturity
        principal_payment = float(principal) if step == years else 0.0
        records.append(
            {
                "payment_date": payment_date.isoformat(),
                "cashflow": round(coupon + principal_payment, 6),
                "principal": round(principal_payment, 6),
                "interest": round(coupon, 6),
            }
        )
    return records


def calculate_fixed_income_metrics(
    *,
    price: float,
    settlement_date: str,
    cashflows: list[dict[str, Any]],
) -> dict[str, Any]:
    settlement = _parse_date(settlement_date)
    if settlement is None or not cashflows or price <= 0:
        return {
            "yield_to_maturity": None,
            "macaulay_duration_years": None,
            "modified_duration_years": None,
            "present_value": None,
        }
    flows: list[tuple[float, float]] = []
    for flow in cashflows:
        payment = _parse_date(flow.get("payment_date", ""))
        amount = _safe_float(flow.get("cashflow"))
        if payment is None or amount is None or payment <= settlement:
            continue
        flows.append((_year_fraction(settlement, payment), amount))
    if not flows:
        return {
            "yield_to_maturity": None,
            "macaulay_duration_years": None,
            "modified_duration_years": None,
            "present_value": None,
        }
    ytm = _solve_yield(price=float(price), flows=flows)
    present_values = [amount / pow(1 + ytm, years) for years, amount in flows]
    pv_total = sum(present_values)
    macaulay = sum(years * pv for (years, _amount), pv in zip(flows, present_values, strict=False)) / pv_total
    modified = macaulay / (1 + ytm)
    return {
        "yield_to_maturity": round(ytm, 10),
        "macaulay_duration_years": round(macaulay, 2),
        "modified_duration_years": round(modified, 2),
        "present_value": round(pv_total, 6),
    }


def build_credit_spread_curve(
    instruments: list[dict[str, Any]],
    *,
    benchmark_rate: float,
    observed_at: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for instrument in instruments:
        yield_rate = _safe_float(instrument.get("yield_rate"))
        if yield_rate is None:
            continue
        records.append(
            {
                "instrument_id": instrument.get("instrument_id", ""),
                "issuer_name": instrument.get("issuer_name", ""),
                "maturity_date": instrument.get("maturity_date", ""),
                "observed_at": observed_at,
                "yield_rate": yield_rate,
                "benchmark_rate": benchmark_rate,
                "spread_bps": round((yield_rate - benchmark_rate) * 10000, 6),
            }
        )
    return sorted(records, key=lambda item: str(item.get("maturity_date", "")))


def build_fixed_income_master(
    *,
    tesouro_rates: list[dict[str, Any]] | None = None,
    debentures: list[dict[str, Any]] | None = None,
    fund_portfolio: list[dict[str, Any]] | None = None,
) -> dict:
    records: list[dict[str, Any]] = []
    records.extend(canonical_tesouro_instrument(row) for row in tesouro_rates or [])
    records.extend(normalize_bndes_debenture(row) for row in debentures or [])
    for row in fund_portfolio or []:
        asset_class = classify_fixed_income_asset(
            str(row.get("asset_type", "")),
            str(row.get("asset_code", "")),
            str(row.get("issuer", "")),
        )
        if asset_class == "not_fixed_income":
            continue
        asset_code = str(row.get("asset_code", "")).strip().upper()
        records.append(
            {
                "instrument_id": f"FUND_HOLDING:{asset_class.upper()}:{asset_code}",
                "asset_class": asset_class,
                "issuer_name": row.get("issuer", ""),
                "ticker": asset_code,
                "market_value": _safe_float(row.get("market_value")),
                "source_id": "cvm_dados_abertos",
                "data_stage": "classified",
                "source_refs": [{"source_id": "cvm_dados_abertos", "field": "asset_code"}],
            }
        )
    return make_success(
        source_id=SOURCE_ID,
        source_url="local://dadosbr/fixed-income/master",
        records=records,
        raw_sha256=sha256_json(records),
        limitations=[
            "Private credit records depend on available public fields; maturity, cashflow and yield may be missing."
        ],
    ).model_dump(mode="json")


def get_tesouro_fixed_income(limit: int = 200) -> dict:
    response = fetch_tesouro_rates(limit=limit)
    if not response.get("ok"):
        return response
    records = [canonical_tesouro_instrument(row) for row in response.get("records", [])]
    return make_success(
        source_id=SOURCE_ID,
        source_url=response.get("source_url", ""),
        records=records,
        raw_sha256=sha256_json(records),
        limitations=["Derived from Tesouro Direto offered bonds; not an ANBIMA curve."],
    ).model_dump(mode="json")


def get_private_credit_debentures(company: str = "", year: int = 0, limit: int = 200) -> dict:
    response = fetch_bndes_variable_income(kind="debentures", company=company, year=year, limit=limit)
    if not response.get("ok"):
        return response
    records = [normalize_bndes_debenture(row) for row in response.get("records", [])]
    return make_success(
        source_id=SOURCE_ID,
        source_url=response.get("source_url", ""),
        records=records,
        raw_sha256=sha256_json(records),
        limitations=[
            "BNDES debenture data is position/investment data, not secondary-market pricing.",
            "The public BNDES debenture CSV usually does not include maturity date, indexer or market yield.",
        ],
    ).model_dump(mode="json")


def get_fund_fixed_income_exposure(cnpj: str = "", date: str = "", limit: int = 5000) -> dict:
    response = fetch_cvm_fund_portfolio(cnpj=cnpj, date=date, limit=limit)
    if not response.get("ok"):
        return response
    summary = summarize_fund_fixed_income_exposure(response.get("records", []))
    summary["cnpj"] = cnpj
    summary["date"] = date
    return make_success(
        source_id=SOURCE_ID,
        source_url=response.get("source_url", ""),
        records=[summary],
        raw_sha256=sha256_json([summary]),
        limitations=["Classification is heuristic from CVM portfolio asset_type, asset_code and issuer fields."],
    ).model_dump(mode="json")


def get_fixed_income_cashflows(
    *,
    settlement_date: str,
    maturity_date: str,
    principal: float,
    annual_coupon_rate: float,
    payments_per_year: int = 1,
) -> dict:
    records = generate_fixed_rate_cashflows(
        settlement_date=settlement_date,
        maturity_date=maturity_date,
        principal=principal,
        annual_coupon_rate=annual_coupon_rate,
        payments_per_year=payments_per_year,
    )
    return make_success(
        source_id=SOURCE_ID,
        source_url="local://dadosbr/fixed-income/cashflows",
        records=records,
        raw_sha256=sha256_json(records),
    ).model_dump(mode="json")


def get_fixed_income_analytics(
    *,
    price: float,
    settlement_date: str,
    maturity_date: str,
    principal: float,
    annual_coupon_rate: float,
    payments_per_year: int = 1,
) -> dict:
    cashflows = generate_fixed_rate_cashflows(
        settlement_date=settlement_date,
        maturity_date=maturity_date,
        principal=principal,
        annual_coupon_rate=annual_coupon_rate,
        payments_per_year=payments_per_year,
    )
    metrics = calculate_fixed_income_metrics(
        price=price,
        settlement_date=settlement_date,
        cashflows=cashflows,
    )
    metrics["cashflow_count"] = len(cashflows)
    return make_success(
        source_id=SOURCE_ID,
        source_url="local://dadosbr/fixed-income/analytics",
        records=[metrics],
        raw_sha256=sha256_json([metrics]),
    ).model_dump(mode="json")


def get_fixed_income_credit_spread_curve(
    *,
    benchmark_rate: float,
    observed_at: str = "",
    company: str = "",
    year: int = 0,
    limit: int = 200,
) -> dict:
    response = get_private_credit_debentures(company=company, year=year, limit=limit)
    if not response.get("ok"):
        return response
    records = build_credit_spread_curve(
        response.get("records", []),
        benchmark_rate=benchmark_rate,
        observed_at=observed_at or datetime.utcnow().date().isoformat(),
    )
    return make_success(
        source_id=SOURCE_ID,
        source_url=response.get("source_url", ""),
        records=records,
        raw_sha256=sha256_json(records),
        limitations=["Only instruments with yield_rate can enter spread curve; BNDES records usually lack market yield."],
    ).model_dump(mode="json")


def _tesouro_indexer(bond_type: str) -> str:
    text = bond_type.upper()
    if "IPCA" in text:
        return "IPCA"
    if "SELIC" in text:
        return "SELIC"
    if "PREFIX" in text:
        return "PRE"
    return ""


def _tesouro_rate_type(bond_type: str) -> str:
    text = bond_type.upper()
    if "IPCA" in text:
        return "inflation_linked"
    if "SELIC" in text:
        return "post_fixed"
    if "PREFIX" in text:
        return "fixed_rate"
    return "unknown"


def _duration_bucket(tenor_years: float | None) -> str:
    if tenor_years is None:
        return "unknown"
    if tenor_years <= 3:
        return "short"
    if tenor_years <= 7:
        return "medium"
    return "long"


def _tenor_years(start: str, end: str) -> float | None:
    start_date = _parse_date(start)
    end_date = _parse_date(end)
    if start_date is None or end_date is None:
        return None
    return round((end_date - start_date).days / 365.25, 2)


def _solve_yield(*, price: float, flows: list[tuple[float, float]]) -> float:
    low = -0.95
    high = 1.0
    for _ in range(120):
        mid = (low + high) / 2
        pv = sum(amount / pow(1 + mid, years) for years, amount in flows)
        if pv > price:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def _year_fraction(start: date, end: date) -> float:
    years = (end - start).days / 365.25
    rounded = round(years)
    if abs(years - rounded) < 0.01:
        return float(rounded)
    return years


def _add_months(value: date, months: int) -> date:
    month = value.month - 1 + months
    year = value.year + month // 12
    month = month % 12 + 1
    day = min(value.day, _days_in_month(year, month))
    return date(year, month, day)


def _days_in_month(year: int, month: int) -> int:
    if month == 2:
        return 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28
    if month in {4, 6, 9, 11}:
        return 30
    return 31


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()[:10]
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _slug(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in value.upper().replace("+", ""))
    return "_".join(part for part in cleaned.split("_") if part)


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0
