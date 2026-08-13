from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def test_empty_catalog_runs_and_shuts_down_cleanly(tmp_path: Path):
    options = tmp_path / "options.json"
    catalog = tmp_path / "catalog"
    apps = tmp_path / "apps"
    data = tmp_path / "data"
    options.write_text(
        json.dumps({"enabled_extensions": [], "log_level": "info"}),
        encoding="utf-8",
    )
    catalog.mkdir()
    apps.mkdir()
    env = os.environ.copy()
    env.update(
        {
            "EHA_EXTENSIONS_OPTIONS_FILE": str(options),
            "EHA_EXTENSIONS_CATALOG_DIR": str(catalog),
            "EHA_EXTENSIONS_APPS_DIR": str(apps),
            "EHA_EXTENSIONS_DATA_ROOT": str(data),
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "manager.main"],
        cwd=Path(__file__).resolve().parents[1] / "embodied_ha_extensions",
        env=env,
    )
    status = data / "status.json"
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not status.exists():
        time.sleep(0.02)
    assert status.exists()
    process.terminate()
    assert process.wait(timeout=5) == 0
    payload = json.loads(status.read_text(encoding="utf-8"))
    assert payload == {"schema_version": 1, "stopping": True, "apps": {}}


def test_unknown_id_rejects_entire_startup_before_known_app_runs(tmp_path: Path):
    options = tmp_path / "options.json"
    catalog = tmp_path / "catalog"
    apps = tmp_path / "apps"
    app_dir = apps / "known"
    marker = tmp_path / "must-not-exist"
    catalog.mkdir()
    app_dir.mkdir(parents=True)
    executable = app_dir / "run.py"
    executable.write_text(
        f"#!/usr/bin/env python3\nfrom pathlib import Path\nPath({str(marker)!r}).touch()\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    manifest = {
        "id": "known",
        "name": "Known",
        "version": "test",
        "description": "fixture",
        "entrypoint": ["run.py"],
        "default_enabled": False,
        "required_capabilities": [],
        "input_contracts": [],
        "output_files": [],
        "extra_context_profiles": [],
    }
    (catalog / "known.json").write_text(json.dumps(manifest), encoding="utf-8")
    options.write_text(
        json.dumps({"enabled_extensions": ["known", "unknown"], "log_level": "info"}),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(
        {
            "EHA_EXTENSIONS_OPTIONS_FILE": str(options),
            "EHA_EXTENSIONS_CATALOG_DIR": str(catalog),
            "EHA_EXTENSIONS_APPS_DIR": str(apps),
            "EHA_EXTENSIONS_DATA_ROOT": str(tmp_path / "data"),
        }
    )
    result = subprocess.run(
        [sys.executable, "-m", "manager.main"],
        cwd=Path(__file__).resolve().parents[1] / "embodied_ha_extensions",
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert "unknown enabled extension ids" in result.stderr
    assert not marker.exists()


def test_context_wrapper_exists_only_while_selected_child_is_running(tmp_path: Path):
    options = tmp_path / "options.json"
    catalog = tmp_path / "catalog"
    apps = tmp_path / "apps"
    data = tmp_path / "data"
    app_dir = apps / "context_app"
    catalog.mkdir()
    app_dir.mkdir(parents=True)
    executable = app_dir / "run.py"
    executable.write_text(
        "#!/usr/bin/env python3\nimport time\nwhile True:\n    time.sleep(0.1)\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    manifest = {
        "id": "context_app",
        "name": "Context app",
        "version": "test",
        "description": "fixture",
        "entrypoint": ["run.py"],
        "default_enabled": False,
        "required_capabilities": [],
        "input_contracts": [],
        "output_files": ["extra_context.conf"],
        "extra_context_profiles": ["context"],
    }
    (catalog / "context_app.json").write_text(json.dumps(manifest), encoding="utf-8")
    options.write_text(
        json.dumps({"enabled_extensions": ["context_app"], "log_level": "info"}),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(
        {
            "EHA_EXTENSIONS_OPTIONS_FILE": str(options),
            "EHA_EXTENSIONS_CATALOG_DIR": str(catalog),
            "EHA_EXTENSIONS_APPS_DIR": str(apps),
            "EHA_EXTENSIONS_DATA_ROOT": str(data),
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "manager.main"],
        cwd=Path(__file__).resolve().parents[1] / "embodied_ha_extensions",
        env=env,
    )
    wrapper = data / "enabled" / "context_app.conf"
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not wrapper.exists():
        time.sleep(0.02)
    assert wrapper.exists()
    process.terminate()
    assert process.wait(timeout=5) == 0
    assert not wrapper.exists()
