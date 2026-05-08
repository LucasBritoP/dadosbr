from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ADMIN_TOKEN = "admin-test-token"


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    workspace = Path(tempfile.mkdtemp(prefix="dadosbr-admin-mcp-"))
    server: ThreadingHTTPServer | None = None
    try:
        web_root = prepare_receita_fixture_site(repo_root=repo_root, workspace=workspace)
        server = start_fixture_server(web_root)
        base_url = f"http://127.0.0.1:{server.server_port}/"
        result = asyncio.run(run_admin_sync(repo_root=repo_root, workspace=workspace, base_url=base_url))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        shutil.rmtree(workspace, ignore_errors=True)


def prepare_receita_fixture_site(*, repo_root: Path, workspace: Path) -> Path:
    web_root = workspace / "receita_site"
    period_dir = web_root / "2026-05"
    period_dir.mkdir(parents=True, exist_ok=True)

    fixture_dir = repo_root / "tests" / "fixtures" / "receita_cnpj"
    zip_names = []
    for source in sorted(fixture_dir.glob("*.zip")):
        shutil.copy2(source, period_dir / source.name)
        zip_names.append(source.name)

    (web_root / "index.html").write_text('<a href="2026-05/">2026-05/</a>\n', encoding="utf-8")
    (period_dir / "index.html").write_text(
        "\n".join(f'<a href="{name}">{name}</a>' for name in zip_names),
        encoding="utf-8",
    )
    return web_root


def start_fixture_server(web_root: Path) -> ThreadingHTTPServer:
    handler = partial(SimpleHTTPRequestHandler, directory=str(web_root))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, name="dadosbr-receita-fixture", daemon=True)
    thread.start()
    return server


async def run_admin_sync(*, repo_root: Path, workspace: Path, base_url: str) -> dict[str, Any]:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(repo_root / "src"),
            "DADOSBR_CACHE_DIR": str(workspace / ".dadosbr" / "cache"),
            "DADOSBR_HTTP_RETRIES": "1",
            "DADOSBR_HTTP_RETRY_BACKOFF_SECONDS": "0.05",
            "DADOSBR_RECEITA_CNPJ_BASE_URL": base_url,
            "DADOSBR_ENABLE_ADMIN_MCP": "1",
            "DADOSBR_ADMIN_TOKEN": ADMIN_TOKEN,
        }
    )
    params = StdioServerParameters(
        command=os.environ.get("PYTHON", "python"),
        args=["-m", "dadosbr.mcp.server"],
        env=env,
        cwd=str(workspace),
    )
    started = time.perf_counter()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await asyncio.wait_for(session.initialize(), timeout=15)
            sync_response = await asyncio.wait_for(
                session.call_tool(
                    "admin_sync_cnpj",
                    {
                        "period": "latest",
                        "groups": "empresas,estabelecimentos,socios,simples,domains",
                        "max_files": 0,
                        "admin_token": ADMIN_TOKEN,
                    },
                ),
                timeout=60,
            )
            sync_payload = _payload(sync_response)
            status_response = await asyncio.wait_for(session.call_tool("get_cnpj_status", {}), timeout=15)
            company_response = await asyncio.wait_for(
                session.call_tool("get_cnpj_company", {"cnpj": "12345678000190"}),
                timeout=15,
            )
            partners_response = await asyncio.wait_for(
                session.call_tool("get_cnpj_partners", {"cnpj": "12345678000190"}),
                timeout=15,
            )

    status_payload = _payload(status_response)
    company_payload = _payload(company_response)
    partners_payload = _payload(partners_response)
    counts = (status_payload.get("records") or [{}])[0].get("counts", {})
    ok = (
        sync_payload.get("ok") is True
        and status_payload.get("ok") is True
        and company_payload.get("ok") is True
        and partners_payload.get("ok") is True
        and counts.get("empresas") == 1
        and counts.get("estabelecimentos") == 1
        and counts.get("socios") == 1
        and counts.get("simples") == 1
    )
    return {
        "ok": ok,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "base_url": base_url,
        "sync_records": len(sync_payload.get("records", [])),
        "counts": counts,
        "company_sample": (company_payload.get("records") or [{}])[0],
        "partners_count": len(partners_payload.get("records", [])),
        "errors": {
            "sync": sync_payload.get("error"),
            "status": status_payload.get("error"),
            "company": company_payload.get("error"),
            "partners": partners_payload.get("error"),
        },
    }


def _payload(response: Any) -> dict[str, Any]:
    if not getattr(response, "content", None):
        return {"ok": False, "error": {"code": "empty_response"}}
    return json.loads(response.content[0].text)


if __name__ == "__main__":
    raise SystemExit(main())
