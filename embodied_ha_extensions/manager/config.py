from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ManagerConfig:
    enabled_extensions: list[str]
    log_level: str
    extension_configs: dict[str, dict[str, int]]


def _ambient_speech_config(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ConfigError("ambient_speech_context must contain an object")
    unknown = sorted(set(value) - {"retention_hours", "max_lines"})
    if unknown:
        raise ConfigError(f"unknown ambient_speech_context options: {unknown}")
    retention_hours = value.get("retention_hours", 24)
    max_lines = value.get("max_lines", 3)
    if (
        isinstance(retention_hours, bool)
        or not isinstance(retention_hours, int)
        or not 1 <= retention_hours <= 168
    ):
        raise ConfigError("ambient_speech_context.retention_hours must be 1..168")
    if isinstance(max_lines, bool) or not isinstance(max_lines, int) or not 1 <= max_lines <= 20:
        raise ConfigError("ambient_speech_context.max_lines must be 1..20")
    return {"retention_hours": retention_hours, "max_lines": max_lines}


def load_options(path: Path) -> ManagerConfig:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"cannot read options: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("options must contain an object")
    unknown = sorted(set(raw) - {"enabled_extensions", "log_level", "ambient_speech_context"})
    if unknown:
        raise ConfigError(f"unknown options: {unknown}")
    enabled = raw.get("enabled_extensions", [])
    if not isinstance(enabled, list) or any(not isinstance(item, str) for item in enabled):
        raise ConfigError("enabled_extensions must be a list of ids")
    log_level = raw.get("log_level", "info")
    if log_level not in {"debug", "info", "warning", "error"}:
        raise ConfigError("log_level must be debug, info, warning, or error")
    ambient = _ambient_speech_config(raw.get("ambient_speech_context", {}))
    return ManagerConfig(
        enabled_extensions=enabled,
        log_level=log_level,
        extension_configs={"ambient_speech_context": ambient},
    )
