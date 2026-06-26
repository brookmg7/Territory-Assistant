"""
# Python Expert
Other_Functions.py — utilities for Export / Cleanup / Cache

This module hosts the four "Other" tools that used to live in Territory_Assistant.py:
  9) Export Script/Log Into Sections
 10) Remove All Output Files
 11) Remove All Files In 'New_Addresses_By_Suburb' Folder
 12) Delete 'geocode_cache.json' File

It exposes a small sub‑menu via `open_menu()` so Territory_Assistant can call it.
All functions are self‑contained and avoid depending on globals from the main app.
"""
from __future__ import annotations

import os
import re
import csv
import sys
from typing import Iterable, List, Tuple


# Folder for Option 2 (JavaScript/HTML export)
JS_HTML_DIR = r"C:\script\JavaScript HTML"

# Header for Option 2
APP_SCRIPT_HEADER_HINT = (
    "#App Script Expert- Here's my script in different parts, please read as one file. "
    "Give suggestions after you recieved all the parts\n"
)



# Fixed folder for Option 2 (no prompt)
BACKUP_CSV_DIR = r"C:\script\Backup CSV Files"


# Header placed at the very top of each split file
SPLIT_HEADER_HINT = "#Python Expert - Here's my script in different parts, please read as one file. Give suggestions after you recieved all the parts\n"


# Suggestion threshold for advising parts (can override via env)
SPLIT_HINT_LINES = int(os.environ.get("SPLIT_HINT_LINES", "2500"))

# ---------------------------
# Constants (kept local)
# ---------------------------
OUTPUT_FILES = [
    "output_clean.csv",
    "output_fail.csv",
    "corrections_log.csv",
    "corrections_log_grouped.csv",
]

SUBURB_DIR = "New_Addresses_By_Suburb"
DEFAULT_EXPORT_DIR = "Exported Files"

# ---------------------------
# Helpers (safe, no globals)
# ---------------------------

def option_2_split_js_html() -> None:
    """Menu handler for option 2: choose a JS/HTML file in JS_HTML_DIR, show stats, choose N, split."""
    chosen = _choose_script_file_jshtml(JS_HTML_DIR)
    if not chosen:
        return

    # Count lines and report (same UX as option 1)
    try:
        total_lines = 0
        with open(chosen, "r", encoding="utf-8", errors="replace") as f:
            for _ in f:
                total_lines += 1
    except Exception as e:
        print(f"❌ Could not read '{chosen}': {e}")
        return

    _hint = SPLIT_HINT_LINES if isinstance(SPLIT_HINT_LINES, int) and SPLIT_HINT_LINES > 0 else 2000
    if total_lines > _hint:
        quotient = total_lines / float(_hint)
        suggested_parts = (total_lines + _hint - 1) // _hint
        print(f"\nℹ️ File: '{Path(chosen).name}' has {total_lines} line(s).")
        print(f"   {total_lines} / {_hint} = {quotient:.2f}  → Suggested parts ≈ {suggested_parts}")
    else:
        print(f"\nℹ️ File: '{Path(chosen).name}' has {total_lines} line(s) (≤ {_hint}).")

    default = max(2, int(suggested_parts)) if total_lines > _hint else 2
    num_parts_str = (input(f"Into how many parts should I split it? (integer ≥ 2) [{default}]: ") or "").strip()
    num_parts = default if num_parts_str == "" else (int(num_parts_str) if num_parts_str.isdigit() else 0)
    if num_parts < 2:
        print("❌ Invalid number of parts.")
        return

    split_script_evenly(chosen, num_parts, out_dir=DEFAULT_EXPORT_DIR, header_hint=APP_SCRIPT_HEADER_HINT)


def _choose_script_file_jshtml(folder: str = JS_HTML_DIR) -> str | None:
    """
    Let the user pick a .js or .html file from the JS/HTML folder.
    Returns the absolute path, or None if cancelled.
    """
    root = Path(folder)
    if not root.exists():
        print(f"❌ Folder not found: {root}")
        return None

    files = sorted([p for p in root.iterdir()
                    if p.is_file() and p.suffix.lower() in {".js", ".html"}])

    if not files:
        print(f"ℹ️ No .js or .html files found in '{root}'.")
        return None

    print("\n📂 Available JavaScript/HTML files:")
    for idx, p in enumerate(files, 1):
        print(f"  {idx}) {p.name}")

    choice = (input(f"Choose a file to split (1-{len(files)}): ") or "").strip()
    if not choice.isdigit() or not (1 <= int(choice) <= len(files)):
        print("❌ Invalid choice.")
        return None

    chosen = files[int(choice) - 1]
    confirm = (input(f"Confirm split of '{chosen.name}'? (y/N): ") or "").strip().lower()
    if confirm != "y":
        print("❌ Cancelled.")
        return None

    return str(chosen.resolve())


