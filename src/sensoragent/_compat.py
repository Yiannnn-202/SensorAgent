"""Compatibility helpers for supported Python runtimes."""

from __future__ import annotations

from enum import Enum

try:  # Python 3.11+
  from enum import StrEnum as StrEnum
except ImportError:  # pragma: no cover - exercised on Python 3.10 runtimes.
  class StrEnum(str, Enum):
    """Minimal backport of enum.StrEnum for Python 3.10."""

    def __str__(self) -> str:
      return str(self.value)

    @staticmethod
    def _generate_next_value_(name: str, start: int, count: int, last_values: list[str]) -> str:
      return name.lower()
