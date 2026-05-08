from __future__ import annotations

import csv
import html.parser
import os
import re
import sqlite3
import zipfile
from datetime import UTC, datetime
from io import TextIOWrapper
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urljoin, urlsplit

from dadosbr.core import DataSourceError, make_failure, make_success
from dadosbr.core.dataset_store import DatasetStore
from dadosbr.core.http import (
    http_download_to_file,
    http_get_bytes,
    http_get_bytes_cached,
    http_response_metadata,
)
from dadosbr.core.utils import parse_maybe_br_decimal, sha256_json

SOURCE_ID = "receita_cnpj"
DEFAULT_BASE_URL = "https://arquivos.receitafederal.gov.br/dados/cnpj/dados_abertos_cnpj/"
BASE_URL = DEFAULT_BASE_URL

GROUP_PREFIXES: dict[str, tuple[str, ...]] = {
    "empresas": ("Empresas",),
    "estabelecimentos": ("Estabelecimentos",),
    "socios": ("Socios",),
    "simples": ("Simples",),
    "domains": ("Cnaes", "Municipios", "Naturezas", "Motivos", "Paises", "Qualificacoes"),
}

GROUP_TOKENS: dict[str, tuple[str, ...]] = {
    "empresas": ("empresas",),
    "estabelecimentos": ("estabelecimentos",),
    "socios": ("socios",),
    "simples": ("simples",),
    "domains": ("cnaes", "municipios", "naturezas", "motivos", "paises", "qualificacoes"),
}


class _HrefParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)


def discover_latest_cnpj_period() -> dict:
    failures: list[dict[str, str]] = []
    for base_url in _base_urls():
        try:
            body, headers = _fetch_receita_page_bytes(base_url, timeout_seconds=30)
            cache_source_mode, cache_resilience, cache_limitations = http_response_metadata(headers)
            parser = _HrefParser()
            parser.feed(body.decode("utf-8", errors="ignore"))
            periods = sorted({_period_from_href(href) for href in parser.hrefs if _period_from_href(href)})
            if not periods:
                raise DataSourceError(
                    code="source_layout_changed",
                    message="No period directories found in Receita CNPJ index page.",
                    source_id=SOURCE_ID,
                    source_url=base_url,
                )
            latest = periods[-1]
            fallback_source = base_url != _base_url()
            source_mode = cache_source_mode
            if fallback_source and source_mode == "live":
                source_mode = "fallback_source"
            resilience = {"fallback_source": fallback_source, "failures_before_success": failures}
            resilience.update(cache_resilience)
            return make_success(
                source_id=SOURCE_ID,
                source_url=base_url,
                records=[{"period": latest, "base_url": base_url}],
                raw_sha256=sha256_json(periods),
                limitations=cache_limitations,
                source_mode=source_mode,
                resilience=resilience,
            ).model_dump(mode="json")
        except DataSourceError as exc:
            failures.append({"source": base_url, "error": exc.message})

    return make_failure(
        DataSourceError(
            "source_unavailable",
            "No CNPJ period index could be retrieved from configured Receita bases.",
            SOURCE_ID,
            source_url=_base_url(),
            details={"failures": failures},
            retryable=True,
        )
    ).model_dump(mode="json")


def download_cnpj_period(
    period: str = "latest",
    groups: str | list[str] | None = None,
    max_files: int | None = None,
    store: str | Path | DatasetStore | None = None,
) -> dict:
    dataset_store = _resolve_store(store)
    selected_groups = _normalize_groups(groups)
    resolved_period = period
    if period == "latest":
        latest = discover_latest_cnpj_period()
        if not latest.get("ok"):
            return latest
        resolved_period = latest["records"][0]["period"]
        base_urls = [latest["records"][0].get("base_url", _base_url())]
    else:
        base_urls = _base_urls()

    failures: list[dict[str, str]] = []
    for base_url in base_urls:
        period_url = urljoin(base_url, f"{resolved_period}/")
        try:
            return _download_cnpj_period_from_url(
                period_url=period_url,
                resolved_period=resolved_period,
                selected_groups=selected_groups,
                max_files=max_files,
                dataset_store=dataset_store,
            )
        except DataSourceError as exc:
            failures.append({"source": period_url, "error": exc.message})

    return make_failure(
        DataSourceError(
            "source_unavailable",
            "No CNPJ files could be retrieved from configured Receita bases.",
            SOURCE_ID,
            source_url=urljoin(_base_url(), f"{resolved_period}/"),
            details={"failures": failures},
            retryable=True,
        )
    ).model_dump(mode="json")


