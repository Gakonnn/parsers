from __future__ import annotations

from abc import ABC, abstractmethod
from argparse import ArgumentParser, Namespace
from pathlib import Path


class SourceAdapter(ABC):
    key: str
    title: str
    implemented: bool = True

    @abstractmethod
    def add_run_arguments(self, parser: ArgumentParser) -> None:
        """Register source-specific CLI arguments."""

    @abstractmethod
    def build_command(self, args: Namespace, project_root: Path) -> list[str]:
        """Build subprocess command for the source parser."""

    def execution_cwd(self, project_root: Path) -> Path:
        """Working directory for subprocess execution."""
        return project_root

    def output_path(self, args: Namespace, project_root: Path) -> Path | None:
        """Expected output file path for run report."""
        _ = args
        _ = project_root
        return None
