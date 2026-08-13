from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest
from manager.config import ConfigError, load_options
from manager.paths import PathBoundaryError, atomic_write_json, owned_path


def test_options_contain_ids_only(tmp_path: Path):
    path = tmp_path / "options.json"
    path.write_text(
        json.dumps({"enabled_extensions": ["ambient_speech_context"], "log_level": "info"}),
        encoding="utf-8",
    )
    options = load_options(path)
    assert options.enabled_extensions == ["ambient_speech_context"]
    assert options.extension_configs["ambient_speech_context"] == {
        "retention_hours": 24,
        "max_lines": 3,
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"enabled_extensions": "sample"},
        {"enabled_extensions": ["sample"], "command": "sh -c id"},
        {"enabled_extensions": [], "log_level": "verbose"},
        {"enabled_extensions": [], "ambient_speech_context": {"retention_hours": 0}},
        {"enabled_extensions": [], "ambient_speech_context": {"max_lines": 21}},
        {"enabled_extensions": [], "ambient_speech_context": {"shell": "id"}},
    ],
)
def test_options_fail_closed(payload: dict, tmp_path: Path):
    path = tmp_path / "options.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_options(path)


def test_owned_path_rejects_traversal_and_symlink(tmp_path: Path):
    root = tmp_path / "owned"
    root.mkdir()
    assert owned_path(root, "apps", "sample") == root / "apps" / "sample"
    with pytest.raises(PathBoundaryError):
        owned_path(root, "..", "configuration.yaml")

    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PathBoundaryError):
        owned_path(root, "link", "value.json")


def test_atomic_json_is_private_and_replaced(tmp_path: Path):
    path = tmp_path / "status.json"
    atomic_write_json(path, {"generation": 1})
    first_inode = path.stat().st_ino
    atomic_write_json(path, {"generation": 2})
    assert json.loads(path.read_text(encoding="utf-8")) == {"generation": 2}
    assert path.stat().st_ino != first_inode
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