def _download_cnpj_period_from_url(
    *,
    period_url: str,
    resolved_period: str,
    selected_groups: list[str],
    max_files: int | None,
    dataset_store: DatasetStore,
) -> dict:
    try:
        body, _headers = _fetch_receita_page_bytes(period_url, timeout_seconds=60)
        parser = _HrefParser()
        parser.feed(body.decode("utf-8", errors="ignore"))
        zip_names = _filter_zip_names(parser.hrefs, selected_groups)
        if max_files is not None:
            zip_names = zip_names[: max(0, int(max_files))]
        if not zip_names:
            raise DataSourceError(
                code="source_layout_changed",
                message="No matching ZIP files found for selected CNPJ groups.",
                source_id=SOURCE_ID,
                source_url=period_url,
                details={"groups": selected_groups},
            )

        downloaded: list[dict] = []
        for name in zip_names:
            file_url = urljoin(period_url, name)
            output_path = dataset_store.file_path(SOURCE_ID, resolved_period, Path(name).name)
            size_bytes, _file_headers = http_download_to_file(
                file_url,
                output_path,
                source_id=SOURCE_ID,
                timeout_seconds=120,
            )
            downloaded.append(
                {
                    "name": Path(name).name,
                    "url": file_url,
                    "path": str(output_path),
                    "size_bytes": size_bytes,
                }
            )

        manifest = {"source_id": SOURCE_ID, "period": resolved_period, "downloaded_at": datetime.now(UTC).isoformat(), "files": downloaded}
        dataset_store.write_manifest(SOURCE_ID, resolved_period, manifest)
        return make_success(
            source_id=SOURCE_ID,
            source_url=period_url,
            records=downloaded,
            raw_sha256=sha256_json(downloaded),
        ).model_dump(mode="json")
    except DataSourceError as exc:
        raise exc


def build_cnpj_index(input_dir: str | Path, db_path: str | Path | None = None) -> dict:
    source_path = Path(input_dir)
    if not source_path.exists():
        return make_failure(
            DataSourceError(
                code="validation_error",
                message=f"Input directory does not exist: {source_path}",
                source_id=SOURCE_ID,
            )
        ).model_dump(mode="json")
    db_file = _resolve_db_path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    zip_paths = sorted(source_path.glob("*.zip"))
    if not zip_paths:
        return make_failure(
            DataSourceError(
                code="validation_error",
                message=f"No ZIP files found in {source_path}",
                source_id=SOURCE_ID,
            )
        ).model_dump(mode="json")

    conn = sqlite3.connect(str(db_file))
    try:
        _create_schema(conn)
        _truncate_tables(conn)
        loaded_files = []
        for zip_path in zip_paths:
            loaded = _load_zip_into_db(conn, zip_path)
            loaded_files.append({"file": zip_path.name, "rows": loaded})
        built_at = datetime.now(UTC).isoformat()
        conn.execute("DELETE FROM metadata")
        conn.execute(
            "INSERT INTO metadata (key, value) VALUES (?, ?)",
            ("built_at", built_at),
        )
        conn.commit()
        return make_success(
            source_id=SOURCE_ID,
            source_url=str(source_path),
            records=loaded_files,
            raw_sha256=sha256_json(loaded_files),
        ).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        return make_failure(
            DataSourceError(
                code="parse_error",
                message=str(exc),
                source_id=SOURCE_ID,
                source_url=str(source_path),
            )
        ).model_dump(mode="json")
    finally:
        conn.close()


