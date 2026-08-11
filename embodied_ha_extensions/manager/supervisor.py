from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from .models import AppManifest
from .paths import owned_path


@dataclass(frozen=True)
class RestartPolicy:
    initial_seconds: float = 1.0
    maximum_seconds: float = 60.0
    quarantine_after: int = 5
    stable_after_seconds: float = 300.0
    shutdown_timeout_seconds: float = 10.0


@dataclass
class AppRuntime:
    manifest: AppManifest
    process: subprocess.Popen[str] | None = None
    pgid: int | None = None
    state: str = "waiting"
    starts: int = 0
    consecutive_failures: int = 0
    started_at: float | None = None
    restart_at: float = 0.0
    last_exit_code: int | None = None
    quarantined: bool = False


class ExtensionSupervisor:
    def __init__(
        self,
        manifests: list[AppManifest],
        data_root: Path,
        *,
        policy: RestartPolicy | None = None,
        clock: Callable[[], float] = time.monotonic,
        logger: Callable[[str], None] = print,
    ) -> None:
        self.policy = policy or RestartPolicy()
        self.clock = clock
        self.logger = logger
        self.data_root = data_root.resolve(strict=False)
        self.runtimes = {item.id: AppRuntime(manifest=item) for item in manifests}
        self.stopping = False

    def _log_output(self, app_id: str, stream) -> None:
        try:
            for line in stream:
                self.logger(f"[app:{app_id}] {line.rstrip()}")
        finally:
            stream.close()

    def _launch(self, runtime: AppRuntime, now: float) -> None:
        app_id = runtime.manifest.id
        app_data = owned_path(self.data_root, "apps", app_id)
        app_data.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["EHA_EXTENSION_ID"] = app_id
        env["EHA_EXTENSION_DATA_DIR"] = str(app_data)
        process = subprocess.Popen(
            list(runtime.manifest.command),
            cwd=runtime.manifest.app_dir,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        runtime.process = process
        runtime.pgid = process.pid
        runtime.state = "running"
        runtime.starts += 1
        runtime.started_at = now
        self.logger(f"[manager] started app={app_id} pid={process.pid}")
        if process.stdout is not None:
            threading.Thread(
                target=self._log_output,
                args=(app_id, process.stdout),
                daemon=True,
                name=f"extension-log-{app_id}",
            ).start()

    @staticmethod
    def _signal_group(pgid: int | None, sig: signal.Signals) -> None:
        if pgid is None:
            return
        with suppress(ProcessLookupError):
            os.killpg(pgid, sig)

    def _handle_exit(self, runtime: AppRuntime, now: float) -> None:
        assert runtime.process is not None
        code = runtime.process.poll()
        if code is None:
            return
        uptime = max(0.0, now - (runtime.started_at or now))
        self._signal_group(runtime.pgid, signal.SIGKILL)
        try:
            runtime.process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            runtime.process.kill()
            runtime.process.wait(timeout=1)
        runtime.process = None
        runtime.last_exit_code = code
        runtime.started_at = None

        if uptime >= self.policy.stable_after_seconds:
            runtime.consecutive_failures = 1
        else:
            runtime.consecutive_failures += 1
        if runtime.consecutive_failures >= self.policy.quarantine_after:
            runtime.quarantined = True
            runtime.state = "quarantined"
            self.logger(
                f"[manager] quarantined app={runtime.manifest.id} "
                f"exit={code} failures={runtime.consecutive_failures}"
            )
            return
        delay = min(
            self.policy.initial_seconds * (2 ** (runtime.consecutive_failures - 1)),
            self.policy.maximum_seconds,
        )
        runtime.restart_at = now + delay
        runtime.state = "backoff"
        self.logger(
            f"[manager] exited app={runtime.manifest.id} exit={code} restart_in={delay:.2f}s"
        )

    def tick(self) -> None:
        if self.stopping:
            return
        now = self.clock()
        for runtime in self.runtimes.values():
            if runtime.process is not None:
                self._handle_exit(runtime, now)
            if runtime.process is None and not runtime.quarantined and now >= runtime.restart_at:
                self._launch(runtime, now)

    def shutdown(self) -> None:
        self.stopping = True
        running = [runtime for runtime in self.runtimes.values() if runtime.process is not None]
        for runtime in running:
            runtime.state = "stopping"
            self._signal_group(runtime.pgid, signal.SIGTERM)

        deadline = self.clock() + self.policy.shutdown_timeout_seconds
        while running and self.clock() < deadline:
            running = [item for item in running if item.process and item.process.poll() is None]
            if running:
                time.sleep(0.02)

        for runtime in running:
            self.logger(f"[manager] kill timeout app={runtime.manifest.id}")
            self._signal_group(runtime.pgid, signal.SIGKILL)
        for runtime in self.runtimes.values():
            if runtime.process is not None:
                try:
                    runtime.process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    runtime.process.kill()
                    runtime.process.wait(timeout=1)
                runtime.last_exit_code = runtime.process.returncode
                runtime.process = None
            runtime.state = "stopped"

    def status(self) -> dict:
        return {
            "schema_version": 1,
            "stopping": self.stopping,
            "apps": {
                app_id: {
                    "state": runtime.state,
                    "pid": runtime.process.pid if runtime.process else None,
                    "starts": runtime.starts,
                    "consecutive_failures": runtime.consecutive_failures,
                    "last_exit_code": runtime.last_exit_code,
                    "quarantined": runtime.quarantined,
                }
                for app_id, runtime in sorted(self.runtimes.items())
            },
        }
