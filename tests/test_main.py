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
