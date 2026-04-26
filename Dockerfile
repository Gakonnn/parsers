FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    ca-certificates \
    curl \
    fonts-liberation \
    libnss3 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    libasound2 \
    libxss1 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . /app

RUN python -m pip install --upgrade pip && \
    python -m pip install --no-cache-dir \
      selenium \
      psycopg2-binary \
      requests \
      "pydantic<2" \
      pychrome==0.2.4 \
      psutil \
      xlsxwriter \
      parser-2gis && \
    python - <<'PY'
from pathlib import Path

import parser_2gis

package_root = Path(parser_2gis.__file__).resolve().parent

main_py = package_root / "parser" / "parsers" / "main.py"
main_text = main_py.read_text(encoding="utf-8")
main_patched = main_text.replace(
    "self._item_response_pattern = r'https://catalog\\.api\\.2gis.[^/]+/.*/items/byid'",
    "self._item_response_pattern = r'https://catalog\\.api\\.2gis\\.[^/]+/.*/items(?:/byid)?(?:\\?.*)?$'",
)
if main_patched == main_text:
    raise SystemExit(f"Patch pattern not found in {main_py}")
main_py.write_text(main_patched, encoding="utf-8")
print(f'Patched parser-2gis API matcher in {main_py}')

catalog_item_py = package_root / "writer" / "models" / "catalog_item.py"
catalog_text = catalog_item_py.read_text(encoding="utf-8")
catalog_patched = catalog_text.replace("locale: str", "locale: Optional[str] = None")
if catalog_patched == catalog_text:
    raise SystemExit(f"Locale patch pattern not found in {catalog_item_py}")
catalog_item_py.write_text(catalog_patched, encoding="utf-8")
print(f'Patched parser-2gis locale optional in {catalog_item_py}')
PY

ENV PARSERS_PROJECT_ROOT=/app \
    PARSERS_PYTHON_BIN=/usr/local/bin/python \
    PARSERS_2GIS_BINARY=

EXPOSE 8090

CMD ["python", "parsers_hub/server.py"]
