from __future__ import annotations

import json
import os
from typing import Any

from ...logger import logger
from .file_writer import FileWriter
from unified_parsers.phone_utils import normalize_2gis_contact_phones


class JSONWriter(FileWriter):
    """Writer to JSON file."""
    def __enter__(self) -> JSONWriter:
        super().__enter__()
        self._wrote_count = 0
        self._file.write('[')
        return self

    def __exit__(self, *exc_info) -> None:
        if self._wrote_count > 0:
            self._file.write(os.linesep)
        self._file.write(']')
        super().__exit__(*exc_info)

    def _writedoc(self, catalog_doc: Any) -> None:
        """Write a `catalog_doc` into JSON document."""
        item = normalize_2gis_contact_phones(catalog_doc['result']['items'][0])

        if self._options.verbose:
            try:
                name = item['name_ex']['primary']
            except KeyError:
                name = '...'

            logger.info('Парсинг [%d] > %s', self._wrote_count + 1, name)

        if self._wrote_count > 0:
            self._file.write(',')

        self._file.write(os.linesep)
        self._file.write(json.dumps(item, ensure_ascii=False))
        self._wrote_count += 1

    def write(self, catalog_doc: Any) -> None:
        """Write Catalog Item API JSON document down to JSON file.

        Args:
            catalog_doc: Catalog Item API JSON document.
        """
        if not self._check_catalog_doc(catalog_doc):
            return

        self._writedoc(catalog_doc)
        item = normalize_2gis_contact_phones(catalog_doc['result']['items'][0])
        external_id = str(item.get('id', '') or item.get('url', '') or item.get('name', '')).strip()
        self._live_db_insert(item, external_id)
