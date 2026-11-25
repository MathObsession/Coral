import base64
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path


RUNTIME = Path(__file__).resolve().parents[2] / "codespace/runtime.py"


def launch(tmp_path, command, seconds=10):
    task_id = str(uuid.uuid4())
    directory = tmp_path / ".local/state/coral" / task_id
    directory.mkdir(parents=True)
    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    request = {"id": task_id, "kind": "terminal", "prompt": command, "deadline": time.time() + seconds}
    encoded = base64.b64encode(json.dumps(request).encode()).decode()
    environment = {"HOME": str(tmp_path), "PATH": os.environ["PATH"], "CORAL_WORKSPACE": str(workspace)}
    child = subprocess.Popen([sys.executable, str(RUNTIME), "worker", task_id, encoded], env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    return child, directory


def finish(child, directory):
    out, err = child.communicate(timeout=8)
    assert child.returncode == 0, err.decode()
    result = json.loads((directory / "result").read_text())
    output = (directory / "output").read_text()
    return result, output


def test_remote_worker_streams_and_persists_real_output(tmp_path):
    child, directory = launch(tmp_path, "printf 'Working\\n'; sleep 0.5; printf 'Coral done'")
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if (directory / "output").exists() and "Working" in (directory / "output").read_text():
                break
            time.sleep(0.01)
        assert "Working" in (directory / "output").read_text()
        assert not (directory / "result").exists()
        result, output = finish(child, directory)
        assert result["status"] == "succeeded"
        assert output == "Working\nCoral done"
    finally:
        if child.poll() is None: child.kill(); child.wait()


def test_remote_worker_enforces_deadline(tmp_path):
    child, directory = launch(tmp_path, "sleep 30", seconds=0.3)
    started = time.monotonic()
    result, output = finish(child, directory)
    assert time.monotonic() - started < 4
    assert result["status"] == "failed"
    assert "daily allowance" in result["error"]


def test_remote_worker_cancels_process_group(tmp_path):
    child, directory = launch(tmp_path, "printf ready; sleep 30")
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if (directory / "output").exists() and (directory / "output").read_text() == "ready": break
        time.sleep(0.01)
    os.killpg(child.pid, signal.SIGTERM)
    result, output = finish(child, directory)
    assert result["status"] == "cancelled"
    assert output == "ready"


def test_remote_output_is_capped_before_disk_exhaustion(tmp_path):
    command = "python3 -c 'print(\"x\" * 600000)'"
    child, directory = launch(tmp_path, command)
    result, output = finish(child, directory)
    assert result["status"] == "failed"
    assert "512 KB" in result["error"]
    assert (directory / "output").stat().st_size <= 512_000
