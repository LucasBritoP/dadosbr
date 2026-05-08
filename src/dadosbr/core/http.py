from __future__ import annotations

import base64
import json
import os
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from .cache import DiskCache
from .errors import DataSourceError


DEFAULT_USER_AGENT = "dadosbr/0.1.0 (+https://github.com/)"
DEFAULT_HTTP_RETRIES = 2
DEFAULT_RETRY_BACKOFF_SECONDS = 0.25
DEFAULT_MAX_STALE_SECONDS = 7 * 24 * 60 * 60
DEFAULT_DOWNLOAD_CHUNK_BYTES = 1024 * 1024
DEFAULT_HTTP_CACHE_MAX_INLINE_BYTES = 1024 * 1024
DEFAULT_HTTP_CACHE_MAX_BODY_BYTES = 100 * 1024 * 1024


def http_get_bytes(
    url: str,
    *,
    timeout_seconds: int = 30,
    headers: dict[str, str] | None = None,
    source_id: str = "unknown",
    verify_ssl: bool = True,
) -> tuple[bytes, dict[str, str]]:
    attempts = _http_attempts()
    last_error: DataSourceError | None = None
    for attempt in range(attempts):
        try:
            return _http_get_bytes_once(
                url,
                timeout_seconds=timeout_seconds,
                headers=headers,
                source_id=source_id,
                verify_ssl=verify_ssl,
            )
        except DataSourceError as exc:
            last_error = exc
            if not exc.retryable or attempt >= attempts - 1:
                raise
            _sleep_before_retry(attempt)
    if last_error is not None:
        raise last_error
    raise DataSourceError("network_error", "Request failed without response.", source_id, source_url=url, retryable=True)


def http_download_to_file(
    url: str,
    output_path: str | Path,
    *,
    timeout_seconds: int = 30,
    headers: dict[str, str] | None = None,
    source_id: str = "unknown",
    verify_ssl: bool = True,
    chunk_bytes: int = DEFAULT_DOWNLOAD_CHUNK_BYTES,
) -> tuple[int, dict[str, str]]:
    attempts = _http_attempts()
    last_error: DataSourceError | None = None
    for attempt in range(attempts):
        try:
            return _http_download_to_file_once(
                url,
                Path(output_path),
                timeout_seconds=timeout_seconds,
                headers=headers,
                source_id=source_id,
                verify_ssl=verify_ssl,
                chunk_bytes=chunk_bytes,
            )
        except DataSourceError as exc:
            last_error = exc
            if not exc.retryable or attempt >= attempts - 1:
                raise
            _sleep_before_retry(attempt)
    if last_error is not None:
        raise last_error
    raise DataSourceError("network_error", "Request failed without response.", source_id, source_url=url, retryable=True)


def _http_get_bytes_once(
    url: str,
    *,
    timeout_seconds: int = 30,
    headers: dict[str, str] | None = None,
    source_id: str = "unknown",
    verify_ssl: bool = True,
) -> tuple[bytes, dict[str, str]]:
    req_headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "*/*"}
    if headers:
        req_headers.update(headers)

    request = urllib.request.Request(url=url, headers=req_headers, method="GET")
    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout_seconds,
            context=_ssl_context(verify_ssl=verify_ssl),
        ) as resp:
            status = getattr(resp, "status", 200)
            if status >= 400:
                raise DataSourceError(
                    code="http_error",
                    message=f"HTTP {status} from source",
                    source_id=source_id,
                    source_url=url,
                    retryable=status >= 500,
                    details={"status": status},
                )
            body = resp.read()
            response_headers = {k.lower(): v for k, v in resp.headers.items()}
            return body, response_headers
    except urllib.error.HTTPError as exc:
        raise DataSourceError(
            code="http_error",
            message=f"HTTP {exc.code} from source",
            source_id=source_id,
            source_url=url,
            retryable=exc.code >= 500,
            details={"status": exc.code},
        ) from exc
    except urllib.error.URLError as exc:
        raise DataSourceError(
            code="network_error",
            message=f"Network failure: {exc.reason}",
            source_id=source_id,
            source_url=url,
            retryable=True,
        ) from exc
    except TimeoutError as exc:
        raise DataSourceError(
            code="timeout",
            message="Request timed out",
            source_id=source_id,
            source_url=url,
            retryable=True,
        ) from exc


