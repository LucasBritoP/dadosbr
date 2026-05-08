from __future__ import annotations

import csv
from io import TextIOWrapper
from typing import Iterable, Iterator


def decode_text(data: bytes, encodings: tuple[str, ...] = ("utf-8-sig", "windows-1252", "latin-1")) -> str:
    for encoding in encodings:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("decode_text", b"", 0, 1, "unable to decode payload")


def iter_csv_rows(
    file_obj,
    delimiter: str = ";",
    encoding: str = "windows-1252",
) -> Iterator[dict[str, str]]:
    wrapper = TextIOWrapper(file_obj, encoding=encoding, newline="")
    reader = csv.DictReader(wrapper, delimiter=delimiter)
    for row in reader:
        yield {str(key): str(value) for key, value in row.items()}


def limit_rows(rows: Iterable[dict[str, str]], limit: int) -> list[dict[str, str]]:
    safe_limit = max(1, int(limit))
    output: list[dict[str, str]] = []
    for row in rows:
        output.append(row)
        if len(output) >= safe_limit:
            break
    return output
