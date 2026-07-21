from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class VisionAdapter(ABC):
    name: str
    region: str | None = None

    @abstractmethod
    def analyze(self, image_bytes: bytes, minimum_confidence: int) -> dict[str, Any]:
        raise NotImplementedError
