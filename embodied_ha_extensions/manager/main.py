from __future__ import annotations

import logging
import os
import signal
import sys
import threading
from pathlib import Path

from .catalog import CatalogError, load_catalog, select_apps
from .config import ConfigError, load_options
from .paths import atomic_write_json, owned_path
from .supervisor import ExtensionSupervisor


def _path(name: str, default: str) -> Path:
    return Path(os.environ.get(name, default))


def run() -> int:
    options_path = _path("EHA_EXTENSIONS_OPTIONS_FILE", "/data/options.json")
    catalog_dir = _path("EHA_EXTENSIONS_CATALOG_DIR", "/app/catalog")
    apps_root = _path("EHA_EXTENSIONS_APPS_DIR", "/app/apps")
    data_root = _path("EHA_EXTENSIONS_DATA_ROOT", "/data/extensions")
    try:
        options = load_options(options_path)
        logging.basicConfig(
            level=getattr(logging, options.log_level.upper()),
            format="%(message)s",
        )
        catalog = load_catalog(catalog_dir, apps_root)
        selected = select_apps(catalog, options.enabled_extensions)
    except (ConfigError, CatalogError) as exc:
        print(f"[manager] configuration rejected: {exc}", file=sys.stderr, flush=True)
        return 2

    stop_event = threading.Event()

    def request_stop(_signum, _frame) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    supervisor = ExtensionSupervisor(selected, data_root, logger=lambda msg: print(msg, flush=True))
    status_path = owned_path(data_root, "status.json")
    print(
        f"[manager] catalog={len(catalog)} enabled={len(selected)} data={data_root}",
        flush=True,
    )
    try:
        while not stop_event.is_set():
            supervisor.tick()
            atomic_write_json(status_path, supervisor.status())
            stop_event.wait(0.5)
    finally:
        supervisor.shutdown()
        atomic_write_json(status_path, supervisor.status())
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