def _safe_title(s: str) -> str:
    try:
        return str(s or "").strip().title()
    except Exception:
        return str(s or "").strip()

# Prefer to export parts from the core NWS script
CORE_SCRIPT = "Clean_NewWorldScheduler.py"

def _preferred_script_path(script_path: str | None) -> str:
    """
    Decide which source file to split into Part 1..4 for the export tool.
    Priority:
      1) explicit script_path argument (if given)
      2) Clean_NewWorldScheduler.py in the same folder as this module
      3) Menu.py (as a fallback if you want to export the master menu instead)
      4) sys.argv[0] (whatever was executed)
    """
    if script_path:
        return script_path

    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, CORE_SCRIPT),   # <— your new core file
        os.path.join(here, "Menu.py"),
        sys.argv[0] if sys.argv and sys.argv[0] else "",
    ]
    for p in candidates:
        if p and os.path.exists(p):
            return p
    # final fallback (may not exist; caller will print a friendly error)
    return os.path.join(here, CORE_SCRIPT)


from pathlib import Path

def backup_csv_files(
    folder: str = "Backup CSV Files",
    status_col_name: str = "Status",
    from_value: str = "Home",
    to_value: str = "At Home",
) -> None:
    """
    For every CSV in `folder`, replace Status=='Home' with 'At Home' and
    write a new file named '<Original Base> (Updated).csv' in the same folder.
    - Leaves originals untouched
    - Skips files already ending in ' (Updated).csv'
    - Tries to preserve CSV dialect (delimiter/quote)
    """

    root = Path(folder)
    if not root.exists():
        print(f"ℹ️ Folder not found: {root}")
        return

    csv_files = sorted(p for p in root.iterdir()
                       if p.is_file() and p.suffix.lower() == ".csv")

    if not csv_files:
        print(f"ℹ️ No CSV files found in '{root}'.")
        return

    changed_total = 0
    written_total = 0

    for src in csv_files:
        # Skip files already marked as updated
        if src.stem.endswith(" (Updated)"):
            print(f"↪ Skipping already updated file: {src.name}")
            continue

        try:
            # Read a small sample to sniff dialect
            sample_bytes = src.read_bytes()[:4096]
            sample = sample_bytes.decode("utf-8-sig", errors="replace")

            # Default dialect fallback
            dialect = csv.excel
            try:
                sniffer = csv.Sniffer()
                sniffed = sniffer.sniff(sample)
                # Be conservative: only accept sniff if it found a delimiter
                if getattr(sniffed, "delimiter", None):
                    dialect = sniffed
            except Exception:
                pass

            # Now open with utf-8-sig to transparently handle BOM
            with src.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.reader(f, dialect)
                rows = list(reader)

            if not rows:
                print(f"⚠️ Empty CSV — no output written: {src.name}")
                continue

            header = rows[0]
            data = rows[1:]

            # Case-insensitive match for 'Status' header
            idx = None
            for i, col in enumerate(header):
                if str(col).strip().lower() == status_col_name.lower():
                    idx = i
                    break

            if idx is None:
                print(f"ℹ️ No '{status_col_name}' column — unchanged: {src.name}")
                continue

            # Transform rows
            updated_rows = 0
            for r in data:
                # Ensure row has enough columns
                if idx < len(r) and r[idx].strip() == from_value:
                    r[idx] = to_value
                    updated_rows += 1

            if updated_rows == 0:
                print(f"ℹ️ No rows with {status_col_name}='{from_value}' in {src.name}")
                continue

            # Destination path
            dst = src.with_name(f"{src.stem} (Updated){src.suffix}")
            # Avoid accidental overwrite
            if dst.exists():
                n = 2
                while True:
                    candidate = src.with_name(f"{src.stem} (Updated {n}){src.suffix}")
                    if not candidate.exists():
                        dst = candidate
                        break
                    n += 1

            # Write using the same dialect
            with dst.open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f, dialect)
                writer.writerow(header)
                writer.writerows(data)

            print(f"✅ Wrote {dst.name}  — {updated_rows} row(s) changed")
            changed_total += updated_rows
            written_total += 1

        except Exception as e:
            print(f"❌ Failed on '{src.name}': {e}")

    if written_total:
        print(f"\n📦 Done. Created {written_total} updated file(s); "
              f"{changed_total} total row(s) modified to '{to_value}'.")
    else:
        print("\nℹ️ No updated files were created.")



