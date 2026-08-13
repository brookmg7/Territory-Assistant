#!/usr/bin/env python3
"""
GoogleSheets_Menu.py

Purpose
-------
Google Sheets submenu entrypoint (portable), extracted from Clean_GoogleSheets.py.

This module contains ONLY:
  - Menu rendering + input loop
  - Option wrappers:
      _run_option1_clean_only   (Full geocode check, no split)   [was old option 2]
      _run_option2_routed       (Full geocode check, split)      [was old option 4]
      _run_option3_routed       (Master DB duplicate audit)      [was old option 5]

Design rules (per your split plan)
----------------------------------
- This module imports GoogleSheets_Flows ONLY.
- Cancel handling (q-to-cancel) is provided by CoreLite, but accessed via:
      flows.core
  so we still only import Flows.

Portability
-----------
- Works when run from anywhere (double-click, cmd, PowerShell, scheduled task, etc.)
- Works when frozen (PyInstaller):
    - uses the EXE folder as APP_ROOT
    - adds APP_ROOT to sys.path
    - sets cwd to APP_ROOT

Notes
-----
- GoogleSheets_Flows must expose:
    - core (GoogleSheets_CoreLite) as flows.core
    - the flow functions used below:
        run_sheets_clean_and_split_after_purge_verify
        run_sheets_clean_and_split_new_streets_verify
    - helpers used below (either defined in Flows or re-exported by Flows from Utils/Master/Verify):
        _merge_csvs
        _summarize_final_status
        verify_split_matches_clean
        run_final_master_duplicate_filter
        run_verify_fail_against_master
        run_master_db_duplicate_audit
        enforce_outputs_routing  (optional but recommended)
"""

from __future__ import annotations

import os
import sys
import threading
import time
import faulthandler
from pathlib import Path
from contextlib import contextmanager

class _StageProgress:
    """
    Indeterminate CLI progress bar (no %), safe for long blocking work.

    Key behavior:
    - Renders on ONE line using carriage-return updates.
    - Clears the animated line on demand (before external prints).
    - Clears the animated line before printing the final ✅/🛑/❌ line.
    """

    def __init__(self, label: str, tick_s: float = 0.25, width: int = 16):
        self.label = str(label)
        self.tick_s = float(tick_s)
        self.width = max(8, int(width))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._start: float = 0.0
        self._last_render_len: int = 0

    def start(self) -> None:
        self._start = time.time()
        self._thread = threading.Thread(target=self._run, daemon=True, name=f"Progress_{self.label}")
        self._thread.start()

    def clear_line(self) -> None:
        """
        Public: clears whatever the progress thread last rendered.
        Safe to call even if the thread is not running yet.
        """
        sys.stdout.write("\r" + (" " * max(self._last_render_len, 120)) + "\r")
        sys.stdout.flush()

    def stop(self, status: str = "done") -> None:
        """
        Stop the animation and print a final line.

        status:
          - "done" -> ✅
          - "cancelled" -> 🛑
          - anything else -> ❌
        """
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=0.8)

        elapsed = int(time.time() - self._start)
        prefix = "✅" if status == "done" else ("🛑" if status == "cancelled" else "❌")

        self.clear_line()
        sys.stdout.write(f"{prefix} {self.label} ({elapsed}s)\n")
        sys.stdout.flush()

    def _run(self) -> None:
        i = 0
        while not self._stop.wait(self.tick_s):
            elapsed = int(time.time() - self._start)

            pos = i % self.width
            bar = ["·"] * self.width
            bar[pos] = "█"

            line = f"⏳ {self.label} [{''.join(bar)}] {elapsed}s"
            self._last_render_len = len(line) + 5  # padding
            sys.stdout.write("\r" + line)
            sys.stdout.flush()
            i += 1


@contextmanager
def progress_stage(label: str, cancel_flag=None):
    """
    Context manager for indeterminate progress indication.

    Fixes:
    - Clears the progress line BEFORE yielding so subsequent prints (stage/print/log)
      start on a clean line.
    - Clears again on exit and prints a final ✅/🛑/❌ line.

    cancel_flag (optional):
    - If provided and looks like a threading.Event (has is_set()), we will mark the
      stage as 🛑 cancelled when exiting and the flag is set.
    """
    prog = _StageProgress(label)
    prog.start()
    try:
        # Important: clear the animated line before letting anything else print
        prog.clear_line()
        yield
    except Exception:
        prog.stop(status="error")
        raise
    else:
        cancelled = False
        try:
            if cancel_flag is not None and hasattr(cancel_flag, "is_set"):
                cancelled = bool(cancel_flag.is_set())
        except Exception:
            cancelled = False

        prog.stop(status="cancelled" if cancelled else "done")

def _start_heartbeat(label: str, every_s: int = 30):
    stop = threading.Event()

    def _hb():
        while not stop.is_set():
            print(f"⏱️  {label}: still running...", flush=True)
            stop.wait(every_s)

    t = threading.Thread(target=_hb, daemon=True, name=f"HB_{label}")
    t.start()
    return stop

def _dump_stacks_after(seconds: int = 120, label: str = "phase"):
    """
    Start a timer that will dump Python stack traces for all threads after N seconds.

    Returns:
        cancel(): call this to prevent the dump (e.g., when the phase completes).

    Why:
    - When a run "hangs", the traceback tells you exactly where it is blocked.
    - The returned cancel() prevents false dumps after successful completion.
    """
    stop = threading.Event()

    def _later():
        if not stop.wait(seconds):
            print(f"\n\n=== STACK DUMP (no progress timeout) [{label}] ===", flush=True)
            try:
                faulthandler.dump_traceback(all_threads=True)
            except Exception as e:
                print(f"(stack dump failed: {e})", flush=True)
            print(f"=== END STACK DUMP [{label}] ===\n", flush=True)

    threading.Thread(
        target=_later,
        daemon=True,
        name=f"GS_StackDumpTimer_{label}",
    ).start()

    def cancel():
        stop.set()

    return cancel
# =============================================================================
# REQUIRED PYTHON PACKAGES (EDIT THIS LIST ONLY)
# Format: (pip_name, import_name)
# =============================================================================

REQUIRED_PACKAGES = [
    ("pandas", "pandas"),
    ("numpy", "numpy"),
    ("requests", "requests"),
    ("geopy", "geopy"),
    ("shapely", "shapely"),
    ("pyproj", "pyproj"),
    ("fiona", "fiona"),
    ("colorama", "colorama"),
    ("python-dateutil", "dateutil"),  # IMPORTANT: import is dateutil
    ("tqdm", "tqdm"),                 # progress bars used by GoogleSheets_Flows.py
]
# =============================================================================
# Portable bootstrap (run anywhere)
# =============================================================================

