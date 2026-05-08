from __future__ import annotations

import unicodedata
from datetime import datetime
from math import pow
from typing import Any

from dadosbr.benchmarks import fetch_yield_curve
from dadosbr.core import make_success
from dadosbr.core.utils import parse_maybe_br_decimal, sha256_json

SOURCE_ID = "interest_curves"

CURVE_SOURCE_CATALOG: list[dict[str, Any]] = [
    {
        "curve_id": "tesouro_direto",
        "name": "Curva derivada do Tesouro Direto",
        "provider": "tesouro_transparente",
        "source_id": "tesouro_transparente",
        "curve_type": "government_bond_offered_rates",
        "frequency": "daily",
        "official": True,
        "redistribution_note": "Dados abertos do Tesouro; curva derivada pelo DadosBR.",
    },
    {
        "curve_id": "anbima_prefixado",
        "name": "ANBIMA ETTJ prefixada",
        "provider": "anbima_feed",
        "source_id": "anbima_curves",
        "curve_type": "zero_coupon_nominal",
        "frequency": "daily",
        "official": True,
        "redistribution_note": "Use conforme termos do ANBIMA Feed; DadosBR normaliza registros fornecidos.",
    },
    {
        "curve_id": "anbima_ipca",
        "name": "ANBIMA ETTJ IPCA",
        "provider": "anbima_feed",
        "source_id": "anbima_curves",
        "curve_type": "zero_coupon_real",
        "frequency": "daily",
        "official": True,
        "redistribution_note": "Use conforme termos do ANBIMA Feed; DadosBR normaliza registros fornecidos.",
    },
    {
        "curve_id": "anbima_inflacao_implicita",
        "name": "ANBIMA inflacao implicita",
        "provider": "anbima_feed",
        "source_id": "anbima_curves",
        "curve_type": "breakeven_inflation",
        "frequency": "daily",
        "official": True,
        "redistribution_note": "Derivada das curvas ANBIMA conforme campos do feed.",
    },
    {
        "curve_id": "b3_di_pre",
        "name": "Curva DI x Pre por futuros DI1",
        "provider": "b3_derivatives",
        "source_id": "b3_derivatives",
        "curve_type": "listed_derivatives_implied",
        "frequency": "daily",
        "official": True,
        "redistribution_note": "Derivada de precos de ajuste B3 informados pelo usuario ou arquivo local.",
    },
]


def list_interest_curve_sources() -> dict:
    return make_success(
        source_id=SOURCE_ID,
        source_url="local://dadosbr/curves/sources",
        records=CURVE_SOURCE_CATALOG,
        raw_sha256=sha256_json(CURVE_SOURCE_CATALOG),
    ).model_dump(mode="json")


def make_interest_curve_response(
    records: list[dict[str, Any]],
    *,
    source_url: str = "local://dadosbr/curves",
    limitations: list[str] | None = None,
) -> dict:
    return make_success(
        source_id=SOURCE_ID,
        source_url=source_url,
        records=records,
        raw_sha256=sha256_json(records),
        limitations=limitations or [],
    ).model_dump(mode="json")