def _http_download_to_file_once(
    url: str,
    output_path: Path,
    *,
    timeout_seconds: int = 30,
    headers: dict[str, str] | None = None,
    source_id: str = "unknown",
    verify_ssl: bool = True,
    chunk_bytes: int = DEFAULT_DOWNLOAD_CHUNK_BYTES,
) -> tuple[int, dict[str, str]]:
    req_headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "*/*"}
    if headers:
        req_headers.update(headers)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f".{output_path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    request = urllib.request.Request(url=url, headers=req_headers, method="GET")
    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout_seconds,
            context=_ssl_context(verify_ssl=verify_ssl),
        ) as resp:
            status = getattr(resp, "status", 200)
            if status >= 400:
                raise DataSourceError(
                    code="http_error",
                    message=f"HTTP {status} from source",
                    source_id=source_id,
                    source_url=url,
                    retryable=status >= 500,
                    details={"status": status},
                )
            response_headers = {k.lower(): v for k, v in resp.headers.items()}
            total_bytes = 0
            with tmp_path.open("wb") as target:
                while True:
                    chunk = resp.read(max(1, int(chunk_bytes)))
                    if not chunk:
                        break
                    target.write(chunk)
                    total_bytes += len(chunk)
            tmp_path.replace(output_path)
            return total_bytes, response_headers
    except urllib.error.HTTPError as exc:
        raise DataSourceError(
            code="http_error",
            message=f"HTTP {exc.code} from source",
            source_id=source_id,
            source_url=url,
            retryable=exc.code >= 500,
            details={"status": exc.code},
        ) from exc
    except urllib.error.URLError as exc:
        raise DataSourceError(
            code="network_error",
            message=f"Network failure: {exc.reason}",
            source_id=source_id,
            source_url=url,
            retryable=True,
        ) from exc
    except TimeoutError as exc:
        raise DataSourceError(
            code="timeout",
            message="Request timed out",
            source_id=source_id,
            source_url=url,
            retryable=True,
        ) from exc
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def http_get_bytes_cached(
    url: str,
    *,
    timeout_seconds: int = 30,
    headers: dict[str, str] | None = None,
    source_id: str = "unknown",
    cache_namespace: str = "http",
    verify_ssl: bool = True,
    fetcher: Callable[..., tuple[bytes, dict[str, str]]] | None = None,
    strict: bool = False,
    max_stale_seconds: int | None = None,
) -> tuple[bytes, dict[str, str]]:
    if _env_flag("DADOSBR_DISABLE_HTTP_CACHE"):
        body, response_headers = (fetcher or http_get_bytes)(
            url,
            timeout_seconds=timeout_seconds,
            headers=headers,
            source_id=source_id,
            verify_ssl=verify_ssl,
        )
        return body, {**response_headers, "x-dadosbr-cache": "disabled"}

    cache = DiskCache(_cache_dir(cache_namespace, source_id), ttl_seconds=_cache_ttl_seconds())
    key = json.dumps(
        {
            "method": "GET",
            "url": url,
            "headers": headers or {},
            "source_id": source_id,
            "verify_ssl": verify_ssl,
        },
        sort_keys=True,
    )
    cached_entry = cache.get_with_metadata(key)
    if cached_entry:
        cached, metadata = cached_entry
        cached_body = _cached_body_from_record(cache, cached)
        if cached_body is not None:
            cached_headers = dict(cached.get("headers", {}))
            cached_headers["x-dadosbr-cache"] = "hit"
            cached_headers["x-dadosbr-cache-age-seconds"] = str(metadata.get("age_seconds", 0))
            return cached_body, cached_headers

    try:
        body, response_headers = (fetcher or http_get_bytes)(
            url,
            timeout_seconds=timeout_seconds,
            headers=headers,
            source_id=source_id,
            verify_ssl=verify_ssl,
        )
    except DataSourceError as exc:
        stale_entry = cache.get_with_metadata(key, allow_expired=True)
        if _stale_cache_allowed(strict=strict) and exc.retryable and stale_entry:
            cached, metadata = stale_entry
            cached_body = _cached_body_from_record(cache, cached)
            if cached_body is not None and _stale_age_allowed(
                int(metadata.get("age_seconds", 0)),
                max_stale_seconds=max_stale_seconds,
            ):
                cached_headers = dict(cached.get("headers", {}))
                cached_headers.update(
                    {
                        "x-dadosbr-cache": "stale",
                        "x-dadosbr-cache-stale": "true",
                        "x-dadosbr-cache-age-seconds": str(metadata.get("age_seconds", 0)),
                        "x-dadosbr-cache-created-at": str(metadata.get("created_at", "")),
                        "x-dadosbr-cache-error-code": exc.code,
                        "x-dadosbr-cache-error-message": exc.message,
                    }
                )
                return cached_body, cached_headers
        raise

    body_size = len(body)
    if body_size > _http_cache_max_body_bytes():
        return body, {
            **response_headers,
            "x-dadosbr-cache": "skip",
            "x-dadosbr-cache-skip-reason": "body_too_large",
            "x-dadosbr-cache-body-bytes": str(body_size),
        }
    cache.set(
        key,
        {
            "url": url,
            "headers": dict(response_headers),
            "body_size_bytes": body_size,
            **_cached_body_record(cache, key, body),
        },
    )
    return body, {**response_headers, "x-dadosbr-cache": "miss", "x-dadosbr-cache-body-bytes": str(body_size)}


