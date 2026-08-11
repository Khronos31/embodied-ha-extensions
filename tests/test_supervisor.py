from __future__ import annotations

import time
from pathlib import Path

from manager.models import AppManifest
from manager.supervisor import ExtensionSupervisor, RestartPolicy


def make_app(tmp_path: Path, app_id: str, source: str) -> AppManifest:
    app_dir = tmp_path / "apps" / app_id
    app_dir.mkdir(parents=True)
    executable = app_dir / "run.py"
    executable.write_text("#!/usr/bin/env python3\n" + source, encoding="utf-8")
    executable.chmod(0o755)
    return AppManifest(
        id=app_id,
        name=app_id,
        version="test",
        description="fixture",
        command=(str(executable),),
        app_dir=app_dir,
        default_enabled=False,
        required_capabilities=(),
        input_contracts=(),
        output_files=(),
        extra_context_profiles=(),
    )


def wait_until(predicate, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition did not become true")


def effectively_alive(pid: int) -> bool:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
    except (FileNotFoundError, ProcessLookupError):
        return False
    return len(fields) > 2 and fields[2] != "Z"


def test_crashing_app_is_quarantined_without_stopping_peer(tmp_path: Path):
    stable = make_app(
        tmp_path,
        "stable",
        "import time\nwhile True:\n    time.sleep(0.1)\n",
    )
    crashing = make_app(
        tmp_path,
        "crashing",
        "import os\nfrom pathlib import Path\n"
        "path = Path(os.environ['EHA_EXTENSION_DATA_DIR']) / 'starts'\n"
        "with path.open('a', encoding='utf-8') as handle:\n    handle.write('start\\n')\n"
        "raise SystemExit(3)\n",
    )
    policy = RestartPolicy(
        initial_seconds=0.01,
        maximum_seconds=0.02,
        quarantine_after=3,
        stable_after_seconds=10,
        shutdown_timeout_seconds=0.3,
    )
    supervisor = ExtensionSupervisor(
        [stable, crashing], tmp_path / "data", policy=policy
    )
    try:
        wait_until(
            lambda: (
                supervisor.tick() is None
                and supervisor.runtimes["crashing"].quarantined
            )
        )
        stable_runtime = supervisor.runtimes["stable"]
        assert stable_runtime.process is not None
        assert stable_runtime.process.poll() is None
        assert stable_runtime.starts == 1
        assert (tmp_path / "data" / "apps" / "crashing" / "starts").read_text().count(
            "start"
        ) == 3
    finally:
        supervisor.shutdown()


def test_shutdown_terminates_child_and_grandchild_process_group(tmp_path: Path):
    app = make_app(
        tmp_path,
        "tree",
        "import os, subprocess, sys, time\nfrom pathlib import Path\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "data = Path(os.environ['EHA_EXTENSION_DATA_DIR'])\n"
        "(data / 'pids').write_text(f'{os.getpid()} {child.pid}', encoding='utf-8')\n"
        "while True:\n    time.sleep(0.1)\n",
    )
    supervisor = ExtensionSupervisor(
        [app],
        tmp_path / "data",
        policy=RestartPolicy(shutdown_timeout_seconds=0.2),
    )
    supervisor.tick()
    pid_file = tmp_path / "data" / "apps" / "tree" / "pids"
    wait_until(pid_file.exists)
    parent_pid, child_pid = map(int, pid_file.read_text(encoding="utf-8").split())
    assert effectively_alive(parent_pid)
    assert effectively_alive(child_pid)

    supervisor.shutdown()
    wait_until(
        lambda: not effectively_alive(parent_pid) and not effectively_alive(child_pid)
    )
    assert supervisor.runtimes["tree"].state == "stopped"


def test_child_receives_only_owned_data_directory(tmp_path: Path):
    app = make_app(
        tmp_path,
        "environment",
        "import os\nfrom pathlib import Path\n"
        "data = Path(os.environ['EHA_EXTENSION_DATA_DIR'])\n"
        "(data / 'identity').write_text(os.environ['EHA_EXTENSION_ID'], encoding='utf-8')\n",
    )
    supervisor = ExtensionSupervisor(
        [app],
        tmp_path / "owned",
        policy=RestartPolicy(initial_seconds=10, quarantine_after=2),
    )
    try:
        supervisor.tick()
        identity = tmp_path / "owned" / "apps" / "environment" / "identity"
        wait_until(identity.exists)
        assert identity.read_text(encoding="utf-8") == "environment"
        assert str(identity.resolve()).startswith(str((tmp_path / "owned").resolve()))
    finally:
        supervisor.shutdown()
