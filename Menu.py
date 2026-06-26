# Python Expert
# Menu.py

import sys
import importlib
import importlib.util
from pathlib import Path
import os
import shutil

# ---------- Status symbols ----------
OK = "✅"
BAD = "❌"

# ---------- App root & resource resolver (robust anywhere you place the EXE) ----------
def _app_root() -> Path:
    # If frozen (PyInstaller), use the EXE's folder; else the script folder.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

APP_ROOT = _app_root()

def _force_cwd_to_app_root() -> None:
    try:
        os.chdir(APP_ROOT)
    except Exception as e:
        print(f"{BAD} Could not set working directory to app folder: {e}")

def resource_path(rel: str) -> str:
    """
    Portable resource resolver.

    Order:
    1) Next to EXE / script folder (APP_ROOT)  [preferred]
    2) PyInstaller onefile extraction folder (_MEIPASS)
    3) Fallback to APP_ROOT/rel (even if missing, caller may create it)
    """
    rel = rel.lstrip("/\\")
    p1 = APP_ROOT / rel
    if p1.exists():
        return str(p1)

    base = getattr(sys, "_MEIPASS", None)
    if base:
        p2 = Path(base) / rel
        if p2.exists():
            return str(p2)

    return str(p1)


# ---- ensure required input CSVs exist (next to the EXE) ----
FILE_TEMPLATES: dict[str, str] = {
    "input_googlesheets.csv": (
        "Number,Street,Suburb,PostalCode,Apartment/Business,Type,Language,Notes,Latitude,Longitude\n"
    ),
    "input_nws.csv": (
        "Number,Street,Suburb,PostalCode,Apartment/Business,Type,Language,Notes,Latitude,Longitude\n"
    ),
    "input_utf8.csv": (
        "Number,Street,Suburb,PostalCode,Apartment/Business,Type,Language,Notes,Latitude,Longitude\n"
    ),
    # outputs can start empty
    "output_clean.csv": "",
    "output_fail.csv": "",
}

def _touch_file_with(path: Path, content: str) -> None:
    try:
        if not path.exists() or path.stat().st_size == 0:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8-sig")
    except Exception as e:
        print(f"{BAD} Could not create {path.name}: {e}")

def _ensure_required_files_here() -> None:
    for fname, text in FILE_TEMPLATES.items():
        _touch_file_with(APP_ROOT / fname, text)


def _print_runtime_info():
    print(f"📁 APP_ROOT: {APP_ROOT}")
    print(f"📌 CWD: {Path.cwd()}")
    if getattr(sys, "frozen", False):
        print(f"🧊 Frozen EXE: {sys.executable}")

def _set_proj_lib_local() -> None:
    """
    Prefer PROJ data next to the EXE.

    We set PROJ_LIB only when we find proj.db.
    Supports common layouts:
      - Street Database/bin/proj.db
      - Street Database/share/proj/proj.db
      - Street Database/proj/proj.db
    """
    candidates = [
        APP_ROOT / "Street Database" / "bin",
        APP_ROOT / "Street Database" / "share" / "proj",
        APP_ROOT / "Street Database" / "proj",
    ]

    for p in candidates:
        try:
            if (p / "proj.db").exists():
                os.environ["PROJ_LIB"] = str(p)
                return
        except Exception:
            pass

    # Optional fallback for legacy installs (won't break portability)
    fallback = Path(r"C:\Script\Street Database\bin")
    try:
        if (fallback / "proj.db").exists():
            os.environ["PROJ_LIB"] = str(fallback)
    except Exception:
        pass