def http_response_metadata(headers: dict[str, str]) -> tuple[str, dict[str, Any], list[str]]:
    cache_status = str(headers.get("x-dadosbr-cache", "")).strip().lower()
    source_mode = "live"
    if cache_status == "hit":
        source_mode = "cache_hit"
    elif cache_status == "stale":
        source_mode = "stale_cache"

    resilience: dict[str, Any] = {}
    limitations: list[str] = []
    if cache_status:
        resilience["cache_status"] = cache_status
    if "x-dadosbr-cache-age-seconds" in headers:
        resilience["cache_age_seconds"] = _safe_int(headers.get("x-dadosbr-cache-age-seconds"))
    if headers.get("x-dadosbr-cache-stale") == "true":
        resilience["stale"] = True
        resilience["stale_reason"] = {
            "code": headers.get("x-dadosbr-cache-error-code", ""),
            "message": headers.get("x-dadosbr-cache-error-message", ""),
        }
        limitations.append("Fonte primaria indisponivel; resposta servida a partir de cache stale.")
    return source_mode, resilience, limitations


def _ssl_context(*, verify_ssl: bool = True) -> ssl.SSLContext:
    if not verify_ssl:
        return ssl._create_unverified_context()
    ca_file = _ca_bundle_path()
    if ca_file:
        return ssl.create_default_context(cafile=ca_file)
    return ssl.create_default_context()


def _ca_bundle_path() -> str | None:
    for env_name in ("DADOSBR_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"):
        configured = os.getenv(env_name, "").strip()
        if configured:
            return configured
    try:
        import certifi  # type: ignore[import-not-found]

        return certifi.where()
    except Exception:  # noqa: BLE001
        return None


def _cache_dir(cache_namespace: str, source_id: str) -> Path:
    root = Path(os.getenv("DADOSBR_CACHE_DIR", ".dadosbr/cache"))
    safe_namespace = _safe_path_part(cache_namespace)
    safe_source = _safe_path_part(source_id)
    return root / safe_namespace / safe_source


