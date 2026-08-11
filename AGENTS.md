# Embodied HA Extensions project instructions

This repository hosts small, first-party, opt-in extensions for Embodied HA in one HAOS add-on.

- Keep the catalog fixed and bundled with the image. Do not add runtime package installation, arbitrary repositories, user-provided entrypoints, shell commands, or a third-party plugin ABI.
- Options select stable extension IDs only. Unknown, duplicate, malformed, or unavailable IDs fail closed before any child starts.
- Keep extension processes isolated. One child crash must not restart or stop its peers; restart loops require bounded backoff and quarantine.
- Start each extension in its own process group. Shutdown and crash cleanup must include descendants, with a bounded TERM-to-KILL deadline.
- Do not load executable code or manifests from `/config`. When shared files are added later, every write must stay under `/config/embodied-ha-extensions` after realpath and symlink checks.
- Raw household audio must not be stored. Transcript features are opt-in, disabled by default, and must document retention and broker/file exposure.
- Do not add Ingress or a custom Web UI while the Supervisor configuration tab and logs are sufficient.
- Add executable tests for lifecycle, validation, privacy, path boundaries, and recovery changes.
- Public commits authored by Codex must end with `Co-Authored-By: Codex <noreply@openai.com>`.
