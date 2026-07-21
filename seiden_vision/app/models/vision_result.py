from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class VisionResult:
    provider: str
    face_count: int
    dominant_emotion: str
    confidence: float
    emotions: dict[str, float] = field(default_factory=dict)
    quality: dict[str, float | None] = field(default_factory=dict)
    pose: dict[str, float | None] = field(default_factory=dict)
    age_range: dict[str, int | None] = field(default_factory=dict)
    gender: dict[str, Any] = field(default_factory=dict)
    smile: dict[str, Any] = field(default_factory=dict)
    eyes_open: dict[str, Any] = field(default_factory=dict)
    mouth_open: dict[str, Any] = field(default_factory=dict)
    eyeglasses: dict[str, Any] = field(default_factory=dict)
    sunglasses: dict[str, Any] = field(default_factory=dict)
    beard: dict[str, Any] = field(default_factory=dict)
    mustache: dict[str, Any] = field(default_factory=dict)
    face_occluded: dict[str, Any] = field(default_factory=dict)
    bounding_box: dict[str, float] = field(default_factory=dict)
    processing_ms: int = 0
    region: str | None = None
    request_id: str | None = None
    raw_response: dict[str, Any] | None = None
    mock: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