# ---------- Requirements catalogue (only list what's actually used) ----------
# Adjust/extend as your modules evolve.
REQUIREMENTS = {
    "1 - Clean New World Scheduler": {
        "modules": ["Clean_NewWorldScheduler"],
        "files": [
            "input_nws.csv",
            "output_clean.csv",
            "output_fail.csv",
        ],
        "folders": [
            # "lookups",
        ],
        "env": [
            # ("PROJ_LIB", "Street Database/bin"),
        ],
    },
    "2 - Clean Google Sheets": {
        "modules": ["Clean_GoogleSheets"],
        "files": [
            "input_googlesheets.csv",
            "output_clean.csv",
            "output_fail.csv",
        ],
        "folders": [],
        "env": [],
    },
    "3 - GeoPackage Borders (Option 9)": {
        "modules": ["GeoPackage_Borders"],  # may be frozen or loose .py next to EXE
        "files": [],
        "folders": [
            "Street Database/bin",  # for PROJ/GDAL data
            "KML Boundaries",
            "GeoPackage Borders",   # your working/output folder(s)
        ],
        "env": [
            ("PROJ_LIB", "Street Database/bin"),
        ],
        "alt_module_files": ["GeoPackage_Borders.py", "GeoPackage Borders.py"],
    },
    "4 - Finding New Addresses": {
        "modules": ["Finding_New_Addresses"],
        "files": [
            # add if this tool requires specific CSVs
        ],
        "folders": [],
        "env": [],
    },
    "5 - Other Functions": {
        "modules": ["Other_Functions"],
        "files": [],
        "folders": [],
        "env": [],
    },
}

def _check_path(rel: str) -> tuple[bool, Path]:
    """Check existence of a relative file/folder next to EXE."""
    p = APP_ROOT / rel
    return p.exists(), p

def _check_module(modname: str, alt_files: list[str] | None = None) -> tuple[bool, str]:
    """
    Probe for a module WITHOUT importing it (no side effects/prints).
    If not found, see if there’s a loose .py file next to the EXE.
    Returns (is_ok, source_string).
    """
    try:
        spec = importlib.util.find_spec(modname)
    except Exception:
        spec = None

    if spec is not None:
        return True, f"module:{modname}"

    if alt_files:
        for fname in alt_files:
            if (APP_ROOT / fname).exists():
                return True, f"file:{fname}"

    return False, modname

def _scan_requirements():
    print("\n🔍 Startup Check — Locating Required Components For NWS_Tools\n")

    grand_ok = 0
    grand_total = 0

    for option, req in REQUIREMENTS.items():
        ok_count = 0
        total_count = 0
        lines_out = []

        # Modules
        mods = req.get("modules", [])
        alt_files = req.get("alt_module_files", [])
        for m in mods:
            ok, src = _check_module(m, alt_files=alt_files)
            total_count += 1
            if ok:
                ok_count += 1
                lines_out.append(f"   {OK} module found: {src}")
            else:
                lines_out.append(f"   {BAD} module missing: {src}")

        # Files
        for rel in req.get("files", []):
            total_count += 1
            ok, p = _check_path(rel)
            if ok:
                ok_count += 1
                lines_out.append(f"   {OK} file: {p.name}")
            else:
                lines_out.append(f"   {BAD} file missing: {rel}")

        # Folders
        for rel in req.get("folders", []):
            total_count += 1
            ok, p = _check_path(rel)
            if ok and p.is_dir():
                ok_count += 1
                lines_out.append(f"   {OK} folder: {rel}")
            else:
                lines_out.append(f"   {BAD} folder missing: {rel}")

        # Env expectations: variable set AND points to an existing path (if provided)
        for item in req.get("env", []):
            total_count += 1
            var, hint_rel = (item if isinstance(item, tuple) else (item, None))
            val = os.environ.get(var, "")
            if val and Path(val).exists():
                ok_count += 1
                lines_out.append(f"   {OK} env {var} -> {val}")
            else:
                msg = f"   {BAD} env {var} not set or path missing"
                if hint_rel:
                    msg += f" (expected like: {APP_ROOT / hint_rel})"
                lines_out.append(msg)

        # Header with counts per section
        print(f"— {option} — ({ok_count}/{total_count} OK)")
        if total_count == 0:
            print("   (no external files/folders required)")
        else:
            for line in lines_out:
                print(line)
        print()

        # Tally into grand totals
        grand_ok += ok_count
        grand_total += total_count

    # ---- Final summary across all sections ----
    missing = grand_total - grand_ok
    print("— Summary —")
    print(f"   {OK} Found: {grand_ok}")
    print(f"   {BAD} Missing: {missing}")
    print(f"   Total checked: {grand_total}\n")

# ---------- bootstrap ----------
def bootstrap_setup():
    _force_cwd_to_app_root()

    # Ensure imports work even when launched from anywhere
    if str(APP_ROOT) not in sys.path:
        sys.path.insert(0, str(APP_ROOT))

    _ensure_required_files_here()
    _set_proj_lib_local()


# ---------- dynamic loader (handles filenames with spaces) ----------
import traceback

