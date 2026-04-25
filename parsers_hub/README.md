# Parsers Hub

Локальный веб-интерфейс для управления тремя парсерами:

- `OLX`
- `2GIS`
- `Krisha`

## Запуск

```bash
/Users/gakon/PycharmProjects/olx/venv/bin/python /Users/gakon/PycharmProjects/olx/parsers_hub/server.py
```

После запуска открой:

```text
http://127.0.0.1:8090
```

## Что умеет

- выбирать один из трёх парсеров
- вводить параметры запуска через форму
- запускать существующие CLI-скрипты без переписывания их логики
- ставить задачу на паузу и продолжать (`Пауза` / `Старт`)
- перезапускать завершённую задачу (`Перезапуск`)
- смотреть статус задачи
- смотреть live-лог
- останавливать активную задачу (`Стоп`)
- сохранять текущий результат и лог в recovery-папку (`Сохранить текущий результат`)
- автоматически сохранять recovery-данные при ошибке/прерывании
- сохранять результаты в папку `parsers_hub/runs/`

## PostgreSQL режим

Теперь Parsers Hub запускает unified CLI в режиме записи в PostgreSQL (`output-target=db`).

- Основные данные парсинга пишутся в БД (`parser_runs`, `parser_records`)
- В `parsers_hub/runs/<source>/` сохраняется JSON-отчет запуска

Пример DSN:

```text
postgresql://postgres:postgres@127.0.0.1:5432/parsers
```

## 2GIS через домашний IP (Home Worker)

Для `2GIS` в форме появился выбор `Где запускать 2GIS`:

- `home_worker` (по умолчанию) — задача ставится в очередь на сервере и выполняется на домашнем ПК
- `server` — обычный запуск внутри сервера

### 1) На сервере включить токен воркера

Укажи переменную окружения для `parsers_hub`:

```text
PARSERS_WORKER_TOKEN=<любой_длинный_секрет>
```

### 2) Запустить домашний worker на ПК с Wi-Fi IP

```bash
/Users/gakon/PycharmProjects/olx/venv/bin/python /Users/gakon/PycharmProjects/olx/parsers_hub/home_worker_2gis.py \
  --server-url http://46.62.225.70:8090 \
  --token <PARSERS_WORKER_TOKEN>
```

После этого `2GIS` задачи из Hub (режим `home_worker`) будут выполняться локально, а логи и статусы отобразятся в серверном интерфейсе.

## Как это устроено

Фронтенд не заменяет ваши существующие проекты. Он работает как control panel и запускает:

- `/Users/gakon/PycharmProjects/olx/olx_scraper.py`
- `/Users/gakon/PycharmProjects/olx/unified_sources/2gis/parser-2gis.py`
- `/Users/gakon/PycharmProjects/olx/unified_sources/krisha/krisha_phone_parser.py`
