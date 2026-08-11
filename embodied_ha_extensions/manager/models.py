from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppManifest:
    id: str
    name: str
    version: str
    description: str
    command: tuple[str, ...]
    app_dir: Path
    default_enabled: bool
    required_capabilities: tuple[str, ...]
    input_contracts: tuple[str, ...]
    output_files: tuple[str, ...]
    extra_context_profiles: tuple[str, ...]
