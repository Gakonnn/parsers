from __future__ import annotations

import html
import json
import mimetypes
import os
import queue
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING

from ..logger import setup_cli_logger, setup_gui_logger
from ..runner import GUIRunner

if TYPE_CHECKING:
    from ..config import Configuration


class _WebState:
    def __init__(self, urls: list[str] | None, output_path: str | None,
                 format: str | None, config: Configuration) -> None:
        self.lock = threading.Lock()
        self.urls = list(urls) if urls else []
        self.output_path = output_path or ''
        self.format = format if format in ('csv', 'xlsx', 'json') else 'csv'
        self.runner: GUIRunner | None = None
        self.controller: threading.Thread | None = None
        self.stop_requested = False
        self.log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.logs: list[str] = []
        self.config = config
        self.auto_restart = True
        self.auto_max_attempts = 30
        self.auto_probe_seconds = 12
        self.auto_first_parse_deadline = 5.0
        self.auto_min_records = 3
        self.auto_error_budget = 1
        self.auto_prewarm_delay = 2.5
        self.auto_current_attempt = 0
        self.attempt_started_at = 0.0
        self.attempt_parsed_events = 0
        self.attempt_first_parse_delay: float | None = None
        self.attempt_error_events = 0

    def drain_logs(self) -> None:
        while True:
            try:
                _, message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.logs.append(message)
            if 'Парсинг [' in message and self.attempt_started_at > 0:
                self.attempt_parsed_events += 1
                if self.attempt_first_parse_delay is None:
                    self.attempt_first_parse_delay = max(0.0, time.time() - self.attempt_started_at)
            if self.attempt_started_at > 0 and ('Данные не получены' in message or 'ERROR' in message):
                self.attempt_error_events += 1


def _is_runner_alive(state: _WebState) -> bool:
    return state.runner is not None and state.runner.is_alive()


def _is_controller_alive(state: _WebState) -> bool:
    return state.controller is not None and state.controller.is_alive()


def _csv_data_rows(path: str) -> int:
    if not path or not os.path.isfile(path):
        return 0
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as fp:
            rows = sum(1 for _ in fp)
        return max(0, rows - 1)
    except Exception:
        return 0


def _parse_urls(raw_urls: str) -> list[str]:
    urls = [line.strip() for line in raw_urls.splitlines()]
    return [url for url in urls if url]


