from __future__ import annotations

from config import Settings
from vision_adapters.base import VisionAdapter
from vision_adapters.mock import MockVisionAdapter


def create_adapter(settings: Settings) -> VisionAdapter:
    if settings.provider == "mock":
        return MockVisionAdapter()
    if settings.provider == "aws_rekognition":
        from vision_adapters.aws_rekognition import AwsRekognitionAdapter
        return AwsRekognitionAdapter(settings)
    raise ValueError(f"Adaptador de visão não suportado: {settings.provider}")
