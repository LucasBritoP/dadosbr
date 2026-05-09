import json
import urllib.error

from dadosbr.core import DataSourceError, http


def test_ssl_context_uses_configured_ca_bundle(monkeypatch, tmp_path) -> None:
    ca_file = tmp_path / "ca.pem"
    ca_file.write_text("fixture", encoding="utf-8")
    seen: dict[str, str | None] = {}

    def fake_context(*, cafile=None):
        seen["cafile"] = cafile
        return "context"

    monkeypatch.setenv("DADOSBR_CA_BUNDLE", str(ca_file))
    monkeypatch.setattr(http.ssl, "create_default_context", fake_context)

    assert http._ssl_context() == "context"
    assert seen["cafile"] == str(ca_file)


def test_ssl_context_can_disable_verification(monkeypatch) -> None:
    monkeypatch.setattr(http.ssl, "_create_unverified_context", lambda: "unverified")

    assert http._ssl_context(verify_ssl=False) == "unverified"


def test_http_get_bytes_cached_reuses_cached_response(monkeypatch, tmp_path) -> None:
    calls = {"count": 0}

    def fake_get(url: str, **_kwargs):
        calls["count"] += 1
        return f"body-{calls['count']}".encode(), {"content-type": "text/plain"}

    monkeypatch.setenv("DADOSBR_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(http, "http_get_bytes", fake_get)

    first_body, first_headers = http.http_get_bytes_cached("https://example.test/data.csv", source_id="test")
    second_body, second_headers = http.http_get_bytes_cached("https://example.test/data.csv", source_id="test")

    assert first_body == b"body-1"
    assert second_body == b"body-1"
    assert calls["count"] == 1
    assert first_headers["x-dadosbr-cache"] == "miss"
    assert second_headers["x-dadosbr-cache"] == "hit"


def test_http_get_bytes_cached_stores_large_body_as_sidecar(monkeypatch, tmp_path) -> None:
    calls = {"count": 0}

    def fake_get(url: str, **_kwargs):
        calls["count"] += 1
        return b"larger-than-inline", {"content-type": "application/zip"}

    cache_root = tmp_path / "cache"
    monkeypatch.setenv("DADOSBR_CACHE_DIR", str(cache_root))
    monkeypatch.setenv("DADOSBR_HTTP_CACHE_MAX_INLINE_BYTES", "4")
    monkeypatch.setenv("DADOSBR_HTTP_CACHE_MAX_BODY_BYTES", "1024")
    monkeypatch.setattr(http, "http_get_bytes", fake_get)

    first_body, first_headers = http.http_get_bytes_cached("https://example.test/data.zip", source_id="test")
    second_body, second_headers = http.http_get_bytes_cached("https://example.test/data.zip", source_id="test")

    cache_file = next(cache_root.rglob("*.json"))
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    value = payload["value"]
    body_file = cache_file.parent / value["body_file"]

    assert first_body == b"larger-than-inline"
    assert second_body == b"larger-than-inline"
    assert calls["count"] == 1
    assert first_headers["x-dadosbr-cache"] == "miss"
    assert second_headers["x-dadosbr-cache"] == "hit"
    assert "body_b64" not in value
    assert value["body_file"] == body_file.name
    assert value["body_size_bytes"] == len(b"larger-than-inline")
    assert body_file.read_bytes() == b"larger-than-inline"


def test_http_get_bytes_cached_skips_cache_when_body_exceeds_limit(monkeypatch, tmp_path) -> None:
    calls = {"count": 0}

    def fake_get(url: str, **_kwargs):
        calls["count"] += 1
        return f"large-{calls['count']}".encode(), {"content-type": "application/zip"}

    cache_root = tmp_path / "cache"
    monkeypatch.setenv("DADOSBR_CACHE_DIR", str(cache_root))
    monkeypatch.setenv("DADOSBR_HTTP_CACHE_MAX_BODY_BYTES", "4")
    monkeypatch.setattr(http, "http_get_bytes", fake_get)

    first_body, first_headers = http.http_get_bytes_cached("https://example.test/data.zip", source_id="test")
    second_body, second_headers = http.http_get_bytes_cached("https://example.test/data.zip", source_id="test")

    assert first_body == b"large-1"
    assert second_body == b"large-2"
    assert calls["count"] == 2
    assert first_headers["x-dadosbr-cache"] == "skip"
    assert first_headers["x-dadosbr-cache-skip-reason"] == "body_too_large"
    assert list(cache_root.rglob("*.json")) == []
    assert list(cache_root.rglob("*.body")) == []


def test_http_get_bytes_cached_passes_ssl_flag_to_fetcher(monkeypatch, tmp_path) -> None:
    seen: dict[str, bool | None] = {}

    def fake_get(url: str, **kwargs):
        seen["verify_ssl"] = kwargs.get("verify_ssl")
        return b"body", {"content-type": "text/plain"}

    monkeypatch.setenv("DADOSBR_CACHE_DIR", str(tmp_path / "cache"))

    body, _headers = http.http_get_bytes_cached(
        "https://example.test/data.csv",
        source_id="test",
        verify_ssl=False,
        fetcher=fake_get,
    )

    assert body == b"body"
    assert seen["verify_ssl"] is False


def test_http_get_bytes_retries_retryable_network_errors(monkeypatch) -> None:
    calls = {"count": 0}

    class FakeResponse:
        status = 200
        headers = {"content-type": "text/plain"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self) -> bytes:
            return b"ok"

    def fake_urlopen(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise urllib.error.URLError("temporary failure")
        return FakeResponse()

    monkeypatch.setenv("DADOSBR_HTTP_RETRIES", "2")
    monkeypatch.setenv("DADOSBR_HTTP_RETRY_BACKOFF_SECONDS", "0")
    monkeypatch.setattr(http.urllib.request, "urlopen", fake_urlopen)

    body, _headers = http.http_get_bytes("https://example.test/data.csv", source_id="test")

    assert body == b"ok"
    assert calls["count"] == 2


def test_http_get_bytes_cached_returns_stale_cache_on_retryable_fetch_error(monkeypatch, tmp_path) -> None:
    cache_root = tmp_path / "cache"
    monkeypatch.setenv("DADOSBR_CACHE_DIR", str(cache_root))
    monkeypatch.setenv("DADOSBR_CACHE_TTL_SECONDS", "1")
    monkeypatch.setenv("DADOSBR_MAX_STALE_SECONDS", "999999999")

    def first_fetch(url: str, **_kwargs):
        return b"cached-body", {"content-type": "text/plain"}

    body, headers = http.http_get_bytes_cached("https://example.test/data.csv", source_id="test", fetcher=first_fetch)
    assert body == b"cached-body"
    assert headers["x-dadosbr-cache"] == "miss"

    cache_file = next(cache_root.rglob("*.json"))
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    payload["created_at"] = "2026-05-09T00:00:00+00:00"
    cache_file.write_text(json.dumps(payload), encoding="utf-8")

    def failing_fetch(url: str, **_kwargs):
        raise DataSourceError("network_error", "offline", "test", source_url=url, retryable=True)

    stale_body, stale_headers = http.http_get_bytes_cached(
        "https://example.test/data.csv",
        source_id="test",
        fetcher=failing_fetch,
    )

    assert stale_body == b"cached-body"
    assert stale_headers["x-dadosbr-cache"] == "stale"
    assert stale_headers["x-dadosbr-cache-stale"] == "true"
    assert int(stale_headers["x-dadosbr-cache-age-seconds"]) > 0


def test_http_get_bytes_cached_strict_mode_rejects_stale_cache(monkeypatch, tmp_path) -> None:
    cache_root = tmp_path / "cache"
    monkeypatch.setenv("DADOSBR_CACHE_DIR", str(cache_root))
    monkeypatch.setenv("DADOSBR_CACHE_TTL_SECONDS", "1")
    monkeypatch.setenv("DADOSBR_MAX_STALE_SECONDS", "0")

    http.http_get_bytes_cached("https://example.test/data.csv", source_id="test", fetcher=lambda *_a, **_k: (b"old", {}))
    cache_file = next(cache_root.rglob("*.json"))
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    payload["created_at"] = "2000-01-01T00:00:00+00:00"
    cache_file.write_text(json.dumps(payload), encoding="utf-8")

    def failing_fetch(url: str, **_kwargs):
        raise DataSourceError("network_error", "offline", "test", source_url=url, retryable=True)

    try:
        http.http_get_bytes_cached(
            "https://example.test/data.csv",
            source_id="test",
            fetcher=failing_fetch,
            strict=True,
        )
    except DataSourceError as exc:
        assert exc.code == "network_error"
    else:  # pragma: no cover
        raise AssertionError("strict mode should not return stale cache")


def test_stale_age_allowed_disables_stale_when_limit_zero(monkeypatch) -> None:
    monkeypatch.setenv("DADOSBR_MAX_STALE_SECONDS", "0")

    assert http._stale_age_allowed(1) is False
