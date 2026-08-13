# Embodied HA Extensions

Small, first-party, opt-in extensions for [Embodied HA](https://github.com/Khronos31/embodied-ha), hosted in one Home Assistant OS add-on.

> **Development snapshot:** `ambient_speech_context` is implemented for automated review, but this repository is not yet an installable supported release. There is no release tag or Add-on Store installation guidance. A Supervisor canary, privacy review, and shadow comparison are still required before v0.1.0.

## Why this exists

Embodied HA Core should focus on an agent's personality, body, memory, decisions, and Home Assistant actions. Tiny optional features should not turn Core back into a monolith, but creating a separate HAOS add-on for every small feature also creates unnecessary operational overhead.

This repository is a curated host for features that share the same trust boundary and can tolerate being restarted together. It is **not** a third-party plugin marketplace.

## Fixed boundaries

- Only applications bundled into the image and declared in the fixed catalog can run.
- Configuration selects stable application IDs; it never supplies commands or code paths.
- Unknown and duplicate IDs fail closed before any child starts.
- Each application runs in its own process group with independent health, bounded exponential backoff, and crash-loop quarantine.
- Shutdown propagates to descendants and escalates from `SIGTERM` to process-group `SIGKILL` after a deadline.
- There is no Ingress or custom Web UI. Configuration uses the Supervisor configuration tab; diagnostics use logs and private owned status files.
- Extensions are disabled by default. Runtime package installation, external code loading, and arbitrary plugin repositories are out of scope.

## Ambient speech context

`ambient_speech_context` subscribes at QoS 1 to the fixed `rtsp_assist_gateway/transcript` MQTT topic. It accepts only the RTSP Assist Gateway v1 event schema, rejects retained messages, deduplicates event IDs across restart, and publishes:

```text
/config/embodied-ha-extensions/
├── extra_context-loader.conf
├── enabled/ambient_speech_context.conf
└── apps/ambient_speech_context/
    ├── auditory_events.jsonl
    ├── recent_auditory_events.jsonl
    ├── usage.md
    ├── usage-short.md
    ├── extra_context.conf
    └── status.json
```

### Erasing the stored transcripts

There is no delete button yet. To erase what is held right now:

1. Stop the add-on, or clear it from **Enabled extensions**.
2. Delete `auditory_events.jsonl` and `recent_auditory_events.jsonl` from
   `/config/embodied-ha-extensions/apps/ambient_speech_context/`.
3. Start it again.

**Deleting them while it runs does not clear anything.** The history is held in memory and rewritten
to disk on the next accepted event, so the lines come back. After a stop-delete-start the counters
return to zero and nothing is reported as recovered or corrupt.

The default history window is 24 hours and the prompt projection is the latest 3 complete events in old-to-new order. Disk use is additionally bounded to 2,048 complete events and 32 MiB. Rewritten files use private mode and atomic replacement. The extension does not capture RTSP, run VAD/STT, identify speakers, store raw audio, or call an LLM.

The generated context labels transcripts as **untrusted environmental observations**, not commands. This is an interpretation boundary, not publisher authentication: any MQTT client with broker access may read or forge messages on the fixed topic. Enabling the feature therefore exposes household transcripts to authorized broker clients and stores them on the Home Assistant configuration volume.

The add-on needs Supervisor MQTT service discovery and a writable `homeassistant_config` mount at `/config`. HAOS grants that mount to the whole add-on container; application path checks are not a sandbox against compromised bundled code. No runtime code or user-provided entrypoint is accepted.

### Development configuration

The current configuration-tab contract is:

```yaml
enabled_extensions:
  - ambient_speech_context
ambient_speech_context:
  retention_hours: 24
  max_lines: 3
```

Enabling the app creates a fixed wrapper and a common loader file. It does **not** edit any Embodied HA instance. A later canary may copy the single line from `extra_context-loader.conf` into each user-owned `extra_context.conf` after explicit review.

## Development

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
ruff check .
ruff format --check .
python -m compileall -q embodied_ha_extensions tests scripts
python scripts/verify_packaging.py
```

See [CONDUCTOR.md](CONDUCTOR.md) for executable acceptance criteria and remaining live gates.
