from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from app.core.config import get_settings


class ParsersHubError(RuntimeError):
    pass


def _request_json(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = get_settings()
    url = urljoin(f"{settings.parsers_hub_url}/", path.lstrip("/"))
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url=url, data=body, headers=headers, method=method.upper())
    try:
        with urlopen(request, timeout=settings.parsers_hub_timeout_sec) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(raw)
        except json.JSONDecodeError:
            detail = raw
        raise ParsersHubError(f"Parsers hub HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise ParsersHubError(f"Parsers hub is unavailable: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ParsersHubError(f"Parsers hub returned non-JSON response: {raw[:300]}") from exc
    if isinstance(data, dict) and data.get("error"):
        raise ParsersHubError(str(data["error"]))
    if not isinstance(data, dict):
        raise ParsersHubError("Parsers hub returned invalid JSON payload")
    return data


def start_parser_job(source: str, parameters: dict[str, Any]) -> dict[str, Any]:
    data = _request_json("POST", "/api/run", {"parser_key": source, "payload": parameters})
    job = data.get("job")
    if not isinstance(job, dict):
        raise ParsersHubError("Parsers hub did not return job data")
    return job


def get_parser_job(runner_job_id: str) -> dict[str, Any]:
    return _request_json("GET", f"/api/jobs/{runner_job_id}")


def run_parser_job_action(runner_job_id: str, action: str) -> dict[str, Any]:
    return _request_json("POST", f"/api/jobs/{runner_job_id}/{action}")


def get_parser_meta(path: str) -> dict[str, Any]:
    return _request_json("GET", path)