def get_cnpj_status(db_path: str | Path | None = None) -> dict:
    db_file = _resolve_db_path(db_path)
    if not db_file.exists():
        return make_failure(
            DataSourceError(
                code="index_missing",
                message="CNPJ index not found. Run dadosbr-admin cnpj sync before querying.",
                source_id=SOURCE_ID,
                source_url=str(db_file),
            )
        ).model_dump(mode="json")
    conn = sqlite3.connect(str(db_file))
    try:
        tables = ("empresas", "estabelecimentos", "socios", "simples")
        counts = {}
        for table in tables:
            counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        built_at_row = conn.execute("SELECT value FROM metadata WHERE key='built_at'").fetchone()
        built_at = built_at_row[0] if built_at_row else None
        return make_success(
            source_id=SOURCE_ID,
            source_url=str(db_file),
            records=[{"db_path": str(db_file), "built_at": built_at, "counts": counts}],
            raw_sha256=sha256_json({"built_at": built_at, "counts": counts}),
        ).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        return make_failure(
            DataSourceError("parse_error", str(exc), SOURCE_ID, source_url=str(db_file))
        ).model_dump(mode="json")
    finally:
        conn.close()


def get_cnpj_company(cnpj: str, db_path: str | Path | None = None) -> dict:
    normalized = _normalize_cnpj(cnpj)
    if not normalized:
        return make_failure(
            DataSourceError("validation_error", "Invalid CNPJ.", SOURCE_ID)
        ).model_dump(mode="json")
    db_file = _resolve_db_path(db_path)
    if not db_file.exists():
        return _missing_index_response(db_file)
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT
                e.cnpj,
                e.uf,
                e.situacao_cadastral,
                e.nome_fantasia,
                e.cnae_principal,
                em.razao_social,
                em.natureza_juridica,
                em.capital_social,
                s.opcao_simples,
                s.opcao_mei
            FROM estabelecimentos e
            JOIN empresas em ON em.cnpj_basico = e.cnpj_basico
            LEFT JOIN simples s ON s.cnpj_basico = e.cnpj_basico
            WHERE e.cnpj = ?
            """,
            (normalized,),
        ).fetchone()
        if row is None:
            return make_success(
                source_id=SOURCE_ID,
                source_url=str(db_file),
                records=[],
                raw_sha256=sha256_json([]),
            ).model_dump(mode="json")
        record = dict(row)
        record["capital_social"] = float(record["capital_social"]) if record["capital_social"] is not None else None
        return make_success(
            source_id=SOURCE_ID,
            source_url=str(db_file),
            records=[record],
            raw_sha256=sha256_json(record),
        ).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        return make_failure(DataSourceError("parse_error", str(exc), SOURCE_ID, source_url=str(db_file))).model_dump(mode="json")
    finally:
        conn.close()


def get_cnpj_partners(cnpj: str, db_path: str | Path | None = None) -> dict:
    normalized = _normalize_cnpj(cnpj)
    if not normalized:
        return make_failure(
            DataSourceError("validation_error", "Invalid CNPJ.", SOURCE_ID)
        ).model_dump(mode="json")
    db_file = _resolve_db_path(db_path)
    if not db_file.exists():
        return _missing_index_response(db_file)

    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    try:
        basico = normalized[:8]
        rows = conn.execute(
            """
            SELECT cnpj_basico, nome_socio, cnpj_cpf_socio, qualificacao_socio, data_entrada_sociedade
            FROM socios
            WHERE cnpj_basico = ?
            ORDER BY nome_socio
            """,
            (basico,),
        ).fetchall()
        return make_success(
            source_id=SOURCE_ID,
            source_url=str(db_file),
            records=[dict(row) for row in rows],
            raw_sha256=sha256_json([dict(row) for row in rows]),
        ).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        return make_failure(DataSourceError("parse_error", str(exc), SOURCE_ID, source_url=str(db_file))).model_dump(mode="json")
    finally:
        conn.close()


def search_cnpj_companies(
    q: str = "",
    uf: str = "",
    cnae: str = "",
    situacao: str = "",
    limit: int = 50,
    db_path: str | Path | None = None,
) -> dict:
    db_file = _resolve_db_path(db_path)
    if not db_file.exists():
        return _missing_index_response(db_file)

    safe_limit = max(1, min(int(limit or 50), 1000))
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    try:
        sql = """
            SELECT
                e.cnpj,
                em.razao_social,
                e.nome_fantasia,
                e.uf,
                e.cnae_principal,
                e.situacao_cadastral
            FROM estabelecimentos e
            JOIN empresas em ON em.cnpj_basico = e.cnpj_basico
            WHERE 1=1
        """
        params: list[str | int] = []
        if q:
            sql += " AND (UPPER(em.razao_social) LIKE ? OR UPPER(e.nome_fantasia) LIKE ?)"
            token = f"%{q.upper()}%"
            params.extend([token, token])
        if uf:
            sql += " AND e.uf = ?"
            params.append(uf.upper())
        if cnae:
            sql += " AND e.cnae_principal = ?"
            params.append(cnae)
        if situacao:
            sql += " AND e.situacao_cadastral = ?"
            params.append(situacao)
        sql += " ORDER BY em.razao_social LIMIT ?"
        params.append(safe_limit)
        rows = conn.execute(sql, params).fetchall()
        data = [dict(row) for row in rows]
        return make_success(
            source_id=SOURCE_ID,
            source_url=str(db_file),
            records=data,
            raw_sha256=sha256_json(data),
        ).model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001
        return make_failure(DataSourceError("parse_error", str(exc), SOURCE_ID, source_url=str(db_file))).model_dump(mode="json")
    finally:
        conn.close()


def _resolve_store(store: str | Path | DatasetStore | None) -> DatasetStore:
    if isinstance(store, DatasetStore):
        return store
    if store is None:
        return DatasetStore()
    return DatasetStore(store)


def _resolve_db_path(db_path: str | Path | None) -> Path:
    if db_path is not None:
        return Path(db_path)
    return DatasetStore().root / SOURCE_ID / "index" / "cnpj.sqlite"


def _normalize_groups(groups: str | list[str] | None) -> list[str]:
    if groups is None:
        return list(GROUP_PREFIXES.keys())
    if isinstance(groups, str):
        values = [part.strip().lower() for part in groups.split(",") if part.strip()]
    else:
        values = [str(part).strip().lower() for part in groups if str(part).strip()]
    valid = [group for group in values if group in GROUP_PREFIXES]
    return valid or list(GROUP_PREFIXES.keys())


def _base_url() -> str:
    raw = os.getenv("DADOSBR_RECEITA_CNPJ_BASE_URL", DEFAULT_BASE_URL).strip()
    return raw.rstrip("/") + "/" if raw else DEFAULT_BASE_URL


def _base_urls() -> list[str]:
    urls = [_base_url()]
    raw = os.getenv("DADOSBR_RECEITA_CNPJ_FALLBACK_BASE_URLS", "")
    for part in re.split(r"[,;]", raw):
        value = part.strip()
        if value:
            urls.append(value.rstrip("/") + "/")
    return list(dict.fromkeys(urls))


def _fetch_receita_page_bytes(url: str, *, timeout_seconds: int) -> tuple[bytes, dict[str, str]]:
    return http_get_bytes_cached(
        url,
        source_id=SOURCE_ID,
        timeout_seconds=timeout_seconds,
        cache_namespace="receita_cnpj_pages",
        fetcher=http_get_bytes,
        max_stale_seconds=30 * 24 * 60 * 60,
    )


def _period_from_href(href: str) -> str:
    name = _href_filename(href).strip("/")
    if re.fullmatch(r"\d{4}-\d{2}", name) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", name):
        return name
    return ""


def _filter_zip_names(hrefs: Iterable[str], groups: list[str]) -> list[str]:
    output: list[str] = []
    for href in hrefs:
        name = _href_filename(href)
        if not name.lower().endswith(".zip"):
            continue
        if _filename_matches_any_group(name, groups):
            output.append(name)
    return sorted(dict.fromkeys(output))


def _href_filename(href: str) -> str:
    path = urlsplit(str(href).strip()).path
    return Path(unquote(path)).name


def _filename_matches_any_group(filename: str, groups: Iterable[str]) -> bool:
    normalized = _normalize_filename(filename)
    return any(any(token in normalized for token in GROUP_TOKENS[group]) for group in groups)


def _normalize_filename(filename: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", Path(filename).name.lower())


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS empresas (
            cnpj_basico TEXT PRIMARY KEY,
            razao_social TEXT,
            natureza_juridica TEXT,
            qualificacao_responsavel TEXT,
            capital_social REAL,
            porte_empresa TEXT,
            ente_federativo_responsavel TEXT
        );
        CREATE TABLE IF NOT EXISTS estabelecimentos (
            cnpj TEXT PRIMARY KEY,
            cnpj_basico TEXT,
            cnpj_ordem TEXT,
            cnpj_dv TEXT,
            identificador_matriz_filial TEXT,
            nome_fantasia TEXT,
            situacao_cadastral TEXT,
            data_situacao_cadastral TEXT,
            motivo_situacao_cadastral TEXT,
            data_inicio_atividade TEXT,
            cnae_principal TEXT,
            cnae_secundaria TEXT,
            tipo_logradouro TEXT,
            logradouro TEXT,
            numero TEXT,
            complemento TEXT,
            bairro TEXT,
            cep TEXT,
            uf TEXT,
            municipio TEXT,
            ddd1 TEXT,
            telefone1 TEXT,
            ddd2 TEXT,
            telefone2 TEXT,
            correio_eletronico TEXT,
            situacao_especial TEXT,
            data_situacao_especial TEXT
        );
        CREATE TABLE IF NOT EXISTS socios (
            cnpj_basico TEXT,
            identificador_socio TEXT,
            nome_socio TEXT,
            cnpj_cpf_socio TEXT,
            qualificacao_socio TEXT,
            data_entrada_sociedade TEXT,
            pais TEXT,
            representante_legal TEXT,
            nome_representante TEXT,
            qualificacao_representante TEXT,
            faixa_etaria TEXT
        );
        CREATE TABLE IF NOT EXISTS simples (
            cnpj_basico TEXT PRIMARY KEY,
            opcao_simples TEXT,
            data_opcao_simples TEXT,
            data_exclusao_simples TEXT,
            opcao_mei TEXT,
            data_opcao_mei TEXT,
            data_exclusao_mei TEXT
        );
        CREATE TABLE IF NOT EXISTS cnaes (
            code TEXT PRIMARY KEY,
            description TEXT
        );
        CREATE TABLE IF NOT EXISTS municipios (
            code TEXT PRIMARY KEY,
            name TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_estabelecimentos_razao_lookup ON estabelecimentos (uf, situacao_cadastral, cnae_principal);
        CREATE INDEX IF NOT EXISTS idx_socios_cnpj_basico ON socios (cnpj_basico);
        """
    )
    conn.commit()


