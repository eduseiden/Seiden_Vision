from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

FACTORY_PROFILES_PATH = Path(__file__).resolve().parent / "profiles" / "environmental_profiles.default.json"
ADDON_CONFIG_DIR = Path(os.getenv("SEIDEN_ADDON_CONFIG_DIR", "/config"))
HOMEASSISTANT_CONFIG_DIR = Path(os.getenv("SEIDEN_HOMEASSISTANT_CONFIG_DIR", "/homeassistant"))
PERSISTENT_PROFILES_PATH = HOMEASSISTANT_CONFIG_DIR / "seiden_vision" / "environmental_profiles.json"
LEGACY_PROFILES_PATH = ADDON_CONFIG_DIR / "environmental_profiles.json"
LEGACY_BACKUP_PATH = ADDON_CONFIG_DIR / "environmental_profiles.migrated-0.8.2.backup.json"
CONFIGURATION_MODE = "authoritative"


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


def _read_document(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de perfis não encontrado: {path}")
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Falha ao carregar perfis de {path}: {exc}") from exc
    if not isinstance(content, dict):
        raise ValueError(f"O arquivo {path} deve conter um objeto JSON.")
    profiles = content.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError(f"A propriedade 'profiles' de {path} deve ser um objeto não vazio.")
    return content


def _write_document_atomic(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


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


def _validate_profiles(profiles: dict[str, Any], source: str) -> None:
    if "human_indoor" not in profiles:
        raise ValueError("O arquivo de perfis exige o perfil de fallback 'human_indoor'.")
    for profile_id, raw in profiles.items():
        if not isinstance(profile_id, str) or not profile_id.strip():
            raise ValueError("Todo profile_id deve ser uma string não vazia.")
        _build_profile(profile_id, raw, source, customized=(source != "persistent_default"))


def _migrate_legacy_file_if_needed() -> bool:
    """Move o JSON da pasta privada do add-on para a pasta editável do Home Assistant."""
    if PERSISTENT_PROFILES_PATH.exists() or not LEGACY_PROFILES_PATH.exists():
        return False

    legacy_document = _read_document(LEGACY_PROFILES_PATH)
    _write_document_atomic(PERSISTENT_PROFILES_PATH, legacy_document)

    try:
        if not LEGACY_BACKUP_PATH.exists():
            os.replace(LEGACY_PROFILES_PATH, LEGACY_BACKUP_PATH)
            LOGGER.info(
                "Arquivo legado preservado como backup em %s",
                LEGACY_BACKUP_PATH,
            )
    except OSError as exc:
        LOGGER.warning(
            "O perfil foi migrado, mas não foi possível renomear o arquivo legado %s: %s",
            LEGACY_PROFILES_PATH,
            exc,
        )

    LOGGER.info(
        "Perfis ambientais migrados de %s para %s",
        LEGACY_PROFILES_PATH,
        PERSISTENT_PROFILES_PATH,
    )
    return True


def _prepare_persistent_document() -> dict[str, Any]:
    factory_document = _read_document(FACTORY_PROFILES_PATH)
    factory_profiles = factory_document["profiles"]
    _validate_profiles(factory_profiles, "factory")

    _migrate_legacy_file_if_needed()

    if not PERSISTENT_PROFILES_PATH.exists():
        _write_document_atomic(PERSISTENT_PROFILES_PATH, factory_document)
        LOGGER.info("Arquivo de perfis ambientais criado em %s", PERSISTENT_PROFILES_PATH)
        return factory_document

    persistent_document = _read_document(PERSISTENT_PROFILES_PATH)

    # Migração transparente da 0.8.1: aquele arquivo representava apenas overrides.
    if persistent_document.get("configuration_mode") != CONFIGURATION_MODE:
        merged_profiles = deepcopy(factory_profiles)
        for profile_id, override in persistent_document["profiles"].items():
            base = merged_profiles.get(profile_id, {})
            merged_profiles[profile_id] = _deep_merge(base, override)
        migrated_document = {
            "schema_version": "1.0",
            "configuration_mode": CONFIGURATION_MODE,
            "managed_by": "seiden_vision",
            "profiles": merged_profiles,
        }
        _validate_profiles(merged_profiles, "persistent_file")
        _write_document_atomic(PERSISTENT_PROFILES_PATH, migrated_document)
        LOGGER.info("Arquivo legado de perfis ambientais migrado para o formato autoritativo em %s", PERSISTENT_PROFILES_PATH)
        return migrated_document

    _validate_profiles(persistent_document["profiles"], "persistent_file")
    return persistent_document


class EnvironmentalProfileRegistry:
    """Usa o JSON persistente como fonte única dos parâmetros ambientais."""

    def __init__(self) -> None:
        document = _prepare_persistent_document()
        self._profiles = document["profiles"]
        LOGGER.info(
            "Perfis ambientais carregados de %s (%d perfis)",
            PERSISTENT_PROFILES_PATH,
            len(self._profiles),
        )

    def resolve(self, requested_profile_id: str, profile_override: Any = None) -> tuple[EnvironmentalProfile, bool]:
        profile_fallback = requested_profile_id not in self._profiles
        resolved_id = requested_profile_id if not profile_fallback else "human_indoor"
        base = deepcopy(self._profiles[resolved_id])
        source = "persistent_file"
        customized = False

        if isinstance(profile_override, dict) and profile_override:
            base = _deep_merge(base, profile_override)
            source = "source_override"
            customized = True

        return _build_profile(resolved_id, base, source, customized), profile_fallback


PROFILE_REGISTRY = EnvironmentalProfileRegistry()
