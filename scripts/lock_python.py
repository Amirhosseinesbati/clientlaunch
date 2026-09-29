"""Resolve a universal uv.lock and an exact pip-installable export."""

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
runtime = ROOT / ".runtime"
runtime.mkdir(exist_ok=True)
environment = os.environ.copy()
environment.update({
    "UV_CACHE_DIR": str(runtime / "uv-cache"),
    "UV_PYTHON_INSTALL_DIR": str(runtime / "uv-python"),
    "UV_STATE_DIR": str(runtime / "uv-state"),
    "UV_MANAGED_PYTHON": "false",
})
python = ROOT / ".venv" / "Scripts" / "python.exe"
if not python.exists():
    raise SystemExit("Create .venv with Python 3.12 first")
subprocess.run(["uv", "lock", "--python", str(python)], cwd=ROOT, env=environment, check=True)
subprocess.run(["uv", "export", "--format", "requirements-txt", "--no-dev", "--output-file", "requirements.lock"],
               cwd=ROOT, env=environment, check=True)
