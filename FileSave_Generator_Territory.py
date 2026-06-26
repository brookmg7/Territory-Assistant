#!/usr/bin/env python3
r"""
FileSave_Generator_Territory.py

PASS 1:
- Scans whatever folder this script is in (or --root)
- Looks for MAIN folders (top-level dirs)
- Each MAIN folder is considered to contain Sub_### slots directly underneath its
- Finds the next EMPTY Sub_### slot (empty = no files anywhere under that Sub_### recursively)

PASS 2:
- Scans external folder:
  C:\\Users\\brook\\OneDrive\\Desktop\\Python_AI Bot

- Prints:
  (1) all code files (.py/.bat/.yaml/.yml) (recursive)
  (2) all OTHER items in that folder (top-level) numbered, with size

- Copies all code files into next empty Sub_### folder (structure preserved)
- Opens the destination Sub_### folder in Explorer (EXCLUSIVE: only 1 Sub window open at a time)
- Menu:
    S = Save again to NEXT Sub folder (auto-advance; skips non-empty; spills to next Backup; can auto-create Backup+Subs)
    A = Add selected "other items" (by number) into SAME current Sub folder (never into a new empty Sub folder)
    R = Rename the current Sub folder by appending a suffix: "Sub_011 (Update)" etc
    Enter = continue (keeps looping)

Notes:
- Copy preserves relative subfolder structure under the external root.
- Add (A) preserves top-level item name (folder copied as a folder into Sub_###).
- Rename (R) replaces any existing trailing " (....)" suffix.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Folders to exclude from recursive code scan
EXCLUDE_DIR_NAMES = {
    ".idea",
    ".venv",
    "__pycache__",
}

# Add extra common junk folders to exclude
EXCLUDE_DIR_NAMES |= {
    ".git",
    "node_modules",
    "site-packages",
    "build",
    "dist",
}

DEFAULT_RENAME_SUFFIX = "In Progress"


TERRITORY_ROOT = Path(
    r"C:\Users\brook\OneDrive\Desktop\Territory Assistant"
)


DEFAULT_CHANGED_SUFFIX = "New Update"   # used when changes detected
DEFAULT_UNCHANGED_SUFFIX = DEFAULT_RENAME_SUFFIX  # "In Progress"

ONEDRIVE_ROOT = Path(r"C:\Users\brook\OneDrive\Desktop\Python_AI Bot")

# ----------------------------
# Console color helpers (ANSI)
# ----------------------------
COLOR_RESET = "\033[0m"
COLOR_BRIGHT_YELLOW = "\033[93m"

_DIGIT_RE = re.compile(r"(\d+)")
_SUB_SLOT_RE = re.compile(r"^Sub_(\d+)", re.IGNORECASE)

# Rename suffix options (numbered in UI)
RENAME_SUFFIX_OPTIONS: List[str] = [
    "Working Well",
    "Good",
    "In Progress",
    "New Update",
    "Updating In Progress...",
    "Issues",
    "Errors",
    "New Function",
    "Splitting Modules",
    "Folder Backup",
    "Testing",
    "Restructuring",
    "Problems",
]

# Code file extensions to auto-save (flat copy)
CODE_EXTS = {".py", ".bat", ".yaml", ".yml"}

# ============================================================
# LOGGING SETUP
# ============================================================



def ensure_default_suffix_on_subfolder(subfolder: Path, logger: logging.Logger) -> Path:
    """
    If subfolder name does NOT already end with ' (...)', rename it to add
    DEFAULT_RENAME_SUFFIX, e.g. 'Sub_135' -> 'Sub_135 (In Progress)'.
    If it already has a suffix, do nothing.
    Returns the resulting Path (new or unchanged).
    """
    try:
        if not subfolder.exists() or not subfolder.is_dir():
            return subfolder

        # already has '(...)' suffix -> leave it
        if re.search(r"\s+\([^()]*\)\s*$", subfolder.name):
            return subfolder

        ok, msg, new_path = rename_subfolder_append_suffix(subfolder, DEFAULT_RENAME_SUFFIX, logger)
        if ok:
            logger.info("Default suffix applied: %s -> %s", subfolder, new_path)
            return new_path

        logger.warning("Default suffix NOT applied (%s): %s", subfolder, msg)
        return subfolder

    except Exception as e:
        logger.warning("ensure_default_suffix_on_subfolder failed (%s)", e)
        return subfolder

def build_change_suffix(
    added: List[str],
    updated: List[str],
    removed: List[str],
    max_names: int = 2,
) -> str:

    """
    Build a human-readable suffix from changed files.

    Examples:
      - "vpm_io.py updated"
      - "a.py, b.py updated"
      - "3 files updated"
      - "x.py added"
      - "y.py removed"
      - "mixed changes"
    """
    def short(names: List[str]) -> List[str]:
        return [Path(n).name for n in names[:max_names]]

    if updated and not added and not removed:
        names = short(updated)
        if len(updated) <= max_names:
            return f"{', '.join(names)} updated"
        return f"{len(updated)} files updated"

    if added and not updated and not removed:
        names = short(added)
        if len(added) <= max_names:
            return f"{', '.join(names)} added"
        return f"{len(added)} files added"

    if removed and not added and not updated:
        names = short(removed)
        if len(removed) <= max_names:
            return f"{', '.join(names)} removed"
        return f"{len(removed)} files removed"

    # Mixed changes
    parts = []
    if added:
        parts.append("added")
    if updated:
        parts.append("updated")
    if removed:
        parts.append("removed")

    return " & ".join(parts)

def setup_logging(root: Path) -> logging.Logger:
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    ts = time.strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"FolderFillScanner_{ts}.log"

    logger = logging.getLogger("FolderFillScanner")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.WARNING)  # keep console clean; log file has details
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)

    logger.info("============================================================")
    logger.info("FolderFillScanner started")
    logger.info("Python      : %s", sys.version.replace("\n", " "))
    logger.info("Executable  : %s", sys.executable)
    logger.info("Log file    : %s", log_path)
    logger.info("============================================================")

    return logger


# ============================================================
# Helpers
# ============================================================




def find_brook_t7_root() -> Optional[Path]:
    """
    Locate drive with volume label 'Brook T7'.
    Returns root Path (e.g. E:\\) or None.
    """
    try:
        import string
        for d in string.ascii_uppercase:
            drive = Path(f"{d}:\\")
            if not drive.exists():
                continue
            try:
                result = subprocess.run(
                    ["cmd", "/c", f"vol {d}:"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if "Brook T7" in result.stdout:
                    return drive
            except Exception:
                continue
    except Exception:
        return None
    return None


def locate_filesave_generator(logger: logging.Logger) -> Optional[Path]:
    """
    Locate FileSave_Generator.py from:
      1) G:\\Python Scripts\\Forex Python Bot
      2) <Brook T7>:\\Python Scripts\\Forex Python Bot
    """
    primary = Path(r"G:\Python Scripts\Forex Python Bot\FileSave_Generator.py")
    if primary.exists():
        return primary

    t7 = find_brook_t7_root()
    if t7:
        fallback = t7 / "Python Scripts" / "Forex Python Bot" / "FileSave_Generator.py"
        if fallback.exists():
            return fallback

    logger.warning("FileSave_Generator.py not found on G: or Brook T7 drive")
    return None

def natural_key(s: str) -> Tuple:
    parts = _DIGIT_RE.split(s)
    key: List[tuple] = []
    for p in parts:
        if not p:
            continue
        if p.isdigit():
            key.append((0, int(p)))
        else:
            key.append((1, p.casefold()))
    return tuple(key)


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def format_size(num_bytes: int) -> str:
    """Human readable size."""
    try:
        n = float(num_bytes)
    except Exception:
        return "N/A"
    units = ["B", "KB", "MB", "GB", "TB"]
    for u in units:
        if n < 1024.0 or u == units[-1]:
            if u == "B":
                return f"{int(n)} {u}"
            return f"{n:.2f} {u}"
        n /= 1024.0
    return f"{int(num_bytes)} B"


def dir_size_bytes(folder: Path, logger: logging.Logger) -> int | None:
    """
    Total size of all files under folder (recursive).
    Returns None if size cannot be computed (permission issues, etc).
    """
    total = 0
    try:
        for p in folder.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except (PermissionError, OSError):
                    continue
        return total
    except (PermissionError, OSError) as e:
        logger.warning("dir_size_bytes: cannot size %s (%s)", folder, e)
        return None


def open_in_explorer(path: Path, logger: logging.Logger) -> None:
    try:
        if not path.exists():
            logger.error("Explorer open failed; path missing: %s", path)
            return
        logger.info("Opening folder in Explorer: %s", path)
        os.startfile(str(path))
    except Exception as e:
        logger.error("Failed to open Explorer for %s (%s)", path, e)



def close_all_open_sub_windows(logger: logging.Logger) -> None:
    """
    Close ALL open Explorer windows that are currently showing a Sub_### folder,
    including suffixed variants like:
      Sub_141 (Good)
      Sub_141 (In Progress)

    Adds a short delay to let Explorer release locks.
    """
    try:
        ps = r"""
