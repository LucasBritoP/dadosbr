from __future__ import annotations

import csv
import io
import re
import unicodedata
from pathlib import Path
from typing import Any

from dadosbr.core import DataSourceError, make_failure, make_success
from dadosbr.core.utils import parse_maybe_br_decimal, sha256_bytes, sha256_json

SOURCE_ID = "derivatives"
B3_SOURCE_ID = "b3_derivatives"

MONTH_CODES = {
    "F": 1,
    "G": 2,
    "H": 3,
    "J": 4,
    "K": 5,
    "M": 6,
    "N": 7,
    "Q": 8,
    "U": 9,
    "V": 10,
    "X": 11,
    "Z": 12,
}

CALL_MONTH_CODES = set("ABCDEFGHIJKL")
PUT_MONTH_CODES = set("MNOPQRSTUVWX")

DERIVATIVE_FAMILIES: list[dict[str, Any]] = [
    {
        "family_id": "DI1",
        "name": "Futuro de DI de um dia",
        "instrument_type": "future",
        "asset_class": "interest_rate",
        "underlying_asset": "one_day_interbank_deposit",
        "price_unit": "PU",
        "source_id": B3_SOURCE_ID,
    },
    {
        "family_id": "DAP",
        "name": "Futuro de cupom de IPCA",
        "instrument_type": "future",
        "asset_class": "interest_rate",
        "underlying_asset": "ipca_coupon",
        "price_unit": "rate_or_pu",
        "source_id": B3_SOURCE_ID,
    },
    {
        "family_id": "DOL",
        "name": "Futuro de dolar comercial",
        "instrument_type": "future",
        "asset_class": "fx",
        "underlying_asset": "usd_brl",
        "price_unit": "BRL_per_USD_1000",
        "source_id": B3_SOURCE_ID,
    },
    {
        "family_id": "WDO",
        "name": "Minicontrato futuro de dolar comercial",
        "instrument_type": "future",
        "asset_class": "fx",
        "underlying_asset": "usd_brl",
        "price_unit": "BRL_per_USD_1000",
        "source_id": B3_SOURCE_ID,
    },
    {
        "family_id": "IND",
        "name": "Futuro de Ibovespa",
        "instrument_type": "future",
        "asset_class": "equity_index",
        "underlying_asset": "ibovespa",
        "price_unit": "index_points",
        "source_id": B3_SOURCE_ID,
    },
    {
        "family_id": "WIN",
        "name": "Minicontrato futuro de Ibovespa",
        "instrument_type": "future",
        "asset_class": "equity_index",
        "underlying_asset": "ibovespa",
        "price_unit": "index_points",
        "source_id": B3_SOURCE_ID,
    },
    {
        "family_id": "equity_options",
        "name": "Opcoes listadas sobre acoes e units",
        "instrument_type": "option",
        "asset_class": "equity",
        "underlying_asset": "listed_equity",
        "price_unit": "BRL",
        "source_id": B3_SOURCE_ID,
    },
]

_FAMILY_BY_ID = {record["family_id"]: record for record in DERIVATIVE_FAMILIES}


def list_derivative_families() -> dict:
    records = sorted(DERIVATIVE_FAMILIES, key=lambda item: str(item["family_id"]))
    return make_success(
        source_id=SOURCE_ID,
        source_url="local://dadosbr/derivatives/families",
        records=records,
        raw_sha256=sha256_json(records),
        limitations=[
            "Catalogo alfa cobre familias liquidas principais; outros contratos B3 podem ser normalizados como unknown."
        ],
    ).model_dump(mode="json")


def make_derivatives_response(
    records: list[dict[str, Any]],
    *,
    source_url: str = "local://dadosbr/derivatives",
    limitations: list[str] | None = None,
) -> dict:
    return make_success(
        source_id=SOURCE_ID,
        source_url=source_url,
        records=records,
        raw_sha256=sha256_json(records),
        limitations=limitations or [],
    ).model_dump(mode="json")


