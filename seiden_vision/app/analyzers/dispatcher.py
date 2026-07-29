from __future__ import annotations

from typing import Any, Iterable

from analyzers.base import Analyzer


class AnalyzerDispatcher:
    """Seleciona todos os analisadores compatíveis com uma evidência."""

    def __init__(self, analyzers: Iterable[Analyzer]) -> None:
        self.analyzers = tuple(analyzers)

    def dispatch(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for analyzer in self.analyzers:
            if not analyzer.can_handle(payload):
                continue
            result = analyzer.analyze(payload)
            if result is not None:
                results.append(result)
        return results

    @property
    def names(self) -> list[str]:
        return [analyzer.name for analyzer in self.analyzers]
