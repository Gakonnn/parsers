from __future__ import annotations

import importlib.util
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PARSERS_HUB_SERVER = PROJECT_ROOT / "parsers_hub" / "server.py"


class ParserMetaFallbackError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _hub_module() -> Any:
    if not PARSERS_HUB_SERVER.exists():
        raise ParserMetaFallbackError(f"Parsers hub server.py not found: {PARSERS_HUB_SERVER}")
    spec = importlib.util.spec_from_file_location("_parserdesk_hub_meta", PARSERS_HUB_SERVER)
    if spec is None or spec.loader is None:
        raise ParserMetaFallbackError("Could not load parsers hub metadata helpers")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def get_fallback_meta(path: str) -> dict[str, Any]:
    module = _hub_module()
    if path == "/api/2gis/rubrics":
        return module.get_2gis_rubrics_tree()
    if path == "/api/2gis/cities":
        return module.get_2gis_cities()
    if path == "/api/olx/categories":
        try:
            return module.get_olx_categories_tree()
        except Exception as exc:
            raise ParserMetaFallbackError(f"Could not load live OLX categories: {exc}") from exc
    if path == "/api/config":
        return {"parsers": module.parser_definitions()}
    raise ParserMetaFallbackError(f"No fallback metadata handler for {path}")
