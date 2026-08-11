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


def load_options(path: Path) -> ManagerConfig:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"cannot read options: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("options must contain an object")
    unknown = sorted(set(raw) - {"enabled_extensions", "log_level"})
    if unknown:
        raise ConfigError(f"unknown options: {unknown}")
    enabled = raw.get("enabled_extensions", [])
    if not isinstance(enabled, list) or any(not isinstance(item, str) for item in enabled):
        raise ConfigError("enabled_extensions must be a list of ids")
    log_level = raw.get("log_level", "info")
    if log_level not in {"debug", "info", "warning", "error"}:
        raise ConfigError("log_level must be debug, info, warning, or error")
    return ManagerConfig(enabled_extensions=enabled, log_level=log_level)