def _truncate_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        DELETE FROM metadata;
        DELETE FROM empresas;
        DELETE FROM estabelecimentos;
        DELETE FROM socios;
        DELETE FROM simples;
        DELETE FROM cnaes;
        DELETE FROM municipios;
        """
    )
    conn.commit()


def _load_zip_into_db(conn: sqlite3.Connection, zip_path: Path) -> int:
    filename = zip_path.name
    table = _table_from_filename(filename)
    if not table:
        return 0
    inserted = 0
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            if not member.lower().endswith(".csv"):
                continue
            with zf.open(member) as raw_file:
                with TextIOWrapper(
                    raw_file,
                    encoding="latin-1",
                    errors="ignore",
                    newline="",
                ) as decoded:
                    reader = csv.reader(decoded, delimiter=";")
                    for row in reader:
                        if not row:
                            continue
                        _insert_row(conn, table, row)
                        inserted += 1
    conn.commit()
    return inserted


def _table_from_filename(filename: str) -> str | None:
    normalized = _normalize_filename(filename)
    for table in GROUP_TOKENS["domains"]:
        if table in normalized:
            return table
    for group in ("empresas", "estabelecimentos", "socios", "simples"):
        if any(token in normalized for token in GROUP_TOKENS[group]):
            return group
    return None


def _insert_row(conn: sqlite3.Connection, table: str, row: list[str]) -> None:
    if table == "empresas":
        values = (row + [""] * 7)[:7]
        conn.execute(
            """
            INSERT OR REPLACE INTO empresas
            (cnpj_basico, razao_social, natureza_juridica, qualificacao_responsavel, capital_social, porte_empresa, ente_federativo_responsavel)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _digits(values[0]).zfill(8),
                values[1].strip(),
                values[2].strip(),
                values[3].strip(),
                parse_maybe_br_decimal(values[4]),
                values[5].strip(),
                values[6].strip(),
            ),
        )
        return
    if table == "cnaes":
        values = (row + [""] * 2)[:2]
        conn.execute(
            "INSERT OR REPLACE INTO cnaes (code, description) VALUES (?, ?)",
            (values[0].strip(), values[1].strip()),
        )
        return
    if table == "municipios":
        values = (row + [""] * 2)[:2]
        conn.execute(
            "INSERT OR REPLACE INTO municipios (code, name) VALUES (?, ?)",
            (values[0].strip(), values[1].strip()),
        )
        return
    if table == "estabelecimentos":
        values = (row + [""] * 30)[:30]
        cnpj_basico = _digits(values[0]).zfill(8)
        cnpj_ordem = _digits(values[1]).zfill(4)
        cnpj_dv = _digits(values[2]).zfill(2)
        cnpj = f"{cnpj_basico}{cnpj_ordem}{cnpj_dv}"
        conn.execute(
            """
            INSERT OR REPLACE INTO estabelecimentos
            (cnpj, cnpj_basico, cnpj_ordem, cnpj_dv, identificador_matriz_filial, nome_fantasia, situacao_cadastral, data_situacao_cadastral, motivo_situacao_cadastral, data_inicio_atividade, cnae_principal, cnae_secundaria, tipo_logradouro, logradouro, numero, complemento, bairro, cep, uf, municipio, ddd1, telefone1, ddd2, telefone2, correio_eletronico, situacao_especial, data_situacao_especial)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cnpj,
                cnpj_basico,
                cnpj_ordem,
                cnpj_dv,
                values[3].strip(),
                values[4].strip(),
                values[5].strip(),
                _normalize_date(values[6]),
                values[7].strip(),
                _normalize_date(values[11]),
                values[12].strip(),
                values[13].strip(),
                values[14].strip(),
                values[15].strip(),
                values[16].strip(),
                values[17].strip(),
                values[18].strip(),
                values[19].strip(),
                values[20].strip(),
                values[21].strip(),
                values[22].strip(),
                values[23].strip(),
                values[24].strip(),
                values[25].strip(),
                values[27].strip(),
                values[28].strip(),
                _normalize_date(values[29]),
            ),
        )
        return
    if table == "socios":
        values = (row + [""] * 11)[:11]
        conn.execute(
            """
            INSERT INTO socios
            (cnpj_basico, identificador_socio, nome_socio, cnpj_cpf_socio, qualificacao_socio, data_entrada_sociedade, pais, representante_legal, nome_representante, qualificacao_representante, faixa_etaria)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _digits(values[0]).zfill(8),
                values[1].strip(),
                values[2].strip(),
                values[3].strip(),
                values[4].strip(),
                _normalize_date(values[5]),
                values[6].strip(),
                values[7].strip(),
                values[8].strip(),
                values[9].strip(),
                values[10].strip(),
            ),
        )
        return
    if table == "simples":
        values = (row + [""] * 7)[:7]
        conn.execute(
            """
            INSERT OR REPLACE INTO simples
            (cnpj_basico, opcao_simples, data_opcao_simples, data_exclusao_simples, opcao_mei, data_opcao_mei, data_exclusao_mei)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _digits(values[0]).zfill(8),
                values[1].strip(),
                _normalize_date(values[2]),
                _normalize_date(values[3]),
                values[4].strip(),
                _normalize_date(values[5]),
                _normalize_date(values[6]),
            ),
        )


def _digits(text: str) -> str:
    return "".join(ch for ch in str(text or "") if ch.isdigit())


def _normalize_cnpj(cnpj: str) -> str:
    digits = _digits(cnpj)
    if len(digits) != 14:
        return ""
    return digits


def _normalize_date(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
    return raw


def _missing_index_response(db_file: Path) -> dict:
    return make_failure(
        DataSourceError(
            code="index_missing",
            message="CNPJ index not found. Run dadosbr-admin cnpj sync --period latest --groups empresas,estabelecimentos,socios,simples,domains",
            source_id=SOURCE_ID,
            source_url=str(db_file),
        )
    ).model_dump(mode="json")
