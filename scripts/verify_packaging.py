from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "embodied_ha_extensions"
sys.path.insert(0, str(ADDON))

from manager import __version__  # noqa: E402


def main() -> int:
    config = yaml.safe_load((ADDON / "config.yaml").read_text(encoding="utf-8"))
    assert config["version"] == __version__
    assert config["slug"] == "embodied_ha_extensions"
    assert config["stage"] == "experimental"
    assert config["boot"] == "manual"
    assert config["hassio_api"] is True
    assert config["services"] == ["mqtt:need"]
    assert config["map"] == [
        {
            "type": "homeassistant_config",
            "read_only": False,
            "path": "/config",
        }
    ]
    for forbidden in ("ingress", "homeassistant_api", "privileged", "full_access"):
        assert forbidden not in config, f"add-on must not declare {forbidden}"
    assert config["options"] == {
        "log_level": "info",
        "enabled_extensions": [],
        "ambient_speech_context": {"retention_hours": 24, "max_lines": 3},
    }
    manifests = list((ADDON / "catalog").glob("*.json"))
    catalog_ids = sorted(
        json.loads(path.read_text(encoding="utf-8"))["id"] for path in manifests
    )
    assert config["schema"] == {
        "log_level": "list(debug|info|warning|error)",
        "enabled_extensions": [f"list({'|'.join(catalog_ids)})"],
        "ambient_speech_context": {
            "retention_hours": "int(1,168)",
            "max_lines": "int(1,20)",
        },
    }, "enabled_extensions must offer exactly the bundled catalog ids"

    # The configuration tab is the only place a user selects an extension, so every schema key
    # needs a name and a description there, in each shipped language.
    for language in ("en", "ja"):
        path = ADDON / "translations" / f"{language}.yaml"
        assert path.is_file(), f"missing translations/{language}.yaml"
        translated = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        section = translated.get("configuration") or {}
        assert set(section) == set(config["schema"]), (
            f"translations/{language}.yaml must describe exactly the schema keys"
        )
        for key, entry in section.items():
            assert entry.get("name") and entry.get("description"), (
                f"translations/{language}.yaml: {key} needs a name and a description"
            )
        nested = section["ambient_speech_context"].get("fields") or {}
        assert set(nested) == set(config["schema"]["ambient_speech_context"])


    assert [path.name for path in manifests] == ["ambient_speech_context.json"]
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["id"] == "ambient_speech_context"
    assert manifest["version"] == __version__
    assert manifest["default_enabled"] is False
    assert manifest["entrypoint"] == ["run.py"]
    assert manifest["required_capabilities"] == ["mqtt", "supervisor_api", "config_rw"]
    assert manifest["input_contracts"] == ["rtsp_assist_gateway.transcript.v1"]
    app = ADDON / "apps" / "ambient_speech_context"
    assert (app / "run.py").stat().st_mode & 0o111
    assert not any(path.is_symlink() for path in app.rglob("*"))

    requirements = (ADDON / "requirements.txt").read_text(encoding="utf-8").splitlines()
    assert requirements == ["paho-mqtt==2.1.0"]
    dockerfile = (ADDON / "Dockerfile").read_text(encoding="utf-8")
    for required in (
        "COPY requirements.txt",
        "pip install --no-cache-dir",
        "COPY manager",
        "COPY catalog",
        "COPY apps",
        'CMD ["/app/run.sh"]',
    ):
        assert required in dockerfile
    assert (ADDON / "run.sh").stat().st_mode & 0o111
    print("packaging verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
