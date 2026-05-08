from __future__ import annotations

import argparse
import json
from pathlib import Path

from dadosbr.api.app import app


def main() -> int:
    parser = argparse.ArgumentParser(description="Export or validate DadosBR OpenAPI schema.")
    parser.add_argument("--output", default="", help="Write schema to this path.")
    parser.add_argument("--check", action="store_true", help="Validate schema generation only.")
    args = parser.parse_args()

    schema = app.openapi()
    if schema.get("info", {}).get("title") != "DadosBR API":
        raise SystemExit("unexpected OpenAPI title")
    if "/health" not in schema.get("paths", {}):
        raise SystemExit("missing /health path")

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    if args.check:
        print(f"OpenAPI OK: {len(schema.get('paths', {}))} paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
