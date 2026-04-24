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
    xvfb \
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
      xlsxwriter

ENV PARSERS_PROJECT_ROOT=/app \
    PARSERS_PYTHON_BIN=/usr/local/bin/python \
    CHROME_BINARY=/usr/bin/chromium \
    CHROMIUM_BINARY=/usr/bin/chromium

EXPOSE 8090

CMD ["python", "parsers_hub/server.py"]