def normalize_futures_quotes(
    rows: list[dict[str, Any]],
    *,
    family: str = "",
    limit: int = 5000,
) -> list[dict[str, Any]]:
    selected_family = str(family or "").strip().upper()
    records: list[dict[str, Any]] = []
    for row in rows:
        if len(records) >= _safe_limit(limit, maximum=50000):
            break
        symbol = _clean_symbol(_field(row, "symbol"))
        if not symbol:
            continue
        record = normalize_futures_quote(row)
        if selected_family and record["contract_family"] != selected_family:
            continue
        records.append(record)
    return records


def normalize_futures_quote(row: dict[str, Any]) -> dict[str, Any]:
    symbol = _clean_symbol(_field(row, "symbol"))
    family_id = _infer_family_id(symbol)
    family = _FAMILY_BY_ID.get(family_id, {})
    maturity_code, maturity_month, maturity_year = _parse_maturity_code(symbol, family_id)
    settlement_price = _safe_float(_field(row, "settlement_price"))
    previous_settlement_price = _safe_float(_field(row, "previous_settlement_price"))
    settlement_variation = _safe_float(_field(row, "settlement_variation"))
    if settlement_variation is None and settlement_price is not None and previous_settlement_price is not None:
        settlement_variation = round(settlement_price - previous_settlement_price, 10)

    observed_at = _date_text(_field(row, "observed_at"))
    maturity_date = _date_text(_field(row, "maturity_date"))
    quality_flags: list[str] = []
    if not symbol:
        quality_flags.append("missing_symbol")
    if not observed_at:
        quality_flags.append("missing_observed_at")
    if family_id == "unknown":
        quality_flags.append("unknown_contract_family")
    if settlement_price is None:
        quality_flags.append("missing_settlement_price")

    return {
        "contract_id": f"B3_DERIV:{symbol}" if symbol else "",
        "symbol": symbol,
        "instrument_type": str(family.get("instrument_type", "future" if family_id != "unknown" else "unknown")),
        "contract_family": family_id,
        "asset_class": str(family.get("asset_class", "unknown")),
        "underlying_asset": str(family.get("underlying_asset", "")),
        "maturity_code": maturity_code,
        "maturity_month": maturity_month,
        "maturity_year": maturity_year,
        "maturity_date": maturity_date,
        "observed_at": observed_at,
        "business_days": _safe_int(_field(row, "business_days")),
        "calendar_days": _safe_int(_field(row, "calendar_days")),
        "open_price": _safe_float(_field(row, "open_price")),
        "high_price": _safe_float(_field(row, "high_price")),
        "low_price": _safe_float(_field(row, "low_price")),
        "close_price": _safe_float(_field(row, "close_price")),
        "settlement_price": settlement_price,
        "previous_settlement_price": previous_settlement_price,
        "settlement_variation": settlement_variation,
        "settlement_rate": _safe_float(_field(row, "settlement_rate")),
        "quantity_traded": _safe_int(_field(row, "quantity_traded")),
        "financial_volume": _safe_float(_field(row, "financial_volume")),
        "volume": _safe_float(_field(row, "volume")),
        "open_interest": _safe_int(_field(row, "open_interest")),
        "price_unit": str(family.get("price_unit", "")),
        "source_id": B3_SOURCE_ID,
        "data_stage": "normalized",
        "quality_flags": quality_flags,
    }


def parse_derivatives_csv_file(
    path: str,
    *,
    family: str = "",
    limit: int = 5000,
) -> dict:
    file_path = Path(path)
    if not file_path.exists():
        return make_failure(
            DataSourceError("validation_error", f"File not found: {path}", SOURCE_ID)
        ).model_dump(mode="json")
    return parse_derivatives_csv_bytes(
        file_path.read_bytes(),
        source_url=str(file_path),
        family=family,
        limit=limit,
    )