def remove_files(paths: Iterable[str]) -> None:
    """Delete the given file paths if they exist (prints a short report)."""
    if not paths:
        print("ℹ️ No files specified.")
        return
    removed, failed, missing = [], [], []
    for p in paths:
        if os.path.exists(p):
            try:
                os.remove(p)
                removed.append(p)
            except Exception as e:
                failed.append((p, str(e)))
        else:
            missing.append(p)
    if removed:
        print("✅ Deleted file(s):")
        for p in removed:
            print(f"   • {p}")
    if failed:
        print("❌ Could not remove:")
        for p, err in failed:
            print(f"   • {p} — {err}")
    if missing and not removed and not failed:
        print("ℹ️ Nothing to delete (no matching files found).")


def remove_files_in_folder(folder: str) -> None:
    """Delete only files (not subfolders) inside a folder."""
    if not os.path.exists(folder):
        print(f"ℹ️ Folder not found: {folder}")
        return
    removed, failed = [], []
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            try:
                os.remove(path)
                removed.append(name)
            except Exception as e:
                failed.append((name, str(e)))
    if removed:
        print(f"✅ Deleted {len(removed)} file(s) inside '{folder}':")
        for n in removed:
            print(f"   • {n}")
    if failed:
        print("❌ Some files could not be deleted:")
        for n, err in failed:
            print(f"   • {n} — {err}")


# ---------------------------
# Export: split script into parts + logs bundle
# ---------------------------

