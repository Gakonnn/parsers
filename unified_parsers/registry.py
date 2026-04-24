from __future__ import annotations

from .adapters.base import SourceAdapter
from .adapters.gis2 import Gis2Adapter
from .adapters.krisha import KrishaAdapter
from .adapters.olx import OlxAdapter


def get_adapters() -> dict[str, SourceAdapter]:
    adapters: list[SourceAdapter] = [
        OlxAdapter(),
        KrishaAdapter(),
        Gis2Adapter(),
    ]
    return {adapter.key: adapter for adapter in adapters}

