from __future__ import annotations

import io
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from dadosbr.core import DataSourceError, make_failure, make_success
from dadosbr.core.http import http_get_bytes, http_get_bytes_cached, http_response_metadata
from dadosbr.core.utils import sha256_bytes

SOURCE_ID = "b3_cotahist"
ALLOW_ENV = "DADOSBR_ALLOW_B3_DOWNLOAD"
LEGACY_ALLOW_ENV = "PREVER_AGENT_ALLOW_B3_PUBLIC_DOWNLOAD"


def fetch_b3_cotahist(*, year: int | None = None, ticker: str | None = None, limit: int = 200) -> dict:
    local_file = os.getenv("DADOSBR_B3_COTAHIST_FILE", "").strip()
    if local_file:
        return parse_b3_cotahist_file(local_file, ticker=ticker, limit=limit)

    if not _is_download_allowed():
        return make_failure(
            DataSourceError(
                "source_unavailable",
                "B3 auto-download disabled. Set DADOSBR_ALLOW_B3_DOWNLOAD=1 in authorized environment.",
                SOURCE_ID,
            )
        ).model_dump(mode="json")
    selected_year = int(year or datetime.now(UTC).year)
    url = f"https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{selected_year}.ZIP"
    try:
        raw_zip, headers = http_get_bytes_cached(
            url,
            source_id=SOURCE_ID,
            timeout_seconds=30,
            cache_namespace="b3_cotahist",
            fetcher=http_get_bytes,
            max_stale_seconds=7 * 24 * 60 * 60,
        )
        source_mode, resilience, cache_limitations = http_response_metadata(headers)
        with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
            txt_member = next((n for n in zf.namelist() if n.upper().endswith(".TXT")), None)
            if not txt_member:
                raise DataSourceError("parse_error", "COTAHIST ZIP without TXT file", SOURCE_ID, url)
            raw_txt = zf.read(txt_member)
        return parse_b3_cotahist_bytes(
            raw_txt,
            source_url=url,
            ticker=ticker,
            limit=limit,
            source_mode=source_mode,
            resilience=resilience,
            extra_limitations=cache_limitations,
        )
    except DataSourceError as exc:
        return make_failure(exc).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        return make_failure(
            DataSourceError("network_error", str(exc), SOURCE_ID, source_url=url, retryable=True)
        ).model_dump(mode="json")


def parse_b3_cotahist_file(path: str, *, ticker: str | None = None, limit: int = 200) -> dict:
    file_path = Path(path)
    if not file_path.exists():
        return make_failure(
            DataSourceError("validation_error", f"File not found: {path}", SOURCE_ID)
        ).model_dump(mode="json")
    return parse_b3_cotahist_bytes(
        file_path.read_bytes(),
        source_url=str(file_path),
        ticker=ticker,
        limit=limit,
        source_mode="local_snapshot",
        resilience={"local_file": str(file_path)},
    )


def parse_b3_cotahist_bytes(
    raw_bytes: bytes,
    *,
    source_url: str,
    ticker: str | None = None,
    limit: int = 200,
    source_mode: str = "live",
    resilience: dict | None = None,
    extra_limitations: list[str] | None = None,
) -> dict:
    safe_limit = max(1, min(int(limit or 200), 5000))
    filter_ticker = str(ticker or "").strip().upper()
    records: list[dict] = []
    try:
        for line in _iter_lines(raw_bytes):
            if not line.startswith("01"):
                continue
            raw_ticker = line[12:24].strip().upper()
            if filter_ticker and raw_ticker != filter_ticker:
                continue
            date_text = line[2:10].strip()
            observed_at = datetime.strptime(date_text, "%Y%m%d").replace(tzinfo=UTC)
            open_price = _parse_price(line[56:69].strip())
            high_price = _parse_price(line[69:82].strip())
            low_price = _parse_price(line[82:95].strip())
            average_price = _parse_price(line[95:108].strip())
            close_price = _parse_price(line[108:121].strip())
            best_bid_price = _parse_price(line[121:134].strip())
            best_ask_price = _parse_price(line[134:147].strip())
            total_volume = _parse_int(line[170:188].strip())
            total_trades = _parse_int(line[147:152].strip())
            quantity_traded = _parse_int(line[152:170].strip())
            financial_volume = _parse_price(line[170:188].strip())
            records.append(
                {
                    "ticker": raw_ticker,
                    "observed_at": observed_at.isoformat(),
                    "bdi_code": line[10:12].strip(),
                    "market_type": line[24:27].strip(),
                    "short_name": line[27:39].strip(),
                    "specification": line[39:49].strip(),
                    "currency_ref": line[52:56].strip(),
                    "open_price": open_price,
                    "high_price": high_price,
                    "low_price": low_price,
                    "average_price": average_price,
                    "close_price": close_price,
                    "best_bid_price": best_bid_price,
                    "best_ask_price": best_ask_price,
                    "total_volume": total_volume,
                    "total_trades": total_trades,
                    "quantity_traded": quantity_traded,
                    "financial_volume": financial_volume,
                    "isin": line[230:242].strip(),
                    "distribution_number": line[242:245].strip(),
                }
            )
            if len(records) >= safe_limit:
                break
        limitations = [
            "COTAHIST is historical end-of-day data. Intraday and real-time are outside alpha scope.",
            "Prices are not adjusted for splits, dividends or other corporate actions.",
        ]
        if extra_limitations:
            limitations.extend(extra_limitations)
        return make_success(
            source_id=SOURCE_ID,
            source_url=source_url,
            records=records,
            raw_sha256=sha256_bytes(raw_bytes),
            limitations=limitations,
            source_mode=source_mode,
            resilience=resilience,
        ).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        return make_failure(
            DataSourceError("parse_error", str(exc), SOURCE_ID, source_url=source_url)
        ).model_dump(mode="json")


def _is_download_allowed() -> bool:
    return os.getenv(ALLOW_ENV) == "1" or os.getenv(LEGACY_ALLOW_ENV) == "1"


def _iter_lines(raw_bytes: bytes) -> Iterable[str]:
    return raw_bytes.decode("latin-1").splitlines()


def _parse_price(raw: str) -> float:
    return int(raw) / 100.0


def _parse_int(raw: str) -> int:
    return int(raw or "0")
