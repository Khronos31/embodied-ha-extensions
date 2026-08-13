from __future__ import annotations

import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any


class PathBoundaryError(ValueError):
    pass


def owned_path(root: Path, *parts: str) -> Path:
    """Resolve a path and reject absolute, traversal, and symlink escapes."""
    resolved_root = root.resolve(strict=False)
    candidate = resolved_root.joinpath(*parts).resolve(strict=False)
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise PathBoundaryError(f"path escapes owned root: {candidate}")
    return candidate


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        with suppress(OSError):
            os.close(fd)
        with suppress(OSError):
            os.unlink(temporary)
        raise
