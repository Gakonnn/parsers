FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    fonts-liberation \
    libnss3 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    libasound2 \
    libxss1 \
    libxrandr2 \
    xdg-utils \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /etc/apt/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends google-chrome-stable \
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
import shutil
from pathlib import Path

import parser_2gis

package_root = Path(parser_2gis.__file__).resolve().parent
local_package_root = Path("/app/unified_sources/2gis/parser_2gis")
if not local_package_root.exists():
    raise SystemExit(f"Local parser_2gis package not found: {local_package_root}")

shutil.copytree(local_package_root, package_root, dirs_exist_ok=True)
print(f'Replaced parser-2gis package with local stable package from {local_package_root}')

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
    PARSERS_2GIS_BINARY=/usr/bin/google-chrome-stable

EXPOSE 8090

CMD ["python", "parsers_hub/server.py"]
