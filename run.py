import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
FRONTEND_DIR = ROOT_DIR / "frontend"
ENV_FILE = ROOT_DIR / ".env"
BACKEND_VENV_PYTHON = BACKEND_DIR / ".venv" / "bin" / "python"

DEFAULT_ENV_VALUES = {
    "LLM_BASE_URL": "https://api.evx.llc/v1",
    "LLM_MODEL_NAME": "claude-opus-4-6",
    "UNIVERRA_LLM_RPM": "30",
    "UNIVERRA_SIM_SEMAPHORE": "1",
    "UNIVERRA_MAX_ACTIVE_AGENTS": "2",
    "FLASK_DEBUG": "False",
    "FLASK_HOST": "0.0.0.0",
    "FLASK_PORT": "5001",
    "MONGODB_URI": "mongodb://127.0.0.1:27017",
    "MONGODB_DB_NAME": "univerra",
    "MONGODB_TIMEOUT_MS": "5000",
    "AUTH_TOKEN_MAX_AGE_SECONDS": "604800",
    "RATE_LIMIT_AUTH_ATTEMPTS": "5",
    "RATE_LIMIT_AUTH_WINDOW_SECONDS": "900",
    "RATE_LIMIT_GRAPH_GENERATE_PER_HOUR": "20",
    "RATE_LIMIT_GRAPH_BUILD_PER_HOUR": "30",
    "RATE_LIMIT_SIMULATION_CREATE_PER_HOUR": "30",
    "RATE_LIMIT_SIMULATION_PREPARE_PER_HOUR": "10",
    "RATE_LIMIT_SIMULATION_START_PER_HOUR": "20",
    "RATE_LIMIT_REPORT_GENERATE_PER_HOUR": "20",
}


def find_uv_binary() -> str:
    candidates = [
        shutil.which("uv"),
        str(Path.home() / ".local" / "bin" / "uv"),
        "/usr/local/bin/uv",
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    raise RuntimeError("Required command `uv` was not found in PATH.")


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def ensure_env_file():
    existing_values = parse_env_file(ENV_FILE)
    if ENV_FILE.exists():
        existing_lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    else:
        existing_lines = []

    merged_values = dict(DEFAULT_ENV_VALUES)
    merged_values.update(existing_values)
    merged_values.setdefault("LLM_API_KEY", "")
    if "AUTH_SECRET_KEY" not in existing_values:
        merged_values["AUTH_SECRET_KEY"] = secrets.token_hex(32)

    missing_lines = []
    for key, value in merged_values.items():
        if key not in existing_values:
            missing_lines.append(f"{key}={value}")

    if not ENV_FILE.exists():
        ordered_keys = (
            "LLM_API_KEY",
            "LLM_BASE_URL",
            "LLM_MODEL_NAME",
            "UNIVERRA_LLM_RPM",
            "UNIVERRA_SIM_SEMAPHORE",
            "UNIVERRA_MAX_ACTIVE_AGENTS",
            "FLASK_DEBUG",
            "FLASK_HOST",
            "FLASK_PORT",
            "MONGODB_URI",
            "MONGODB_DB_NAME",
            "MONGODB_TIMEOUT_MS",
            "AUTH_SECRET_KEY",
            "AUTH_TOKEN_MAX_AGE_SECONDS",
            "RATE_LIMIT_AUTH_ATTEMPTS",
            "RATE_LIMIT_AUTH_WINDOW_SECONDS",
            "RATE_LIMIT_GRAPH_GENERATE_PER_HOUR",
            "RATE_LIMIT_GRAPH_BUILD_PER_HOUR",
            "RATE_LIMIT_SIMULATION_CREATE_PER_HOUR",
            "RATE_LIMIT_SIMULATION_PREPARE_PER_HOUR",
            "RATE_LIMIT_SIMULATION_START_PER_HOUR",
            "RATE_LIMIT_REPORT_GENERATE_PER_HOUR",
        )
        ENV_FILE.write_text(
            "\n".join(f"{key}={merged_values.get(key, '')}" for key in ordered_keys) + "\n",
            encoding="utf-8",
        )
    elif missing_lines:
        content = "\n".join(existing_lines)
        if content and not content.endswith("\n"):
            content += "\n"
        content += "\n".join(missing_lines) + "\n"
        ENV_FILE.write_text(content, encoding="utf-8")

    return parse_env_file(ENV_FILE)


def require_command(command: str):
    if shutil.which(command):
        return
    raise RuntimeError(f"Required command `{command}` was not found in PATH.")


def run_step(command: list[str], cwd: Path):
    print(f"[setup] Running: {' '.join(command)}")
    completed = subprocess.run(command, cwd=str(cwd), check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"Command failed ({completed.returncode}): {' '.join(command)}")


def ensure_uv():
    if shutil.which("uv") or os.path.exists(str(Path.home() / ".local" / "bin" / "uv")):
        return
    print("[setup] `uv` not found. Installing it with pip...")
    run_step([sys.executable, "-m", "pip", "install", "uv"], ROOT_DIR)


def wait_for_port(port: int, timeout_seconds: int = 90) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(1)
    return False


def stream_output(prefix: str, process: subprocess.Popen[str]):
    assert process.stdout is not None
    for line in process.stdout:
        print(f"[{prefix}] {line.rstrip()}")


def start_process(prefix: str, command: list[str], cwd: Path, env: dict[str, str]) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    threading.Thread(target=stream_output, args=(prefix, process), daemon=True).start()
    return process


def stop_processes(processes: list[subprocess.Popen[str]]):
    for process in processes:
        if process.poll() is None:
            process.terminate()

    for process in processes:
        if process.poll() is None:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


def main():
    env_values = ensure_env_file()

    require_command("node")
    require_command("npm")
    ensure_uv()
    uv_bin = find_uv_binary()

    run_step(["npm", "install"], ROOT_DIR)
    run_step(["npm", "install"], FRONTEND_DIR)
    run_step([uv_bin, "sync"], BACKEND_DIR)

    runtime_env = os.environ.copy()
    runtime_env.update(env_values)

    backend_command = [str(BACKEND_VENV_PYTHON), "run.py"] if BACKEND_VENV_PYTHON.exists() else [uv_bin, "run", "python", "run.py"]
    backend_process = start_process("backend", backend_command, BACKEND_DIR, runtime_env)
    frontend_process = start_process("frontend", ["npm", "run", "dev"], FRONTEND_DIR, runtime_env)
    processes = [backend_process, frontend_process]

    def handle_shutdown(signum, frame):
        print("\n[run] Stopping services...")
        stop_processes(processes)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    backend_ready = wait_for_port(int(env_values.get("FLASK_PORT", "5001")))
    frontend_ready = wait_for_port(3000)

    if backend_process.poll() is not None:
        stop_processes(processes)
        raise RuntimeError("Backend exited before startup completed.")

    if frontend_process.poll() is not None:
        stop_processes(processes)
        raise RuntimeError("Frontend exited before startup completed.")

    if backend_ready and frontend_ready:
        print("\n[run] Backend URL:  http://localhost:5001")
        print("[run] Frontend URL: http://localhost:3000")
    else:
        print("\n[run] Services started, but a port health check timed out.")
        print("[run] Expected frontend URL: http://localhost:3000")

    while True:
        for process in processes:
            if process.poll() is not None:
                stop_processes(processes)
                raise RuntimeError("A service stopped unexpectedly. See logs above.")
        time.sleep(1)


if __name__ == "__main__":
    main()