def normalize_curve_points(
    rows: list[dict[str, Any]],
    *,
    source_id: str = "manual",
    curve_id: str = "",
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rows:
        resolved_curve_id = str(_field(row, "curve_id") or curve_id or "unknown_curve").strip()
        business_days = _safe_int(_field(row, "business_days"))
        calendar_days = _safe_int(_field(row, "calendar_days"))
        observed_at = _date_text(_field(row, "observed_at"))
        maturity_date = _date_text(_field(row, "maturity_date"))
        tenor_years = _safe_float(_field(row, "tenor_years"))
        if tenor_years is None:
            tenor_years = _infer_tenor_years(
                observed_at=observed_at,
                maturity_date=maturity_date,
                business_days=business_days,
                calendar_days=calendar_days,
            )
        annual_rate, annual_rate_pct = _rate_pair(
            annual_rate=_field(row, "annual_rate"),
            annual_rate_pct=_field(row, "annual_rate_pct"),
        )
        discount_factor = _safe_float(_field(row, "discount_factor"))
        quality_flags: list[str] = []
        if annual_rate is None:
            quality_flags.append("missing_annual_rate")
        if tenor_years is None:
            quality_flags.append("missing_tenor")
        records.append(
            {
                "curve_id": resolved_curve_id,
                "observed_at": observed_at,
                "maturity_date": maturity_date,
                "business_days": business_days,
                "calendar_days": calendar_days,
                "tenor_years": round(tenor_years, 10) if tenor_years is not None else None,
                "annual_rate": annual_rate,
                "annual_rate_pct": annual_rate_pct,
                "discount_factor": discount_factor,
                "source_id": source_id,
                "data_stage": "normalized",
                "quality_flags": quality_flags,
            }
        )
    return calculate_discount_factors(records)


def normalize_anbima_curve_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []
    for row in rows:
        observed_at = _date_text(_field(row, "observed_at"))
        business_days = _safe_int(_field(row, "business_days"))
        if _field(row, "taxa_prefixadas") not in (None, ""):
            expanded.append(
                _anbima_point(row, "anbima_prefixado", "taxa_prefixadas", observed_at, business_days)
            )
        if _field(row, "taxa_ipca") not in (None, ""):
            expanded.append(_anbima_point(row, "anbima_ipca", "taxa_ipca", observed_at, business_days))
        if _field(row, "taxa_implicita") not in (None, ""):
            expanded.append(
                _anbima_point(
                    row,
                    "anbima_inflacao_implicita",
                    "taxa_implicita",
                    observed_at,
                    business_days,
                )
            )
        group = str(_field(row, "grupo_indexador") or "").strip().lower()
        taxa = _field(row, "taxa")
        if taxa not in (None, "") and group:
            expanded.append(
                {
                    "curve_id": "anbima_ipca" if "ipca" in group else "anbima_prefixado",
                    "observed_at": observed_at,
                    "business_days": business_days,
                    "annual_rate_pct": taxa,
                }
            )
    return normalize_curve_points(expanded, source_id="anbima_curves")


def build_di_curve_from_futures(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rows:
        family = str(row.get("contract_family") or "").strip().upper()
        symbol = str(row.get("symbol") or row.get("vertex_symbol") or "").strip().upper()
        if family and family != "DI1":
            continue
        if not family and not symbol.startswith("DI1"):
            continue
        settlement_price = _safe_float(row.get("settlement_price"))
        business_days = _safe_int(row.get("business_days"))
        quality_flags: list[str] = []
        if business_days is None:
            business_days = _approx_business_days(
                str(row.get("observed_at") or ""),
                str(row.get("maturity_date") or ""),
            )
            if business_days is not None:
                quality_flags.append("approximate_business_days")
        if settlement_price is None or settlement_price <= 0 or not business_days:
            continue
        annual_rate = pow(100000 / settlement_price, 252 / business_days) - 1
        discount_factor = settlement_price / 100000
        records.append(
            {
                "curve_id": "b3_di_pre",
                "vertex_symbol": symbol,
                "observed_at": str(row.get("observed_at") or "")[:10],
                "maturity_date": str(row.get("maturity_date") or "")[:10],
                "business_days": business_days,
                "calendar_days": _safe_int(row.get("calendar_days")),
                "tenor_years": round(business_days / 252, 10),
                "annual_rate": annual_rate,
                "annual_rate_pct": round(annual_rate * 100, 6),
                "discount_factor": round(discount_factor, 10),
                "rate_convention": "annual_exponential_252_business_days",
                "source_id": "b3_derivatives",
                "data_stage": "derived",
                "quality_flags": quality_flags,
            }
        )
    return sorted(records, key=lambda item: int(item["business_days"]))


def interpolate_interest_curve(
    rows: list[dict[str, Any]],
    *,
    target_tenor_years: float,
) -> dict[str, Any]:
    points = sorted(
        (point for point in rows if _safe_float(point.get("tenor_years")) is not None),
        key=lambda point: float(point["tenor_years"]),
    )
    if not points:
        return {
            "curve_id": "",
            "tenor_years": target_tenor_years,
            "annual_rate": None,
            "annual_rate_pct": None,
            "interpolated": False,
            "quality_flags": ["empty_curve"],
        }
    target = float(target_tenor_years)
    for point in points:
        if float(point["tenor_years"]) == target:
            result = dict(point)
            result["interpolated"] = False
            return result
    left = points[0]
    right = points[-1]
    for index in range(1, len(points)):
        if float(points[index]["tenor_years"]) >= target:
            left = points[index - 1]
            right = points[index]
            break
    left_tenor = float(left["tenor_years"])
    right_tenor = float(right["tenor_years"])
    left_rate = _safe_float(left.get("annual_rate"))
    right_rate = _safe_float(right.get("annual_rate"))
    if left_rate is None or right_rate is None or left_tenor == right_tenor:
        return {
            "curve_id": str(left.get("curve_id") or right.get("curve_id") or ""),
            "tenor_years": target,
            "annual_rate": None,
            "annual_rate_pct": None,
            "interpolated": False,
            "quality_flags": ["cannot_interpolate"],
        }
    weight = (target - left_tenor) / (right_tenor - left_tenor)
    annual_rate = left_rate + weight * (right_rate - left_rate)
    return {
        "curve_id": str(left.get("curve_id") or right.get("curve_id") or ""),
        "tenor_years": round(target, 10),
        "annual_rate": round(annual_rate, 10),
        "annual_rate_pct": round(annual_rate * 100, 6),
        "left_tenor_years": left_tenor,
        "right_tenor_years": right_tenor,
        "interpolated": True,
        "source_id": str(left.get("source_id") or right.get("source_id") or SOURCE_ID),
        "data_stage": "derived",
        "quality_flags": [],
    }


def calculate_discount_factors(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rows:
        record = dict(row)
        tenor_years = _safe_float(record.get("tenor_years"))
        annual_rate = _safe_float(record.get("annual_rate"))
        discount_factor = _safe_float(record.get("discount_factor"))
        if discount_factor is None and tenor_years is not None and annual_rate is not None:
            discount_factor = 1 / pow(1 + annual_rate, tenor_years)
        record["discount_factor"] = round(discount_factor, 10) if discount_factor is not None else None
        record["zero_price_per_100"] = (
            round(discount_factor * 100, 6) if discount_factor is not None else None
        )
        records.append(record)
    return records


def calculate_forward_rates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    discounted = calculate_discount_factors(rows)
    points = sorted(
        (
            point
            for point in discounted
            if _safe_float(point.get("annual_rate")) is not None
            and _safe_float(point.get("tenor_years")) is not None
        ),
        key=lambda point: float(point["tenor_years"]),
    )
    records: list[dict[str, Any]] = []
    for left, right in zip(points, points[1:], strict=False):
        left_tenor = float(left["tenor_years"])
        right_tenor = float(right["tenor_years"])
        if right_tenor <= left_tenor:
            continue
        left_rate = float(left["annual_rate"])
        right_rate = float(right["annual_rate"])
        forward_rate = pow(
            pow(1 + right_rate, right_tenor) / pow(1 + left_rate, left_tenor),
            1 / (right_tenor - left_tenor),
        ) - 1
        records.append(
            {
                "curve_id": str(right.get("curve_id") or left.get("curve_id") or ""),
                "observed_at": str(right.get("observed_at") or left.get("observed_at") or ""),
                "start_tenor_years": left_tenor,
                "end_tenor_years": right_tenor,
                "start_business_days": left.get("business_days"),
                "end_business_days": right.get("business_days"),
                "forward_rate": forward_rate,
                "forward_rate_pct": round(forward_rate * 100, 6),
                "source_id": str(right.get("source_id") or left.get("source_id") or SOURCE_ID),
                "data_stage": "derived",
            }
        )
    return records


def get_tesouro_interest_curve(limit: int = 200) -> dict:
    response = fetch_yield_curve(limit=limit)
    if not response.get("ok"):
        return response
    records: list[dict[str, Any]] = []
    for row in response.get("records", []):
        buy_rate = _safe_float(row.get("buy_rate"))
        if buy_rate is None:
            continue
        annual_rate = buy_rate / 100
        records.append(
            {
                "curve_id": "tesouro_direto",
                "observed_at": str(row.get("observed_at") or "")[:10],
                "maturity_date": str(row.get("maturity_date") or "")[:10],
                "bond_type": row.get("bond_type", ""),
                "rate_type": row.get("rate_type", ""),
                "tenor_years": _safe_float(row.get("tenor_years")),
                "annual_rate": annual_rate,
                "annual_rate_pct": buy_rate,
                "source_id": "tesouro_transparente",
                "data_stage": "derived",
                "quality_flags": ["offered_rate_curve"],
            }
        )
    records = calculate_discount_factors(records)
    return make_interest_curve_response(
        records,
        source_url=response.get("source_url", ""),
        limitations=["Curva Tesouro e derivada de taxas ofertadas no Tesouro Direto; nao substitui ETTJ ANBIMA."],
    )


def _anbima_point(
    row: dict[str, Any],
    curve_id: str,
    rate_field: str,
    observed_at: str,
    business_days: int | None,
) -> dict[str, Any]:
    return {
        "curve_id": curve_id,
        "observed_at": observed_at,
        "business_days": business_days,
        "annual_rate_pct": _field(row, rate_field),
    }


def _field(row: dict[str, Any], field_name: str) -> Any:
    aliases = _FIELD_ALIASES[field_name]
    normalized = {_normalize_key(key): value for key, value in row.items()}
    for alias in aliases:
        value = normalized.get(_normalize_key(alias))
        if value not in (None, ""):
            return value
    return ""


_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "curve_id": ("curve_id", "curva", "curve"),
    "observed_at": ("observed_at", "data_referencia", "data referencia", "data", "dtref"),
    "maturity_date": ("maturity_date", "data_vencimento", "data vencimento", "vencimento"),
    "business_days": ("business_days", "vertice_du", "vertice", "du", "dias uteis"),
    "calendar_days": ("calendar_days", "dc", "dias corridos"),
    "tenor_years": ("tenor_years", "prazo_anos", "prazo anos"),
    "annual_rate": ("annual_rate", "taxa_decimal", "zero_rate", "rate"),
    "annual_rate_pct": ("annual_rate_pct", "taxa_pct", "taxa", "taxa_aa"),
    "discount_factor": ("discount_factor", "fator_desconto", "df"),
    "taxa_prefixadas": ("taxa_prefixadas", "taxa prefixadas", "taxa_prefixada"),
    "taxa_ipca": ("taxa_ipca", "taxa ipca"),
    "taxa_implicita": ("taxa_implicita", "taxa implicita"),
    "grupo_indexador": ("grupo_indexador", "grupo indexador", "indexador"),
    "taxa": ("taxa", "rate"),
}


def _rate_pair(*, annual_rate: Any, annual_rate_pct: Any) -> tuple[float | None, float | None]:
    pct = _safe_float(annual_rate_pct)
    rate = _safe_float(annual_rate)
    if pct is not None:
        return round(pct / 100, 10), pct
    if rate is None:
        return None, None
    if abs(rate) > 2:
        return round(rate / 100, 10), rate
    return rate, round(rate * 100, 6)


def _infer_tenor_years(
    *,
    observed_at: str,
    maturity_date: str,
    business_days: int | None,
    calendar_days: int | None,
) -> float | None:
    if business_days is not None:
        return business_days / 252
    if calendar_days is not None:
        return calendar_days / 365.25
    if observed_at and maturity_date:
        try:
            start = datetime.fromisoformat(observed_at[:10]).date()
            end = datetime.fromisoformat(maturity_date[:10]).date()
            return (end - start).days / 365.25
        except ValueError:
            return None
    return None


def _approx_business_days(observed_at: str, maturity_date: str) -> int | None:
    tenor = _infer_tenor_years(
        observed_at=observed_at,
        maturity_date=maturity_date,
        business_days=None,
        calendar_days=None,
    )
    if tenor is None or tenor <= 0:
        return None
    return max(1, round(tenor * 252))


def _normalize_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return "".join(char for char in text.lower() if char.isalnum())


def _safe_float(value: Any) -> float | None:
    try:
        return parse_maybe_br_decimal(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    parsed = _safe_float(value)
    if parsed is None:
        return None
    return int(parsed)


def _date_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text[:10]
