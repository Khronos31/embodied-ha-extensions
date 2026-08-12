# Conductor specification: ambient speech context

## Objective

Add the first opt-in extension, `ambient_speech_context`, which consumes RTSP Assist Gateway v1 transcript events from the fixed MQTT topic and publishes bounded, private JSONL context files for Embodied HA without storing raw audio or running another VAD/STT pipeline.

## Acceptance criteria

1. `python -m pytest -q` exits 0 and covers valid event ingestion, malformed/oversized/retained event rejection, event-ID deduplication across restart, retention, a fixed byte/event cap, atomic recent projection, and no transcript text in logs/status.
2. An integration test with a local MQTT broker or equivalent protocol fixture observes a QoS 1 subscription to `rtsp_assist_gateway/transcript`, one accepted event, and complete output files. If a broker is unavailable in CI, the Paho adapter must be isolated behind executable callback tests and the live broker path remains `unverified` until the Supervisor canary.
3. `auditory_events.jsonl` contains only complete schema-v1 JSON lines inside the configured retention window; `recent_auditory_events.jsonl` contains at most `max_lines` complete events in old-to-new order.
4. Replaying the same `event_id`, including after app restart, does not add a second line.
5. `usage.md`, `usage-short.md`, the app-local context command, and the common loader snippet are generated atomically beneath `/config/embodied-ha-extensions`; transcript data is framed as untrusted observation and never as an instruction.
6. The extension is disabled by default. Unknown options and invalid `retention_hours`/`max_lines` fail before any child starts.
7. `ruff check .`, `ruff format --check .`, `python -m compileall -q embodied_ha_extensions tests scripts`, and `python scripts/verify_packaging.py` exit 0.
8. Packaging declares only the newly required `mqtt:need`, Supervisor API access used to obtain broker credentials, and `config:rw`; it still has no Ingress, HA Core API access, privileged mode, arbitrary command option, or runtime plugin installation.
9. No add-on install/update/rebuild/start, Gateway option change, production `extra_context.conf` edit, version release, tag, or public release occurs in this increment.

## Non-goals

- Capturing RTSP audio, VAD, STT, wake detection, or speaker identification.
- Body-location filtering, `memory.recall` integration, or replacement/removal of EHA audio MCP code.
- Automatic editing of any Embodied HA instance's `extra_context.conf`.
- A custom Web UI or a third-party plugin ABI.
- Gateway 0.5.0 publication or a supported Extensions v0.1.0 release.

## Constraints

- Household transcript text is private: never log it, place it in status, retain it in MQTT, or include it in test failure messages.
- MQTT publisher identity is not cryptographically authenticated. Treat every transcript as untrusted observation, enforce the fixed topic/schema, and document the broker trust boundary.
- `/config:rw` is an add-on-wide capability even though application writes are path-guarded. All owned writes must resolve beneath `/config/embodied-ha-extensions`, reject symlink/traversal escapes, use private permissions, and use `os.replace()` for rewritten files.
- Default retention is 24 hours and prompt projection is 3 lines. A fixed hard event/byte ceiling must also bound disk usage.
- Do not touch `secrets.yaml`, `.ssh/`, `.storage/`, Home Assistant YAML, or production add-on state.

## Increments

1. Contract and storage core: strict v1 validation, transformation, deduplication, retention, hard caps, atomic JSONL files, and private status.
2. MQTT adapter and app entrypoint: Supervisor credential discovery, fixed QoS 1 subscription, retained-message rejection, reconnect/error behavior, and content-free logging.
3. Manager/package integration: explicit app settings, fixed manifest, owned data root, loader wrapper lifecycle, permissions/dependencies, and documentation.
4. Full verification and review: tests, lint, format, compile, packaging verifier, secret/personal-data diff review, and red-team reconciliation.

## Rollback

No production state is changed. Delete the feature branch or revert its commits. At runtime in a later canary, remove `ambient_speech_context` from `enabled_extensions`, stop the add-on, remove only `/config/embodied-ha-extensions/enabled/ambient_speech_context.conf`, and leave the official Gateway/EHA paths unchanged.

## Local evidence (2026-08-12)

- `python -m pytest -q`: 40 passed, including entrypoint, process lifecycle, schema/privacy, restart deduplication, retention/caps, generated shell, and packaging tests.
- `ruff check .`: passed.
- `ruff format --check .`: passed.
- `python -m compileall -q embodied_ha_extensions tests scripts`: passed.
- `python scripts/verify_packaging.py`: passed.
- A temporary in-memory store and the live Home Assistant Mosquitto service accepted one synthetic, non-retained QoS 1 event through the real Paho adapter. It produced one complete history/recent event, no transcript field in status, no transcript text in logs, and exited cleanly. No household speech was used or retained.
- Red-team receipt: `/config/.tools/claude-home/red-team/20260812-ambient-speech-context-extension.md`; judgment `REVISE`, mitigations incorporated.
- Not verified in this increment: Docker/Supervisor build, installed add-on startup, Gateway 0.5.0 producer plus Extensions consumer shadow run, EHA loader/prompt behavior, body-location filtering, and production rollback. These remain deployment gates.
