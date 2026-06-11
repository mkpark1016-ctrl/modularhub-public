from __future__ import annotations

from abc import ABC, abstractmethod


class BaseCollector(ABC):
    @abstractmethod
    def collect(self) -> list[dict]:
        """Return raw source items."""

    @abstractmethod
    def get_source_type(self) -> str:
        """Return the normalized source type."""

    @abstractmethod
    def get_source_name(self) -> str:
        """Return the collector/source display name."""
