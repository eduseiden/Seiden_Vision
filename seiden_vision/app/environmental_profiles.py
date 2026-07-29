from __future__ import annotations

import hashlib
import json
import logging
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

DEFAULT_PROFILES_PATH = Path(__file__).resolve().parent / "profiles" / "environmental_profiles.json"
CUSTOM_PROFILES_PATH = Path("/config/environmental_profiles.json")


@dataclass(frozen=True)
class MetricBand:
    optimal_min: float
    optimal_max: float
    attention_min: float
    attention_max: float
    critical_min: float
    critical_max: float
    weight: float = 1.0


@dataclass(frozen=True)
class EnvironmentalProfile:
    profile_id: str
    label: str
    analysis_type: str
    temperature: MetricBand
    humidity: MetricBand | None
    ruleset: str
    ruleset_source: str
    customized: bool


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _load_json(path: Path, *, required: bool) -> dict[str, Any]:
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Arquivo de perfis não encontrado: {path}")
        return {}
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        if required:
            raise ValueError(f"Falha ao carregar perfis de {path}: {exc}") from exc
        LOGGER.error("Arquivo de perfis customizados inválido (%s): %s", path, exc)
        return {}
    if not isinstance(content, dict):
        raise ValueError(f"O arquivo {path} deve conter um objeto JSON.")
    profiles = content.get("profiles", content)
    if not isinstance(profiles, dict):
        raise ValueError(f"A propriedade 'profiles' de {path} deve ser um objeto.")
    return profiles


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} deve ser numérico.")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} deve ser numérico.") from exc


def _metric_band(raw: Any, field: str) -> MetricBand | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"{field} deve ser um objeto ou null.")

    optimal = raw.get("optimal")
    attention = raw.get("attention")
    critical = raw.get("critical")
    if not all(isinstance(item, dict) for item in (optimal, attention, critical)):
        raise ValueError(f"{field} exige as faixas optimal, attention e critical.")

    band = MetricBand(
        optimal_min=_number(optimal.get("min"), f"{field}.optimal.min"),
        optimal_max=_number(optimal.get("max"), f"{field}.optimal.max"),
        attention_min=_number(attention.get("min"), f"{field}.attention.min"),
        attention_max=_number(attention.get("max"), f"{field}.attention.max"),
        critical_min=_number(critical.get("min"), f"{field}.critical.min"),
        critical_max=_number(critical.get("max"), f"{field}.critical.max"),
        weight=_number(raw.get("weight", 1.0), f"{field}.weight"),
    )
    if not (
        band.critical_min <= band.attention_min <= band.optimal_min
        <= band.optimal_max <= band.attention_max <= band.critical_max
    ):
        raise ValueError(
            f"{field} possui faixas inconsistentes; esperado critical.min <= attention.min "
            "<= optimal.min <= optimal.max <= attention.max <= critical.max."
        )
    if band.weight < 0:
        raise ValueError(f"{field}.weight não pode ser negativo.")
    return band


def _ruleset_id(profile_id: str, raw: dict[str, Any], source: str, customized: bool) -> str:
    explicit = str(raw.get("ruleset") or "").strip()
    if explicit and not customized:
        return explicit
    canonical = json.dumps(raw, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:10]
    suffix = "custom" if customized else source
    return f"seiden_environmental_profile_{profile_id}_{suffix}_{digest}"


def _build_profile(profile_id: str, raw: dict[str, Any], source: str, customized: bool) -> EnvironmentalProfile:
    if not isinstance(raw, dict):
        raise ValueError(f"Perfil {profile_id} deve ser um objeto.")
    temperature = _metric_band(raw.get("temperature"), f"{profile_id}.temperature")
    if temperature is None:
        raise ValueError(f"Perfil {profile_id} exige configuração de temperatura.")
    return EnvironmentalProfile(
        profile_id=profile_id,
        label=str(raw.get("label") or profile_id).strip(),
        analysis_type=str(raw.get("analysis_type") or "environmental_compliance").strip(),
        temperature=temperature,
        humidity=_metric_band(raw.get("humidity"), f"{profile_id}.humidity"),
        ruleset=_ruleset_id(profile_id, raw, source, customized),
        ruleset_source=source,
        customized=customized,
    )


class EnvironmentalProfileRegistry:
    """Carrega perfis padrão, customizações locais e overrides por fonte."""

    def __init__(self) -> None:
        self._default_profiles = _load_json(DEFAULT_PROFILES_PATH, required=True)

    def resolve(self, requested_profile_id: str, profile_override: Any = None) -> tuple[EnvironmentalProfile, bool]:
        custom_profiles = _load_json(CUSTOM_PROFILES_PATH, required=False)
        profile_fallback = requested_profile_id not in self._default_profiles and requested_profile_id not in custom_profiles
        resolved_id = requested_profile_id if not profile_fallback else "human_indoor"

        base = self._default_profiles.get(resolved_id, {})
        source = "default"
        customized = False

        if resolved_id in custom_profiles:
            base = _deep_merge(base, custom_profiles[resolved_id])
            source = "custom_profile"
            customized = True

        if isinstance(profile_override, dict) and profile_override:
            base = _deep_merge(base, profile_override)
            source = "source_override"
            customized = True

        return _build_profile(resolved_id, base, source, customized), profile_fallback


PROFILE_REGISTRY = EnvironmentalProfileRegistry()
