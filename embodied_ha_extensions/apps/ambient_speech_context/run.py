#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from apps.ambient_speech_context.contract import TRANSCRIPT_TOPIC
from apps.ambient_speech_context.mqtt_client import (
    TranscriptSubscriber,
    fetch_mqtt_credentials,
)
from apps.ambient_speech_context.storage import AmbientSpeechStore


def _config() -> tuple[int, int]:
    try:
        raw = json.loads(os.environ.get("EHA_EXTENSION_CONFIG_JSON", "{}"))
    except json.JSONDecodeError as exc:
        raise ValueError("invalid_extension_config") from exc
    if not isinstance(raw, dict) or set(raw) != {"retention_hours", "max_lines"}:
        raise ValueError("invalid_extension_config")
    retention = raw["retention_hours"]
    max_lines = raw["max_lines"]
    if (
        isinstance(retention, bool)
        or not isinstance(retention, int)
        or not 1 <= retention <= 168
        or isinstance(max_lines, bool)
        or not isinstance(max_lines, int)
        or not 1 <= max_lines <= 20
    ):
        raise ValueError("invalid_extension_config")
    return retention, max_lines


def _data_dir() -> Path:
    app_id = os.environ.get("EHA_EXTENSION_ID", "")
    if app_id != "ambient_speech_context":
        raise ValueError("invalid_extension_identity")
    root = Path(os.environ.get("EHA_EXTENSIONS_DATA_ROOT", "")).resolve(strict=False)
    data = Path(os.environ.get("EHA_EXTENSION_DATA_DIR", "")).resolve(strict=False)
    if not str(root) or data != root / "apps" / app_id:
        raise ValueError("invalid_extension_data_path")
    return data


def main() -> int:
    try:
        retention, max_lines = _config()
        store = AmbientSpeechStore(_data_dir(), retention_hours=retention, max_lines=max_lines)
        store.initialize()
        credentials = fetch_mqtt_credentials()
    except Exception as exc:
        print(
            f"[ambient_speech_context] startup_failed error_type={type(exc).__name__}",
            file=sys.stderr,
            flush=True,
        )
        return 2

    subscriber = TranscriptSubscriber(store, credentials)

    def stop(_signum, _frame) -> None:
        subscriber.stop()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print(
        "[ambient_speech_context] started "
        f"topic={TRANSCRIPT_TOPIC} retention_hours={retention} max_lines={max_lines}",
        flush=True,
    )
    return subscriber.run()


if __name__ == "__main__":
    raise SystemExit(main())