def parse_derivatives_csv_bytes(
    raw_bytes: bytes,
    *,
    source_url: str,
    family: str = "",
    limit: int = 5000,
) -> dict:
    try:
        rows = _read_csv_rows(raw_bytes)
        records = normalize_futures_quotes(rows, family=family, limit=limit)
        return make_success(
            source_id=SOURCE_ID,
            source_url=source_url,
            records=records,
            raw_sha256=sha256_bytes(raw_bytes),
            limitations=[
                "Parser aceita CSVs ou exports tabulares com aliases B3 comuns; layouts oficiais especificos podem exigir mapeamento adicional."
            ],
        ).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        return make_failure(
            DataSourceError("parse_error", str(exc), SOURCE_ID, source_url=source_url)
        ).model_dump(mode="json")


def get_derivative_futures_from_file(
    *,
    file_path: str,
    family: str = "",
    limit: int = 5000,
) -> dict:
    if not file_path:
        return make_failure(
            DataSourceError(
                "validation_error",
                "file_path is required for local B3 derivatives parsing.",
                SOURCE_ID,
            )
        ).model_dump(mode="json")
    return parse_derivatives_csv_file(file_path, family=family, limit=limit)


def normalize_options_chain(rows: list[dict[str, Any]], *, limit: int = 5000) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in rows:
        if len(records) >= _safe_limit(limit, maximum=50000):
            break
        symbol = _clean_symbol(_field(row, "symbol"))
        if not symbol:
            continue
        option_type = _infer_option_type(symbol, _field(row, "option_type"))
        expiration_date = _date_text(_field(row, "expiration_date"))
        strike_price = _safe_float(_field(row, "strike_price"))
        quality_flags: list[str] = []
        if option_type == "unknown":
            quality_flags.append("unknown_option_type")
        if not expiration_date:
            quality_flags.append("missing_expiration_date")
        if strike_price is None:
            quality_flags.append("missing_strike_price")

        records.append(
            {
                "option_id": f"B3_OPT:{symbol}",
                "symbol": symbol,
                "underlying_ticker": _clean_symbol(_field(row, "underlying_ticker")),
                "instrument_type": "option",
                "option_style": str(_field(row, "option_style") or "unknown").strip().lower(),
                "option_type": option_type,
                "expiration_date": expiration_date,
                "strike_price": strike_price,
                "last_price": _safe_float(_field(row, "last_price")),
                "bid_price": _safe_float(_field(row, "bid_price")),
                "ask_price": _safe_float(_field(row, "ask_price")),
                "implied_volatility": _safe_float(_field(row, "implied_volatility")),
                "delta": _safe_float(_field(row, "delta")),
                "observed_at": _date_text(_field(row, "observed_at")),
                "source_id": B3_SOURCE_ID,
                "data_stage": "normalized",
                "quality_flags": quality_flags,
            }
        )
    return records


def _read_csv_rows(raw_bytes: bytes) -> list[dict[str, Any]]:
    text = _decode(raw_bytes)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,|\t,")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";"
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    return [dict(row) for row in reader]