def export_script_parts(script_path: str | None = None,
                        out_dir: str = DEFAULT_EXPORT_DIR,
                        min_lines_per_part: int = 30,
                        min_nonblank_per_part: int = 5) -> None:
    """
    Export the source script into Part 1.py .. Part 4.py using 1/4..4/4 markers only.
    - Does NOT modify the source file.
    - Deletes prior Part*.py in out_dir, then writes fresh ones.
    - Skips a part if its marker block is missing/too small.
    """
    # 🔁 choose default source file intelligently (now prefers Clean_NewWorldScheduler.py)
    script_path = _preferred_script_path(script_path)

    PART_PATTERNS: List[Tuple[str, re.Pattern, re.Pattern]] = [
        ("Part 1.py",
         re.compile(r"^\s*#\s*📌\s*Part\s*1/4\s*Start\s*$"),
         re.compile(r"^\s*#\s*📌\s*Part\s*1/4\s*End\s*$")),
        ("Part 2.py",
         re.compile(r"^\s*#\s*📌\s*Part\s*2/4\s*Start\s*$"),
         re.compile(r"^\s*#\s*📌\s*Part\s*2/4\s*End\s*$")),
        ("Part 3.py",
         re.compile(r"^\s*#\s*📌\s*Part\s*3/4\s*Start\s*$"),
         re.compile(r"^\s*#\s*📌\s*Part\s*3/4\s*End\s*$")),
        ("Part 4.py",
         re.compile(r"^\s*#\s*📌\s*Part\s*4/4\s*Start\s*$"),
         re.compile(r"^\s*#\s*📌\s*Part\s*4/4\s*End\s*$")),
    ]

    if not os.path.exists(script_path):
        print(f"❌ Script not found: {script_path}")
        return

    os.makedirs(out_dir, exist_ok=True)

    # Remove old Part*.py in the export folder only
    for p in [os.path.join(out_dir, x) for x in ("Part 1.py","Part 2.py","Part 3.py","Part 4.py")]:
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception as e:
            print(f"⚠️ Could not delete {p}: {e}")

    with open(script_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines(keepends=True)

    def _find_blocks(rx_start: re.Pattern, rx_end: re.Pattern) -> List[Tuple[int,int]]:
        starts = [i for i, ln in enumerate(lines) if rx_start.match(ln)]
        ends   = [i for i, ln in enumerate(lines) if rx_end.match(ln)]
        pairs: List[Tuple[int,int]] = []
        for s in starts:
            following = [e for e in ends if e > s]
            if following:
                pairs.append((s, min(following)))
        return pairs

    made = 0
    for out_name, rx_start, rx_end in PART_PATTERNS:
        blocks = _find_blocks(rx_start, rx_end)
        if not blocks:
            print(f"⚠️ {out_name}: markers not found — skipping.")
            continue
        # choose the largest block if duplicates exist
        s, e = max(blocks, key=lambda p: p[1] - p[0])
        block = lines[s:e+1]
        non_blank = [ln for ln in block if ln.strip()]
        if len(non_blank) < min_nonblank_per_part or len(block) < min_lines_per_part:
            print(f"⚠️ {out_name}: too small ({len(non_blank)} non-blank, {len(block)} total) — skipping.")
            continue

        dst_path = os.path.join(out_dir, out_name)
        with open(dst_path, "w", encoding="utf-8") as out:
            out.writelines(block)
        print(f"✅ Created {dst_path} — {len(block)} lines.")
        made += 1

    if made == 0:
        print("ℹ️ No parts were exported. Ensure 1/4..4/4 markers exist.")



def export_bundle_after_parts(out_dir: str = DEFAULT_EXPORT_DIR,
                              max_lines_per_file: int = 1000) -> None:
    """
    Prepares export folder and writes only logs (Log*.csv) inside.
    - Splits corrections_log.csv into chunks of at most `max_lines_per_file` lines.
    """
    os.makedirs(out_dir, exist_ok=True)

    # Clean only logs in export dir (leave Part*.py for export_script_parts)
    for f in os.listdir(out_dir):
        if f.lower().startswith("log") and f.lower().endswith(".csv"):
            try:
                os.remove(os.path.join(out_dir, f))
            except Exception as e:
                print(f"⚠️ Could not delete {f}: {e}")

    created: List[Tuple[str,int]] = []
    log_src = "corrections_log.csv"

    if not os.path.exists(log_src):
        print("⚠️ corrections_log.csv not found — skipping log splitting.")
    else:
        try:
            with open(log_src, "r", encoding="utf-8", newline="") as f:
                rows = list(csv.reader(f))
        except Exception as e:
            print(f"❌ Failed to read '{log_src}': {e}")
            rows = []

        if not rows:
            print("ℹ️ corrections_log.csv is empty — no logs to export.")
        else:
            header, data = rows[0], rows[1:]
            chunk_size = max(1, max_lines_per_file - 1)
            if not data:
                out_path = os.path.join(out_dir, "Log1.csv")
                with open(out_path, "w", encoding="utf-8", newline="") as out:
                    csv.writer(out).writerow(header)
                created.append(("Log1.csv", 1))
            else:
                for idx in range(0, len(data), chunk_size):
                    out_name = f"Log{(idx // chunk_size) + 1}.csv"
                    out_path = os.path.join(out_dir, out_name)
                    with open(out_path, "w", encoding="utf-8", newline="") as out:
                        w = csv.writer(out)
                        w.writerow(header)
                        w.writerows(data[idx:idx + chunk_size])
                    created.append((out_name, 1 + len(data[idx:idx + chunk_size])))

    if created:
        print(f"\n✅ Export complete. Files in '{out_dir}':")
        for name, line_count in created:
            print(f"   • {name} — {line_count} line(s)")
    else:
        print("\nℹ️ Nothing was exported (no logs found).")


def print_created_files(export_dir: str = DEFAULT_EXPORT_DIR) -> None:
    """List the files in the export directory in a friendly way."""
    if not os.path.exists(export_dir):
        print(f"ℹ️ Export directory not found: {export_dir}")
        return
    files = sorted([f for f in os.listdir(export_dir) if f.strip()])
    if not files:
        print(f"ℹ️ No files in '{export_dir}'.")
        return
    print(f"\n📦 Files in '{export_dir}':")
    for f in files:
        print(f"   • {f}")


def export_script_and_logs(script_path: str | None = None,
                           out_dir: str = DEFAULT_EXPORT_DIR,
                           max_lines_per_file: int = 1000) -> None:
    """Convenience wrapper for menu option 9."""
    export_script_parts(script_path=script_path, out_dir=out_dir)
    export_bundle_after_parts(out_dir=out_dir, max_lines_per_file=max_lines_per_file)
    print_created_files(out_dir)


# ---------------------------
# Cache deletion (option 12)
# ---------------------------

def prompt_delete_cache(exit_after: bool = False, cache_path: str | None = None) -> None:
    """
    Ask to delete geocode_cache.json (default path is CWD). If `exit_after` is True,
    `sys.exit()` after the operation (handy when called as a standalone tool).
    """
    if cache_path is None:
        cache_path = os.path.join(os.getcwd(), "geocode_cache.json")

    confirm = input(f"⚠️ Are you sure you want to delete '{os.path.basename(cache_path)}'? (y/N): ").strip().lower()
    if confirm != "y":
        print("❌ Cancelled — cache file not deleted.")
        return

    if os.path.exists(cache_path):
        try:
            os.remove(cache_path)
            print(f"✅ Deleted '{os.path.basename(cache_path)}'")
        except Exception as e:
            print(f"❌ Failed to delete '{os.path.basename(cache_path)}': {e}")
    else:
        print("⚠️ Cache file not found.")

    if exit_after:
        print("👋 Exiting after cache deletion...")
        sys.exit()


def _module_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))

