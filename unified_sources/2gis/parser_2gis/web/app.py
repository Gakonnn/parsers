from __future__ import annotations

import html
import json
import queue
import threading
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
        self.stop_requested = False
        self.log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.logs: list[str] = []
        self.config = config

    def drain_logs(self) -> None:
        while True:
            try:
                _, message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.logs.append(message)


def _parse_urls(raw_urls: str) -> list[str]:
    urls = [line.strip() for line in raw_urls.splitlines()]
    return [url for url in urls if url]


def _render_page(state: _WebState) -> str:
    with state.lock:
        state.drain_logs()
        running = state.runner is not None and state.runner.is_alive()
        urls_value = '\n'.join(state.urls)
        output_path = state.output_path
        output_format = state.format

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

        <div class="btns">
          <button type="submit" {'disabled' if running else ''}>Запуск</button>
        </div>
      </form>

      <form method="post" action="/stop" class="btns">
        <button class="danger" type="submit" {'disabled' if not running else ''}>Стоп</button>
      </form>

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

        def _redirect_home(self) -> None:
            self.send_response(303)
            self.send_header('Location', '/')
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            if self.path == '/':
                self._send_html(_render_page(state))
                return

            if self.path == '/status':
                with state.lock:
                    state.drain_logs()
                    running = state.runner is not None and state.runner.is_alive()
                    payload = {
                        'running': running,
                        'stop_requested': state.stop_requested,
                        'logs': state.logs,
                    }
                    state.logs = []
                self._send_json(payload)
                return

            self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            if self.path == '/start':
                content_length = int(self.headers.get('Content-Length', '0'))
                form_data = urllib.parse.parse_qs(self.rfile.read(content_length).decode('utf-8'))

                urls_form = _parse_urls(form_data.get('urls', [''])[0])
                output_path_form = form_data.get('output_path', [''])[0].strip()
                format_form = form_data.get('format', ['csv'])[0]
                if format_form not in ('csv', 'xlsx', 'json'):
                    format_form = 'csv'

                with state.lock:
                    if state.runner is None or not state.runner.is_alive():
                        state.urls = urls_form
                        state.output_path = output_path_form
                        state.format = format_form
                        state.stop_requested = False
                        state.logs = []
                        state.runner = GUIRunner(state.urls, state.output_path, state.format, state.config)
                        state.runner.start()

                self._redirect_home()
                return

            if self.path == '/stop':
                with state.lock:
                    if state.runner is not None and state.runner.is_alive():
                        state.stop_requested = True
                        state.runner.stop()
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
        with state.lock:
            if state.runner is not None and state.runner.is_alive():
                state.runner.stop()
                state.runner.join()
        server.server_close()
