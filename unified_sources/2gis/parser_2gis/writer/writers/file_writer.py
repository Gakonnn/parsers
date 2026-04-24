from __future__ import annotations

from abc import ABC, abstractmethod
import json
import os
import uuid
from typing import TYPE_CHECKING, Any, IO

from ...logger import logger

if TYPE_CHECKING:
    from ..options import WriterOptions

try:
    import psycopg2
    from psycopg2.extras import Json
except ModuleNotFoundError:  # pragma: no cover
    psycopg2 = None
    Json = None


class FileWriter(ABC):
    """Base writer."""
    def __init__(self, file_path: str, writer_options: WriterOptions) -> None:
        self._file_path = file_path
        self._options = writer_options
        self._live_db_conn = None
        self._live_db_source = os.environ.get("PARSER_LIVE_DB_SOURCE", "").strip()
        self._live_db_mode = os.environ.get("PARSER_LIVE_DB_MODE", "").strip().lower()
        self._live_db_url = os.environ.get("PARSER_LIVE_DB_URL", "").strip()
        self._live_db_run_id = os.environ.get("PARSER_LIVE_DB_RUN_ID", "").strip() or str(uuid.uuid4())
        self._live_db_enabled = (
            bool(self._live_db_url)
            and self._live_db_mode in {"1", "true", "yes", "on"}
            and self._live_db_source == "2gis"
            and psycopg2 is not None
            and Json is not None
        )
        self._live_db_records = 0
        if self._live_db_enabled:
            self._init_live_db()

    @abstractmethod
    def write(self, catalog_doc: Any) -> None:
        """Write Catalog Item API JSON document retrieved by parser."""
        pass

    def _open_file(self, file_path: str, mode: str = 'r') -> IO[Any]:
        return open(file_path, mode, encoding=self._options.encoding,
                    newline='', errors='replace')

    def _check_catalog_doc(self, catalog_doc: Any, verbose: bool = True) -> bool:
        """Check Catalog Item API JSON document for errors.

        Args:
            catalog_doc: Catalog Item API JSON document.
            verbose: Whether to report about found errors.

        Returns:
            `True` if document passed all checks.
            `False` if errors found in document.
        """
        try:
            assert isinstance(catalog_doc, dict)

            if 'error' in catalog_doc['meta']:  # An error is found
                if verbose:
                    error_msg = catalog_doc['meta']['error'].get('message', None)
                    if error_msg:
                        logger.error('Сервер ответил ошибкой: %s', error_msg)
                    else:
                        logger.error('Сервер ответил неизвестной ошибкой.')

                return False

            assert catalog_doc['meta']['code'] == 200
            assert 'result' in catalog_doc
            assert 'items' in catalog_doc['result']
            assert isinstance(catalog_doc['result']['items'], list)
            assert len(catalog_doc['result']['items']) > 0
            assert isinstance(catalog_doc['result']['items'][0], dict)

            if len(catalog_doc['result']['items']) > 1 and verbose:
                logger.warning('Сервер вернул больше одного ответа.')

            return True
        except (KeyError, AssertionError):
            if verbose:
                logger.error('Сервер ответил неизвестным документом.')
            return False

    def __enter__(self) -> FileWriter:
        self._file = self._open_file(self._file_path, 'w')
        return self

    def __exit__(self, *exc_info) -> None:
        self._file.close()
        if self._live_db_enabled and self._live_db_conn is not None:
            status = "completed" if not exc_info or exc_info[0] is None else "failed"
            processed = int(getattr(self, "_wrote_count", self._live_db_records))
            self._finalize_live_db(status=status, processed=processed)
            self._live_db_conn.close()

    def _init_live_db(self) -> None:
        self._live_db_conn = psycopg2.connect(self._live_db_url)
        self._live_db_conn.autocommit = True
        with self._live_db_conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS parser_runs (
                    run_id UUID PRIMARY KEY,
                    source TEXT NOT NULL,
                    status TEXT NOT NULL,
                    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS parser_records (
                    id BIGSERIAL PRIMARY KEY,
                    run_id UUID NOT NULL REFERENCES parser_runs(run_id) ON DELETE CASCADE,
                    source TEXT NOT NULL,
                    external_id TEXT NOT NULL DEFAULT '',
                    payload JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                "INSERT INTO parser_runs (run_id, source, status, metrics) "
                "VALUES (%s::uuid, %s, %s, %s::jsonb) "
                "ON CONFLICT (run_id) DO NOTHING",
                (self._live_db_run_id, "2gis", "running", json.dumps({})),
            )
        logger.info("Live DB mode enabled for 2GIS, run_id=%s", self._live_db_run_id)

    def _live_db_insert(self, payload: dict[str, Any], external_id: str = "") -> None:
        if not self._live_db_enabled or self._live_db_conn is None:
            return
        with self._live_db_conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO parser_records (run_id, source, external_id, payload)
                VALUES (%s::uuid, %s, %s, %s)
                """,
                (self._live_db_run_id, "2gis", external_id, Json(payload)),
            )
        self._live_db_records += 1

    def _finalize_live_db(self, *, status: str, processed: int) -> None:
        if self._live_db_conn is None:
            return
        metrics = {
            "processed": processed,
            "skipped": 0,
            "errors": 0 if status == "completed" else 1,
            "output_path": self._file_path,
        }
        with self._live_db_conn.cursor() as cur:
            cur.execute(
                """
                UPDATE parser_runs
                SET status = %s, metrics = %s::jsonb
                WHERE run_id = %s::uuid
                """,
                (status, json.dumps(metrics, ensure_ascii=False), self._live_db_run_id),
            )
