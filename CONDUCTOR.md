# Conductor specification: initial skeleton

## Objective

Create a public development skeleton for a first-party HAOS add-on that supervises a fixed catalog of small Embodied HA extensions.

## Acceptance criteria

1. `python -m pytest -q` exits 0, including real child/grandchild lifecycle tests.
2. `ruff check .` and `ruff format --check .` exit 0.
3. `python -m compileall -q embodied_ha_extensions tests scripts` exits 0.
4. `python scripts/verify_packaging.py` confirms version consistency, no Ingress, no HA/Supervisor API capability, no `/config` mount, and ID-only options.
5. Unknown or duplicate extension IDs fail before any child starts.
6. A crash-looping child reaches quarantine while a healthy peer keeps its original PID.
7. Manager shutdown removes a child and its grandchild process.
8. The public repository is explicitly development-only and has no release tag or production installation.

## Non-goals

- Gateway transcript transport and schema.
- Ambient speech retention or prompt injection.
- Third-party plugins or runtime installation.
- Custom Web UI or Ingress.
- HAOS installation, add-on deployment, release tag, or v0.1.0 support declaration.

## Constraints

- Do not touch production Home Assistant configuration or restart HA/add-ons.
- Do not read or copy secrets.
- Do not add `/config:rw` until a real extension requires shared files and its path guards are separately reviewed.

## Rollback

No production state changes are made. Stop at the last green commit; the new repository can remain as an untagged development artifact.
