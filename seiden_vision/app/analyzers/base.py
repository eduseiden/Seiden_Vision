from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Analyzer(ABC):
    """Contrato comum dos analisadores do Seiden Vision."""

    name: str

    @abstractmethod
    def can_handle(self, payload: dict[str, Any]) -> bool:
        """Retorna True quando o analisador reconhece o payload."""

    @abstractmethod
    def analyze(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Transforma uma evidência bruta em evidência enriquecida."""
