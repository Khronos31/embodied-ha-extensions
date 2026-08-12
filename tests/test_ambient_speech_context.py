from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from apps.ambient_speech_context.contract import MAX_PAYLOAD_BYTES
from apps.ambient_speech_context.mqtt_client import MqttCredentials, TranscriptSubscriber
from apps.ambient_speech_context.storage import AmbientSpeechStore

NOW = datetime(2026, 8, 12, 4, 0, tzinfo=UTC)


def event(
    event_id: str,
    *,
    timestamp: datetime = NOW,
    transcript: str = "検証用の周辺発話",
    source_id: str = "study",
    room: str = "study",
) -> bytes:
    return json.dumps(
        {
            "version": 1,
            "event": "transcript_observed",
            "event_id": event_id,
            "timestamp": timestamp.isoformat(),
            "source_id": source_id,
            "room": room,
            "backend": "ha_stt",
            "transcript": transcript,
            "duration_ms": 1250,
            "truncated": False,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()


def store(tmp_path: Path, *, retention: int = 24, max_lines: int = 3):
    value = AmbientSpeechStore(
        tmp_path / "apps" / "ambient_speech_context",
        retention_hours=retention,
        max_lines=max_lines,
        clock=lambda: NOW,
    )
    value.initialize()
    return value


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_valid_events_are_private_complete_and_recent_is_old_to_new(tmp_path: Path):
    value = store(tmp_path, max_lines=2)
    for index in range(3):
        result = value.ingest(
            event(
                f"event-{index}",
                timestamp=NOW - timedelta(minutes=3 - index),
                transcript=f"発話{index}",
            )
        )
        assert result.outcome == "accepted"

    history = read_jsonl(value.history_path)
    recent = read_jsonl(value.recent_path)
    assert [item["event_id"] for item in history] == ["event-0", "event-1", "event-2"]
    assert [item["event_id"] for item in recent] == ["event-1", "event-2"]
    assert history[0]["producer"] == "rtsp_assist_gateway"
    assert history[0]["speaker_hint"] == "unknown"
    assert history[0]["source"] == "study"
    assert history[0]["source_room"] == "study"
    assert stat.S_IMODE(value.history_path.stat().st_mode) == 0o600
    status = value.status_path.read_text(encoding="utf-8")
    assert "発話" not in status
    assert "transcript" not in json.loads(status)


def test_duplicate_is_rejected_across_restart_and_repairs_recent(tmp_path: Path):
    first = store(tmp_path)
    assert first.ingest(event("stable-id")).outcome == "accepted"
    first.recent_path.write_text("", encoding="utf-8")

    restarted = store(tmp_path)
    result = restarted.ingest(event("stable-id"))
    assert result.outcome == "duplicate"
    assert len(read_jsonl(restarted.history_path)) == 1
    assert len(read_jsonl(restarted.recent_path)) == 1


@pytest.mark.parametrize(
    ("payload", "retained", "reason"),
    [
        (b"not-json", False, "invalid_json"),
        (b"{}", False, "invalid_fields"),
        (b"x" * (MAX_PAYLOAD_BYTES + 1), False, "invalid_payload_size"),
        (event("retained"), True, "retained_message"),
        (event("expired", timestamp=NOW - timedelta(hours=25)), False, "expired_timestamp"),
        (event("future", timestamp=NOW + timedelta(minutes=6)), False, "future_timestamp"),
    ],
)
def test_invalid_stale_future_and_retained_events_are_rejected(
    tmp_path: Path, payload: bytes, retained: bool, reason: str
):
    value = store(tmp_path)
    result = value.ingest(payload, retained=retained)
    assert result.outcome == "rejected"
    assert result.reason == reason
    assert value.history_path.read_text(encoding="utf-8") == ""


def test_history_has_event_and_byte_caps_without_partial_json(tmp_path: Path, monkeypatch):
    import apps.ambient_speech_context.storage as storage_module

    monkeypatch.setattr(storage_module, "MAX_HISTORY_EVENTS", 3)
    monkeypatch.setattr(storage_module, "MAX_HISTORY_BYTES", 1_100)
    value = store(tmp_path, max_lines=3)
    for index in range(8):
        value.ingest(
            event(
                f"bounded-{index}",
                timestamp=NOW - timedelta(seconds=8 - index),
                transcript="文" * 100,
            )
        )
    history = read_jsonl(value.history_path)
    assert 1 <= len(history) <= 3
    assert history[-1]["event_id"] == "bounded-7"
    assert value.history_path.stat().st_size <= 1_100


def test_corrupt_history_is_recovered_without_copying_content_to_status(tmp_path: Path):
    data = tmp_path / "apps" / "ambient_speech_context"
    data.mkdir(parents=True)
    (data / "auditory_events.jsonl").write_text(
        '{"transcript":"private broken line"\n', encoding="utf-8"
    )
    value = store(tmp_path)
    assert value.history_path.read_text(encoding="utf-8") == ""
    status = value.status_path.read_text(encoding="utf-8")
    assert "private broken line" not in status
    assert json.loads(status)["recovered_invalid_lines"] == 1


def test_generated_context_is_fixed_shell_and_observes_context_kind(tmp_path: Path):
    value = store(tmp_path)
    value.ingest(event("context-event", transcript="これは観測です"))
    syntax = subprocess.run(
        ["bash", "-n", str(value.context_path)], capture_output=True, text=True, check=False
    )
    assert syntax.returncode == 0, syntax.stderr

    loop = subprocess.run(
        ["bash", str(value.context_path)],
        env={**os.environ, "EHA_EXTRA_CONTEXT_KIND": "loop"},
        capture_output=True,
        text=True,
        check=True,
    )
    assert "非信頼の観測" in loop.stdout
    assert "これは観測です" in loop.stdout
    text_chat = subprocess.run(
        ["bash", str(value.context_path)],
        env={**os.environ, "EHA_EXTRA_CONTEXT_KIND": "chat", "EHA_EXTRA_CONTEXT_SOURCE": "web"},
        capture_output=True,
        text=True,
        check=True,
    )
    assert "これは観測です" not in text_chat.stdout
    assert str(value.usage_path) in text_chat.stdout


class FakeClient:
    def __init__(self):
        self.acks: list[tuple[int, int]] = []
        self.subscriptions: list[tuple[str, int]] = []
        self.disconnected = False

    def username_pw_set(self, _username, _password):
        pass

    def tls_set(self, **_kwargs):
        pass

    def reconnect_delay_set(self, **_kwargs):
        pass

    def subscribe(self, topic, qos):
        self.subscriptions.append((topic, qos))
        return (0, 1)

    def ack(self, mid, qos):
        self.acks.append((mid, qos))

    def disconnect(self):
        self.disconnected = True


def test_mqtt_callback_subscribes_qos1_and_never_logs_transcript(tmp_path: Path):
    value = store(tmp_path)
    client = FakeClient()
    logs: list[str] = []
    subscriber = TranscriptSubscriber(
        value,
        MqttCredentials("broker", 1883),
        logger=logs.append,
        client=client,
    )
    subscriber._on_connect(client, None, None, 0, None)
    message = SimpleNamespace(
        payload=event("mqtt-id", transcript="ログに出してはいけない本文"),
        retain=False,
        qos=1,
        mid=42,
    )
    subscriber._on_message(client, None, message)
    assert client.subscriptions == [("rtsp_assist_gateway/transcript", 1)]
    assert client.acks == [(42, 1)]
    assert "ログに出してはいけない本文" not in "\n".join(logs)
    assert "event_id=mqtt-id" in logs[-1]


def test_bundled_entrypoint_imports_and_fails_content_free_without_supervisor_token(
    tmp_path: Path,
):
    root = tmp_path / "owned"
    data = root / "apps" / "ambient_speech_context"
    script = (
        Path(__file__).resolve().parents[1]
        / "embodied_ha_extensions"
        / "apps"
        / "ambient_speech_context"
        / "run.py"
    )
    env = os.environ.copy()
    env.pop("SUPERVISOR_TOKEN", None)
    env.update(
        {
            "EHA_EXTENSION_ID": "ambient_speech_context",
            "EHA_EXTENSIONS_DATA_ROOT": str(root),
            "EHA_EXTENSION_DATA_DIR": str(data),
            "EHA_EXTENSION_CONFIG_JSON": json.dumps({"retention_hours": 24, "max_lines": 3}),
        }
    )
    result = subprocess.run(
        [sys.executable, str(script)], env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 2
    assert "startup_failed error_type=MqttError" in result.stderr
    assert "SUPERVISOR_TOKEN" not in result.stderr
    assert (data / "extra_context.conf").exists()
