from __future__ import annotations

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
    for forbidden in (
        "ingress",
        "map",
        "hassio_api",
        "homeassistant_api",
        "services",
        "privileged",
        "full_access",
    ):
        assert forbidden not in config, f"development skeleton must not declare {forbidden}"
    assert config["options"] == {"log_level": "info", "enabled_extensions": []}
    assert config["schema"] == {
        "log_level": "list(debug|info|warning|error)",
        "enabled_extensions": ["str"],
    }
    assert not list((ADDON / "catalog").glob("*.json"))
    assert not any(
        path.is_file() and path.name != "README.md" for path in (ADDON / "apps").iterdir()
    )

    dockerfile = (ADDON / "Dockerfile").read_text(encoding="utf-8")
    for required in ("COPY manager", "COPY catalog", "COPY apps", 'CMD ["/app/run.sh"]'):
        assert required in dockerfile
    assert (ADDON / "run.sh").stat().st_mode & 0o111
    print("packaging verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