def _resolve_in_module_dir(name: str) -> str:
    p = os.path.join(_module_dir(), name)
    return p if os.path.exists(p) else name  # fall back if user runs from that dir

def _discover_scripts(extra: list[str] | None = None) -> list[str]:
    """
    Discover candidate scripts to split:
      • Start with a curated shortlist (your existing 5)
      • Add any *.py in this module's directory
      • Ignore files that look like copies or numbered variants (e.g., 'Foo copy.py', 'Foo (1).py', 'Foo 2.py')
      • Merge + de-duplicate while preserving order (case-insensitive)
    """
    curated = [
        "Clean_GoogleSheets.py",
        "Clean_NewWorldScheduler.py",
        "GeoPackage_Borders.py",
        "Finding_New_Addresses.py",
        "Other_Functions.py",
    ]
    if extra:
        curated.extend(extra)

    def _is_ignored(filename: str) -> bool:
        # ignore hidden/temp
        if filename.startswith((".", "~")):
            return True
        stem, _ = os.path.splitext(filename)
        s_low = stem.lower()
        if "copy" in s_low:
            return True
        # ignore isolated numbers like " (1)", " 2", "-3", "_4", or trailing/leading numeric tokens
        # (but not numbers inside words like "python3x" unless separated by delimiter/space/parens)
        return bool(re.search(r'(^|\s|[-_()\[\]])\d+($|\s|[-_()\[\]])', stem))

    here = _module_dir()
    try:
        found = [
            f for f in os.listdir(here)
            if f.lower().endswith(".py")
            and not _is_ignored(f)
        ]
    except Exception:
        found = []

    # Merge curated + discovered (case-insensitive de-dupe, preserve first occurrence)
    seen_ci, merged = set(), []
    for name in curated + sorted(found, key=str.lower):
        key = name.lower()
        if key not in seen_ci:
            seen_ci.add(key)
            merged.append(name)
    return merged



def _choose_script_file() -> str | None:
    """Interactive chooser that lists all .py scripts immediately (no filter prompt)."""
    # Optional: let users seed extra names via env (semicolon-separated)
    extra = os.environ.get("OTHER_TOOLS_EXTRA_SCRIPTS", "")
    extra_list = [x.strip() for x in extra.split(";") if x.strip()] if extra else []

    scripts = _discover_scripts(extra_list)
    if not scripts:
        print("ℹ️ No Python files found to choose from.")
        return None

    # 👇 Removed filter prompt — just show everything right away
    view = scripts

    print("\n📂 Available scripts:")
    for idx, s in enumerate(view, 1):
        print(f"  {idx}) {s}")
    print(f"  0) Enter a custom path…")

    choice = (input(f"Choose a script to split (0-{len(view)}): ") or "").strip()
    if not choice.isdigit():
        print("❌ Invalid choice.")
        return None

    num = int(choice)
    if num == 0:
        custom = (input("Enter a full or relative path to a script: ") or "").strip()
        if not custom:
            print("❌ No path entered.")
            return None
        chosen = _resolve_in_module_dir(custom)
    elif 1 <= num <= len(view):
        chosen = _resolve_in_module_dir(view[num - 1])
    else:
        print("❌ Choice out of range.")
        return None

    confirm = (input(f"Confirm split of '{os.path.basename(chosen)}'? (y/N): ") or "").strip().lower()
    if confirm != "y":
        print("❌ Cancelled.")
        return None
    return chosen