def _decode(raw_bytes: bytes) -> str:
    for encoding in ("utf-8-sig", "latin-1", "cp1252"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("utf-8", errors="replace")


def _infer_family_id(symbol: str) -> str:
    for family_id in sorted(_FAMILY_BY_ID, key=len, reverse=True):
        if family_id == "equity_options":
            continue
        if symbol.startswith(family_id):
            return family_id
    return "unknown"


def _parse_maturity_code(symbol: str, family_id: str) -> tuple[str, int | None, int | None]:
    suffix = symbol[len(family_id) :] if family_id != "unknown" else symbol
    match = re.search(r"([FGHJKMNQUVXZ])(\d{2})", suffix)
    if not match:
        return "", None, None
    code = f"{match.group(1)}{match.group(2)}"
    return code, MONTH_CODES.get(match.group(1)), 2000 + int(match.group(2))


def _infer_option_type(symbol: str, explicit_value: Any) -> str:
    text = str(explicit_value or "").strip().lower()
    if text in {"call", "c", "compra"}:
        return "call"
    if text in {"put", "p", "venda"}:
        return "put"
    letter = _option_month_letter(symbol)
    if letter in CALL_MONTH_CODES:
        return "call"
    if letter in PUT_MONTH_CODES:
        return "put"
    return "unknown"


def _option_month_letter(symbol: str) -> str:
    for char in symbol:
        if char.isalpha():
            candidate = char.upper()
    return candidate if "candidate" in locals() else ""


def _field(row: dict[str, Any], field_name: str) -> Any:
    aliases = _FIELD_ALIASES[field_name]
    normalized = {_normalize_key(key): value for key, value in row.items()}
    for alias in aliases:
        value = normalized.get(_normalize_key(alias))
        if value not in (None, ""):
            return value
    return ""


_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "symbol": (
        "symbol",
        "ticker",
        "contract",
        "contrato",
        "codigo instrumento",
        "codigo_instrumento",
        "cod instrumento",
        "cod_negociacao",
        "tckrsymb",
        "instrumento",
    ),
    "observed_at": ("observed_at", "data", "data pregao", "data_pregao", "dtref", "rptdt", "data_referencia"),
    "maturity_date": ("maturity_date", "data vencimento", "data_vencimento", "vencimento", "xprtnDt"),
    "business_days": ("business_days", "dias uteis", "dias_uteis", "du", "vertice_du", "bdays"),
    "calendar_days": ("calendar_days", "dias corridos", "dias_corridos", "dc", "days"),
    "open_price": ("open_price", "preco abertura", "preco_abertura", "abertura"),
    "high_price": ("high_price", "preco maximo", "preco_maximo", "maxima"),
    "low_price": ("low_price", "preco minimo", "preco_minimo", "minima"),
    "close_price": ("close_price", "preco fechamento", "preco_fechamento", "fechamento", "ultimo"),
    "settlement_price": (
        "settlement_price",
        "preco ajuste atual",
        "preco_ajuste_atual",
        "ajuste",
        "ajuste atual",
        "cotacao ajuste",
        "adjstdqt",
    ),
    "previous_settlement_price": (
        "previous_settlement_price",
        "preco ajuste anterior",
        "preco_ajuste_anterior",
        "ajuste anterior",
        "prevadjstdqt",
    ),
    "settlement_variation": (
        "settlement_variation",
        "variacao ajuste",
        "variacao_ajuste",
        "var ajuste",
    ),
    "settlement_rate": ("settlement_rate", "taxa ajuste", "taxa_ajuste", "taxa"),
    "quantity_traded": (
        "quantity_traded",
        "quantidade negociada",
        "quantidade_negociada",
        "contratos negociados",
        "volume contratos",
        "traddqty",
    ),
    "financial_volume": ("financial_volume", "volume financeiro", "volume_financeiro", "vlume"),
    "volume": ("volume", "volume total"),
    "open_interest": (
        "open_interest",
        "contratos em aberto",
        "contratos_em_aberto",
        "posicao em aberto",
        "openinterest",
        "opnIntrst",
    ),
    "underlying_ticker": ("underlying_ticker", "ativo objeto", "ativo_objeto", "underlying", "undrlyg"),
    "option_type": ("option_type", "tipo opcao", "tipo_opcao", "call_put", "put_call"),
    "option_style": ("option_style", "estilo opcao", "estilo_opcao"),
    "expiration_date": ("expiration_date", "data vencimento", "data_vencimento", "vencimento"),
    "strike_price": ("strike_price", "preco exercicio", "preco_exercicio", "strike", "exrcPric"),
    "last_price": ("last_price", "ultimo", "preco ultimo", "last"),
    "bid_price": ("bid_price", "compra", "bid"),
    "ask_price": ("ask_price", "venda", "ask"),
    "implied_volatility": ("implied_volatility", "volatilidade implicita", "vol_implicita", "iv"),
    "delta": ("delta",),
}


def _normalize_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _clean_symbol(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().upper())


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
    if re.fullmatch(r"\d{8}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text[:10]


def _safe_limit(limit: int, *, maximum: int) -> int:
    return max(1, min(int(limit or 5000), maximum))
