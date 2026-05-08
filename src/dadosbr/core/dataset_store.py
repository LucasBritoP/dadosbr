from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class DatasetStore:
    def __init__(self, root: str | Path | None = None) -> None:
        default_root = Path(".dadosbr") / "datasets"
        resolved_root = Path(root or os.getenv("DADOSBR_DATASET_DIR") or default_root)
        self.root = resolved_root
        self.root.mkdir(parents=True, exist_ok=True)

    def dataset_dir(self, source_id: str, period: str) -> Path:
        path = self.root / source_id / period
        path.mkdir(parents=True, exist_ok=True)
        return path

    def file_path(self, source_id: str, period: str, filename: str) -> Path:
        return self.dataset_dir(source_id, period) / filename

    def write_manifest(self, source_id: str, period: str, payload: dict[str, Any]) -> Path:
        manifest_path = self.file_path(source_id, period, "manifest.json")
        manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return manifest_path

    def read_manifest(self, source_id: str, period: str) -> dict[str, Any]:
        manifest_path = self.file_path(source_id, period, "manifest.json")
        if not manifest_path.exists():
            return {}
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