def _render_page(state: _WebState) -> str:
    with state.lock:
        state.drain_logs()
        running = _is_runner_alive(state) or _is_controller_alive(state)
        urls_value = '\n'.join(state.urls)
        output_path = state.output_path
        output_format = state.format
        file_exists = bool(output_path) and os.path.isfile(output_path)
        file_size = os.path.getsize(output_path) if file_exists else 0
        auto_restart = state.auto_restart
        auto_max_attempts = state.auto_max_attempts
        auto_probe_seconds = state.auto_probe_seconds
        auto_first_parse_deadline = state.auto_first_parse_deadline
        auto_min_records = state.auto_min_records
        auto_error_budget = state.auto_error_budget
        auto_prewarm_delay = state.auto_prewarm_delay
        auto_current_attempt = state.auto_current_attempt

    format_options = ''.join(
        f'<option value="{fmt}"{" selected" if fmt == output_format else ""}>{fmt}</option>'
        for fmt in ('csv', 'xlsx', 'json')
    )

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Parser 2GIS - Web</title>
  <style>
    :root {{
      --bg: #f5f7fb;
      --panel: #ffffff;
      --ink: #1f2937;
      --muted: #6b7280;
      --accent: #0f766e;
      --danger: #b42318;
      --border: #d1d5db;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Noto Sans", sans-serif;
      color: var(--ink);
      background: radial-gradient(circle at top left, #e8f5f2, var(--bg));
    }}
    .wrap {{
      max-width: 860px;
      margin: 24px auto;
      padding: 0 16px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px;
      box-shadow: 0 8px 20px rgba(0, 0, 0, 0.06);
    }}
    h1 {{ margin-top: 0; font-size: 24px; }}
    .status {{ margin-bottom: 12px; color: var(--muted); }}
    .status b {{ color: var(--accent); }}
    label {{ display: block; margin-top: 12px; font-weight: 600; }}
    textarea, input, select {{
      width: 100%;
      margin-top: 6px;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px 12px;
      font: inherit;
    }}
    textarea {{ min-height: 110px; resize: vertical; }}
    .row {{ display: grid; grid-template-columns: 1fr 180px; gap: 12px; }}
    .btns {{ display: flex; gap: 8px; margin-top: 16px; flex-wrap: wrap; }}
    button {{
      border: 0;
      border-radius: 8px;
      padding: 10px 14px;
      font: inherit;
      cursor: pointer;
      color: #fff;
      background: var(--accent);
    }}
    button.danger {{ background: var(--danger); }}
    button:disabled {{ opacity: 0.5; cursor: not-allowed; }}
    #log {{
      margin-top: 16px;
      background: #0f172a;
      color: #e2e8f0;
      border-radius: 8px;
      padding: 12px;
      min-height: 220px;
      max-height: 360px;
      overflow: auto;
      white-space: pre-wrap;
      font-family: "SF Mono", "Consolas", monospace;
      font-size: 13px;
    }}
    @media (max-width: 640px) {{
      .row {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Parser 2GIS (Web)</h1>
      <div class="status">Статус: <b id="status">{'Запущен' if running else 'Ожидает запуск'}</b></div>

      <form method="post" action="/start">
        <label for="urls">URL (по одному на строку)</label>
        <textarea id="urls" name="urls" required>{html.escape(urls_value)}</textarea>

        <div class="row">
          <div>
            <label for="output_path">Путь к результату</label>
            <input id="output_path" type="text" name="output_path" value="{html.escape(output_path)}" required>
          </div>
          <div>
            <label for="format">Формат</label>
            <select id="format" name="format">{format_options}</select>
          </div>
        </div>

        <div class="row">
          <div>
            <label for="auto_restart">Авто-перезапуск до стабильного старта (рекомендуется CSV)</label>
            <select id="auto_restart" name="auto_restart">
              <option value="yes"{" selected" if auto_restart else ""}>Вкл</option>
              <option value="no"{" selected" if not auto_restart else ""}>Выкл</option>
            </select>
          </div>
          <div>
            <label for="auto_max_attempts">Макс. попыток</label>
            <input id="auto_max_attempts" type="number" name="auto_max_attempts" value="{auto_max_attempts}" min="1" max="50">
          </div>
        </div>

        <div class="row">
          <div>
            <label for="auto_probe_seconds">Окно проверки (сек)</label>
            <input id="auto_probe_seconds" type="number" name="auto_probe_seconds" value="{auto_probe_seconds}" min="4" max="60">
          </div>
          <div>
            <label for="auto_first_parse_deadline">Первый результат до (сек)</label>
            <input id="auto_first_parse_deadline" type="number" step="0.5" name="auto_first_parse_deadline" value="{auto_first_parse_deadline}" min="1" max="20">
          </div>
        </div>

        <div class="row">
          <div>
            <label for="auto_min_records">Мин. записей для старта</label>
            <input id="auto_min_records" type="number" name="auto_min_records" value="{auto_min_records}" min="1" max="100">
          </div>
          <div>
            <label for="auto_error_budget">Допустимо ошибок</label>
            <input id="auto_error_budget" type="number" name="auto_error_budget" value="{auto_error_budget}" min="0" max="20">
          </div>
        </div>

        <div class="row">
          <div>
            <label for="auto_prewarm_delay">Прогрев перед проверкой (сек)</label>
            <input id="auto_prewarm_delay" type="number" step="0.1" name="auto_prewarm_delay" value="{auto_prewarm_delay}" min="0" max="10">
          </div>
          <div>
            <label>Текущая авто-попытка</label>
            <input type="text" value="{auto_current_attempt if auto_current_attempt else '-'}" readonly>
          </div>
        </div>

        <div class="btns">
          <button type="submit" {'disabled' if running else ''}>Запуск</button>
        </div>
      </form>

      <form method="post" action="/stop" class="btns">
        <button class="danger" type="submit" {'disabled' if not running else ''}>Стоп</button>
      </form>

      <form method="get" action="/download" class="btns">
        <button type="submit" {'disabled' if not file_exists else ''}>Скачать результат</button>
      </form>
      <div class="status">
        Файл: <b>{html.escape(output_path) if output_path else 'не выбран'}</b>
        ({file_size} байт)
      </div>

      <div id="log"></div>
    </div>
  </div>

  <script>
    async function refreshStatus() {{
      const resp = await fetch('/status', {{cache: 'no-store'}});
      const data = await resp.json();
      document.getElementById('status').textContent = data.running
        ? 'Запущен'
        : (data.stop_requested ? 'Остановлен пользователем' : 'Ожидает запуск');

      const log = document.getElementById('log');
      if (data.logs && data.logs.length) {{
        log.textContent += data.logs.join('');
        log.scrollTop = log.scrollHeight;
      }}
    }}

    refreshStatus();
    setInterval(refreshStatus, 1000);
  </script>
</body>
</html>
"""


def web_app(urls: list[str] | None, output_path: str | None,
            format: str | None, config: Configuration,
            host: str = '127.0.0.1', port: int = 8080,
            open_browser: bool = True) -> None:
    """Run parser in browser-based local interface."""
    setup_cli_logger(config.log)

    state = _WebState(urls, output_path, format, config)
    setup_gui_logger(state.log_queue, config.log)

    def _log(message: str) -> None:
        with state.lock:
            state.logs.append(message if message.endswith('\n') else message + '\n')

    def _start_runner() -> GUIRunner:
        with state.lock:
            runner = GUIRunner(state.urls, state.output_path, state.format, state.config)
            state.runner = runner
        runner.start()
        return runner

    def _stop_runner(runner: GUIRunner | None) -> None:
        if runner is None:
            return
        if runner.is_alive():
            try:
                runner.stop()
            except Exception:
                pass
            runner.join(timeout=30)

    def _auto_start_loop() -> None:
        with state.lock:
            max_attempts = max(1, int(state.auto_max_attempts))
            probe_seconds = max(4, int(state.auto_probe_seconds))
            first_deadline = max(1.0, float(state.auto_first_parse_deadline))
            min_records = max(1, int(state.auto_min_records))
            error_budget = max(0, int(state.auto_error_budget))
            prewarm_delay = max(0.0, float(state.auto_prewarm_delay))

        for attempt in range(1, max_attempts + 1):
            with state.lock:
                if state.stop_requested:
                    break
                state.auto_current_attempt = attempt
            _log(f"[auto] Попытка запуска {attempt}/{max_attempts}")

            runner = _start_runner()
            with state.lock:
                state.attempt_parsed_events = 0
                state.attempt_first_parse_delay = None
                state.attempt_error_events = 0
                state.drain_logs()

            warmup_start = time.time()
            if prewarm_delay > 0:
                _log(f"[auto] Прогрев {round(prewarm_delay, 1)}с перед оценкой старта.")
            while time.time() - warmup_start < prewarm_delay:
                with state.lock:
                    if state.stop_requested:
                        _stop_runner(runner)
                        state.runner = None
                        break
                    state.drain_logs()
                if not runner.is_alive():
                    break
                time.sleep(0.25)

            start_ts = time.time()
            with state.lock:
                state.attempt_started_at = start_ts
                state.attempt_parsed_events = 0
                state.attempt_first_parse_delay = None
                state.attempt_error_events = 0
                state.drain_logs()

            while time.time() - start_ts < probe_seconds:
                with state.lock:
                    if state.stop_requested:
                        _stop_runner(runner)
                        state.runner = None
                        break
                    state.drain_logs()
                    records_seen = state.attempt_parsed_events
                    first_record_delay = state.attempt_first_parse_delay
                if not runner.is_alive():
                    break
                time.sleep(1)

            elapsed = max(0.001, time.time() - start_ts)
            with state.lock:
                state.drain_logs()
                records_seen = state.attempt_parsed_events
                first_record_delay = state.attempt_first_parse_delay
                error_count = state.attempt_error_events
                state.attempt_started_at = 0.0
            rps = records_seen / elapsed
            stable = (
                first_record_delay is not None
                and first_record_delay <= first_deadline
                and records_seen >= min_records
                and error_count <= error_budget
            )
            _log(
                f"[auto] Итог попытки {attempt}: records={records_seen}, "
                f"first={round(first_record_delay,2) if first_record_delay is not None else 'none'}s, "
                f"rps={round(rps,2)}, errors={error_count}, min_records={min_records}"
            )

            if stable:
                _log(f"[auto] Стабильный старт найден на попытке {attempt}.")
                with state.lock:
                    state.auto_current_attempt = attempt
                    state.controller = None
                return

            _log(f"[auto] Нестабильный старт, перезапуск.")
            _stop_runner(runner)
            with state.lock:
                if state.runner is runner:
                    state.runner = None
            if attempt < max_attempts:
                time.sleep(1)

        with state.lock:
            state.controller = None
            state.auto_current_attempt = 0
        _log("[auto] Лимит попыток исчерпан.")

    class Handler(BaseHTTPRequestHandler):
        def _send_html(self, body: str) -> None:
            encoded = body.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _send_json(self, payload: dict) -> None:
            encoded = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _send_file(self, path: str) -> None:
            if not os.path.isfile(path):
                self.send_error(404, 'Result file not found')
                return

            file_name = os.path.basename(path)
            content_type = mimetypes.guess_type(file_name)[0] or 'application/octet-stream'
            file_size = os.path.getsize(path)

            with open(path, 'rb') as f:
                data = f.read()

            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Disposition', f'attachment; filename="{file_name}"')
            self.send_header('Content-Length', str(file_size))
            self.end_headers()
            self.wfile.write(data)

        def _redirect_home(self) -> None:
            self.send_response(303)
            self.send_header('Location', '/')
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            path = urllib.parse.urlsplit(self.path).path

            if path == '/':
                self._send_html(_render_page(state))
                return

            if path == '/status':
                with state.lock:
                    state.drain_logs()
                    running = _is_runner_alive(state) or _is_controller_alive(state)
                    payload = {
                        'running': running,
                        'stop_requested': state.stop_requested,
                        'auto_current_attempt': state.auto_current_attempt,
                        'logs': state.logs,
                    }
                    state.logs = []
                self._send_json(payload)
                return

            if path == '/download':
                with state.lock:
                    output_path = state.output_path
                if not output_path:
                    self.send_error(404, 'Output path is empty')
                    return
                self._send_file(output_path)
                return

            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            path = urllib.parse.urlsplit(self.path).path

            if path == '/start':
                content_length = int(self.headers.get('Content-Length', '0'))
                form_data = urllib.parse.parse_qs(self.rfile.read(content_length).decode('utf-8'))

                urls_form = _parse_urls(form_data.get('urls', [''])[0])
                output_path_form = form_data.get('output_path', [''])[0].strip()
                format_form = form_data.get('format', ['csv'])[0]
                if format_form not in ('csv', 'xlsx', 'json'):
                    format_form = 'csv'
                auto_restart = form_data.get('auto_restart', ['yes'])[0] == 'yes'
                auto_max_attempts = int(form_data.get('auto_max_attempts', ['30'])[0] or '30')
                auto_probe_seconds = int(form_data.get('auto_probe_seconds', ['12'])[0] or '12')
                auto_first_parse_deadline = float(form_data.get('auto_first_parse_deadline', ['5'])[0] or '5')
                auto_min_records = int(form_data.get('auto_min_records', ['3'])[0] or '3')
                auto_error_budget = int(form_data.get('auto_error_budget', ['1'])[0] or '1')
                auto_prewarm_delay = float(form_data.get('auto_prewarm_delay', ['2.5'])[0] or '2.5')

                should_start = False
                with state.lock:
                    busy = _is_runner_alive(state) or _is_controller_alive(state)
                    if not busy:
                        state.urls = urls_form
                        state.output_path = output_path_form
                        state.format = format_form
                        state.auto_restart = auto_restart
                        state.auto_max_attempts = max(1, min(auto_max_attempts, 50))
                        state.auto_probe_seconds = max(4, min(auto_probe_seconds, 60))
                        state.auto_first_parse_deadline = max(1.0, min(auto_first_parse_deadline, 20.0))
                        state.auto_min_records = max(1, min(auto_min_records, 100))
                        state.auto_error_budget = max(0, min(auto_error_budget, 20))
                        state.auto_prewarm_delay = max(0.0, min(auto_prewarm_delay, 10.0))
                        state.stop_requested = False
                        state.logs = []
                        state.auto_current_attempt = 0
                        should_start = True

                if should_start:
                    if auto_restart and format_form == 'csv':
                        controller = threading.Thread(target=_auto_start_loop, daemon=True)
                        with state.lock:
                            state.controller = controller
                        controller.start()
                    else:
                        _start_runner()

                self._redirect_home()
                return

            if path == '/stop':
                runner: GUIRunner | None = None
                with state.lock:
                    state.stop_requested = True
                    runner = state.runner
                    state.auto_current_attempt = 0
                _stop_runner(runner)
                with state.lock:
                    state.runner = None
                    state.controller = None
                self._redirect_home()
                return

            self.send_error(404)

        def log_message(self, format: str, *args) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    web_url = f'http://{host}:{port}'

    if open_browser:
        try:
            webbrowser.open(web_url)
        except Exception:
            pass

    print(f'Веб-интерфейс запущен: {web_url}')
    print('Нажмите Ctrl+C для завершения.')

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        runner: GUIRunner | None = None
        with state.lock:
            state.stop_requested = True
            runner = state.runner
        _stop_runner(runner)
        server.server_close()
