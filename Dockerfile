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

main_py = Path(parser_2gis.__file__).resolve().parent / "parser" / "parsers" / "main.py"
text = main_py.read_text(encoding="utf-8")
patched = text.replace(
    "self._item_response_pattern = r'https://catalog\\.api\\.2gis.[^/]+/.*/items/byid'",
    "self._item_response_pattern = r'https://catalog\\.api\\.2gis\\.[^/]+/.*/items(?:/byid)?(?:\\?.*)?$'",
)
if patched == text:
    raise SystemExit(f"Patch pattern not found in {main_py}")
main_py.write_text(patched, encoding="utf-8")
print(f'Patched parser-2gis API matcher in {main_py}')
PY

ENV PARSERS_PROJECT_ROOT=/app \
    PARSERS_PYTHON_BIN=/usr/local/bin/python \
    PARSERS_2GIS_BINARY=

EXPOSE 8090

CMD ["python", "parsers_hub/server.py"]
