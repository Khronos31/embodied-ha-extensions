# Embodied HA Extensions

Small, first-party, opt-in extensions for [Embodied HA](https://github.com/Khronos31/embodied-ha), hosted in one Home Assistant OS add-on.

> **Development snapshot:** this repository does not yet contain a useful extension and is not an installable supported release. There is no release tag or Add-on Store installation guidance. The first supported milestone will include `ambient_speech_context` and will be released separately as v0.1.0 after its privacy and transcript contracts pass review.

## Why this exists

Embodied HA Core should focus on an agent's personality, body, memory, decisions, and Home Assistant actions. Tiny optional features should not turn Core back into a monolith, but creating a separate HAOS add-on for every small feature also creates unnecessary operational overhead.

This repository is a curated host for features that share the same trust boundary and can tolerate being restarted together. It is **not** a third-party plugin marketplace.

## Fixed boundaries

- Only applications bundled into the image and declared in the fixed catalog can run.
- Configuration selects stable application IDs; it never supplies commands or code paths.
- Unknown and duplicate IDs fail closed before any child starts.
- Each application runs in its own process group with independent health, bounded exponential backoff, and crash-loop quarantine.
- Shutdown propagates to descendants and escalates from `SIGTERM` to process-group `SIGKILL` after a deadline.
- There is no Ingress or custom Web UI. Configuration uses the Supervisor configuration tab; diagnostics use logs and owned status files.
- Extensions are disabled by default. Runtime package installation, external code loading, and arbitrary plugin repositories are out of scope.

The development skeleton intentionally has no `/config` mount. A later shared-file extension may request `/config:rw` only after a separate review; all writes will remain under `/config/embodied-ha-extensions` with traversal and symlink escape protection.

## Planned first extension

`ambient_speech_context` will receive versioned, non-retained transcript events from RTSP Assist Gateway and publish bounded JSONL context for explicitly opted-in Embodied HA instances. It will not capture RTSP audio, run a second VAD/STT pipeline, store raw audio, or use a remote LLM for summarization.

The transport, event schema, retention defaults, and privacy disclosure belong to the next design increment and are not implemented here.

## Development

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
ruff check .
ruff format --check .
python -m compileall -q embodied_ha_extensions tests scripts
python scripts/verify_packaging.py
```

See [CONDUCTOR.md](CONDUCTOR.md) for executable acceptance criteria.
