"""Stop running app instances and remove a locked PyInstaller output folder on Windows."""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _stop_running_app() -> None:
    if sys.platform != "win32":
        return
    for image in ("Spindle.exe",):
        subprocess.run(
            ["taskkill", "/IM", image, "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def _remove_tree(path: Path, attempts: int = 5, delay_seconds: float = 2.0) -> bool:
    if not path.exists():
        return True
    for attempt in range(1, attempts + 1):
        try:
            shutil.rmtree(path)
            return True
        except PermissionError:
            if attempt == attempts:
                return False
            time.sleep(delay_seconds)
        except OSError:
            if attempt == attempts:
                return False
            time.sleep(delay_seconds)
    return not path.exists()


def main() -> int:
    root = _project_root()
    dist_dir = root / "dist" / "Spindle"

    print("Stopping any running Spindle.exe instances...")
    _stop_running_app()
    time.sleep(1.5)

    if not dist_dir.exists():
        print("No previous build folder to remove.")
        return 0

    print(f"Removing previous build: {dist_dir}")
    if _remove_tree(dist_dir):
        print("Previous build removed.")
        return 0

    print()
    print("ERROR: Could not delete the previous build folder.")
    print("Close Spindle.exe if it is still running,")
    print("close any File Explorer window open inside dist\\Spindle,")
    print("then run BUILD_WINDOWS_EXE.bat again.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