$shell = New-Object -ComObject Shell.Application
$wins  = @($shell.Windows())

# Match Sub folders anywhere in path:
#   \Sub_123
#   \Sub_123\
#   \Sub_123 (Anything)
#   \Sub_123 (Anything)\
$re = "\\Sub_\d{3}(\s+\([^\\)]*\))?($|\\)"

foreach ($w in $wins) {
  try {
    # Some windows are not file explorer (IE/web) - guard
    $p = $null
    try { $p = $w.Document.Folder.Self.Path } catch { $p = $null }

    if ($p -and ($p -match $re)) {
      $w.Quit()
    }
  } catch {}
}

# Give Explorer time to actually release handle locks
Start-Sleep -Milliseconds 350
"""
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            capture_output=True,
            text=True,
            check=False,
        )
        logger.info("Closed all open Sub_### Explorer windows (including suffixed)")
    except Exception as e:
        logger.warning("close_all_open_sub_windows failed (%s)", e)




def open_sub_folder_exclusive(path: Path, logger: logging.Logger) -> None:
    """
    Close ALL other Sub_### Explorer windows, then open this path.
    """
    close_all_open_sub_windows(logger)
    open_in_explorer(path, logger)


def _strip_trailing_paren_suffix(name: str) -> str:
    """
    If name ends with ' (something)', remove that trailing suffix.
    Examples:
      'Sub_011 (Update)' -> 'Sub_011'
      'Sub_011'          -> 'Sub_011'
    """
    return re.sub(r"\s+\([^()]*\)\s*$", "", name).strip()


def prompt_rename_choice(options: List[str]) -> Optional[str]:
    """
    Returns:
      - suffix string if user chose a preset or typed custom
      - None if cancelled
    """
    print("-" * 72)
    print("🏷️ Rename Subfolder:")

    for i, opt in enumerate(options, start=1):
        print(f"   {i}. {opt}")

    custom_key = len(options) + 1
    print(f"   {custom_key}. (Custom... type your own)")

    try:
        resp = input("Select number (or blank to cancel): ").strip()
        if resp == "":
            return None
        if not resp.isdigit():
            return None

        pick = int(resp)

        if 1 <= pick <= len(options):
            return options[pick - 1]

        if pick == custom_key:
            custom = input("Type your custom suffix (blank to cancel): ").strip()
            if custom == "":
                return None
            return custom

        return None
    except KeyboardInterrupt:
        return None



def rename_subfolder_append_suffix(
    subfolder: Path,
    suffix_text: str,
    logger: logging.Logger
) -> Tuple[bool, str, Path]:
    """
    Rename Sub_### folder to: 'Sub_### (suffix_text)'.
    - If it already has '(...)' at the end, it will be replaced.
    - Closes Explorer windows first and retries to avoid WinError 5.
    Returns (ok, message, new_path_or_old_path).
    """
    try:
        if not subfolder.exists() or not subfolder.is_dir():
            return (False, "Folder does not exist.", subfolder)

        # Close Explorer windows that may be locking the folder
        close_all_open_sub_windows(logger)

        parent = subfolder.parent
        base = _strip_trailing_paren_suffix(subfolder.name)

        new_name = f"{base} ({suffix_text})"
        new_path = parent / new_name

        if new_path.exists():
            return (False, f'Cannot rename: "{new_name}" already exists.', subfolder)

        # Explorer/AV can hold the handle briefly even after Quit().
        # Retry with small backoff.
        last_err: Optional[Exception] = None
        for attempt in range(1, 9):
            try:
                subfolder.rename(new_path)
                logger.info("Renamed subfolder: %s -> %s", subfolder, new_path)
                return (True, f'Renamed to: {new_name}', new_path)
            except PermissionError as e:
                last_err = e
                logger.warning("Rename attempt %d blocked by lock: %s", attempt, e)
                time.sleep(0.15 * attempt)  # 0.15s, 0.30s, 0.45s...
            except OSError as e:
                # Sometimes WinError 32/5 surfaces as generic OSError
                last_err = e
                logger.warning("Rename attempt %d failed: %s", attempt, e)
                time.sleep(0.15 * attempt)

        logger.error("Rename failed after retries: %s (%s)", subfolder, last_err)
        return (False, "Rename failed (folder in use). Close Explorer/VSCode and retry.", subfolder)

    except Exception as e:
        logger.error("Rename failed: %s (%s)", subfolder, e)
        return (False, f"Rename failed: {e}", subfolder)

def collect_all_files(
    target: Path,
    logger: logging.Logger,
    skip_hidden: bool = False,
) -> List[Path]:
    """
    Collect ALL files recursively under target (any extension).

    - Skips excluded folders by PRUNING traversal (fast)
    - Optional: skip hidden (dot paths + Windows hidden attribute)
    - Returns a sorted list of file Paths
    """
    files: List[Path] = []
    exclude = {d.casefold() for d in EXCLUDE_DIR_NAMES}

    if not target.exists() or not target.is_dir():
        logger.warning("collect_all_files: target missing: %s", target)
        return files

    try:
        for root, dirnames, filenames in os.walk(str(target)):
            root_path = Path(root)

            # Prune excluded dirs (and optionally hidden dirs) in-place
            kept_dirs = []
            for d in dirnames:
                if d.casefold() in exclude:
                    continue
                if skip_hidden and d.startswith("."):
                    continue
                kept_dirs.append(d)
            dirnames[:] = kept_dirs

            # Optional: skip if current root itself is hidden
            if skip_hidden and is_hidden_path(root_path):
                continue

            for fn in filenames:
                try:
                    if skip_hidden and fn.startswith("."):
                        continue

                    p = root_path / fn

                    # Optional: skip hidden files (Windows attribute)
                    if skip_hidden and is_hidden_path(p):
                        continue

                    if not p.is_file():
                        continue

                    files.append(p)
                except (PermissionError, OSError):
                    continue

    except (PermissionError, OSError) as e:
        logger.error("collect_all_files failed: %s (%s)", target, e)
        return []

    files.sort(key=lambda p: natural_key(str(p)))
    return files


def parse_backup_num(name: str) -> int | None:
    if "backup" not in name.casefold():
        return None
    m = re.search(r"(\d+)", name)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def format_backup_name(n: int) -> str:
    return f"Backup_{n:03d}"


def next_sub_name_from(n: int) -> str:
    return f"Sub_{n:03d}"


def parse_sub_num(name: str) -> int | None:
    m = re.search(r"(\d+)", name)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def iter_main_folders(root: Path, logger: logging.Logger) -> List[Path]:
    """
    Only treat Backup_### folders as MAIN folders (ignore logs, etc).
    """
    mains: List[Path] = []
    try:
        for p in root.iterdir():
            if not p.is_dir():
                continue
            if parse_backup_num(p.name) is None:
                continue
            mains.append(p)
    except Exception:
        mains = []

    mains.sort(key=lambda p: natural_key(p.name))
    logger.info("Found %d Backup_### folders under %s", len(mains), root)
    return mains




def iter_sub_slots(main_folder: Path) -> List[Path]:
    slots: List[Path] = []
    try:
        for p in main_folder.iterdir():
            if p.is_dir() and _SUB_SLOT_RE.match(p.name):
                slots.append(p)
    except Exception:
        return []
    slots.sort(key=lambda p: natural_key(p.name))
    return slots


def folder_has_any_file_recursive(folder: Path, logger: logging.Logger) -> bool:
    try:
        if not folder.exists():
            return False
        for p in folder.rglob("*"):
            if p.is_file():
                return True
    except (PermissionError, OSError) as e:
        logger.warning("Access issue in %s (%s) → treating as NOT empty", folder, e)
        return True
    return False


def is_dir_empty_recursive(folder: Path, logger: logging.Logger) -> bool:
    if not folder.exists():
        return True
    return not folder_has_any_file_recursive(folder, logger)


def compute_slot_fill(main_folder: Path, logger: logging.Logger) -> Tuple[int, int, float]:
    slots = iter_sub_slots(main_folder)
    total = len(slots)
    if total == 0:
        return (0, 0, 1.0)
    used = 0
    for s in slots:
        if folder_has_any_file_recursive(s, logger):
            used += 1
    return (used, total, used / total)


def find_next_empty_slot(main_folder: Path, logger: logging.Logger) -> Path | None:
    for slot in iter_sub_slots(main_folder):
        if is_dir_empty_recursive(slot, logger):
            return slot
    return None


def find_next_empty_slot_from(main_folder: Path, start_slot_name: str, logger: logging.Logger) -> Path | None:
    slots = iter_sub_slots(main_folder)
    if not slots:
        return None

    start_key = natural_key(start_slot_name)
    start_idx = 0
    for i, s in enumerate(slots):
        if natural_key(s.name) >= start_key:
            start_idx = i
            break

    for slot in slots[start_idx:]:
        if is_dir_empty_recursive(slot, logger):
            return slot

    return None

def _is_valid_backup_folder(p: Path) -> bool:
    """
    Safety: only consider folders named Backup_### (case-insensitive).
    """
    return p.is_dir() and parse_backup_num(p.name) is not None


def clear_backup_contents(backup_folder: Path, logger: logging.Logger) -> None:
    """
    Clear ONLY the contents of a Backup_### folder (delete everything inside it),
    but do NOT delete the backup folder itself.

    This enables "recycling" Backup_001..Backup_005 in a ring.
    """
    try:
        if not backup_folder.exists() or not backup_folder.is_dir():
            return

        if parse_backup_num(backup_folder.name) is None:
            logger.warning("Refusing to clear non-backup folder: %s", backup_folder)
            return

        for child in backup_folder.iterdir():
            try:
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=False)
                else:
                    child.unlink(missing_ok=True)
            except Exception as e:
                logger.warning("Failed to delete %s (%s)", child, e)

        logger.info("Cleared contents of %s", backup_folder)

    except Exception as e:
        logger.error("clear_backup_contents failed for %s (%s)", backup_folder, e)


def ensure_backup_exists(
    root: Path,
    backup_num: int,
    subs_per_backup: int,
    logger: logging.Logger,
) -> Path:
    """
    Ensure Backup_### exists and has Sub_### slots.
    Returns the backup Path.
    """
    b = root / format_backup_name(backup_num)
    ensure_backup_structure(b, subs_per_backup, logger)
    return b


def get_backup_ring(
    root: Path,
    max_backups: int,
    subs_per_backup: int,
    logger: logging.Logger,
) -> List[Path]:
    """
    Return the backup ring: [Backup_001 .. Backup_max_backups] that exist on disk.
    If none exist, create Backup_001.
    """
    mains = iter_main_folders(root, logger)
    mains = [m for m in mains if _is_valid_backup_folder(m)]

    # Filter to <= max_backups (ignore any higher ones if they exist)
    ring = []
    for n in range(1, max_backups + 1):
        p = root / format_backup_name(n)
        if p.exists() and p.is_dir():
            ring.append(p)

    if not ring:
        ring = [ensure_backup_exists(root, 1, subs_per_backup, logger)]

    # Ensure structure for all ring members
    for p in ring:
        ensure_backup_structure(p, subs_per_backup, logger)

    return ring


def find_or_rotate_next_backup(
    root: Path,
    current_backup: Path,
    max_backups: int,
    subs_per_backup: int,
    logger: logging.Logger,
) -> Path:
    """
    Move to the next backup:
      - If fewer than max_backups exist, create the next numbered backup.
      - If max_backups exist, rotate to next in ring (1..max_backups).
        If the target backup is FULL, clear ONLY that backup and restart at Sub_001.

    Returns the new current backup Path.
    """
    cur_n = parse_backup_num(current_backup.name) or 1

    # Determine how many backups exist within the ring range
    existing_in_ring = []
    for n in range(1, max_backups + 1):
        p = root / format_backup_name(n)
        if p.exists() and p.is_dir():
            existing_in_ring.append(p)

    if len(existing_in_ring) < max_backups:
        # Create next backup (but never beyond max_backups)
        nxt_n = min(cur_n + 1, max_backups)
        nxt = ensure_backup_exists(root, nxt_n, subs_per_backup, logger)
        return nxt

    # Ring is full: rotate
    nxt_n = (cur_n % max_backups) + 1  # wraps max -> 1
    nxt = ensure_backup_exists(root, nxt_n, subs_per_backup, logger)

    # If the next backup is full, clear it and recreate subs
    if find_next_empty_slot(nxt, logger) is None:
        print(f"♻️  All backups full (max={max_backups}). Recycling: {COLOR_BRIGHT_YELLOW}{nxt.name}{COLOR_RESET}")
        clear_backup_contents(nxt, logger)
        ensure_backup_structure(nxt, subs_per_backup, logger)

    return nxt

def ensure_backup_structure(
    backup_folder: Path,
    subs_per_backup: int,
    logger: logging.Logger
) -> None:
    """
    Ensure Sub_### slots exist, BUT:
    - If Sub_### already exists in ANY form:
        Sub_001
        Sub_001 (Good)
        Sub_001 (Anything)
      then DO NOT create another Sub_001.
    """

    ensure_dir(backup_folder)

    # Discover which Sub numbers are already taken (base slot numbers)
    existing_nums = set()

    try:
        for p in backup_folder.iterdir():
            if not p.is_dir():
                continue
            m = _SUB_SLOT_RE.match(p.name)
            if m:
                try:
                    existing_nums.add(int(m.group(1)))
                except Exception:
                    pass
    except Exception:
        pass

    # Create only missing Sub_### slots
    for i in range(1, subs_per_backup + 1):
        if i in existing_nums:
            continue  # slot already exists (even if suffixed)

        sub_path = backup_folder / next_sub_name_from(i)
        ensure_dir(sub_path)

    logger.info(
        "Ensured backup structure: %s (existing=%d, max=%d)",
        backup_folder,
        len(existing_nums),
        subs_per_backup,
    )



def find_or_create_next_backup(
    root: Path,
    mains: List[Path],
    cur_main_idx: int,
    subs_per_backup: int,
    logger: logging.Logger
) -> tuple[int, Path]:
    if cur_main_idx + 1 < len(mains):
        nxt = mains[cur_main_idx + 1]
        ensure_backup_structure(nxt, subs_per_backup, logger)
        return (cur_main_idx + 1, nxt)

    max_n = 0
    for m in mains:
        bn = parse_backup_num(m.name)
        if bn is not None:
            max_n = max(max_n, bn)

    new_n = max_n + 1 if max_n > 0 else 1
    new_backup = root / format_backup_name(new_n)

    ensure_backup_structure(new_backup, subs_per_backup, logger)

    mains.append(new_backup)
    mains.sort(key=lambda p: natural_key(p.name))
    return (mains.index(new_backup), new_backup)


# ============================================================
# PASS 2 — External scan (code files + other top-level items)
# ============================================================

def is_hidden_path(p: Path) -> bool:
    """
    Hidden if:
      - any path part starts with '.'
      - OR (Windows) FILE_ATTRIBUTE_HIDDEN is set (best-effort)
    """
    # dotfiles/dotfolders
    if any(part.startswith(".") for part in p.parts):
        return True

    # Windows hidden attribute (best-effort)
    try:
        # FILE_ATTRIBUTE_HIDDEN = 0x2
        return bool(p.stat().st_file_attributes & 0x2)  # type: ignore[attr-defined]
    except Exception:
        return False

def copy_self_script_into_dest(
    dest_slot: Path,
    logger: logging.Logger,
) -> Tuple[bool, str]:
    """
    Copy THIS running script into dest_slot root as:
      FileSave_Generator_Territory.py
    Never overwrite (uses __ADD_## if needed).
    """
    try:
        src = Path(__file__).resolve()
        if not src.exists():
            return (False, "Script source path not found.")

        ensure_dir(dest_slot)

        dest_name = src.name  # keep same filename
        dest_path = dest_slot / dest_name

        # never overwrite
        if dest_path.exists():
            dest_path = safe_dest_path(dest_slot, dest_name)

        shutil.copy2(str(src), str(dest_path))
        logger.info("Copied self script: %s -> %s", src, dest_path)
        return (True, f"Saved script into dest: {dest_path.name}")

    except Exception as e:
        logger.error("copy_self_script_into_dest failed (%s)", e)
        return (False, f"Failed to save script: {e}")

def collect_code_files(
    target: Path,
    logger: logging.Logger,
    allowed_exts: Optional[set[str]] = None,
    skip_hidden: bool = False,
) -> List[Path]:
    """
    Collect code/source files recursively under target.

    - Skips excluded folders by PRUNING traversal (fast)
    - Filters by allowed_exts (defaults to CODE_EXTS)
    - Optional: skip hidden (dot paths + Windows hidden attribute)
    """
    files: List[Path] = []
    exts = {e.lower() for e in (allowed_exts or CODE_EXTS)}
    exclude = {d.casefold() for d in EXCLUDE_DIR_NAMES}

    if not target.exists() or not target.is_dir():
        logger.warning("collect_code_files: target missing: %s", target)
        return files

    try:
        # Use os.walk so we can prune excluded dirs early (MUCH faster than rglob)
        for root, dirnames, filenames in os.walk(str(target)):
            root_path = Path(root)

            # Prune excluded dirs (and optionally hidden dirs) in-place
            kept_dirs = []
            for d in dirnames:
                if d.casefold() in exclude:
                    continue
                if skip_hidden and d.startswith("."):
                    continue
                kept_dirs.append(d)
            dirnames[:] = kept_dirs  # modifies walk traversal

            # Optional: skip if current root itself is hidden (covers deeper dot paths)
            if skip_hidden and is_hidden_path(root_path):
                continue

            for fn in filenames:
                try:
                    if skip_hidden and fn.startswith("."):
                        continue

                    p = root_path / fn

                    # Optional: skip hidden files (Windows attribute)
                    if skip_hidden and is_hidden_path(p):
                        continue

                    suf = p.suffix.lower()
                    if suf not in exts:
                        continue

                    # Ensure it's a file (symlinks / weird entries)
                    if not p.is_file():
                        continue

                    files.append(p)

                except (PermissionError, OSError):
                    continue

    except (PermissionError, OSError) as e:
        logger.error("collect_code_files failed: %s (%s)", target, e)
        return []

    files.sort(key=lambda p: natural_key(str(p)))
    return files




# ============================================================
# Change tracking for code files (NEW / UPDATED / REMOVED)
# ============================================================

FileSig = Tuple[int, float]  # (size_bytes, mtime_epoch_seconds)


def build_code_index(
    source_root: Path,
    logger: logging.Logger,
    skip_hidden: bool = False,
) -> Tuple[List[Path], Dict[str, FileSig]]:
    """
    Build an index for ALL files under source_root (not just code).

    Returns:
      files: List[Path] (all files)
      index: Dict[relative_path -> (size, mtime)]
    """
    files = collect_all_files(
        target=source_root,
        logger=logger,
        skip_hidden=skip_hidden,
    )

    index: Dict[str, FileSig] = {}
    for p in files:
        try:
            rel = str(p.relative_to(source_root))
            st = p.stat()
            index[rel] = (int(st.st_size), float(st.st_mtime))
        except Exception:
            continue

    return files, index



def auto_add_flow_logic_if_present(
    external_root: Path,
    dest_slot: Path,
    logger: logging.Logger,
) -> None:
    """
    Automatically add 'Flow Logic' folder/file into dest_slot if it exists.
    Runs silently on every Save (S).
    """
    try:
        flow_item = external_root / "Flow Logic"
        if not flow_item.exists():
            return

        ok, msg = add_item_into_dest(dest_slot, flow_item, logger)
        if ok:
            logger.info("Auto-added Flow Logic into %s", dest_slot)
        else:
            logger.warning("Flow Logic auto-add skipped: %s", msg)

    except Exception as e:
        logger.error("Flow Logic auto-add failed (%s)", e)

def rescan_external_full_for_save(
    external_root: Path,
    logger: logging.Logger,
    other_max: int,
    prev_index: Optional[Dict[str, FileSig]] = None,
    skip_hidden: bool = False,
) -> Tuple[
    List[Path],
    Dict[str, FileSig],
    Dict[int, Path],
    bool,
    List[str],
    List[str],
    List[str],
]:
    """
    FULL rescan used by the "S" key:
      - Scans external_root for ALL files (any extension)
      - Prints counts + changes (vs prev_index)
      - Prints other-items list for external_root (top-level)

    Returns:
      files, new_index, other_items_map,
      changed_any, added, updated, removed
    """
    print("=" * 72)
    print('🔄 "S" pressed → FULL re-scan before saving')
    print(f"   SOURCE: {external_root}")
    if external_root == TERRITORY_ROOT:
        print("   LABEL : TERRITORY_ROOT")
    print("   MODE  : ALL FILES (folders + csv/doc/xls/etc)")
    print("-" * 72)

    if not external_root.exists() or not external_root.is_dir():
        logger.warning("External scan target not found: %s", external_root)
        print("⚠️  SOURCE folder not found or not accessible")
        print("=" * 72)
        return ([], {}, {}, False, [], [], [])

    files, new_index = build_code_index(
        source_root=external_root,
        logger=logger,
        skip_hidden=skip_hidden,
    )

    # Counts (still show code counts + common “office” types)
    py_count = sum(1 for p in files if p.suffix.lower() == ".py")
    bat_count = sum(1 for p in files if p.suffix.lower() == ".bat")
    yaml_count = sum(1 for p in files if p.suffix.lower() in (".yaml", ".yml"))
    csv_count = sum(1 for p in files if p.suffix.lower() == ".csv")
    xlsx_count = sum(1 for p in files if p.suffix.lower() in (".xls", ".xlsx"))
    docx_count = sum(1 for p in files if p.suffix.lower() in (".doc", ".docx"))

    print(f"🐍 Python files found: {py_count}")
    print(f"🪟 BAT files found   : {bat_count}")
    print(f"🧾 YAML files found  : {yaml_count}")
    print(f"📄 CSV files found   : {csv_count}")
    print(f"📊 Excel files found : {xlsx_count}")
    print(f"📝 Word files found  : {docx_count}")
    print(f"📦 Total files found : {len(files)}")
    print("-" * 72)

    changed_any, added, updated, removed = print_code_changes(prev_index, new_index)

    print("-" * 72)
    print("📄 Files to copy: (list suppressed — summary only)")

    other_items_map = build_other_items_map(external_root, logger)
    print_other_items_numbered(other_items_map, logger=logger, max_items=other_max)

    print("=" * 72)
    return (files, new_index, other_items_map, changed_any, added, updated, removed)




def print_code_changes(
    prev_idx: Optional[Dict[str, FileSig]],
    new_idx: Dict[str, FileSig]
) -> Tuple[bool, List[str], List[str], List[str]]:
    """
    Print NEW / UPDATED / REMOVED since prev_idx.
    A file is "UPDATED" if size or mtime changed.

    Returns:
      (changed_any, added_keys, updated_keys, removed_keys)
    """
    if prev_idx is None:
        print("ℹ️  Change tracking: first scan (no previous snapshot to compare).")
        return (False, [], [], [])

    prev_keys = set(prev_idx.keys())
    new_keys = set(new_idx.keys())

    added = sorted(list(new_keys - prev_keys), key=natural_key)
    removed = sorted(list(prev_keys - new_keys), key=natural_key)

    updated: List[str] = []
    for k in sorted(list(new_keys & prev_keys), key=natural_key):
        if prev_idx.get(k) != new_idx.get(k):
            updated.append(k)

    if not added and not updated and not removed:
        print("✅ No code file changes since last scan.")
        return (False, [], [], [])

    if added:
        print("🆕 NEW files:")
        for k in added:
            print(f"   + {k}")

    if updated:
        print("✏️ UPDATED files:")
        for k in updated:
            print(f"   * {k}")

    if removed:
        print("🗑️ REMOVED files:")
        for k in removed:
            print(f"   - {k}")

    return (True, added, updated, removed)



def build_other_items_map(target: Path, logger: logging.Logger) -> Dict[int, Path]:
    """
    Numbered map of OTHER top-level items in target (folders + files that are NOT code files).
    """
    try:
        entries = [p for p in target.iterdir()]
    except Exception:
        return {}

    other: List[Path] = []
    for p in entries:
        if p.is_file() and p.suffix.lower() in CODE_EXTS:
            continue
        other.append(p)

    other.sort(key=lambda p: natural_key(p.name))
    return {i: p for i, p in enumerate(other, start=1)}


def refresh_and_print_other_items(external_root: Path, logger: logging.Logger, other_max: int) -> Dict[int, Path]:
    """
    Rebuild + reprint the 'other items' list (top-level) every time Add (A) is used.
    Returns the refreshed map.
    """
    other_map = build_other_items_map(external_root, logger)
    print_other_items_numbered(other_map, logger=logger, max_items=other_max)
    return other_map

def print_other_items_numbered(other_map: Dict[int, Path], logger: logging.Logger, max_items: int) -> None:
    print("-" * 72)
    print("📁 Other Files/Folders In Folder:")

    if not other_map:
        print("   (none)")
        return

    keys = sorted(other_map.keys())
    shown_keys = keys[:max_items]
    for k in shown_keys:
        p = other_map[k]
        if p.is_dir():
            tag = "[DIR]"
            sz = dir_size_bytes(p, logger)
            sz_str = "N/A" if sz is None else format_size(sz)
        else:
            tag = "[FILE]"
            try:
                sz_str = format_size(p.stat().st_size)
            except (PermissionError, OSError):
                sz_str = "N/A"
        print(f"   {k:>2}. {tag} {p.name}  ({sz_str})")

    remaining = len(keys) - len(shown_keys)
    if remaining > 0:
        print(f"   ...and {remaining} more (use --other-max to show more)")

def rescan_external_on_save(
    external_root: Path,
    logger: logging.Logger,
    other_max: int,
) -> Tuple[List[Path], Dict[int, Path]]:
    """
    Re-scan external folder each time user presses 'S' to Save Again.
    Returns fresh (code_files, other_items_map) and prints updated counts/lists.
    """
    return scan_external_code_folder(external_root, logger, other_max=other_max)

def scan_external_code_folder(
    target: Path,
    logger: logging.Logger,
    other_max: int,
    skip_hidden: bool = False,
) -> Tuple[List[Path], Dict[int, Path]]:
    """
    Print summary of ALL files, then numbered other items (with sizes).
    Returns (files, other_items_map).
    """
    print("=" * 72)
    print("🔍 Scanning external folder for ALL files")
    print(f"   Location: {target}")
    if target == TERRITORY_ROOT:
        print("   Label   : TERRITORY_ROOT")
    print("   Mode    : ALL FILES")
    print("-" * 72)

    if not target.exists() or not target.is_dir():
        logger.warning("External scan target not found: %s", target)
        print("⚠️  Folder not found or not accessible")
        print("=" * 72)
        return ([], {})

    files = collect_all_files(target, logger, skip_hidden=skip_hidden)

    py_count = sum(1 for p in files if p.suffix.lower() == ".py")
    bat_count = sum(1 for p in files if p.suffix.lower() == ".bat")
    yaml_count = sum(1 for p in files if p.suffix.lower() in (".yaml", ".yml"))
    csv_count = sum(1 for p in files if p.suffix.lower() == ".csv")
    xlsx_count = sum(1 for p in files if p.suffix.lower() in (".xls", ".xlsx"))
    docx_count = sum(1 for p in files if p.suffix.lower() in (".doc", ".docx"))

    print(f"🐍 Python files found: {py_count}")
    print(f"🪟 BAT files found   : {bat_count}")
    print(f"🧾 YAML files found  : {yaml_count}")
    print(f"📄 CSV files found   : {csv_count}")
    print(f"📊 Excel files found : {xlsx_count}")
    print(f"📝 Word files found  : {docx_count}")
    print(f"📦 Total files found : {len(files)}")
    print("-" * 72)
    print("📄 Files: (list suppressed — summary only)")

    other_map = build_other_items_map(target, logger)
    print_other_items_numbered(other_map, logger=logger, max_items=other_max)

    print("=" * 72)
    return (files, other_map)



# ============================================================
# Copy logic
# ============================================================

def safe_dest_path(dest_dir: Path, name: str) -> Path:
    """
    Never overwrite existing.
    If dest exists, append __ADD_01, __ADD_02, ...
    """
    candidate = dest_dir / name
    if not candidate.exists():
        return candidate

    stem = name
    suffix = ""
    # Keep extension for files
    if "." in name and not name.startswith("."):
        parts = name.rsplit(".", 1)
        stem = parts[0]
        suffix = "." + parts[1]

    for i in range(1, 1000):
        cand = dest_dir / f"{stem}__ADD_{i:02d}{suffix}"
        if not cand.exists():
            return cand

    return dest_dir / f"{stem}__ADD_{int(time.time())}{suffix}"


def copy_code_files_into(
    dest_slot: Path,
    src_root: Path,
    files: List[Path],
    logger: logging.Logger,
) -> Tuple[List[str], List[str], List[str]]:
    r"""
    Copy code files into dest_slot while preserving relative structure under src_root:

      dest_slot/<relative_path_under_src_root>

    Never overwrites existing:
      if a destination file exists, appends __ADD_## before extension.
    """
    ensure_dir(dest_slot)

    copied: List[str] = []
    missing: List[str] = []
    failed: List[str] = []

    for f in files:
        try:
            if not f.exists():
                missing.append(str(f))
                continue

            # Preserve relative structure under src_root
            try:
                rel = f.relative_to(src_root)
            except Exception:
                # Fallback: if something weird slips in, store it flat
                rel = Path(f.name)

            dest_path = dest_slot / rel
            ensure_dir(dest_path.parent)

            # Never overwrite: apply __ADD_## if exists
            if dest_path.exists():
                dest_path = safe_dest_path(dest_path.parent, dest_path.name)

            shutil.copy2(str(f), str(dest_path))
            copied.append(str(rel))

        except Exception as e:
            logger.error("Copy failed: %s -> %s (%s)", f, dest_slot, e)
            failed.append(str(f))

    return copied, missing, failed




def add_item_into_dest(dest_slot: Path, item: Path, logger: logging.Logger) -> Tuple[bool, str]:
    """
    Add a top-level external item (file or directory) into dest_slot.
    Never overwrites existing; uses __ADD_## name if needed.
    Returns (ok, message).
    """
    try:
        if not item.exists():
            return (False, "Source item no longer exists.")

        if item.is_dir():
            dest = safe_dest_path(dest_slot, item.name)
            shutil.copytree(str(item), str(dest), dirs_exist_ok=False)
            return (True, f"Added folder: {item.name} -> {dest.name}")

        dest = safe_dest_path(dest_slot, item.name)
        shutil.copy2(str(item), str(dest))
        return (True, f"Added file: {item.name} -> {dest.name}")
    except Exception as e:
        logger.error("Add item failed: %s -> %s (%s)", item, dest_slot, e)
        return (False, f"Failed to add: {e}")


def prompt_action() -> str:
    """
    Menu prompt that NEVER exits.
    - Valid: S / A / R
    - Blank/Enter: Continue (returns "C")
    """
    try:
        y = COLOR_BRIGHT_YELLOW
        r = COLOR_RESET

        while True:
            print()
            print(f'Press {y}"S"{r} to {y}Save{r} Again')
            print(f'Press {y}"A"{r} to {y}Add{r} Files/Folders')
            print(f'Press {y}"R"{r} to {y}Rename{r} Subfolder')
            print(f'Press {y}Enter{r} to {y}Continue{r}')
            print()

            resp = input("> ").strip().upper()

            if resp in ("S", "A", "R"):
                return resp

            if resp == "":
                return "C"

            print("❌ Invalid option. Please try again.")

    except KeyboardInterrupt:
        return "C"



def rescan_external_counts_only(
    external_root: Path,
    logger: logging.Logger,
    prev_index: Optional[Dict[str, FileSig]] = None,
    skip_hidden: bool = False,
) -> Tuple[List[Path], Dict[str, FileSig]]:
    """
    Re-scan external_root and print counts + changes since prev_index.
    Returns:
      (code_files, new_index)
    """
    print("=" * 72)
    print("🔄 Re-scanning source root (counts + changes)")
    print(f"   SOURCE: {external_root}")
    print("-" * 72)

    if not external_root.exists() or not external_root.is_dir():
        logger.warning("External scan target not found: %s", external_root)
        print("⚠️  SOURCE folder not found or not accessible")
        print("=" * 72)
        return ([], {})

    code_files, new_index = build_code_index(
        source_root=external_root,
        logger=logger,
        skip_hidden=skip_hidden,
    )

    py_count = sum(1 for p in code_files if p.suffix.lower() == ".py")
    bat_count = sum(1 for p in code_files if p.suffix.lower() == ".bat")
    yaml_count = sum(1 for p in code_files if p.suffix.lower() in (".yaml", ".yml"))

    print(f"🐍 Python files found: {py_count}")
    print(f"🪟 BAT files found   : {bat_count}")
    print(f"🧾 YAML files found  : {yaml_count}")
    print(f"📦 Total source files: {len(code_files)}")
    print("-" * 72)

    _changed_any, _added, _updated, _removed = print_code_changes(prev_index, new_index)

    print("=" * 72)
    return (code_files, new_index)



def prompt_add_choice(other_map: Dict[int, Path]) -> int | None:
    """
    Ask user for an item number.
    Returns:
      - int: selected item number
      - None: cancel
    """
    try:
        while True:
            resp = input("Enter item number to add (or blank to cancel): ").strip()
            if resp == "":
                return None
            if not resp.isdigit():
                print("❌ Please enter a number.")
                continue

            choice = int(resp)
            if choice not in other_map:
                print("❌ That number doesn’t exist. Try again.")
                continue

            return choice
    except KeyboardInterrupt:
        return None



# ============================================================
# MAIN
# ============================================================

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=str, default="")
    ap.add_argument(
        "--skip-hidden",
        action="store_true",
        help="Skip hidden files/folders (dot paths and Windows hidden attribute).",
    )

    ap.add_argument(
        "--subs-per-backup",
        type=int,
        default=200,
        help="How many Sub_### folders to ensure per Backup folder (default: 200).",
    )

    ap.add_argument(
        "--max-backups",
        type=int,
        default=5,
        help="Maximum number of Backup_### folders to use before recycling (default: 5).",
    )
    ap.add_argument(
        "--other-max",
        type=int,
        default=50,
        help="How many 'other' top-level items to show in the external folder list (default: 50).",
    )

    args = ap.parse_args()

    if args.subs_per_backup < 1 or args.subs_per_backup > 999:
        print("ERROR: --subs-per-backup must be between 1 and 999")
        return 2
    if args.other_max < 1:
        print("ERROR: --other-max must be >= 1")
        return 2
    if args.max_backups < 1 or args.max_backups > 999:
        print("ERROR: --max-backups must be between 1 and 999")
        return 2

    script_dir = Path(__file__).resolve().parent
    root = Path(args.root).expanduser().resolve() if args.root else script_dir

    logger = setup_logging(root)
    start_time = time.perf_counter()

    if not root.exists() or not root.is_dir():
        logger.error("Root not found or not a directory: %s", root)
        return 2

    # ✅ SINGLE source root (Territory Assistant)
    external_root = TERRITORY_ROOT

    # Change tracking state (persists across S presses)
    prev_code_index: Optional[Dict[str, FileSig]] = None

    # Initial FULL scan (same behavior as pressing "S")
    code_files, code_index, other_items_map, changed_any, added, updated, removed = rescan_external_full_for_save(
        external_root=external_root,
        logger=logger,
        other_max=args.other_max,
        prev_index=prev_code_index,
        skip_hidden=args.skip_hidden,
    )

    prev_code_index = code_index
    last_scan_changed_any = changed_any
    last_scan_added = added
    last_scan_updated = updated
    last_scan_removed = removed

    # -----------------------------
    # MAIN folders = Backup_### only (Ring + Recycle)
    # -----------------------------
    ring = get_backup_ring(
        root=root,
        max_backups=args.max_backups,
        subs_per_backup=args.subs_per_backup,
        logger=logger,
    )

    def _bn(p: Path) -> int:
        n = parse_backup_num(p.name)
        return n if n is not None else -1

    cur_main = max(ring, key=_bn)

    if find_next_empty_slot(cur_main, logger) is None:
        cur_main = find_or_rotate_next_backup(
            root=root,
            current_backup=cur_main,
            max_backups=args.max_backups,
            subs_per_backup=args.subs_per_backup,
            logger=logger,
        )

    next_empty = find_next_empty_slot(cur_main, logger)
    if next_empty is None:
        cur_main = find_or_rotate_next_backup(
            root=root,
            current_backup=cur_main,
            max_backups=args.max_backups,
            subs_per_backup=args.subs_per_backup,
            logger=logger,
        )
        next_empty = find_next_empty_slot(cur_main, logger)

    if next_empty is None:
        logger.error("No available Sub_### slot even after rotate/recycle. Check permissions.")
        return 2

    current_slot_name = next_empty.name

    print("-" * 72)
    print(f"🟨 Starting in: {COLOR_BRIGHT_YELLOW}{cur_main.name}{COLOR_RESET}")
    print(f"   Next Empty Sub-Folder: {COLOR_BRIGHT_YELLOW}{current_slot_name}{COLOR_RESET}")
    print("-" * 72)

    if not code_files:
        print("ℹ️ No code files found to copy (source folder empty or inaccessible).")
        print("-" * 72)

    last_dest_slot: Optional[Path] = None

    while True:
        if not code_files:
            action = prompt_action()
            if action == "S":
                code_files, code_index, other_items_map, changed_any, added, updated, removed = rescan_external_full_for_save(
                    external_root=external_root,
                    logger=logger,
                    other_max=args.other_max,
                    prev_index=prev_code_index,
                    skip_hidden=args.skip_hidden,
                )
                prev_code_index = code_index
                last_scan_changed_any = changed_any
                last_scan_added = added
                last_scan_updated = updated
                last_scan_removed = removed
            continue

        dest_slot = find_next_empty_slot_from(cur_main, current_slot_name, logger)

        if dest_slot is None:
            cur_main = find_or_rotate_next_backup(
                root=root,
                current_backup=cur_main,
                max_backups=args.max_backups,
                subs_per_backup=args.subs_per_backup,
                logger=logger,
            )
            current_slot_name = "Sub_001"
            print(f"➡️  Backup FULL. Switching to: {COLOR_BRIGHT_YELLOW}{cur_main.name}{COLOR_RESET}")
            print(f"   Restarting at: {COLOR_BRIGHT_YELLOW}{current_slot_name}{COLOR_RESET}")
            print("-" * 72)
            continue

        # 1) COPY CODE FILES into empty dest_slot (single-root preserve structure)
        copied, missing, failed = copy_code_files_into(dest_slot, external_root, code_files, logger)

        ok_self, msg_self = copy_self_script_into_dest(dest_slot, logger)
        if ok_self:
            print(f"🧾 {msg_self}")
        else:
            print(f"⚠️ {msg_self}")

        # AUTO-ADD: Flow Logic (if present)
        auto_add_flow_logic_if_present(
            external_root=external_root,
            dest_slot=dest_slot,
            logger=logger,
        )

        print(f"📥 Copy destination: {COLOR_BRIGHT_YELLOW}{dest_slot}{COLOR_RESET}")

        expected = len(code_files)
        if len(copied) == expected and not missing and not failed:
            print(f"✅ All code files copied (structure preserved) ({len(copied)}/{expected})")
        else:
            print(f"⚠️ Code copy summary: copied={len(copied)}/{expected}  missing={len(missing)}  failed={len(failed)}")
            if missing:
                print("   ❗ Missing files (not found at copy time):")
                for x in missing:
                    print(f"      - {x}")
            if failed:
                print("   ❌ Failed copies:")
                for x in failed:
                    print(f"      - {x}")

        try:
            if last_scan_changed_any:
                suffix = build_change_suffix(
                    last_scan_added,
                    last_scan_updated,
                    last_scan_removed,
                    max_names=2,
                )
                ok, msg, new_path = rename_subfolder_append_suffix(dest_slot, suffix, logger)
                if ok:
                    last_dest_slot = new_path
                else:
                    print("-" * 72)
                    print(f"⚠️  Auto-rename failed: {msg}")
                    print("   Keeping folder name unchanged (no suffix).")
                    print("-" * 72)
                    last_dest_slot = dest_slot
            else:
                last_dest_slot = ensure_default_suffix_on_subfolder(dest_slot, logger)
        except Exception as e:
            logger.warning("Auto-rename with change suffix failed (%s)", e)
            last_dest_slot = dest_slot

        open_sub_folder_exclusive(last_dest_slot, logger)

        dn = parse_sub_num(dest_slot.name)
        current_slot_name = next_sub_name_from(dn + 1) if dn is not None else current_slot_name

        # 2) MENU LOOP (S/A/R/C) — NO PAUSES, NEVER EXIT
        while True:
            action = prompt_action()

            if action == "S":
                code_files, code_index, other_items_map, changed_any, added, updated, removed = rescan_external_full_for_save(
                    external_root=external_root,
                    logger=logger,
                    other_max=args.other_max,
                    prev_index=prev_code_index,
                    skip_hidden=args.skip_hidden,
                )
                prev_code_index = code_index
                last_scan_changed_any = changed_any
                last_scan_added = added
                last_scan_updated = updated
                last_scan_removed = removed

                if not code_files:
                    print("ℹ️ No code files found on re-scan.")
                    continue

                break  # go save into next Sub_### (immediately)

            if action == "A":
                if last_dest_slot is None or is_dir_empty_recursive(last_dest_slot, logger):
                    print("❌ Add is only allowed after you have saved once.")
                    continue

                other_items_map = refresh_and_print_other_items(
                    external_root, logger, other_max=args.other_max
                )

                if not other_items_map:
                    print("❌ No 'other items' available to add.")
                    continue

                while True:
                    choice = prompt_add_choice(other_items_map)
                    if choice is None:
                        break

                    item = other_items_map[choice]
                    ok, msg = add_item_into_dest(last_dest_slot, item, logger)
                    print(("✅ " if ok else "❌ ") + msg)

                    other_items_map = refresh_and_print_other_items(
                        external_root, logger, other_max=args.other_max
                    )

                    if ok:
                        open_sub_folder_exclusive(last_dest_slot, logger)

                continue

            if action == "R":
                if last_dest_slot is None or is_dir_empty_recursive(last_dest_slot, logger):
                    print("❌ Rename is only allowed after you have saved once.")
                    continue

                while True:
                    suffix = prompt_rename_choice(RENAME_SUFFIX_OPTIONS)
                    if suffix is None:
                        break

                    ok, msg, new_path = rename_subfolder_append_suffix(last_dest_slot, suffix, logger)
                    print(("✅ " if ok else "❌ ") + msg)
                    if ok:
                        last_dest_slot = new_path
                        open_sub_folder_exclusive(last_dest_slot, logger)
                        break

                    print("❌ Rename failed. Pick another suffix (or cancel).")

                continue

            if action == "C":
                continue

    total = time.perf_counter() - start_time
    logger.info("Scan complete in %.3f seconds", total)
    return 0





if __name__ == "__main__":
    raise SystemExit(main())
