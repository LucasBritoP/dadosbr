from __future__ import annotations

import os

DEFAULT_YFINANCE_TIMEOUT_SECONDS = 30
DEFAULT_YFINANCE_HISTORY_PERIOD = "5y"
DEFAULT_YFINANCE_DIVIDEND_PERIOD = "2y"
DEFAULT_YFINANCE_DIVIDEND_CACHE_TTL_SECONDS = 24 * 60 * 60
DEFAULT_YFINANCE_ACTION_PERIOD = "2y"
DEFAULT_YFINANCE_ACTION_CACHE_TTL_SECONDS = 24 * 60 * 60


def yfinance_timeout_seconds() -> int:
    raw = os.getenv("DADOSBR_YFINANCE_TIMEOUT_SECONDS", str(DEFAULT_YFINANCE_TIMEOUT_SECONDS))
    try:
        return max(1, min(int(float(raw)), 120))
    except ValueError:
        return DEFAULT_YFINANCE_TIMEOUT_SECONDS


def yfinance_history_period() -> str:
    return os.getenv("DADOSBR_YFINANCE_HISTORY_PERIOD", DEFAULT_YFINANCE_HISTORY_PERIOD).strip() or DEFAULT_YFINANCE_HISTORY_PERIOD


def yfinance_dividend_period() -> str:
    return os.getenv("DADOSBR_YFINANCE_DIVIDEND_PERIOD", DEFAULT_YFINANCE_DIVIDEND_PERIOD).strip() or DEFAULT_YFINANCE_DIVIDEND_PERIOD


def yfinance_dividend_cache_ttl_seconds() -> int:
    raw = os.getenv("DADOSBR_YFINANCE_DIVIDEND_CACHE_TTL_SECONDS", str(DEFAULT_YFINANCE_DIVIDEND_CACHE_TTL_SECONDS))
    try:
        return max(0, int(float(raw)))
    except ValueError:
        return DEFAULT_YFINANCE_DIVIDEND_CACHE_TTL_SECONDS


def yfinance_action_period() -> str:
    return os.getenv("DADOSBR_YFINANCE_ACTION_PERIOD", DEFAULT_YFINANCE_ACTION_PERIOD).strip() or DEFAULT_YFINANCE_ACTION_PERIOD


def yfinance_action_cache_ttl_seconds() -> int:
    raw = os.getenv("DADOSBR_YFINANCE_ACTION_CACHE_TTL_SECONDS", str(DEFAULT_YFINANCE_ACTION_CACHE_TTL_SECONDS))
    try:
        return max(0, int(float(raw)))
    except ValueError:
        return DEFAULT_YFINANCE_ACTION_CACHE_TTL_SECONDS


def yfinance_history_kwargs(*, start_date: str = "", end_date: str = "") -> dict[str, object]:
    kwargs: dict[str, object] = {"timeout": yfinance_timeout_seconds()}
    if start_date or end_date:
        if start_date:
            kwargs["start"] = start_date
        if end_date:
            kwargs["end"] = end_date
    else:
        kwargs["period"] = yfinance_history_period()
    return kwargs
