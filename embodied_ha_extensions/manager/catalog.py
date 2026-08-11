from __future__ import annotations

import json
import os
import re
from pathlib import Path, PurePosixPath

from .models import AppManifest
from .paths import PathBoundaryError, owned_path

_APP_ID = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_REQUIRED_FIELDS = {
    "id",
    "name",
    "version",
    "description",
    "entrypoint",
    "default_enabled",
    "required_capabilities",
    "input_contracts",
    "output_files",
    "extra_context_profiles",
}
_CONTEXT_PROFILES = {"guide", "hint", "context"}


class CatalogError(ValueError):
    pass


def _string_list(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise CatalogError(f"{field} must be a list of non-empty strings")
    return tuple(value)


def _relative_output(value: str) -> None:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise CatalogError(f"output_files contains an unsafe path: {value!r}")


def _load_manifest(path: Path, apps_root: Path) -> AppManifest:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CatalogError(f"cannot read manifest {path.name}: {exc}") from exc
    if not isinstance(raw, dict):
        raise CatalogError(f"manifest {path.name} must contain an object")
    fields = set(raw)
    if fields != _REQUIRED_FIELDS:
        missing = sorted(_REQUIRED_FIELDS - fields)
        extra = sorted(fields - _REQUIRED_FIELDS)
        raise CatalogError(f"manifest {path.name} fields mismatch missing={missing} extra={extra}")

    app_id = raw["id"]
    if not isinstance(app_id, str) or not _APP_ID.fullmatch(app_id):
        raise CatalogError(f"manifest {path.name} has an invalid id")
    if path.stem != app_id:
        raise CatalogError(f"manifest filename must match id {app_id!r}")

    for field in ("name", "version", "description"):
        if not isinstance(raw[field], str) or not raw[field].strip():
            raise CatalogError(f"{field} must be a non-empty string")
    if not isinstance(raw["default_enabled"], bool):
        raise CatalogError("default_enabled must be boolean")

    entrypoint = _string_list(raw["entrypoint"], "entrypoint")
    if not entrypoint:
        raise CatalogError("entrypoint must not be empty")
    first = PurePosixPath(entrypoint[0])
    if first.is_absolute() or len(first.parts) != 1 or first.parts[0] in {".", ".."}:
        raise CatalogError("entrypoint executable must be one bundled filename")
    app_dir = owned_path(apps_root, app_id)
    try:
        executable = owned_path(app_dir, entrypoint[0])
    except PathBoundaryError as exc:
        raise CatalogError(str(exc)) from exc
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise CatalogError(f"entrypoint is not an executable bundled file: {entrypoint[0]}")
    command = (str(executable), *entrypoint[1:])

    capabilities = _string_list(raw["required_capabilities"], "required_capabilities")
    inputs = _string_list(raw["input_contracts"], "input_contracts")
    outputs = _string_list(raw["output_files"], "output_files")
    for output in outputs:
        _relative_output(output)
    profiles = _string_list(raw["extra_context_profiles"], "extra_context_profiles")
    unknown_profiles = sorted(set(profiles) - _CONTEXT_PROFILES)
    if unknown_profiles:
        raise CatalogError(f"unknown extra_context_profiles: {unknown_profiles}")

    return AppManifest(
        id=app_id,
        name=raw["name"],
        version=raw["version"],
        description=raw["description"],
        command=command,
        app_dir=app_dir,
        default_enabled=raw["default_enabled"],
        required_capabilities=capabilities,
        input_contracts=inputs,
        output_files=outputs,
        extra_context_profiles=profiles,
    )


def load_catalog(catalog_dir: Path, apps_root: Path) -> dict[str, AppManifest]:
    manifests: dict[str, AppManifest] = {}
    try:
        paths = sorted(catalog_dir.glob("*.json"))
    except OSError as exc:
        raise CatalogError(f"cannot list catalog: {exc}") from exc
    for path in paths:
        manifest = _load_manifest(path, apps_root)
        if manifest.id in manifests:
            raise CatalogError(f"duplicate manifest id: {manifest.id}")
        manifests[manifest.id] = manifest
    return manifests


def select_apps(catalog: dict[str, AppManifest], requested: list[str]) -> list[AppManifest]:
    if len(requested) != len(set(requested)):
        raise CatalogError("enabled_extensions contains duplicate ids")
    unknown = sorted(set(requested) - set(catalog))
    if unknown:
        raise CatalogError(f"unknown enabled extension ids: {unknown}")
    return [catalog[app_id] for app_id in requested]
