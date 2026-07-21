from __future__ import annotations

import hashlib
import random
import time
from typing import Any


class MockVisionProvider:
    """Simulador determinístico para validar a arquitetura sem serviço externo."""

    name = "mock"

    def analyze(self, image_bytes: bytes, minimum_confidence: int) -> dict[str, Any]:
        started = time.perf_counter()
        digest = hashlib.sha256(image_bytes).digest()
        seed = int.from_bytes(digest[:8], "big")
        rng = random.Random(seed)

        emotions = ["CALM", "HAPPY", "CONFUSED", "SAD", "SURPRISED"]
        dominant = emotions[seed % len(emotions)]
        confidence = round(max(float(minimum_confidence), rng.uniform(78.0, 99.4)), 2)
        brightness = round(rng.uniform(35.0, 95.0), 2)
        sharpness = round(rng.uniform(40.0, 98.0), 2)
        face_count = 1 if rng.random() > 0.08 else 0

        scores = {emotion: round(rng.uniform(0.1, 8.0), 2) for emotion in emotions}
        if face_count:
            scores[dominant] = confidence
        else:
            dominant = "NO_FACE"
            confidence = 0.0
            scores = {}

        elapsed_ms = max(5, int((time.perf_counter() - started) * 1000) + rng.randint(20, 90))
        return {
            "provider": self.name,
            "face_count": face_count,
            "dominant_emotion": dominant,
            "confidence": confidence,
            "emotions": scores,
            "quality": {
                "brightness": brightness,
                "sharpness": sharpness,
            },
            "processing_ms": elapsed_ms,
            "mock": True,
        }


def create_provider(name: str) -> MockVisionProvider:
    if name != "mock":
        raise ValueError(f"Provedor não suportado nesta versão: {name}")
    return MockVisionProvider()
