from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime

MAX_PAYLOAD_BYTES = 16 * 1024
MAX_STORED_EVENT_BYTES = 20 * 1024
TRANSCRIPT_TOPIC = "rtsp_assist_gateway/transcript"
_EVENT_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_EXPECTED_KEYS = {
    "version",
    "event",
    "event_id",
    "timestamp",
    "source_id",
    "room",
    "backend",
    "transcript",
    "duration_ms",
    "truncated",
}


class EventError(ValueError):
    """Content-free validation error safe to report in logs."""


def _text(value: object, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise EventError(f"invalid_{field}")
    if any(ord(character) < 32 and character not in "\t\n\r" for character in value):
        raise EventError(f"invalid_{field}")
    return value


def parse_timestamp(value: object) -> datetime:
    text = _text(value, "timestamp", 64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EventError("invalid_timestamp") from exc
    if parsed.tzinfo is None:
        raise EventError("invalid_timestamp")
    return parsed.astimezone(UTC)


@dataclass(frozen=True)
class GatewayTranscriptEvent:
    event_id: str
    timestamp: str
    timestamp_value: datetime
    source_id: str
    room: str
    transcript: str
    duration_ms: int
    truncated: bool

    def stored_payload(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "producer": "rtsp_assist_gateway",
            "source": self.source_id,
            "source_room": self.room,
            "origin": "rtsp_assist_gateway",
            "speaker_hint": "unknown",
            "transcript": self.transcript,
            "duration_sec": round(self.duration_ms / 1000, 3),
            "truncated": self.truncated,
        }


def decode_gateway_event(payload: bytes) -> GatewayTranscriptEvent:
    if not payload or len(payload) > MAX_PAYLOAD_BYTES:
        raise EventError("invalid_payload_size")
    try:
        raw = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EventError("invalid_json") from exc
    if not isinstance(raw, dict) or set(raw) != _EXPECTED_KEYS:
        raise EventError("invalid_fields")
    if isinstance(raw["version"], bool) or raw["version"] != 1:
        raise EventError("unsupported_version")
    if raw["event"] != "transcript_observed" or raw["backend"] != "ha_stt":
        raise EventError("invalid_contract")

    event_id = _text(raw["event_id"], "event_id", 128)
    if not _EVENT_ID.fullmatch(event_id):
        raise EventError("invalid_event_id")
    timestamp_value = parse_timestamp(raw["timestamp"])
    source_id = _text(raw["source_id"], "source_id", 128)
    room = _text(raw["room"], "room", 128)
    transcript = _text(raw["transcript"], "transcript", MAX_PAYLOAD_BYTES)
    if not transcript.strip():
        raise EventError("invalid_transcript")
    duration_ms = raw["duration_ms"]
    if (
        isinstance(duration_ms, bool)
        or not isinstance(duration_ms, int)
        or not 1 <= duration_ms <= 3_600_000
    ):
        raise EventError("invalid_duration_ms")
    truncated = raw["truncated"]
    if not isinstance(truncated, bool):
        raise EventError("invalid_truncated")

    event = GatewayTranscriptEvent(
        event_id=event_id,
        timestamp=timestamp_value.isoformat(),
        timestamp_value=timestamp_value,
        source_id=source_id,
        room=room,
        transcript=transcript.strip(),
        duration_ms=duration_ms,
        truncated=truncated,
    )
    encoded = json.dumps(event.stored_payload(), ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    if not math.isfinite(event.duration_ms / 1000) or len(encoded) > MAX_STORED_EVENT_BYTES:
        raise EventError("stored_event_too_large")
    return event


def validate_stored_event(raw: object) -> tuple[dict[str, object], datetime]:
    if not isinstance(raw, dict):
        raise EventError("invalid_stored_event")
    required = {
        "schema_version",
        "event_id",
        "timestamp",
        "producer",
        "source",
        "source_room",
        "origin",
        "speaker_hint",
        "transcript",
        "duration_sec",
        "truncated",
    }
    if set(raw) != required or raw.get("schema_version") != 1:
        raise EventError("invalid_stored_event")
    if raw.get("producer") != "rtsp_assist_gateway" or raw.get("origin") != "rtsp_assist_gateway":
        raise EventError("invalid_stored_event")
    event_id = _text(raw.get("event_id"), "event_id", 128)
    if not _EVENT_ID.fullmatch(event_id):
        raise EventError("invalid_stored_event")
    timestamp = parse_timestamp(raw.get("timestamp"))
    _text(raw.get("source"), "source", 128)
    _text(raw.get("source_room"), "source_room", 128)
    if raw.get("speaker_hint") != "unknown":
        raise EventError("invalid_stored_event")
    _text(raw.get("transcript"), "transcript", MAX_PAYLOAD_BYTES)
    duration = raw.get("duration_sec")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)):
        raise EventError("invalid_stored_event")
    if not math.isfinite(duration) or duration <= 0:
        raise EventError("invalid_stored_event")
    if not isinstance(raw.get("truncated"), bool):
        raise EventError("invalid_stored_event")
    return raw, timestamp
