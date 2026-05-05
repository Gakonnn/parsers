# OLX.kz parser

Скрипт парсит объявления из выбранной категории `olx.kz` и сохраняет данные в Excel (`.xlsx`).

Что собирает:

- `id`
- `название объявления`
- `цена`
- `описание`
- `категория`
- `местоположение`
- `имя продавца`
- `номер продавца`
- `ссылка`

## Как работает

После запуска программа просит:

1. ссылку на категорию OLX
2. лимит объявлений

Потом она собирает ссылки на объявления из категории и сохраняет результат в Excel.

## Запуск

Обычный интерактивный запуск:

```bash
./venv/bin/python olx_scraper.py
```

Пример ввода:

```text
Введите ссылку на категорию OLX [https://www.olx.kz/elektronika/]:
Введите лимит объявлений [10]: 5
```

Можно передать параметры сразу без ручного ввода:

```bash
./venv/bin/python olx_scraper.py -c "https://www.olx.kz/elektronika/" -l 5 -o result.xlsx
```

## Unified Project (Start)

В проект добавлен стартовый unified-слой для объединения всех парсеров в одной точке запуска.

Текущая структура (всё в одном репозитории):

- `olx`:
  - `olx_scraper.py`
- `krisha`:
  - `unified_sources/krisha/krisha_phone_parser.py`
- `kolesa`:
  - `unified_sources/kolesa/kolesa_phone_parser.py`
- `2gis`:
  - `unified_sources/2gis/parser-2gis.py`

Показать источники:

```bash
./venv/bin/python parser_hub.py list
```

Запустить OLX через unified CLI:

```bash
./venv/bin/python parser_hub.py run olx --category-url "https://www.olx.kz/elektronika/" --limit 5 --output unified_olx.xlsx
```

Показать команду Krisha без запуска (dry-run):

```bash
./venv/bin/python parser_hub.py run --dry-run krisha --listing-limit 10 --output result_random.csv
```

Запустить Krisha через unified CLI:

```bash
./venv/bin/python parser_hub.py run krisha --listing-limit 10 --delay 0.7 --random-delay-min 1.2 --random-delay-max 3.5 --no-proxy --no-headless --output result_random.csv
```

Запустить Kolesa через unified CLI:

```bash
./venv/bin/python parser_hub.py run kolesa --listing-url "https://kolesa.kz/cars/" --listing-limit 10 --no-proxy --output kolesa_results.csv
```

Единый run-report для любого источника:

```bash
./venv/bin/python parser_hub.py run olx --limit 5 --output unified_olx.xlsx --report-json unified_runs/reports/olx_last.json
```

Режим записи в PostgreSQL (без сохранения итогового файла):

```bash
DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:5432/parsers" \
./venv/bin/python parser_hub.py run olx --limit 5 --output-target db --output tmp_olx.xlsx
```

Режим и в файл, и в БД:

```bash
DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:5432/parsers" \
./venv/bin/python parser_hub.py run krisha --output-target both --output result_random.csv
```

После выполнения unified CLI всегда печатает summary:

- `processed`
- `skipped`
- `errors`
- `status`
- `output_path`

Точность метрик:

- `olx`: `processed` считается по строкам в итоговом `xlsx`
- `krisha`: `processed` считается по строкам `csv`, `skipped/errors` уточняются по колонкам `status/error`
- `kolesa`: `processed` считается по строкам `csv`, `skipped/errors` уточняются по колонкам `status/error`
- `2gis`: `processed` считается по строкам итогового файла (`xlsx/csv/json`)
- для режима `db` создаются таблицы `parser_runs` и `parser_records` (автоматически при первом запуске)

Текущий статус миграции:

- `olx` - готов к запуску из unified CLI
- `krisha` - готов к запуску из unified CLI
- `kolesa` - готов к запуску из unified CLI
- `2gis` - готов к запуску из unified CLI

## Unified Dependencies

После переноса `krisha` и `2gis` в этот репозиторий установи зависимости одной командой:

```bash
./scripts/bootstrap_unified_env.sh
```

Скрипт устанавливает:

- `selenium` (для `krisha`)
- `psycopg2-binary` (для PostgreSQL режима)
- пакет `2gis` в editable-режиме вместе с зависимостями (`pydantic`, `requests`, `xlsxwriter`, и др.)

## Важно

Скрипт использует:

- HTML страницы категории
- HTML страницы объявления
- API телефона продавца вида `https://www.olx.kz/api/v1/offers/<ID>/limited-phones/`

Если OLX изменит разметку страницы, пагинацию или ограничит доступ к номеру, часть полей может стать пустой.
