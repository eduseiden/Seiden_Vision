from __future__ import annotations

import time
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError, PartialCredentialsError

from config import Settings
from models.vision_result import VisionResult
from vision_adapters.base import VisionAdapter
from version import VERSION


class AwsRekognitionAdapter(VisionAdapter):
    name = "aws_rekognition"

    def __init__(self, settings: Settings) -> None:
        if not settings.aws_configured:
            raise ValueError(
                "AWS Rekognition selecionado, mas Access Key ID e Secret Access Key não foram configuradas."
            )
        self.region = settings.aws_region.strip() or "us-east-1"
        self.store_raw_response = settings.aws_store_raw_response
        config = Config(
            connect_timeout=settings.aws_connect_timeout_seconds,
            read_timeout=settings.aws_read_timeout_seconds,
            retries={"max_attempts": settings.aws_max_attempts, "mode": "standard"},
            user_agent_extra=f"Seiden-Vision/{VERSION}",
        )
        self.client = boto3.client(
            "rekognition",
            region_name=self.region,
            aws_access_key_id=settings.aws_access_key_id.strip(),
            aws_secret_access_key=settings.aws_secret_access_key.strip(),
            config=config,
        )

    @staticmethod
    def _value_confidence(value: dict[str, Any] | None) -> dict[str, Any]:
        if not value:
            return {}
        return {
            "value": value.get("Value"),
            "confidence": round(float(value.get("Confidence", 0.0)), 2),
        }

    @staticmethod
    def _clean_raw(response: dict[str, Any]) -> dict[str, Any]:
        cleaned = dict(response)
        metadata = dict(cleaned.get("ResponseMetadata", {}))
        headers = metadata.get("HTTPHeaders")
        if headers:
            metadata["HTTPHeaders"] = {
                key: value
                for key, value in headers.items()
                if key.lower() in {"date", "content-type", "content-length", "x-amzn-requestid"}
            }
        cleaned["ResponseMetadata"] = metadata
        return cleaned

    def analyze(self, image_bytes: bytes, minimum_confidence: int) -> dict[str, Any]:
        if len(image_bytes) > 5 * 1024 * 1024:
            raise ValueError("AWS Rekognition aceita no máximo 5 MB quando a imagem é enviada em bytes.")

        started = time.perf_counter()
        try:
            response = self.client.detect_faces(
                Image={"Bytes": image_bytes},
                Attributes=["ALL"],
            )
        except NoCredentialsError as exc:
            raise RuntimeError("Credenciais AWS não encontradas.") from exc
        except PartialCredentialsError as exc:
            raise RuntimeError("Credenciais AWS incompletas.") from exc
        except ClientError as exc:
            error = exc.response.get("Error", {})
            code = error.get("Code", "ClientError")
            message = error.get("Message", str(exc))
            raise RuntimeError(f"AWS Rekognition {code}: {message}") from exc
        except BotoCoreError as exc:
            raise RuntimeError(f"Falha de comunicação com a AWS: {exc}") from exc

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        faces = [
            face for face in response.get("FaceDetails", [])
            if float(face.get("Confidence", 0.0)) >= minimum_confidence
        ]
        request_id = response.get("ResponseMetadata", {}).get("RequestId")

        if not faces:
            return VisionResult(
                provider=self.name,
                region=self.region,
                request_id=request_id,
                face_count=0,
                dominant_emotion="NO_FACE",
                confidence=0.0,
                processing_ms=elapsed_ms,
                raw_response=self._clean_raw(response) if self.store_raw_response else None,
            ).to_dict()

        primary = max(faces, key=lambda item: float(item.get("Confidence", 0.0)))
        emotion_items = primary.get("Emotions", [])
        emotions = {
            str(item.get("Type", "UNKNOWN")): round(float(item.get("Confidence", 0.0)), 2)
            for item in emotion_items
        }
        dominant_emotion = max(emotions, key=emotions.get) if emotions else "UNKNOWN"
        quality = primary.get("Quality", {})
        pose = primary.get("Pose", {})
        age = primary.get("AgeRange", {})
        gender = primary.get("Gender", {})

        return VisionResult(
            provider=self.name,
            region=self.region,
            request_id=request_id,
            face_count=len(faces),
            dominant_emotion=dominant_emotion,
            confidence=round(float(primary.get("Confidence", 0.0)), 2),
            emotions=emotions,
            quality={
                "brightness": round(float(quality.get("Brightness", 0.0)), 2),
                "sharpness": round(float(quality.get("Sharpness", 0.0)), 2),
            },
            pose={
                "yaw": round(float(pose.get("Yaw", 0.0)), 2),
                "pitch": round(float(pose.get("Pitch", 0.0)), 2),
                "roll": round(float(pose.get("Roll", 0.0)), 2),
            },
            age_range={"low": age.get("Low"), "high": age.get("High")},
            gender={
                "value": gender.get("Value"),
                "confidence": round(float(gender.get("Confidence", 0.0)), 2),
            },
            smile=self._value_confidence(primary.get("Smile")),
            eyes_open=self._value_confidence(primary.get("EyesOpen")),
            mouth_open=self._value_confidence(primary.get("MouthOpen")),
            eyeglasses=self._value_confidence(primary.get("Eyeglasses")),
            sunglasses=self._value_confidence(primary.get("Sunglasses")),
            beard=self._value_confidence(primary.get("Beard")),
            mustache=self._value_confidence(primary.get("Mustache")),
            face_occluded=self._value_confidence(primary.get("FaceOccluded")),
            bounding_box={
                key.lower(): round(float(value), 6)
                for key, value in primary.get("BoundingBox", {}).items()
            },
            processing_ms=elapsed_ms,
            raw_response=self._clean_raw(response) if self.store_raw_response else None,
        ).to_dict()
