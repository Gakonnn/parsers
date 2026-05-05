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


def _minimal_olx_categories() -> dict[str, Any]:
    categories = [
        ("transport", "Транспорт", [("legkovye-avtomobili", "Легковые автомобили")]),
        ("nedvizhimost", "Недвижимость", [("prodazha-kvartir", "Продажа квартир"), ("arenda-kvartir", "Аренда квартир")]),
        ("elektronika", "Электроника", [("telefony-i-aksesuary", "Телефоны и аксессуары"), ("kompyutery-i-komplektuyuschie", "Компьютеры")]),
        ("dom-i-sad", "Дом и сад", [("mebel", "Мебель"), ("bytovaya-tehnika", "Бытовая техника")]),
        ("rabota", "Работа", [("vakansii", "Вакансии")]),
        ("uslugi", "Услуги", [("stroitelstvo-remont", "Строительство и ремонт")]),
    ]
    level1 = []
    for slug, name, children in categories:
        level1.append(
            {
                "slug": slug,
                "name": name,
                "url": f"https://www.olx.kz/{slug}/",
                "level2": [
                    {
                        "slug": child_slug,
                        "name": child_name,
                        "url": f"https://www.olx.kz/{slug}/{child_slug}/",
                        "level3": [],
                    }
                    for child_slug, child_name in children
                ],
            }
        )
    return {
        "source_url": "local-fallback",
        "updated_at": "",
        "level1": level1,
        "stats": {
            "level1_count": len(level1),
            "level2_count": sum(len(item["level2"]) for item in level1),
            "level3_count": 0,
        },
    }


def get_fallback_meta(path: str) -> dict[str, Any]:
    module = _hub_module()
    if path == "/api/2gis/rubrics":
        return module.get_2gis_rubrics_tree()
    if path == "/api/2gis/cities":
        return module.get_2gis_cities()
    if path == "/api/olx/categories":
        try:
            return module.get_olx_categories_tree()
        except Exception:
            return _minimal_olx_categories()
    if path == "/api/config":
        return {"parsers": module.parser_definitions()}
    raise ParserMetaFallbackError(f"No fallback metadata handler for {path}")
