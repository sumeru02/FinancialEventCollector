#!/usr/bin/env python3
"""
local.py
Cross-platform helper to start or stop the FinancialEventCollector
Python FastAPI app locally.

Usage (run from repo root or python/scripts/):
    python python/scripts/local.py          # start the server
    python python/scripts/local.py stop     # stop the server (kills process on port 8000)

Once running, browse to: http://localhost:8000/docs
Press Ctrl+C in the running terminal to stop.
"""
import os
import platform
import signal
import subprocess
import sys
from pathlib import Path

PORT = 8000
# This script lives at python/scripts/local.py
# parents[0] = python/scripts, parents[1] = python/
SCRIPT_DIR = Path(__file__).parent
PYTHON_DIR = SCRIPT_DIR.parent

# Resolve the venv Python executable for the current OS
if platform.system() == "Windows":
    VENV_PYTHON = PYTHON_DIR / ".venv" / "Scripts" / "python.exe"
else:
    VENV_PYTHON = PYTHON_DIR / ".venv" / "bin" / "python"


def find_pid_on_port(port: int) -> list[int]:
    """Return PIDs of *live* processes listening on the given port (cross-platform)."""
    pids: list[int] = []
    try:
        if platform.system() == "Windows":
            # Use PowerShell Get-NetTCPConnection which is more reliable than netstat
            result = subprocess.run(
                [
                    "PowerShell", "-NoProfile", "-Command",
                    f"Get-NetTCPConnection -LocalPort {port} -State Listen "
                    f"-ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess",
                ],
                capture_output=True, text=True
            )
            for line in result.stdout.strip().splitlines():
                try:
                    pid = int(line.strip())
                    if pid > 0:
                        pids.append(pid)
                except ValueError:
                    pass
        else:
            result = subprocess.run(
                ["lsof", "-ti", f"tcp:{port}"],
                capture_output=True, text=True
            )
            for pid_str in result.stdout.strip().splitlines():
                try:
                    pids.append(int(pid_str))
                except ValueError:
                    pass
    except FileNotFoundError:
        pass
    return list(set(pids))


def pid_exists(pid: int) -> bool:
    """Return True if a process with the given PID is currently running."""
    if platform.system() == "Windows":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True
        )
        return str(pid) in result.stdout
    else:
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False


def kill_venv_python_processes() -> None:
    """Kill any python processes running from this repo's venv (Windows only)."""
    venv_path = str(VENV_PYTHON).lower()
    result = subprocess.run(
        [
            "PowerShell", "-NoProfile", "-Command",
            "Get-Process python3.12,python -ErrorAction SilentlyContinue "
            "| Select-Object Id,@{N='Path';E={$_.Path}} | ConvertTo-Csv -NoTypeInformation",
        ],
        capture_output=True, text=True
    )
    for line in result.stdout.strip().splitlines()[1:]:  # skip header
        parts = line.strip('"').split('","')
        if len(parts) >= 2:
            try:
                pid = int(parts[0])
                path = parts[1].lower()
                if "financialeventcollector" in path or ".venv" in path:
                    subprocess.run(["taskkill", "/F", "/PID", str(pid), "/T"], check=False)
                    print(f"Killed venv python PID={pid}")
            except (ValueError, IndexError):
                pass


def stop_server() -> None:
    """Kill any process listening on PORT, plus any lingering venv python processes."""
    killed_any = False

    # First: kill by port (handles the common case)
    pids = find_pid_on_port(PORT)
    for pid in pids:
        if not pid_exists(pid):
            print(f"PID={pid} listed on port {PORT} but process no longer exists (stale socket).")
            continue
        try:
            if platform.system() == "Windows":
                subprocess.run(["taskkill", "/F", "/PID", str(pid), "/T"], check=False)
            else:
                os.kill(pid, signal.SIGKILL)
            print(f"Killed process PID={pid}")
            killed_any = True
        except (ProcessLookupError, PermissionError) as exc:
            print(f"Could not kill PID={pid}: {exc}")

    # Second: on Windows, also kill any python processes from this venv
    # (catches worker/reload child processes that don't own the socket)
    if platform.system() == "Windows":
        kill_venv_python_processes()
        killed_any = True

    if not killed_any and not pids:
        print(f"No process found listening on port {PORT}.")


def start_server() -> None:
    """Start the FastAPI app using the venv uvicorn."""
    if not VENV_PYTHON.exists():
        print(f"ERROR: Virtual environment not found at {VENV_PYTHON}")
        print("Create it first:")
        print(f"  cd python")
        if platform.system() == "Windows":
            print("  python -m venv .venv && .venv\\Scripts\\pip install -e .[dev]")
        else:
            print("  python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'")
        sys.exit(1)

    print("Starting FinancialEventCollector Python FastAPI app...")
    print(f"Browse to: http://localhost:{PORT}/docs")
    print("Press Ctrl+C to stop.\n")

    cmd = [
        str(VENV_PYTHON), "-m", "uvicorn",
        "app.main:app",
        "--reload",
        "--host", "0.0.0.0",
        "--port", str(PORT),
    ]
    try:
        subprocess.run(cmd, cwd=str(PYTHON_DIR))
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    action = sys.argv[1].lower() if len(sys.argv) > 1 else "start"
    if action == "stop":
        stop_server()
    else:
        start_server()