def _app_root() -> Path:
    """
    If frozen (PyInstaller), use the EXE's folder; else use this file's folder.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_ROOT = _app_root()

# =============================================================================
# Support log bootstrap
# =============================================================================

def _support_log_path() -> Path:
    """
    Support log used by Run_GoogleSheets.bat and early Python startup.

    This is separate from GoogleSheets_All.txt because some startup problems can
    happen before GoogleSheets_Log is initialized.
    """
    raw = os.environ.get("GS_SUPPORT_LOG", "").strip().strip('"')
    if raw:
        return Path(raw)
    return APP_ROOT / "Log" / "Run_GoogleSheets_support_log.txt"


def _support_log(message: str) -> None:
    """
    Best-effort early support logger.
    Never raises.
    """
    try:
        p = _support_log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with p.open("a", encoding="utf-8", errors="replace") as f:
            f.write(f"{ts} | {message}\n")
    except Exception:
        pass


def _support_section(title: str) -> None:
    _support_log("")
    _support_log("=" * 78)
    _support_log(str(title))
    _support_log("=" * 78)


def _support_run_capture(label: str, cmd: list[str], *, timeout: int = 30, max_lines: int = 300) -> None:
    """
    Run a small diagnostic command and write output to support log.

    Used only for diagnostics, not for the main app workflow.
    """
    try:
        _support_log(f"RUN_DIAGNOSTIC_START: {label} | cmd={cmd!r}")
        completed = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        _support_log(f"RUN_DIAGNOSTIC_DONE: {label} | returncode={completed.returncode}")

        out = completed.stdout or ""
        lines = out.splitlines()
        for line in lines[:max_lines]:
            _support_log(f"{label}: {line}")

        if len(lines) > max_lines:
            _support_log(f"{label}: ... truncated {len(lines) - max_lines} extra lines")

    except Exception as e:
        _support_log(f"RUN_DIAGNOSTIC_FAILED: {label} | error={e!r}")


def _write_python_support_snapshot() -> None:
    """
    Write one early Python startup snapshot.

    This runs before GoogleSheets_Log initializes, so support still has useful
    details if dependency setup or imports fail.
    """
    if os.environ.get("GS_PY_SUPPORT_SNAPSHOT_DONE") == "1":
        return

    os.environ["GS_PY_SUPPORT_SNAPSHOT_DONE"] = "1"

    try:
        import platform
        import struct
        import getpass

        _support_section("Python startup snapshot")

        _support_log(f"APP_ROOT={APP_ROOT}")
        _support_log(f"cwd={os.getcwd()}")
        _support_log(f"script_file={Path(__file__).resolve()}")
        _support_log(f"sys.executable={sys.executable}")
        _support_log(f"sys.version={sys.version.replace(chr(10), ' ')}")
        _support_log(f"platform={platform.platform()}")
        _support_log(f"machine={platform.machine()}")
        _support_log(f"python_bits={struct.calcsize('P') * 8}")
        _support_log(f"user={getpass.getuser()}")
        _support_log(f"GS_RUN_FROM_BAT={os.environ.get('GS_RUN_FROM_BAT', '')}")
        _support_log(f"GS_LOG_LEVEL={os.environ.get('GS_LOG_LEVEL', '')}")
        _support_log(f"GS_AUTOWRAP_FLOWS={os.environ.get('GS_AUTOWRAP_FLOWS', '')}")
        _support_log(f"GS_SUPPORT_LOG={os.environ.get('GS_SUPPORT_LOG', '')}")

        _support_section("sys.path")
        for p in sys.path:
            _support_log(str(p))

        _support_section("Required local files")
        required_local_files = [
            "GoogleSheets_Menu.py",
            "GoogleSheets_Flows.py",
            "GoogleSheets_Utils.py",
            "GoogleSheets_Master.py",
            "GoogleSheets_Verify.py",
            "GoogleSheets_CoreLite.py",
            "GoogleSheets_Log.py",
            "GoogleSheets_CoreLite_Geocode.py",
            "GoogleSheets_CoreLite_Polygons.py",
        ]

        for rel in required_local_files:
            p = APP_ROOT / rel
            _support_log(f"{'FOUND' if p.is_file() else 'MISSING'} file: {rel} | {p}")

        _support_section("Runtime folders / files")
        runtime_items = [
            "input_googlesheets.csv",
            "KML Boundaries",
            "Master",
            "Street Database",
            "New_Addresses_By_Suburb",
            "Log",
        ]

        for rel in runtime_items:
            p = APP_ROOT / rel
            _support_log(f"{'FOUND' if p.exists() else 'MISSING'} item: {rel} | {p}")

        _support_section("Required package import check")
        try:
            for pip_name, import_name in REQUIRED_PACKAGES:
                try:
                    spec = importlib.util.find_spec(import_name)
                    _support_log(f"{'OK' if spec is not None else 'MISSING'} package: {pip_name} import={import_name}")
                except Exception as e:
                    _support_log(f"ERROR package check: {pip_name} import={import_name} error={e!r}")
        except Exception as e:
            _support_log(f"Package list check failed: {e!r}")

        _support_section("Python / pip diagnostics")
        _support_run_capture("python_version", [sys.executable, "--version"], timeout=15)
        _support_run_capture("pip_version", [sys.executable, "-m", "pip", "--version"], timeout=20)
        _support_run_capture("pip_freeze", [sys.executable, "-m", "pip", "list", "--format=freeze"], timeout=60, max_lines=500)

    except Exception as e:
        _support_log(f"PYTHON_SUPPORT_SNAPSHOT_FAILED: {e!r}")

# =============================================================================
# Dependency bootstrap (auto install missing packages)
# =============================================================================

import importlib
import importlib.util
import subprocess

def _check_runtime_requirements(print_report: bool = True) -> dict:
    """
    Check everything this Google Sheets menu needs before running.

    Purpose:
    - Useful when Run_GoogleSheets.bat is opened on another computer.
    - Shows ✅ installed / ❌ missing / ⚠️ optional warning.
    - Does NOT import GoogleSheets_Flows or run the cleaning logic.
    - Safe to call before the main menu opens.

    Returns:
        dict with:
          ok: bool
          missing_pip: list[str]
          missing_required_files: list[str]
          warnings: list[str]
    """
    result = {
        "ok": True,
        "missing_pip": [],
        "missing_required_files": [],
        "warnings": [],
    }

    rows: list[tuple[str, str, str, str]] = []

    def _add(section: str, name: str, ok: bool, required: bool = True, detail: str = "") -> None:
        if ok:
            status = "✅"
        else:
            status = "❌" if required else "⚠️"

        rows.append((status, section, name, detail))

        if required and not ok:
            result["ok"] = False
        elif (not required) and (not ok):
            result["warnings"].append(name)

    # -------------------------------------------------------------------------
    # Python runtime
    # -------------------------------------------------------------------------
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    _add(
        "Python",
        "Python 3.10+",
        sys.version_info >= (3, 10),
        required=True,
        detail=f"found {py_version}",
    )

    _add(
        "Python",
        "Python executable",
        bool(sys.executable),
        required=True,
        detail=str(sys.executable or "not found"),
    )

    # pip check
    pip_ok = False
    pip_detail = ""
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
        )
        pip_ok = completed.returncode == 0
        pip_detail = (completed.stdout or completed.stderr or "").strip()
    except Exception as e:
        pip_detail = str(e)

    _add("Python", "pip", pip_ok, required=True, detail=pip_detail)

    # -------------------------------------------------------------------------
    # App root / write access
    # -------------------------------------------------------------------------
    _add(
        "App",
        "APP_ROOT folder",
        APP_ROOT.exists() and APP_ROOT.is_dir(),
        required=True,
        detail=str(APP_ROOT),
    )

    write_ok = False
    write_detail = ""
    try:
        test_file = APP_ROOT / ".gs_write_test.tmp"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        write_ok = True
        write_detail = "can write/delete test file"
    except Exception as e:
        write_detail = str(e)

    _add("App", "Folder write permission", write_ok, required=True, detail=write_detail)

    # -------------------------------------------------------------------------
    # Required Python packages
    # -------------------------------------------------------------------------
    for pip_name, import_name in REQUIRED_PACKAGES:
        installed = False
        detail = ""

        try:
            spec = importlib.util.find_spec(import_name)
            installed = spec is not None
            detail = f"import {import_name}"
        except Exception:
            # Fallback: if find_spec fails for any reason, try a real import.
            try:
                importlib.import_module(import_name)
                installed = True
                detail = f"import {import_name}"
            except Exception as e:
                installed = False
                detail = str(e)

        _add("Package", pip_name, installed, required=True, detail=detail)

        if not installed:
            result["missing_pip"].append(pip_name)

    # -------------------------------------------------------------------------
    # Required local files/modules
    # These are checked as files, not imported, so this is safe.
    # -------------------------------------------------------------------------
    required_local_files = [
        "GoogleSheets_Menu.py",
        "GoogleSheets_Flows.py",
        "GoogleSheets_Utils.py",
        "GoogleSheets_Master.py",
        "GoogleSheets_Verify.py",
        "GoogleSheets_CoreLite.py",
        "GoogleSheets_Log.py",

        # Include these if they exist in your split project.
        # They may be used by CoreLite / geocode / polygon workflows.
        "GoogleSheets_CoreLite_Geocode.py",
        "GoogleSheets_CoreLite_Polygons.py",
    ]

    for rel in required_local_files:
        p = APP_ROOT / rel
        exists = p.exists() and p.is_file()
        _add("Local file", rel, exists, required=True, detail=str(p))
        if not exists:
            result["missing_required_files"].append(rel)

    # -------------------------------------------------------------------------
    # Runtime input/output assets
    # These may be missing on first setup, so show warnings instead of hard fail.
    # -------------------------------------------------------------------------
    try:
        (APP_ROOT / "New_Addresses_By_Suburb").mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    optional_runtime_items = [
        ("input_googlesheets.csv", "needed before running option 1 or 2"),
        ("KML Boundaries", "needed for suburb boundary split/routing"),
        ("Master", "folder containing the master CSV/database"),
        ("Street Database", "folder containing linz_auckland.sqlite if using LINZ geocode"),
        ("New_Addresses_By_Suburb", "output folder; can usually be created later"),
    ]

    for rel, note in optional_runtime_items:
        p = APP_ROOT / rel
        exists = p.exists()
        _add("Runtime item", rel, exists, required=False, detail=f"{note} | {p}")

    # -------------------------------------------------------------------------
    # Print report
    # -------------------------------------------------------------------------
    if print_report:
        print("")
        print("=" * 78)
        print("Google Sheets Requirements Check")
        print("=" * 78)

        for status, section, name, detail in rows:
            print(f"{status} [{section}] {name}")
            if detail:
                print(f"    {detail}")

        print("-" * 78)

        if result["ok"]:
            print("✅ Required setup looks OK.")
        else:
            print("❌ Required setup is missing something.")

        if result["missing_pip"]:
            print("")
            print("Missing packages:")
            print("    " + " ".join(result["missing_pip"]))
            print("")
            print("Manual install command:")
            print(f"    {sys.executable} -m pip install --prefer-binary {' '.join(result['missing_pip'])}")

        if result["missing_required_files"]:
            print("")
            print("Missing required local files:")
            for item in result["missing_required_files"]:
                print(f"    - {item}")

        if result["warnings"]:
            print("")
            print("Warnings:")
            for item in result["warnings"]:
                print(f"    - {item}")

        print("=" * 78)
        print("")

    return result

def _restart_application_after_dependency_install() -> None:
    """
    Ask the BAT launcher to restart the app in the SAME window.

    Why:
    - Keeps all setup output in one visible window.
    - Avoids spawning a second Python process with subprocess.Popen().
    - Lets Run_GoogleSheets.bat log the restart clearly.
    - Exit code 75 is handled by the newer BAT file.
    """
    print("\n✅ Packages installed.", flush=True)
    print("Restarting application in the same window...\n", flush=True)
    raise SystemExit(75)

def _install_or_repair_python_with_winget() -> None:
    """
    Install/repair Python using winget.

    IMPORTANT:
    - This can only run if this menu is already running under Python.
    - It cannot help a computer with zero Python, because GoogleSheets_Menu.py
      would not start in the first place.
    - For zero-Python computers, the BAT launcher is still the correct place
      to bootstrap Python.
    """
    import shutil

    print("")
    print("=" * 78)
    print("Python Install / Repair Helper")
    print("=" * 78)
    print(f"Current Python: {sys.version.split()[0]}")
    print(f"Current executable: {sys.executable}")
    print("")

    winget_path = shutil.which("winget")
    if not winget_path:
        print("❌ winget was not found on this computer.")
        print("Install 'App Installer' / Windows Package Manager first, then try again.")
        print("=" * 78)
        print("")
        return

    print(f"✅ winget found: {winget_path}")
    print("")
    print("This will run:")
    print("    winget install -e --id Python.Python.3.13")
    print("")
    print("Use this only if Python needs installing, repairing, or upgrading.")
    confirm = input("Proceed with Python install/repair? (y to continue): ").strip().lower()

    if confirm != "y":
        print("❌ Cancelled.\n")
        return

    cmd = [
        "winget",
        "install",
        "-e",
        "--id",
        "Python.Python.3.13",
        "--accept-package-agreements",
        "--accept-source-agreements",
    ]

    try:
        print("\n📦 Installing/repairing Python 3.13 via winget...\n", flush=True)
        subprocess.check_call(cmd)
    except Exception as e:
        print("\n❌ Python install/repair failed.", flush=True)
        print(f"Error: {e}", flush=True)
        print("")
        print("Manual command to try:")
        print("    winget install -e --id Python.Python.3.13")
        print("")
        return

    print("")
    print("✅ Python install/repair command completed.")
    print("Close this window, then reopen Run_GoogleSheets.bat.")
    print("=" * 78)
    print("")

def _ensure_dependencies_installed() -> None:
    """
    Automatic startup requirements check.

    Behavior:
    - Runs automatically before the menu opens.
    - Prints the full requirements checklist.
    - Logs setup details to the support log.
    - Stops if Python version is too old.
    - If Python is too old, asks Y/N to install/repair Python with winget.
    - Stops if required local project files are missing.
    - If pip packages are missing, asks user Y/N before installing.
    - Installs only missing pip packages.
    - Restarts safely after package installation.
    """
    if os.environ.get("GS_DEPS_CHECK_DONE") == "1":
        _support_log("Dependency check skipped: GS_DEPS_CHECK_DONE=1")
        return

    _support_section("Dependency check")

    report = _check_runtime_requirements(print_report=True)

    missing_pip = list(report.get("missing_pip") or [])
    missing_required_files = list(report.get("missing_required_files") or [])
    warnings = list(report.get("warnings") or [])

    _support_log(f"Dependency report ok={report.get('ok')}")
    _support_log(f"missing_pip={missing_pip}")
    _support_log(f"missing_required_files={missing_required_files}")
    _support_log(f"warnings={warnings}")

    # ---------------------------------------------------------------------
    # Python version gate
    # ---------------------------------------------------------------------
    if sys.version_info < (3, 10):
        _support_log(f"Python too old: {sys.version.split()[0]} | executable={sys.executable}")

        print("\n❌ Python 3.10+ is required.", flush=True)
        print(f"Current Python: {sys.version.split()[0]}", flush=True)
        print(f"Current executable: {sys.executable}", flush=True)
        print("\nInstall/repair Python 3.13 with winget now?", flush=True)

        confirm = input("Type Y to install/repair Python, or anything else to exit: ").strip().lower()

        _support_log(f"Python install/repair confirmation={confirm!r}")

        if confirm == "y":
            _install_or_repair_python_with_winget()
            print("\nClose this window, then reopen Run_GoogleSheets.bat.", flush=True)
            _support_log("Python install/repair helper finished; user must reopen BAT.")
        else:
            print("\n❌ Setup cancelled. Python was not updated.", flush=True)
            _support_log("Setup cancelled because Python is too old and user declined install.")

        print("\nPress Enter to exit...", flush=True)
        try:
            input()
        except Exception:
            pass
        raise SystemExit(1)

    # ---------------------------------------------------------------------
    # Required local files gate
    # ---------------------------------------------------------------------
    if missing_required_files:
        _support_log(f"Stopping because required local files are missing: {missing_required_files}")

        print("\n❌ Required local project files are missing.", flush=True)
        print("These cannot be installed automatically:", flush=True)
        for item in missing_required_files:
            print(f"    - {item}", flush=True)

        print("\nCopy the missing file(s) into the same folder as GoogleSheets_Menu.py.", flush=True)
        print("\nPress Enter to exit...", flush=True)
        try:
            input()
        except Exception:
            pass
        raise SystemExit(1)

    # ---------------------------------------------------------------------
    # Optional runtime warnings
    # ---------------------------------------------------------------------
    if warnings:
        _support_log(f"Optional runtime warnings present: {warnings}")

    # ---------------------------------------------------------------------
    # Pip package gate
    # ---------------------------------------------------------------------
    if not missing_pip:
        _support_log("No missing pip packages. Dependency check passed.")
        os.environ["GS_DEPS_CHECK_DONE"] = "1"
        return

    _support_log(f"Missing required Python packages: {missing_pip}")

    print("\n❌ Missing required Python packages:", flush=True)
    for pkg in missing_pip:
        print(f"    - {pkg}", flush=True)

    print("\nInstall missing packages now? This requires internet.", flush=True)
    confirm = input("Type Y to install, or anything else to exit: ").strip().lower()

    _support_log(f"Missing package install confirmation={confirm!r}")

    if confirm != "y":
        print("\n❌ Setup cancelled. Missing packages were not installed.", flush=True)
        print("The app cannot continue until the missing packages are installed.", flush=True)
        print("\nManual install command:", flush=True)
        print(f"    {sys.executable} -m pip install --prefer-binary {' '.join(missing_pip)}", flush=True)
        print("\nPress Enter to exit...", flush=True)

        _support_log("Setup cancelled because user declined missing package install.")
        _support_log(f"Manual install command: {sys.executable} -m pip install --prefer-binary {' '.join(missing_pip)}")

        try:
            input()
        except Exception:
            pass
        raise SystemExit(1)

    print("\n📦 Installing required Python packages...", flush=True)
    print("Missing:", ", ".join(missing_pip), flush=True)
    print("This may take a minute.\n", flush=True)

    def run(cmd: list[str], label: str) -> None:
        """
        Run a setup command while printing output and writing it to support log.
        """
        _support_log(f"SETUP_COMMAND_START: {label} | cmd={cmd!r}")

        try:
            p = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            if p.stdout is not None:
                for line in p.stdout:
                    print(line, end="", flush=True)
                    _support_log(f"{label}: {line.rstrip()}")

            rc = p.wait()
            _support_log(f"SETUP_COMMAND_DONE: {label} | returncode={rc}")

            if rc != 0:
                raise subprocess.CalledProcessError(rc, cmd)

        except Exception as e:
            _support_log(f"SETUP_COMMAND_FAILED: {label} | error={e!r}")
            raise

    try:
        try:
            run([sys.executable, "-m", "pip", "--version"], "pip_version_check")
        except Exception:
            run([sys.executable, "-m", "ensurepip", "--upgrade"], "ensurepip_upgrade")

        run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "pip",
                "setuptools",
                "wheel",
            ],
            "upgrade_pip_setuptools_wheel",
        )

        run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-input",
                "--prefer-binary",
                *missing_pip,
            ],
            "install_missing_packages",
        )

    except Exception as e:
        _support_log(f"Dependency installation failed: {e!r}")

        try:
            import traceback
            _support_log(traceback.format_exc())
        except Exception:
            pass

        print("\n❌ Failed to install dependencies automatically.", flush=True)
        print("Try running manually:", flush=True)
        print(f"    {sys.executable} -m pip install --prefer-binary {' '.join(missing_pip)}", flush=True)
        print("\nPress Enter to exit...", flush=True)
        try:
            input()
        except Exception:
            pass
        raise SystemExit(1)

    print("\n✅ Packages installed. Restarting application...\n", flush=True)

    _support_log("Packages installed successfully. Requesting app restart with exit code 75.")
    os.environ["GS_DEPS_CHECK_DONE"] = "1"
    _restart_application_after_dependency_install()

def _portable_bootstrap_here() -> None:
    """
    Make this module runnable from anywhere:
      - force working directory to APP_ROOT
      - ensure APP_ROOT is on sys.path for sibling imports
    Safe to call multiple times.

    Also initializes logging BEFORE importing Flows.

    IMPORTANT:
    - Avoid duplicate logger init lines (can happen if menu is executed/imported twice).
    - Never block startup if logging fails.

    PATCH:
    - Ensures third-party deps are installed *before* attempting to import GoogleSheets_Log,
      because GoogleSheets_Log (or its deps) may rely on packages like colorama.
    - Still skips auto-install when frozen (PyInstaller).
    """
    # --- cwd + sys.path bootstrap (safe to run multiple times) ---
    try:
        os.chdir(APP_ROOT)
    except Exception:
        pass

    try:
        root_str = str(APP_ROOT)
        if root_str not in sys.path:
            sys.path.insert(0, root_str)
    except Exception:
        pass

    # --- Early support logging BEFORE dependency setup and BEFORE GoogleSheets_Log ---
    try:
        if __name__ == "__main__" and not getattr(sys, "frozen", False):
            _write_python_support_snapshot()
    except Exception:
        pass

    # --- Dependency bootstrap (BEFORE importing GoogleSheets_Log) ---
    try:
        # IMPORTANT: never auto-install on import. Only when running directly.
        if __name__ == "__main__" and not getattr(sys, "frozen", False):
            _ensure_dependencies_installed()
    except Exception:
        raise

    # --- Logging bootstrap (before importing Flows) ---
    try:
        # If logger already initialized in this process, just record module load.
        from GoogleSheets_Log import get_log_path

        if get_log_path() is not None:
            try:
                from GoogleSheets_Log import module_loaded, decision
                module_loaded(__name__)
                decision("LOGGER_ALREADY_INITIALIZED", module=__name__, fn="_portable_bootstrap_here")
            except Exception:
                pass
            return

        # Env guard (secondary)
        if os.environ.get("GS_LOGGER_INIT_DONE") == "1":
            try:
                from GoogleSheets_Log import module_loaded
                module_loaded(__name__)
            except Exception:
                pass
            return

        from GoogleSheets_Log import (
            init_logger,
            install_excepthook,
            install_atexit_marker,
            module_loaded,
            stage,
        )

        # echo_console=True is safe: logger itself only prints WARN/ERROR,
        # and stage() prints clean human-friendly lines.
        init_logger(app_root=APP_ROOT, echo_console=True, level=os.environ.get("GS_LOG_LEVEL", "INFO"))

        install_excepthook()
        install_atexit_marker()
        module_loaded(__name__)
        stage("GoogleSheets_Menu loaded", module=__name__, fn="<module>")

        # Mark as done for this process
        os.environ["GS_LOGGER_INIT_DONE"] = "1"
    except Exception:
        # Never block startup if logging fails
        pass


# -----------------------------------------------------------------------------
# Bootstrap is SAFE on import (cwd + sys.path + logger), but DEP installs are
# ONLY allowed when running as __main__.
# -----------------------------------------------------------------------------

_portable_bootstrap_here()  # safe: sets cwd/sys.path + logger (and may check deps only if you keep it)

# IMPORTANT: remove this duplicate call — it can restart process during import
# if not getattr(sys, "frozen", False):
#     _ensure_dependencies_installed()

# =============================================================================
# Imports (Flows only, by design)
# =============================================================================
import GoogleSheets_Flows as flows  # noqa: E402

# =============================================================================
# Quit-key listener lifecycle (start once per process)
# =============================================================================

_QUIT_LISTENER_STARTED = False
_QUIT_LISTENER_LOCK = threading.Lock()


def _ensure_quit_listener_started_once() -> None:
    """
    Start the 'press q to cancel' listener once per process.

    PATCHED:
    - Prefer CoreLite's built-in start_quit_key_listener_once() so we don't
      accidentally create duplicate listener threads if other modules start it.
    - Fall back to manual thread start only if that helper isn't available.
    """
    global _QUIT_LISTENER_STARTED
    from GoogleSheets_Log import decision, log_exception

    with _QUIT_LISTENER_LOCK:
        if _QUIT_LISTENER_STARTED:
            decision("QUIT_LISTENER_ALREADY_STARTED", module=__name__, fn="_ensure_quit_listener_started_once")
            return

        # Preferred: CoreLite owns the "once per process" contract.
        try:
            starter = getattr(flows.core, "start_quit_key_listener_once", None)
            if callable(starter):
                decision("QUIT_LISTENER_STARTING_VIA_CORELITE", module=__name__, fn="_ensure_quit_listener_started_once")
                starter()
                _QUIT_LISTENER_STARTED = True
                decision("QUIT_LISTENER_STARTED", module=__name__, fn="_ensure_quit_listener_started_once")
                return
        except Exception:
            log_exception("QUIT_LISTENER_CORELITE_START_FAILED", module=__name__, fn="_ensure_quit_listener_started_once")

        # Fallback: manual thread start (legacy behavior)
        try:
            decision("QUIT_LISTENER_STARTING_MANUAL", module=__name__, fn="_ensure_quit_listener_started_once")
            t = threading.Thread(
                target=flows.core.listen_for_quit_key,
                daemon=True,
                name="GS_QuitKeyListener",
            )
            t.start()
            _QUIT_LISTENER_STARTED = True
            decision("QUIT_LISTENER_STARTED", module=__name__, fn="_ensure_quit_listener_started_once")
        except Exception:
            _QUIT_LISTENER_STARTED = False
            log_exception("QUIT_LISTENER_FAILED", module=__name__, fn="_ensure_quit_listener_started_once")
            # Never block menu startup


# =============================================================================
# Helpers
# =============================================================================

def _core_cancel_flag():
    """
    Return core.cancel_flag if it exists and looks like a threading.Event-ish object.
    """
    try:
        cf = getattr(flows.core, "cancel_flag", None)
        if cf is None:
            return None
        if not (hasattr(cf, "clear") and hasattr(cf, "is_set")):
            return None
        return cf
    except Exception:
        return None


def _print_run_banner() -> None:
    # Legacy text has the three dots after "starting"
    print("⏳ Process starting... Press 'q' at any time to cancel.\n")


# =============================================================================
# Option wrappers (Menu -> Flows)
# =============================================================================

def _run_option2_routed():
    """
    Option 2 in menu:
      ✨ Clean & Split Into Different Suburbs (Full Geocode Check)

    KEEP NEW STREETS:
      - Clean OTHER (exclude_new=True)
      - Clean NEW STREETS (New Streets flow)
      - Merge -> output_clean.csv / output_fail.csv
      - Enforce routing after merge
      - Split ONCE into New_Addresses_By_Suburb from merged outputs
      - Verify split matches merged clean
      - Master duplicate filter + verify-fail steps
      - Enforce routing after each phase
      - Cleanup intermediate artifacts (*.other/*.new/*.full)
    """
    from GoogleSheets_Log import stage, log_error, log_exception, log_debug, decision

    def _enforce(clean_csv: str, fail_csv: str, tag: str) -> None:
        try:
            fn = getattr(flows, "enforce_outputs_routing", None)
            if callable(fn):
                stats = fn(clean_csv, fail_csv)  # positional-only compat
                decision(
                    f"ENFORCE_ROUTING_{tag}",
                    module=__name__,
                    fn="_run_option2_routed",
                    extra=stats if isinstance(stats, dict) else {"result": str(stats)},
                )
        except Exception as e:
            decision(
                f"ENFORCE_ROUTING_{tag}_FAILED",
                module=__name__,
                fn="_run_option2_routed",
                extra={"error": str(e)},
            )

    src = "input_googlesheets.csv"
    if not os.path.exists(src):
        log_error("Missing input file", module=__name__, fn="_run_option2_routed", extra={"file": src})
        return

    stage("Option 2: Routed clean+split (full verify) started", module=__name__, fn="_run_option2_routed")

    other_clean = "output_clean.other.csv"
    other_fail  = "output_fail.other.csv"
    new_clean   = "output_clean.new.csv"
    new_fail    = "output_fail.new.csv"

    merged_clean = "output_clean.csv"
    merged_fail  = "output_fail.csv"

    try:
        stage("Option 2: Cleaning OTHER (full verify) ...", module=__name__, fn="_run_option2_routed")
        cancel_dump = _dump_stacks_after(120, label="Option2-OTHER")
        with progress_stage("Cleaning OTHER"):
            try:
                flows.run_sheets_clean_and_split_after_purge_verify(
                    input_file=src,
                    do_split=False,
                    out_clean=other_clean,
                    out_fail=other_fail,
                    exclude_new=True,
                )
            finally:
                cancel_dump()

        stage("Option 2: Cleaning NEW STREET (full verify) ...", module=__name__, fn="_run_option2_routed")
        cancel_dump = _dump_stacks_after(120, label="Option2-NEW")
        with progress_stage("Cleaning NEW STREETS"):
            try:
                flows.run_sheets_clean_and_split_new_streets_verify(
                    input_file=src,
                    do_split=False,
                    out_clean=new_clean,
                    out_fail=new_fail,
                )
            finally:
                cancel_dump()

        stage("Option 2: Merging clean/fail outputs ...", module=__name__, fn="_run_option2_routed")
        with progress_stage("Merging outputs"):
            flows._merge_csvs([other_clean, new_clean], merged_clean)
            flows._merge_csvs([other_fail,  new_fail],  merged_fail)

        _enforce(merged_clean, merged_fail, "AFTER_MERGE")

        stage("Option 2: Splitting merged outputs into suburb folder ...", module=__name__, fn="_run_option2_routed")
        final_dir = Path("New_Addresses_By_Suburb")
        with progress_stage("Splitting into suburb folder"):
            try:
                flows._split_into_final_folder(merged_clean, merged_fail, kml_dir="KML Boundaries")
            except TypeError:
                flows._split_into_final_folder(merged_clean, merged_fail)

        stage("Option 2: Deduping suburb folder ...", module=__name__, fn="_run_option2_routed")
        with progress_stage("Deduping suburb folder"):
            try:
                flows._dedupe_suburb_folder(final_dir)
            except Exception:
                pass

        stage("Option 2: Verifying split matches merged clean ...", module=__name__, fn="_run_option2_routed")
        with progress_stage("Verifying split matches merged clean"):
            ok = True
            try:
                ok = bool(flows.verify_split_matches_clean(merged_clean, final_dir))
            except Exception:
                ok = False
        decision("SPLIT_VERIFY_RESULT", module=__name__, fn="_run_option2_routed", extra={"ok": bool(ok)})

        stage("Option 2: Master duplicate filter ...", module=__name__, fn="_run_option2_routed")
        with progress_stage("Master duplicate filter"):
            flows.run_final_master_duplicate_filter(merged_clean, merged_fail)
        _enforce(merged_clean, merged_fail, "AFTER_MASTER")

        stage("Option 2: Verify fails vs master ...", module=__name__, fn="_run_option2_routed")
        with progress_stage("Verify fails vs master"):
            flows.run_verify_fail_against_master(merged_clean, merged_fail)
        _enforce(merged_clean, merged_fail, "AFTER_VERIFY_FAIL")

        stage("Option 2: Summary ...", module=__name__, fn="_run_option2_routed")
        with progress_stage("Summary"):
            flows._summarize_final_status(merged_clean, merged_fail)

        stage("Option 2: Routed clean+split (full verify) finished", module=__name__, fn="_run_option2_routed")

    except Exception:
        log_exception("Option 2 failed", module=__name__, fn="_run_option2_routed", extra={"input_file": src})
        raise

    finally:
        stage("Option 2: Cleaning up intermediate CSV artifacts ...", module=__name__, fn="_run_option2_routed")
        try:
            with progress_stage("Cleanup intermediate CSV artifacts"):
                if hasattr(flows, "cleanup_routed_intermediate_csvs"):
                    flows.cleanup_routed_intermediate_csvs(
                        base_out_clean=merged_clean,
                        base_out_fail=merged_fail,
                        input_file=src,
                        delete_full=True,
                    )
                else:
                    for p in (other_clean, other_fail, new_clean, new_fail, "output_clean.full.csv", "output_fail.full.csv"):
                        try:
                            if Path(p).exists():
                                Path(p).unlink()
                        except Exception:
                            pass
        except Exception as e:
            log_debug(
                "CLEANUP_INTERMEDIATE_CSVS_FAILED",
                module=__name__,
                fn="_run_option2_routed",
                extra={"error": str(e)},
            )



def _run_option3_routed():
    """
    Option 3 in menu:
      📚 Check Master Database For Duplicates

    (Renumbered: was Option 5)
    """
    from GoogleSheets_Log import stage, log_exception

    stage("Option 3: Master DB duplicate audit started", module=__name__, fn="_run_option3_routed")
    try:
        with progress_stage("Master DB duplicate audit"):
            flows.run_master_db_duplicate_audit()
        stage("Option 3: Master DB duplicate audit finished", module=__name__, fn="_run_option3_routed")
    except Exception:
        log_exception("Option 3 failed", module=__name__, fn="_run_option3_routed")
        raise


def _run_option1_clean_only():
    """
    Option 1: ✨ Clean Google Sheets (Full Geocode Check) (no split)

    KEEP NEW STREETS:
      - Clean OTHER (exclude_new=True)
      - Clean NEW STREETS (New Streets flow)
      - Merge -> output_clean.csv / output_fail.csv
      - Master duplicate filter + verify-fail steps
      - Enforce routing after each phase
      - Cleanup intermediate artifacts (*.other/*.new/*.full)

    PATCH:
    - Heartbeat + stack-dump timers are now cancellable per-phase.
    - Prevents "false" stack dumps after a phase finishes.
    - Adds progress bars for ALL stages.
    """
    from GoogleSheets_Log import stage, log_error, log_exception, decision

    def _enforce(clean_csv: str, fail_csv: str, tag: str) -> None:
        try:
            fn = getattr(flows, "enforce_outputs_routing", None)
            if callable(fn):
                stats = fn(clean_csv, fail_csv)
                decision(
                    f"ENFORCE_ROUTING_{tag}",
                    module=__name__,
                    fn="_run_option1_clean_only",
                    extra=stats if isinstance(stats, dict) else {"result": str(stats)},
                )
        except Exception as e:
            decision(
                f"ENFORCE_ROUTING_{tag}_FAILED",
                module=__name__,
                fn="_run_option1_clean_only",
                extra={"error": str(e)},
            )

    src = "input_googlesheets.csv"
    if not os.path.exists(src):
        log_error("Missing input file", module=__name__, fn="_run_option1_clean_only", extra={"file": src})
        return

    stage("Option 1: Clean only (full verify) started", module=__name__, fn="_run_option1_clean_only")

    other_clean = "output_clean.other.csv"
    other_fail  = "output_fail.other.csv"
    new_clean   = "output_clean.new.csv"
    new_fail    = "output_fail.new.csv"

    merged_clean = "output_clean.csv"
    merged_fail  = "output_fail.csv"

    try:
        # -----------------------------
        # Phase 1: OTHER
        # -----------------------------
        stage("Option 1: Cleaning OTHER (full verify) ...", module=__name__, fn="_run_option1_clean_only")
        cancel_dump = _dump_stacks_after(120, label="Option1-OTHER")
        with progress_stage("Cleaning OTHER"):
            try:
                flows.run_sheets_clean_and_split_after_purge_verify(
                    input_file=src,
                    do_split=False,
                    out_clean=other_clean,
                    out_fail=other_fail,
                    exclude_new=True,
                )
            finally:
                cancel_dump()

        # -----------------------------
        # Phase 2: NEW STREETS
        # -----------------------------
        stage("Option 1: Cleaning NEW STREET (full verify) ...", module=__name__, fn="_run_option1_clean_only")
        cancel_dump = _dump_stacks_after(120, label="Option1-NEW")
        with progress_stage("Cleaning NEW STREETS"):
            try:
                flows.run_sheets_clean_and_split_new_streets_verify(
                    input_file=src,
                    do_split=False,
                    out_clean=new_clean,
                    out_fail=new_fail,
                )
            finally:
                cancel_dump()

        # -----------------------------
        # Merge + downstream steps
        # -----------------------------
        stage("Option 1: Merging outputs ...", module=__name__, fn="_run_option1_clean_only")
        with progress_stage("Merging outputs"):
            flows._merge_csvs([other_clean, new_clean], merged_clean)
            flows._merge_csvs([other_fail,  new_fail],  merged_fail)
        _enforce(merged_clean, merged_fail, "AFTER_MERGE")

        stage("Option 1: Master duplicate filter ...", module=__name__, fn="_run_option1_clean_only")
        with progress_stage("Master duplicate filter"):
            flows.run_final_master_duplicate_filter(merged_clean, merged_fail)
        _enforce(merged_clean, merged_fail, "AFTER_MASTER")

        stage("Option 1: Verify fails vs master ...", module=__name__, fn="_run_option1_clean_only")
        with progress_stage("Verify fails vs master"):
            flows.run_verify_fail_against_master(merged_clean, merged_fail)
        _enforce(merged_clean, merged_fail, "AFTER_VERIFY_FAIL")

        stage("Option 1: Summary ...", module=__name__, fn="_run_option1_clean_only")
        with progress_stage("Summary"):
            flows._summarize_final_status(merged_clean, merged_fail)

        stage("Option 1: Clean only (full verify) finished", module=__name__, fn="_run_option1_clean_only")

    except Exception:
        log_exception("Option 1 failed", module=__name__, fn="_run_option1_clean_only", extra={"input_file": src})
        raise

    finally:
        stage("Option 1: Cleaning up intermediate CSV artifacts ...", module=__name__, fn="_run_option1_clean_only")
        try:
            with progress_stage("Cleanup intermediate CSV artifacts"):
                if hasattr(flows, "cleanup_routed_intermediate_csvs"):
                    flows.cleanup_routed_intermediate_csvs(
                        base_out_clean=merged_clean,
                        base_out_fail=merged_fail,
                        input_file=src,
                        delete_full=True,
                    )
                else:
                    for p in (other_clean, other_fail, new_clean, new_fail, "output_clean.full.csv", "output_fail.full.csv"):
                        try:
                            Path(p).unlink(missing_ok=True)
                        except TypeError:
                            if Path(p).exists():
                                Path(p).unlink()
        except Exception:
            pass



# =============================================================================
# Menu UI
# =============================================================================

def render_menu():
    """
    Print the Google Sheets submenu.
    """
    print("")
    print("\n\033[4mGoogle Sheets (input_googlesheets)\033[0m")
    print("1 - ✨ Clean Google Sheets")
    print("2 - ✨ Clean & Split Into Different Suburbs")
    print("3 - 📚 Check Master Database For Duplicates")
    print("8 - 🐍 Install / repair Python with winget")
    print("9 - ✅ Check requirements / installed packages")
    print("0 - Back to Main Menu")


# C:\Users\brook\OneDrive\Desktop\Coding\Territory Assistant\GoogleSheets_Menu.py

def open_menu():
    """
    Interactive menu loop.

    Renumbered:
      - 1: Clean Google Sheets (Full Geocode Check)        (was 2)
      - 2: Clean & Split Into Different Suburbs (Full...)  (was 4)
      - 3: Check Master Database For Duplicates            (was 5)
      - 0: Back

    PERFORMANCE PATCH:
      - Profiles only active Option 1/2/3 execution.
      - Writes Log/GoogleSheets_Performance.txt after each run.
      - Excludes idle menu/input waiting time from the profile.
    """
    from GoogleSheets_Log import (
        decision,
        log_exception,
        stage,
        performance_start,
        performance_stop,
    )

    _ensure_quit_listener_started_once()

    stage(
        "GoogleSheets menu loop entered",
        module=__name__,
        fn="open_menu",
    )

    while True:
        render_menu()

        choice = (
            input(
                "\nChoose an option "
                "(0/1/2/3/8/9): "
            )
            or ""
        ).strip()

        decision(
            "MENU_CHOICE_INPUT",
            module=__name__,
            fn="open_menu",
            extra={
                "choice": choice,
            },
        )

        if choice == "0":
            decision(
                "MENU_EXIT",
                module=__name__,
                fn="open_menu",
            )

            print(
                "↩️  Returning to main menu.\n"
            )

            return

        if choice == "8":
            decision(
                "MENU_PYTHON_INSTALL_REPAIR",
                module=__name__,
                fn="open_menu",
            )

            _install_or_repair_python_with_winget()

            continue

        if choice == "9":
            decision(
                "MENU_REQUIREMENTS_CHECK",
                module=__name__,
                fn="open_menu",
            )

            _check_runtime_requirements(
                print_report=True,
            )

            continue

        if choice not in {
            "1",
            "2",
            "3",
        }:
            decision(
                "MENU_INVALID_CHOICE",
                module=__name__,
                fn="open_menu",
                extra={
                    "choice": choice,
                },
            )

            print(
                "❌ Invalid choice.\n"
            )

            continue

        confirm = input(
            "Proceed? "
            "(y to continue / any other key to cancel): "
        ).strip().lower()

        decision(
            "MENU_CONFIRM",
            module=__name__,
            fn="open_menu",
            extra={
                "choice": choice,
                "confirm": confirm,
            },
        )

        if confirm != "y":
            print(
                "❌ Cancelled.\n"
            )

            decision(
                "MENU_CANCELLED_AT_CONFIRM",
                module=__name__,
                fn="open_menu",
                extra={
                    "choice": choice,
                },
            )

            continue

        # Clear cancel flag for this run.
        try:
            cf = _core_cancel_flag()

            if cf is not None:
                cf.clear()

                decision(
                    "CANCEL_FLAG_CLEARED",
                    module=__name__,
                    fn="open_menu",
                    extra={
                        "choice": choice,
                    },
                )

            else:
                decision(
                    "CANCEL_FLAG_NOT_AVAILABLE",
                    module=__name__,
                    fn="open_menu",
                    extra={
                        "choice": choice,
                    },
                )

        except Exception:
            decision(
                "CANCEL_FLAG_CLEAR_FAILED",
                module=__name__,
                fn="open_menu",
                extra={
                    "choice": choice,
                },
            )

        option_map = {
            "1": (
                "_run_option1_clean_only",
                _run_option1_clean_only,
            ),
            "2": (
                "_run_option2_routed",
                _run_option2_routed,
            ),
            "3": (
                "_run_option3_routed",
                _run_option3_routed,
            ),
        }

        opt_name, opt_fn = option_map[
            choice
        ]

        perf_started = False
        perf_status = "OK"

        try:
            _print_run_banner()

            decision(
                "RUN_OPTION_START",
                module=__name__,
                fn="open_menu",
                extra={
                    "option": choice,
                    "name": opt_name,
                },
            )

            # ---------------------------------------------------------
            # Start performance profiler AFTER confirmation/menu input.
            # ---------------------------------------------------------
            try:
                performance_start(
                    label=(
                        f"Option {choice} - "
                        f"{opt_name}"
                    ),
                    app_root=APP_ROOT,
                )

                perf_started = True

            except Exception as e:
                decision(
                    "PERFORMANCE_PROFILE_START_FAILED",
                    module=__name__,
                    fn="open_menu",
                    extra={
                        "option": choice,
                        "error": str(e),
                    },
                )

            # ---------------------------------------------------------
            # Actual Option 1/2/3 execution
            # ---------------------------------------------------------
            flows.core.run_with_cancel(
                opt_fn
            )

            try:
                cf = _core_cancel_flag()

                cancelled = bool(
                    cf is not None
                    and cf.is_set()
                )

            except Exception:
                cancelled = False

            perf_status = (
                "CANCELLED"
                if cancelled
                else "OK"
            )

            decision(
                "RUN_OPTION_DONE",
                module=__name__,
                fn="open_menu",
                extra={
                    "option": choice,
                    "name": opt_name,
                    "cancelled": cancelled,
                },
            )

        except Exception as e:
            perf_status = "ERROR"

            log_exception(
                "MENU_EXCEPTION",
                module=__name__,
                fn="open_menu",
                extra={
                    "choice": choice,
                    "error": str(e),
                },
            )

            print(
                f"❌ Error: {e}"
            )

        finally:
            # ---------------------------------------------------------
            # Always stop/write profile, even after cancellation/error.
            # ---------------------------------------------------------
            if perf_started:
                try:
                    perf_path = performance_stop(
                        status=perf_status
                    )

                    decision(
                        "PERFORMANCE_PROFILE_WRITTEN",
                        module=__name__,
                        fn="open_menu",
                        extra={
                            "option": choice,
                            "status": perf_status,
                            "file": (
                                str(perf_path)
                                if perf_path
                                else ""
                            ),
                        },
                    )

                except Exception as e:
                    decision(
                        "PERFORMANCE_PROFILE_STOP_FAILED",
                        module=__name__,
                        fn="open_menu",
                        extra={
                            "option": choice,
                            "error": str(e),
                        },
                    )


# =============================================================================
# Direct run
# =============================================================================

if __name__ == "__main__":
    try:
        open_menu()
    except KeyboardInterrupt:
        print("\n👋 Exiting.")