def _find_split_points(lines: list[str], num_parts: int) -> list[int]:
    """
    Decide where to split, avoiding inside a function.
    Returns list of split indices (not including 0 and len(lines)).
    """
    total = len(lines)
    approx = total // num_parts
    split_points = []

    for i in range(1, num_parts):
        target = i * approx
        # search near target for a 'def ' line
        offset = 0
        found = None
        while offset < 20 and not found:
            # try forward
            if target + offset < total and lines[target + offset].lstrip().startswith("def "):
                found = target + offset
                break
            # try backward
            if target - offset > 0 and lines[target - offset].lstrip().startswith("def "):
                found = target - offset
                break
            offset += 1
        if found:
            split_points.append(found)
        else:
            split_points.append(target)
    return split_points


def split_script_evenly(script_path: str, num_parts: int,
                        out_dir: str = DEFAULT_EXPORT_DIR,
                        header_hint: str | None = None,
                        out_ext: str | None = None) -> None:
    """
    Split script_path evenly into num_parts parts without cutting in the middle of a function when possible.
    Writes files named: '<BaseName> - Part k<ext>' inside out_dir (ext defaults to the source file's extension).
    Prints a summary with original total lines, per-part lines, sum, and (sum - original).
    Also writes a summary file called 'Split Script' in the same folder as the source script.

    New:
      • Part 1 can include a custom hint header (header_hint). If None, uses SPLIT_HEADER_HINT.
      • Output extension preserves the source file's extension by default (override with out_ext).
      • Console/report 'Difference' compares CONTENT ONLY (excludes the header + markers).
      • Removed duplicated report write block.
    """
    if num_parts < 2:
        print("❌ Number of parts must be at least 2.")
        return

    if not os.path.exists(script_path):
        print(f"❌ Script not found: {script_path}")
        return

    with open(script_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines(keepends=True)

    total = len(lines)
    if total == 0:
        print("ℹ️ File is empty — nothing to split.")
        return

    os.makedirs(out_dir, exist_ok=True)

    base_name, src_ext = os.path.splitext(os.path.basename(script_path))
    ext = out_ext if (isinstance(out_ext, str) and out_ext.startswith(".")) else (src_ext or ".txt")

    # ---- Pre-flight: detect old split files for THIS base_name ----
    deleted_before_split: List[str] = []
    try:
        existing = []
        for fname in os.listdir(out_dir):
            if not fname.lower().endswith(ext.lower()):
                continue
            if not fname.startswith(f"{base_name} - Part "):
                continue
            if re.match(rf'^{re.escape(base_name)} - Part \d+{re.escape(ext)}$', fname):
                existing.append(fname)

        if existing:
            print("\n⚠️ Found existing split files in export folder:")
            for f_ in sorted(existing):
                print(f"   • {f_}")
            ans = (input("Proceeding will delete the above files. Delete and continue? (y/N): ") or "").strip().lower()
            if ans == "y":
                failed = []
                for f_ in sorted(existing):
                    try:
                        os.remove(os.path.join(out_dir, f_))
                        deleted_before_split.append(f_)
                    except Exception as e:
                        failed.append((f_, str(e)))
                if failed:
                    print("❌ Could not remove the following files:")
                    for fname, err in failed:
                        print(f"   • {fname} — {err}")
                    print("🚫 Aborting split due to delete errors.")
                    return
                else:
                    print("🧹 Deleted files:")
                    for f_ in deleted_before_split:
                        print(f"   • {f_}")
                    print("🧹 Old split files removed. Continuing...\n")
            else:
                print("❌ Cancelled — no files deleted; split aborted.")
                return
    except Exception as e:
        print(f"⚠️ Pre-flight check failed: {e}")
        return

    # Compute split boundaries
    cuts = _find_split_points(lines, num_parts)
    boundaries = [0] + cuts + [total]

    # Track both content-only and written (content + header + markers) counts
    part_content_counts: List[int] = []
    part_written_counts: List[int] = []
    created_files: List[str] = []
    empty_parts: List[int] = []  # 1-based indices for empty sections

    for i in range(num_parts):
        s, e = boundaries[i], boundaries[i + 1]
        chunk = lines[s:e]  # content lines for this part

        out_name = f"{base_name} - Part {i + 1}{ext}"
        out_path = os.path.join(out_dir, out_name)

        # ---- Build header (only Part 1 gets the hint and total-parts line) ----
        header_lines = []
        if i == 0:
            # prefer explicit header_hint (for JS/HTML mode), else use Python default SPLIT_HEADER_HINT
            use_hint = header_hint if isinstance(header_hint, str) else SPLIT_HEADER_HINT
            if isinstance(use_hint, str):
                header_lines.append(use_hint)
            header_lines.append(f"# This script is split into {num_parts} parts in total\n")

        header_lines.append(f"# Part {i + 1}/{num_parts} Start\n")

        # ---- Footer ----
        footer = f"# Part {i + 1}/{num_parts} End{' of script' if i == num_parts - 1 else ''}\n"

        with open(out_path, "w", encoding="utf-8") as out:
            for hl in header_lines:
                out.write(hl)
            out.writelines(chunk)
            if chunk and not str(chunk[-1]).endswith("\n"):
                out.write("\n")
            out.write(footer)

        # Count lines: content + headers + footer
        content_count = len(chunk)
        written_count = content_count + len(header_lines) + 1

        if content_count == 0:
            empty_parts.append(i + 1)

        part_content_counts.append(content_count)
        part_written_counts.append(written_count)
        created_files.append(out_name)
        print(f"✅ Created {out_name} — {written_count} line(s) (includes {len(header_lines)} header line(s) +1 footer).")

    split_total_content = sum(part_content_counts)
    difference_content = split_total_content - total  # compare CONTENT ONLY against original

    # ---- Console summary ----
    print("\n📊 Split summary:")
    print(f"   Original total: {total} line(s)")
    for i, (cnt_content, cnt_written) in enumerate(zip(part_content_counts, part_written_counts), 1):
        suffix = "  (missing section)" if cnt_content == 0 else ""
        print(f"   Part {i}: {cnt_content} content line(s) (+headers/footers → {cnt_written}){suffix}")
    print(f"   Sum of parts (content only): {split_total_content} line(s)")
    print(f"   Difference (sum - original, content only): {difference_content} line(s)")
    print("   Note: Only Part 1 includes the special hint and total-parts line.")

    if difference_content == 0:
        if empty_parts:
            print("⚠️ Split completed, but some sections are empty: " + ", ".join(f"Part {i}" for i in empty_parts))
        else:
            print("✅ Split successful.")
    elif difference_content < 0:
        print(f"❌ Failed Split: you're missing {abs(difference_content)} line(s).")
        if empty_parts:
            print("   Missing sections: " + ", ".join(f"Part {i}" for i in empty_parts))
    else:
        print(f"❌ Failed Split: you have {difference_content} extra duplicated content line(s).")

    print()  # trailing newline

    # ---- Write 'Split Script' report in same folder as the source script ----
    try:
        src_dir = os.path.dirname(os.path.abspath(script_path))
        report_path = os.path.join(src_dir, "Split Script")  # no extension per spec

        lines_report = []
        lines_report.append("Split Script Report")
        lines_report.append("=" * 20)
        lines_report.append(f"Source file: {os.path.basename(script_path)}")
        lines_report.append(f"Parts created: {len(part_content_counts)}")
        lines_report.append(f"Export directory: {os.path.abspath(out_dir)}")
        lines_report.append("")
        if deleted_before_split:
            lines_report.append("Deleted files before split:")
            for f_ in deleted_before_split:
                lines_report.append(f" - {f_}")
            lines_report.append("")
        lines_report.append(f"Original total lines: {total}")
        for i, (cnt_content, cnt_written) in enumerate(zip(part_content_counts, part_written_counts), 1):
            suffix = " (missing section)" if cnt_content == 0 else ""
            lines_report.append(f"Part {i} lines: {cnt_content}{suffix} (+headers/footers → {cnt_written})")
        lines_report.append(f"Sum of parts (content only): {split_total_content}")
        lines_report.append(f"Difference (sum - original, content only): {difference_content}")
        if difference_content == 0 and not empty_parts:
            lines_report.append("Result: Split successful.")
        elif difference_content < 0:
            lines_report.append(f"Result: FAILED — missing {abs(difference_content)} content line(s).")
            if empty_parts:
                lines_report.append("Missing sections: " + ", ".join(f"Part {i}" for i in empty_parts))
        else:
            lines_report.append(f"Result: FAILED — {difference_content} extra duplicated content line(s).")
        lines_report.append("")
        lines_report.append("Files:")
        for fname in created_files:
            lines_report.append(f" - {fname}")
        lines_report.append("")
        lines_report.append("Note: Only Part 1 includes the special hint and total-parts line; all parts include start/end markers.")

        with open(report_path, "w", encoding="utf-8") as rf:
            rf.write("\n".join(lines_report) + "\n")

        print(f"📝 Wrote summary file: {report_path}")
    except Exception as e:
        print(f"⚠️ Could not write 'Split Script' report: {e}")





# --- Hook into menu option 9 ---
def option_9_split_scripts() -> None:
    """Menu handler for option 9: choose file → reconfirm → show line stats → choose N → split."""
    chosen = _choose_script_file()
    if not chosen:
        return

    # Count lines and report
    try:
        total_lines = 0
        with open(chosen, "r", encoding="utf-8", errors="replace") as f:
            for _ in f:
                total_lines += 1
    except Exception as e:
        print(f"❌ Could not read '{chosen}': {e}")
        return

    # Use configurable hint threshold
    _hint = SPLIT_HINT_LINES if isinstance(SPLIT_HINT_LINES, int) and SPLIT_HINT_LINES > 0 else 2000

    if total_lines > _hint:
        quotient = total_lines / float(_hint)
        suggested_parts = (total_lines + _hint - 1) // _hint  # ceil division
        print(f"\nℹ️ File: '{chosen}' has {total_lines} line(s).")
        print(f"   {total_lines} / {_hint} = {quotient:.2f}  → Suggested parts ≈ {suggested_parts}")
    else:
        print(f"\nℹ️ File: '{chosen}' has {total_lines} line(s) (≤ {_hint}).")

    num_parts_str = (input("Into how many parts should I split it? (integer ≥ 2): ") or "").strip()
    if not num_parts_str.isdigit():
        print("❌ Invalid number of parts.")
        return

    num_parts = int(num_parts_str)
    if num_parts < 2:
        print("❌ Number of parts must be at least 2.")
        return

    split_script_evenly(chosen, num_parts, out_dir=DEFAULT_EXPORT_DIR)


# ---------------------------
# Sub‑menu (public entry point)
# ---------------------------

def render_menu() -> None:
    print("\n\033[4mOther Tools\033[0m")
    print("1 - 📤 Export Script (Python)")
    print("2 - 📤 Export Script (JavaScript,HTML)")
    print("3 - 💾 Backup CSV Files (Home - At Home)")
    print("4 - 🗑  Remove All Output Files")
    print("5 - 🗑  Remove All Files In 'New_Addresses_By_Suburb' Folder")
    print("6 - 🗑  Delete 'geocode_cache.json' File")
    print("0 - ⬅ Back to main menu")





def open_menu(script_path: str | None = None) -> None:
    """Interactive loop for the Other tools. Call this from the main Menu."""
    script_path = _preferred_script_path(script_path)

    while True:
        render_menu()
        choice = (input("\nChoose an option (0/1/2/3/4/5/6): ") or "").strip()

        if choice == "0":
            print("⬅ Returning to main menu...\n")
            return

        if choice == "1":
            print("\n📤 Export Script/Log Into Sections (even split mode) — Python\n")
            option_9_split_scripts()  # existing Python flow
            continue

        if choice == "2":
            print("\n📤 Export Script (JavaScript,HTML) — even split mode\n")
            option_2_split_js_html()
            continue

        if choice == "3":
            print("\n💾 Backup CSV Files (Home → At Home)\n")
            backup_csv_files(folder=BACKUP_CSV_DIR)
            continue

        if choice == "4":
            print("\n🗑  Remove All Output Files\n")
            confirm = input("Type 'y' to delete the output CSV/log files: ").strip().lower()
            if confirm == "y":
                remove_files(OUTPUT_FILES)
            else:
                print("❌ Cancelled.")
            continue

        if choice == "5":
            print(f"\n🗑  Remove All Files In '{SUBURB_DIR}' Folder\n")
            confirm = input(f"Type 'y' to purge files in '{SUBURB_DIR}': ").strip().lower()
            if confirm == "y":
                remove_files_in_folder(SUBURB_DIR)
            else:
                print("❌ Cancelled.")
            continue

        if choice == "6":
            print("\n🗑  Delete 'geocode_cache.json' File\n")
            prompt_delete_cache(exit_after=False)
            continue

        print("❌ Invalid option. Please try again.\n")



if __name__ == "__main__":
    # Standalone run for quick testing
    open_menu()
