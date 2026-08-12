from __future__ import annotations

import subprocess
from pathlib import Path

from manager.context_files import sync_context_files
from manager.models import AppManifest


def app(tmp_path: Path, app_id: str = "ambient_speech_context") -> AppManifest:
    app_dir = tmp_path / "bundled" / app_id
    app_dir.mkdir(parents=True)
    executable = app_dir / "run.py"
    executable.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    executable.chmod(0o755)
    return AppManifest(
        id=app_id,
        name=app_id,
        version="test",
        description="fixture",
        command=(str(executable),),
        app_dir=app_dir,
        default_enabled=False,
        required_capabilities=(),
        input_contracts=(),
        output_files=(),
        extra_context_profiles=("context",),
    )


def test_context_wrapper_is_fixed_private_and_removed_when_disabled(tmp_path: Path):
    manifest = app(tmp_path)
    root = tmp_path / "owned data"
    sync_context_files(root, {manifest.id: manifest}, [manifest])
    wrapper = root / "enabled" / f"{manifest.id}.conf"
    loader = root / "extra_context-loader.conf"
    expected_context = root / "apps" / manifest.id / "extra_context.conf"
    assert str(expected_context) in wrapper.read_text(encoding="utf-8")
    assert "transcript" not in wrapper.read_text(encoding="utf-8")
    for path in (wrapper, loader):
        result = subprocess.run(
            ["bash", "-n", str(path)], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stderr

    sync_context_files(root, {manifest.id: manifest}, [])
    assert not wrapper.exists()
    assert loader.exists()