def _load_module(preferred_name: str, file_candidates: list[str]):
    # Always allow sibling imports when launched from anywhere
    if str(APP_ROOT) not in sys.path:
        sys.path.insert(0, str(APP_ROOT))

    # Try normal import first (frozen hiddenimports)
    try:
        return importlib.import_module(preferred_name)
    except ModuleNotFoundError:
        pass
    except Exception as e:
        print(f"{BAD} {preferred_name} import failed (crashed on import): {e}")
        traceback.print_exc()
        return None

    # Try loose file next to the EXE
    for fname in file_candidates:
        fpath = APP_ROOT / fname
        if fpath.exists():
            try:
                spec = importlib.util.spec_from_file_location(preferred_name, str(fpath))
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)

                    # IMPORTANT:
                    # 1) register in sys.modules BEFORE exec (helps sibling imports / recursion safety)
                    sys.modules[preferred_name] = mod

                    # 2) make relative imports inside the loaded file resolve like a top-level module
                    mod.__package__ = ""

                    spec.loader.exec_module(mod)
                    return mod
            except Exception as e:
                print(f"{BAD} Failed to load {fname}: {e}")
                traceback.print_exc()
                return None

    return None



def _call_entry(mod):
    for attr in ("open_menu", "run", "main", "finding_new_addresses"):
        fn = getattr(mod, attr, None)
        if callable(fn):
            return fn()
    print("ℹ️ No entry point found (expected open_menu()/run()/main()/finding_new_addresses()).")

# ---------- module openers ----------
def open_clean_new_world_scheduler():
    mod = _load_module("Clean_NewWorldScheduler", ["Clean_NewWorldScheduler.py"])
    if not mod:
        print(f"{BAD} Could not load Clean_NewWorldScheduler.")
        return
    _call_entry(mod)

def open_clean_google_sheets():
    mod = _load_module("Clean_GoogleSheets", ["Clean_GoogleSheets.py"])
    if not mod:
        print(f"{BAD} Could not load Clean_GoogleSheets.")
        return
    _call_entry(mod)

def open_geopackage_borders():
    _set_proj_lib_local()  # ensure GDAL/PROJ can find data
    file_candidates = ["GeoPackage_Borders.py", "GeoPackage Borders.py"]
    mod = _load_module("GeoPackage_Borders", file_candidates)
    if not mod:
        print(f"{BAD} Option 9 (GeoPackage Borders) is not available. "
              "Copy GeoPackage_Borders.py next to the EXE or rebuild with hiddenimports.")
        return
    try:
        print(f"🔌 Option 9 plugin loaded from: {getattr(mod, '__file__', '<frozen>')}")
    except Exception:
        pass
    _call_entry(mod)

def open_finding_new_addresses():
    mod = _load_module("Finding_New_Addresses", ["Finding_New_Addresses.py"])
    if not mod:
        print(f"{BAD} Could not load Finding_New_Addresses.")
        return
    _call_entry(mod)

def open_other_functions():
    mod = _load_module("Other_Functions", ["Other_Functions.py"])
    if not mod:
        print(f"{BAD} Could not load Other_Functions.")
        return
    _call_entry(mod)

# ---------- UI ----------
def render_menu():
    print("\nMain Menu")
    print("1 - ✨ Clean New World Scheduler (input_nws)")
    print("2 - ✨ Clean Google Sheets (input_googlesheets)")
    print("3 - 🌐 GeoPackage Borders")
    print("4 - 🔎 Finding New Addresses")
    print("5 - 🧰 Other Functions (Dev/Ops, Cache, Exports)")
    print("\n0 - Exit")

def main():
    try:
        bootstrap_setup()
        while True:
            render_menu()
            choice = input("\nSelect an option: ").strip().lower()
            if choice == "1":
                open_clean_new_world_scheduler()
            elif choice == "2":
                open_clean_google_sheets()
            elif choice == "3":
                open_geopackage_borders()
            elif choice == "4":
                open_finding_new_addresses()
            elif choice == "5":
                open_other_functions()
            elif choice in ("0", "q", "quit", "exit"):
                print("👋 Bye!")
                sys.exit(0)
            else:
                print("⚠️ Invalid option.")
    except KeyboardInterrupt:
        print("\n👋 Bye!")
        sys.exit(0)

if __name__ == "__main__":
    main()
