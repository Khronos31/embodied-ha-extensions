from __future__ import annotations

import shlex
from pathlib import Path

from .models import AppManifest
from .paths import atomic_write_text, owned_path


def sync_context_files(
    data_root: Path,
    catalog: dict[str, AppManifest],
    selected: list[AppManifest],
) -> None:
    """Publish only fixed wrappers for selected bundled applications."""
    enabled_dir = owned_path(data_root, "enabled")
    enabled_dir.mkdir(parents=True, exist_ok=True)
    selected_ids = {manifest.id for manifest in selected}

    for stale in enabled_dir.glob("*.conf"):
        if stale.is_file() or stale.is_symlink():
            stale.unlink()

    for app_id, manifest in sorted(catalog.items()):
        if app_id not in selected_ids or not manifest.extra_context_profiles:
            continue
        app_context = owned_path(data_root, "apps", app_id, "extra_context.conf")
        wrapper = owned_path(enabled_dir, f"{app_id}.conf")
        quoted = shlex.quote(str(app_context))
        atomic_write_text(wrapper, f"[ -r {quoted} ] && . {quoted}\n")

    loader = owned_path(data_root, "extra_context-loader.conf")
    directory = shlex.quote(str(enabled_dir))
    line = f'for f in {directory}/*.conf; do [ -r "$f" ] && . "$f"; done\n'
    atomic_write_text(loader, line)