def _cache_ttl_seconds() -> int:
    raw = os.getenv("DADOSBR_CACHE_TTL_SECONDS", "3600")
    try:
        return max(0, int(raw))
    except ValueError:
        return 3600


def _http_attempts() -> int:
    raw = os.getenv("DADOSBR_HTTP_RETRIES", str(DEFAULT_HTTP_RETRIES))
    try:
        return max(1, min(int(raw), 5))
    except ValueError:
        return DEFAULT_HTTP_RETRIES


def _sleep_before_retry(attempt: int) -> None:
    delay = _retry_backoff_seconds()
    if delay <= 0:
        return
    time.sleep(delay * (2**attempt))


def _retry_backoff_seconds() -> float:
    raw = os.getenv("DADOSBR_HTTP_RETRY_BACKOFF_SECONDS", str(DEFAULT_RETRY_BACKOFF_SECONDS))
    try:
        return max(0.0, min(float(raw), 10.0))
    except ValueError:
        return DEFAULT_RETRY_BACKOFF_SECONDS


def _stale_cache_allowed(*, strict: bool = False) -> bool:
    if strict or _env_flag("DADOSBR_STRICT_FRESH") or _env_flag("DADOSBR_DISABLE_STALE_CACHE"):
        return False
    return True


def _stale_age_allowed(age_seconds: int, *, max_stale_seconds: int | None = None) -> bool:
    limit = _max_stale_seconds() if max_stale_seconds is None else max_stale_seconds
    if limit <= 0:
        return True
    return age_seconds <= limit


def _max_stale_seconds() -> int:
    raw = os.getenv("DADOSBR_MAX_STALE_SECONDS", str(DEFAULT_MAX_STALE_SECONDS))
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_MAX_STALE_SECONDS


def _cached_body_record(cache: DiskCache, key: str, body: bytes) -> dict[str, str]:
    if len(body) <= _http_cache_max_inline_bytes():
        return {"body_b64": base64.b64encode(body).decode("ascii")}
    return {"body_file": cache.set_bytes(key, body)}


def _cached_body_from_record(cache: DiskCache, record: dict[str, Any]) -> bytes | None:
    if isinstance(record.get("body_b64"), str):
        return base64.b64decode(record["body_b64"])
    if isinstance(record.get("body_file"), str):
        try:
            return cache.get_bytes(record["body_file"])
        except OSError:
            return None
    return None


def _http_cache_max_inline_bytes() -> int:
    return _env_int("DADOSBR_HTTP_CACHE_MAX_INLINE_BYTES", DEFAULT_HTTP_CACHE_MAX_INLINE_BYTES, minimum=0)


def _http_cache_max_body_bytes() -> int:
    return _env_int("DADOSBR_HTTP_CACHE_MAX_BODY_BYTES", DEFAULT_HTTP_CACHE_MAX_BODY_BYTES, minimum=0)


def _safe_path_part(value: str) -> str:
    text = str(value or "unknown").strip().lower()
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in text) or "unknown"


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _safe_int(value: str | None) -> int:
    try:
        return int(str(value or "0"))
    except ValueError:
        return 0


def _env_int(name: str, default: int, *, minimum: int) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def parse_json_bytes(raw: bytes, *, source_id: str, source_url: str) -> Any:
    try:
        return json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError:
        try:
            return json.loads(raw.decode("latin-1"))
        except Exception as exc:  # noqa: BLE001
            raise DataSourceError(
                code="parse_error",
                message="Response is not valid UTF-8/Latin-1 JSON",
                source_id=source_id,
                source_url=source_url,
            ) from exc
    except json.JSONDecodeError as exc:
        raise DataSourceError(
            code="parse_error",
            message=f"Invalid JSON: {exc.msg}",
            source_id=source_id,
            source_url=source_url,
        ) from exc
