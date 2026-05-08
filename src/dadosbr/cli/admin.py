from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dadosbr.connectors.receita_cnpj import (
    build_cnpj_index,
    download_cnpj_period,
    get_cnpj_status,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="dadosbr-admin", description="DadosBR admin commands")
    sub = parser.add_subparsers(dest="entity", required=True)

    cnpj = sub.add_parser("cnpj", help="Manage Receita CNPJ local dataset and index")
    cnpj_sub = cnpj.add_subparsers(dest="action", required=True)

    cnpj_sub.add_parser("status", help="Show local CNPJ index status")

    sync = cnpj_sub.add_parser("sync", help="Download Receita CNPJ files and rebuild index")
    sync.add_argument("--period", default="latest")
    sync.add_argument("--groups", default="empresas,estabelecimentos,socios,simples,domains")
    sync.add_argument("--max-files", type=int, default=0)
    sync.add_argument("--dataset-dir", default="")
    sync.add_argument("--db-path", default="")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.entity != "cnpj":
        output = {"ok": False, "error": {"code": "validation_error", "message": f"Unknown entity: {args.entity}"}}
        print(json.dumps(output, ensure_ascii=False))
        return 1

    if args.action == "status":
        status = get_cnpj_status(db_path=args.db_path or None)
        print(json.dumps(status, ensure_ascii=False))
        return 0 if status.get("ok") else 1

    if args.action == "sync":
        dataset_dir = Path(args.dataset_dir) if args.dataset_dir else None
        download = download_cnpj_period(
            period=args.period,
            groups=args.groups,
            max_files=args.max_files if args.max_files > 0 else None,
            store=dataset_dir,
        )
        if not download.get("ok"):
            print(json.dumps(download, ensure_ascii=False))
            return 1

        downloaded_files = download.get("records", [])
        if not downloaded_files:
            output = {"ok": False, "error": {"code": "source_unavailable", "message": "No files downloaded for CNPJ sync."}}
            print(json.dumps(output, ensure_ascii=False))
            return 1

        period_dir = Path(downloaded_files[0]["path"]).parent
        build = build_cnpj_index(period_dir, db_path=args.db_path or None)
        output = {"ok": bool(build.get("ok")), "download": download, "build": build}
        print(json.dumps(output, ensure_ascii=False))
        return 0 if output["ok"] else 1

    output = {"ok": False, "error": {"code": "validation_error", "message": f"Unknown action: {args.action}"}}
    print(json.dumps(output, ensure_ascii=False))
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
