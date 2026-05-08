from __future__ import annotations

import re
import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("windows_user_path", re.compile(r"(?i)[A-Z]:\\Users\\")),
    ("unix_home_path", re.compile(r"(?i)/(Users|home)/[A-Za-z0-9._-]+")),
    ("local_username_panze", re.compile(r"(?i)\bpanze\b")),
    ("github_token", re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}")),
    ("openai_or_generic_sk_token", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("google_api_key", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("slack_token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}")),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("bearer_literal_token", re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-.=]{24,}")),
    (
        "env_secret_assignment",
        re.compile(
            r"(?i)(GITHUB_PAT_TOKEN|GITHUB_TOKEN|OPENAI_API_KEY|ANTHROPIC_API_KEY|"
            r"GOOGLE_API_KEY|SUPABASE_SERVICE_ROLE_KEY|SUPABASE_ACCESS_TOKEN|"
            r"DADOSBR_ADMIN_TOKEN)\s*[:=]\s*[\"']?[^\s\"']{8,}"
        ),
    ),
    ("possible_cpf", re.compile(r"\b[0-9]{3}\.?[0-9]{3}\.?[0-9]{3}-?[0-9]{2}\b")),
    ("email_address", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
)


def git_ls_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [ROOT / line for line in result.stdout.splitlines() if line]


def is_probably_binary(path: Path) -> bool:
    chunk = path.read_bytes()[:4096]
    return b"\0" in chunk


def scan_text(label: str, text: str) -> list[str]:
    findings: list[str] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        for name, pattern in PATTERNS:
            if pattern.search(line):
                findings.append(f"{label}:{line_no}: {name}")
    return findings


def scan_file(path: Path) -> list[str]:
    rel = path.relative_to(ROOT).as_posix()
    if path.suffix.lower() == ".zip":
        findings: list[str] = []
        with zipfile.ZipFile(path) as archive:
            for item in archive.infolist():
                if item.file_size > 5 * 1024 * 1024:
                    continue
                data = archive.read(item)
                if b"\0" in data[:4096]:
                    continue
                text = data.decode("utf-8", errors="replace")
                findings.extend(scan_text(f"{rel}::{item.filename}", text))
        return findings
    if is_probably_binary(path):
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    return scan_text(rel, text)


def main() -> int:
    findings: list[str] = []
    for path in git_ls_files():
        if path.name == "uv.lock":
            continue
        findings.extend(scan_file(path))
    if findings:
        print("Public safety scan failed. Matches are redacted by pattern only:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    print("Public safety scan passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
