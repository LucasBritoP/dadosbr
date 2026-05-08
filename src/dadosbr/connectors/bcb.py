from __future__ import annotations

from datetime import date
from urllib.parse import quote, urlencode

from dadosbr.core import DataSourceError, make_failure, make_success
from dadosbr.core.http import http_get_bytes, http_get_bytes_cached, http_response_metadata, parse_json_bytes
from dadosbr.core.utils import parse_br_decimal, parse_iso_date, parse_iso_datetime, sha256_bytes

SGS_SOURCE = "bcb_sgs"
PTAX_SOURCE = "bcb_ptax"
FOCUS_SOURCE = "bcb_focus"


def fetch_sgs_series(
    series_id: str | int,
    *,
    last: int | None = 12,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    series_text = str(series_id).strip()
    if not series_text:
        return make_failure(
            DataSourceError("validation_error", "series_id is required", SGS_SOURCE)
        ).model_dump(mode="json")

    url = _build_sgs_url(series_text, last=last, start_date=start_date, end_date=end_date)
    try:
        body, headers = _fetch_bcb_bytes(url, source_id=SGS_SOURCE)
        rows = parse_json_bytes(body, source_id=SGS_SOURCE, source_url=url)
        source_mode, resilience, cache_limitations = http_response_metadata(headers)
        records: list[dict] = []
        for row in rows:
            observed = _parse_sgs_date(str(row.get("data", "")))
            records.append(
                {
                    "series_id": series_text,
                    "observed_at": observed.isoformat(),
                    "value": parse_br_decimal(row.get("valor")),
                }
            )
        return make_success(
            source_id=SGS_SOURCE,
            source_url=url,
            records=records,
            raw_sha256=sha256_bytes(body),
            limitations=cache_limitations,
            source_mode=source_mode,
            resilience=resilience,
        ).model_dump(mode="json")
    except DataSourceError as exc:
        return make_failure(exc).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        return make_failure(
            DataSourceError(
                "parse_error",
                str(exc),
                SGS_SOURCE,
                source_url=url,
            )
        ).model_dump(mode="json")


def fetch_ptax(*, target_date: str, currency: str = "USD") -> dict:
    if currency.upper() != "USD":
        return make_failure(
            DataSourceError(
                "validation_error",
                "Only USD is supported by this endpoint.",
                PTAX_SOURCE,
            )
        ).model_dump(mode="json")

    try:
        parsed_date = parse_iso_date(target_date, "target_date")
    except ValueError as exc:
        return make_failure(
            DataSourceError("validation_error", str(exc), PTAX_SOURCE)
        ).model_dump(mode="json")

    endpoint = "CotacaoDolarDia(dataCotacao=@dataCotacao)"
    query = {"@dataCotacao": f"'{parsed_date.strftime('%m-%d-%Y')}'", "$format": "json"}
    url = (
        "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
        + quote(endpoint, safe="()=@")
        + "?"
        + urlencode(query, quote_via=quote, safe="'")
    )
    try:
        body, headers = _fetch_bcb_bytes(url, source_id=PTAX_SOURCE)
        doc = parse_json_bytes(body, source_id=PTAX_SOURCE, source_url=url)
        source_mode, resilience, cache_limitations = http_response_metadata(headers)
        records = []
        for row in doc.get("value", []):
            records.append(
                {
                    "currency": "USD",
                    "date": parsed_date.isoformat(),
                    "observed_at": parse_iso_datetime(
                        str(row.get("dataHoraCotacao")).replace(" ", "T"),
                        "dataHoraCotacao",
                    ).isoformat(),
                    "buy_rate": float(row.get("cotacaoCompra")),
                    "sell_rate": float(row.get("cotacaoVenda")),
                }
            )
        return make_success(
            source_id=PTAX_SOURCE,
            source_url=url,
            records=records,
            raw_sha256=sha256_bytes(body),
            limitations=cache_limitations,
            source_mode=source_mode,
            resilience=resilience,
        ).model_dump(mode="json")
    except DataSourceError as exc:
        return make_failure(exc).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        return make_failure(
            DataSourceError("parse_error", str(exc), PTAX_SOURCE, source_url=url)
        ).model_dump(mode="json")


def fetch_focus_expectations(
    *,
    indicator: str,
    top: int = 50,
) -> dict:
    indicator_text = str(indicator).strip()
    if not indicator_text:
        return make_failure(
            DataSourceError("validation_error", "indicator is required", FOCUS_SOURCE)
        ).model_dump(mode="json")
    max_top = max(1, min(int(top or 50), 500))

    entity = "ExpectativasMercadoAnuais"
    query = {
        "$top": max_top,
        "$orderby": "Data desc",
        "$filter": f"Indicador eq '{indicator_text}'",
        "$format": "json",
    }
    url = (
        "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/"
        + quote(entity, safe="()")
        + "?"
        + urlencode(query, quote_via=quote, safe="'")
    )
    try:
        body, headers = _fetch_bcb_bytes(url, source_id=FOCUS_SOURCE)
        doc = parse_json_bytes(body, source_id=FOCUS_SOURCE, source_url=url)
        source_mode, resilience, cache_limitations = http_response_metadata(headers)
        records: list[dict] = []
        for row in doc.get("value", []):
            data = str(row.get("Data", ""))
            observed_at = parse_iso_datetime(data.replace(" ", "T"), "Data")
            records.append(
                {
                    "indicator": indicator_text,
                    "observed_at": observed_at.isoformat(),
                    "reference": str(row.get("DataReferencia", "")),
                    "mean": _safe_float(row.get("Media")),
                    "median": _safe_float(row.get("Mediana")),
                    "minimum": _safe_float(row.get("Minimo")),
                    "maximum": _safe_float(row.get("Maximo")),
                }
            )
        return make_success(
            source_id=FOCUS_SOURCE,
            source_url=url,
            records=records,
            raw_sha256=sha256_bytes(body),
            limitations=cache_limitations,
            source_mode=source_mode,
            resilience=resilience,
        ).model_dump(mode="json")
    except DataSourceError as exc:
        return make_failure(exc).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        return make_failure(
            DataSourceError("parse_error", str(exc), FOCUS_SOURCE, source_url=url)
        ).model_dump(mode="json")


def _build_sgs_url(
    series_id: str,
    *,
    last: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series_id}/dados"
    if last is not None:
        url += f"/ultimos/{max(1, int(last))}"
    params = {"formato": "json"}
    if start_date:
        parsed_start = parse_iso_date(start_date, "start_date")
        params["dataInicial"] = parsed_start.strftime("%d/%m/%Y")
    if end_date:
        parsed_end = parse_iso_date(end_date, "end_date")
        params["dataFinal"] = parsed_end.strftime("%d/%m/%Y")
    return url + "?" + urlencode(params)


def _fetch_bcb_bytes(url: str, *, source_id: str) -> tuple[bytes, dict[str, str]]:
    return http_get_bytes_cached(
        url,
        source_id=source_id,
        timeout_seconds=30,
        cache_namespace="bcb",
        fetcher=http_get_bytes,
    )


def _parse_sgs_date(value: str) -> date:
    try:
        day, month, year = value.split("/")
        return date(int(year), int(month), int(day))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"invalid SGS date {value!r}") from exc


def _safe_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
