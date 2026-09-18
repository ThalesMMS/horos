"""Launch the isolated development bundle against a private database, headless.

`script/build_and_run.sh` builds, signs and opens the bundle through
LaunchServices, which sends the app's stderr nowhere. Scenario scripts that
must read what the app logged, choose a fresh database per case, or add
preferences to the argument domain run the bundle's executable directly with
the same isolation arguments instead. Nothing here touches the user's real
database, preferences domain or Trash.
"""
from __future__ import annotations

import os
import signal
import sqlite3
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT_APP = ROOT / "build/Development/HorosDevelopment.app"


def isolation_arguments(test_root: Path) -> list[str]:
    """The arguments build_and_run.sh passes, so a direct launch is equally isolated."""
    root = str(test_root)
    return ["-hideListenerError", "NO", "-DATABASELOCATION", "1", "-DATABASELOCATIONURL", root,
            "-DEFAULT_DATABASELOCATION", "1", "-DEFAULT_DATABASELOCATIONURL", root,
            "-WebPortalDatabasePath", f"{root}/WebUsers.sql", "-AUTOCLEANINGSPACE", "NO",
            "-AUTOCLEANINGDATE", "NO", "-AUTOROUTINGACTIVATED", "NO", "-STORESCP", "NO", "-USESTORESCP", "NO",
            "-checkForUpdatesPlugins", "NO", "-SUEnableAutomaticChecks", "NO"]


def user_temporary_directory() -> str:
    return subprocess.run(["/usr/bin/getconf", "DARWIN_USER_TEMP_DIR"], capture_output=True,
                          text=True, check=True).stdout.strip()


def running_development_pids(app: Path = DEVELOPMENT_APP) -> list[int]:
    executable = str(app / "Contents/MacOS/Horos")
    suffix = "/".join(executable.split("/")[-4:])
    pids = []
    for line in subprocess.run(["/bin/ps", "-axo", "pid=,command="], capture_output=True, text=True).stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and (parts[1].startswith(executable) or suffix in parts[1].split(" -")[0]):
            pids.append(int(parts[0]))
    return pids


def stop_pid(pid: int, timeout: float = 20.0) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.2)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def stop_all(app: Path = DEVELOPMENT_APP) -> None:
    for pid in running_development_pids(app):
        stop_pid(pid)


def launch(test_root: Path, log: Path, extra_arguments: list[str] = (), app: Path = DEVELOPMENT_APP,
           environment: dict[str, str] | None = None) -> subprocess.Popen:
    test_root.mkdir(parents=True, exist_ok=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, TMPDIR=user_temporary_directory())
    env.update(environment or {})
    handle = open(log, "wb")
    return subprocess.Popen([str(app / "Contents/MacOS/Horos")] + isolation_arguments(test_root) + list(extra_arguments),
                            stdout=handle, stderr=subprocess.STDOUT, env=env, start_new_session=True)


def stop(process: subprocess.Popen, timeout: float = 20.0) -> int | None:
    if process.poll() is None:
        stop_pid(process.pid, timeout)
    try:
        return process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        return None


def wait_for(predicate, timeout: float, interval: float = 0.25, description: str = "condition"):
    """Poll a predicate with a hard deadline; return its last truthy value or raise."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    raise TimeoutError(f"timed out after {timeout:.0f} s waiting for {description}")


def database_folder(test_root: Path) -> Path:
    return test_root / "Horos Data"


def image_count(test_root: Path) -> int | None:
    sql = database_folder(test_root) / "Database.sql"
    if not sql.is_file():
        return None
    try:
        with sqlite3.connect(f"file:{sql}?mode=ro", uri=True, timeout=1) as connection:
            return connection.execute("SELECT COUNT(*) FROM ZIMAGE").fetchone()[0]
    except sqlite3.Error:
        return None
