#!/usr/bin/env python3
"""
GoogleSheets_Master.py

Purpose
-------
Master DB/CSV index + duplicate logic + street whitelist repair.

This module contains ONLY the Master-related functions you listed:

    • _canon_triplet
    • _ensure_sqlite_from_csv
    • _load_master_index
    • _duplicate_status_against_master
    • _debug_probe_against_master
    • run_master_db_duplicate_audit
    • run_final_master_duplicate_filter
    • run_verify_fail_against_master
    • _init_street_whitelist_from_master
    • _repair_corrupted_street

Design / Imports
----------------
- May import GoogleSheets_Utils (canon helpers, suburb helpers, parsing helpers).
- MUST NOT import Flows or Menu (prevents circular imports).

Portability
-----------
Master files live under:
  <APP_ROOT>/Master/
    - Auckland East Mandarin Territory Addresses.csv
    - Auckland_East_Mandarin_Addresses.db (auto-built from CSV)

APP_ROOT is sourced from GoogleSheets_Utils when available.
"""

from __future__ import annotations

import os
import re
import csv
import sqlite3
import difflib
from pathlib import Path
from functools import lru_cache

# --- Logging: record module import as early as possible ---
from GoogleSheets_Log import module_loaded  # noqa: E402
module_loaded(__name__)

# =============================================================================
# Imports from Utils (canonicalization + parsing + suburb helpers)
# =============================================================================
# NOTE: These names are referenced by the verbatim-copied functions below.
try:
    from GoogleSheets_Utils import (
        APP_ROOT,
        _canon_text_cached,
        _strip_macrons,
        _split_unit_house,
        _strip_unit_prefix_for_match,  # ✅ ADD THIS
        _combine_unit_and_number,
        gs_strip_leading_duplicate_number_from_street,
        _canon_suburb_sheets,
        _postal_for_suburb_sheets,
        HOUSE_FLIP_A,
        HOUSE_FLIP_B,
    )

except Exception:
    # Fallback (should rarely happen): define a minimal APP_ROOT for path building.
    # You still must ensure GoogleSheets_Utils exists for real runs.
    APP_ROOT = Path(__file__).resolve().parent  # type: ignore[assignment]
    raise


# =============================================================================
# Master file locations (portable)
# Looks in:
#   1) <APP_ROOT>/Master/<default name>
#   2) <APP_ROOT>/<default name>
#   3) Any *.csv inside <APP_ROOT>/Master (newest)
#   4) Any *.csv inside <APP_ROOT> (newest)
# =============================================================================

DEFAULT_MASTER_CSV_NAME = "Auckland East Mandarin Territory Addresses.csv"
DEFAULT_MASTER_DB_NAME = "Auckland_East_Mandarin_Addresses.db"

MASTER_DIR = APP_ROOT / "Master"
MASTER_CSV_DIR = MASTER_DIR  # alias for legacy name used below
# NOTE:
# Do NOT resolve master paths at import time.
# Paths are resolved lazily at runtime for portability.


def resolve_master_paths() -> tuple[Path, Path]:
    """
    Runtime-safe resolver for master CSV + DB.

    - CSV is selected by resolve_master_csv_path()
    - DB always lives next to the selected CSV, but uses a stable filename
      so other modules/tools can rely on it.
    - Safe to call repeatedly

    Side effect (compat):
    - Updates MASTER_CSV_PATH / MASTER_DB_PATH globals for legacy callers.
    """
    global MASTER_CSV_PATH, MASTER_DB_PATH

    csv_path = resolve_master_csv_path()
    db_path = csv_path.parent / DEFAULT_MASTER_DB_NAME

    # Keep legacy globals in sync (many older modules expect these)
    MASTER_CSV_PATH = csv_path
    MASTER_DB_PATH = db_path

    return csv_path, db_path

def _read_csv_header_best_effort(p: Path) -> list[str]:
    """
    Read first row (header) from CSV with encoding fallbacks.
    Handles UTF-8 BOM and common Windows encodings.
    """
    encodings = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
    last_err = None

    for enc in encodings:
        try:
            with open(p, newline="", encoding=enc) as f:
                r = csv.reader(f)
                return next(r, []) or []
        except Exception as e:
            last_err = e

    # If everything failed, re-raise the last error
    raise last_err  # type: ignore[misc]


def _canon_header_cols(header: list[str]) -> set[str]:
    """
    Canonicalize header names: trim, lower, remove spaces/underscores.
    So 'Apartment Number' and 'ApartmentNumber' both match.
    """
    out = set()
    for x in header:
        s = str(x or "").strip().lower()
        s = s.replace(" ", "").replace("_", "")
        out.add(s)
    return out


def _looks_like_master_csv(p: Path) -> bool:
    """
    True if CSV looks like the master list:
      must contain at least these headers (case-insensitive, space/underscore-insensitive):
        ApartmentNumber, Number, Street, Suburb
    """
    from GoogleSheets_Log import log_warn

    try:
        if not p.exists() or not p.is_file():
            return False

        header = _read_csv_header_best_effort(p)
        cols = _canon_header_cols(header)

        required = {"apartmentnumber", "number", "street", "suburb"}
        ok = required.issubset(cols)

        if not ok:
            # SUPER IMPORTANT: this tells you "file exists but header doesn't match"
            log_warn(
                "MASTER_CSV_HEADER_MISMATCH",
                module=__name__,
                fn="_looks_like_master_csv",
                extra={
                    "path": str(p),
                    "header": header[:20],
                    "missing": sorted(list(required - cols)),
                    "have": sorted(list(cols))[:40],
                },
            )

        return ok

    except Exception as e:
        log_warn(
            "MASTER_CSV_HEADER_READ_FAILED",
            module=__name__,
            fn="_looks_like_master_csv",
            extra={"path": str(p), "error": str(e)},
        )
        return False



def _pick_newest_csv(folder: Path) -> Path | None:
    """
    Pick newest CSV in a folder, but IGNORE run artefacts like:
      - output_clean*.csv
      - output_fail*.csv
      - input_*.csv
    """
    try:
        csvs = [p for p in folder.glob("*.csv") if p.is_file()]
        if not csvs:
            return None

        def is_run_artifact(p: Path) -> bool:
            n = p.name.lower()
            return (
                n.startswith("output_clean")
                or n.startswith("output_fail")
                or n.startswith("input_")
                or n == "input_googlesheets.csv"
            )

        csvs = [p for p in csvs if not is_run_artifact(p)]
        if not csvs:
            return None

        return max(csvs, key=lambda p: p.stat().st_mtime)
    except Exception:
        return None


def resolve_master_csv_path() -> Path:
    """
    Resolve the master CSV safely.

    Priority:
      1) <APP_ROOT>/Master/<DEFAULT_MASTER_CSV_NAME> (exact name)
      2) newest valid master-looking CSV inside <APP_ROOT>/Master
      3) <APP_ROOT>/<DEFAULT_MASTER_CSV_NAME> (exact name)
      4) <APP_ROOT> a file that *looks like master* AND whose name contains
         'Auckland East Mandarin Territory Addresses' (case-insensitive),
         while still IGNORING run artefacts (output_clean/output_fail/input_*).

    IMPORTANT:
      - We still do NOT pick the "newest CSV in APP_ROOT" (that can grab output_fail.csv).
      - This adds a SAFE fallback for when your master CSV is placed next to the app.
    """
    # helper: avoid accidentally selecting run artefacts
    def _is_run_artifact(p: Path) -> bool:
        n = p.name.lower()
        return (
            n.startswith("output_clean")
            or n.startswith("output_fail")
            or n.startswith("input_")
            or n == "input_googlesheets.csv"
        )

    # 0) Explicit override for any PC / any folder
    # Example:
    #   set MASTER_CSV="D:\Territory Assistant\Master\Auckland East Mandarin Territory Addresses.csv"
    #   or on Windows: setx MASTER_CSV "D:\...\Addresses.csv"
    env_csv = os.environ.get("MASTER_CSV", "").strip().strip('"')
    if env_csv:
        p0 = Path(env_csv)
        if p0.exists() and _looks_like_master_csv(p0):
            return p0

    # 1) Preferred: Master folder + default name
    p1 = MASTER_DIR / DEFAULT_MASTER_CSV_NAME
    if p1.exists() and _looks_like_master_csv(p1):
        return p1

    # 2) Any valid master CSV in Master folder (newest)
    p2 = _pick_newest_csv(MASTER_DIR)
    if p2 and _looks_like_master_csv(p2):
        return p2

    # 3) Fallback: APP_ROOT + default name (some installs keep master next to the app)
    p3 = APP_ROOT / DEFAULT_MASTER_CSV_NAME
    if p3.exists() and _looks_like_master_csv(p3):
        return p3

    # 4) SAFE fallback: APP_ROOT file that looks like master AND name contains the master phrase
    # (prevents grabbing output_fail.csv while still matching your real file name variations)
    try:
        key = "auckland east mandarin territory addresses"
        candidates = []
        for p in APP_ROOT.glob("*.csv"):
            if not p.is_file():
                continue
            if _is_run_artifact(p):
                continue
            if key not in p.name.lower():
                continue
            if _looks_like_master_csv(p):
                candidates.append(p)

        if candidates:
            # choose newest among ONLY the safe, name-matched, header-validated candidates
            return max(candidates, key=lambda p: p.stat().st_mtime)
    except Exception:
        pass

    # Keep consistent error path (points to expected location in Master folder)
    return p1


MASTER_CSV_PATH: Path | None = None
MASTER_DB_PATH: Path | None = None




# =============================================================================
# Master-index globals (populated by _load_master_index)
# =============================================================================

# Also index house-only numbers per (Street, Suburb) for fallback duplicate checks
# (Kept for compatibility; current strict duplicate rule uses _MASTER_TRIPLET_SET.)
_MASTER_STSUB_TO_HOUSES: dict[tuple[str, str], set[str]] = {}

# Display strings for house-only matches → used to explain which master row we matched
# Key: (canon(Street), canon(Suburb), canon(house_only))  Value: set[str display]
_MASTER_HOUSEONLY_TO_ADDRS: dict[tuple[str, str, str], set[str]] = {}

# (Street, Suburb) presence set
_MASTER_STREET_SUBURB_SET: set[tuple[str, str]] = set()

# Canonical (ApartmentNumber, Number, Street) triplets present in master DB/CSV
# This is what we now use for strict duplicate detection:
#   duplicate ⇔ same ApartmentNumber + Number + Street (after canonicalisation)
_MASTER_TRIPLET_SET: set[tuple[str, str, str]] = set()


# =============================================================================
# Street whitelist repair (used to clean corrupted street names)
# =============================================================================

_STREET_WHITELIST = set()

# Prevent repeated expensive whitelist rebuild attempts when master files are missing.
_STREET_WHITELIST_INIT_ATTEMPTED: bool = False

_STREET_CORRUPTION_MAP = {
    # Add any known 1:1 street fixes you encounter
    # "Fencotie Place": "Fencottie Place",
}

_BAD_STREET_CHARS_RX = re.compile(r"[^A-Za-z0-9'\-\s]")


# =============================================================================
# Local helpers (non-exported)
# =============================================================================

def _canon_street_suburb(street: str, suburb: str) -> tuple[str, str]:
    c = _canon_text_cached
    return (c((street or "").strip()), c((suburb or "").strip()))


# =============================================================================
# Functions (copied from Clean_GoogleSheets.py)
# =============================================================================

def _canon_triplet(ap_num: str, number: str, street: str) -> tuple[str, str, str]:
    """
    Canonical triplet for (ApartmentNumber, Number, Street).

    Legacy parity fix:
    - Treat ApartmentNumber consistently whether it's stored as "A" or "UnitA".
    - If Number is in merged form ("UnitA/12" or "12/UnitA"), normalize it so:
        ApartmentNumber="A" and Number="12" (when possible).
    - This makes master index triplets match sheet output triplets reliably.
    """
    c = _canon_text_cached

    ap = (ap_num or "").strip()
    num = (number or "").strip()
    st = (street or "").strip()

    # Normalize apartment/unit prefix for matching (UnitA == A)
    try:
        ap = _strip_unit_prefix_for_match(ap)
    except Exception:
        pass

    # Normalize merged Number forms into (ap, house) where possible
    if num:
        try:
            ap_guess, num_guess = _split_unit_house(num)
        except Exception:
            ap_guess = num_guess = None

        if num_guess:
            # Normalize guessed unit prefix too
            try:
                ap_guess_norm = _strip_unit_prefix_for_match(ap_guess or "")
            except Exception:
                ap_guess_norm = (ap_guess or "")

            if (not ap) and ap_guess_norm:
                ap = ap_guess_norm
                num = num_guess
            elif ap and ap_guess_norm:
                if c(ap) == c(ap_guess_norm):
                    num = num_guess

    return (c(ap), c(num), c(st))



def _ensure_sqlite_from_csv(csv_path: Path | None = None, db_path: Path | None = None) -> None:
    """
    Build/update a small SQLite DB from the master CSV if needed.
    Rebuild when DB missing or CSV is newer.

    Console policy:
    - Only STAGE + ERROR print (via GoogleSheets_Log)
    - No direct print() calls here
    """
    from GoogleSheets_Log import stage, log_warn, log_error, log_exception

    try:
        # Always re-resolve at runtime (portable)
        csv_path, db_path = resolve_master_paths()

        try:
            MASTER_CSV_DIR.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        if not csv_path.exists():
            cand = _pick_newest_csv(MASTER_CSV_DIR)

            if cand and cand.exists() and _looks_like_master_csv(cand):
                csv_path = cand
                db_path = csv_path.parent / DEFAULT_MASTER_DB_NAME
                log_warn(
                    "MASTER_CSV_DEFAULT_NAME_NOT_FOUND_USING_NEWEST",
                    module=__name__,
                    fn="_ensure_sqlite_from_csv",
                    extra={"csv": str(csv_path)},
                )
            else:
                log_warn(
                    "MASTER_CSV_NOT_FOUND",
                    module=__name__,
                    fn="_ensure_sqlite_from_csv",
                    extra={"expected": str(csv_path), "master_dir": str(MASTER_CSV_DIR)},
                )
                return

        # Ensure DB always pairs with the chosen CSV (stable name)
        db_path = csv_path.parent / DEFAULT_MASTER_DB_NAME

        # --- Legacy DB migration (optional) ---
        legacy_db = csv_path.with_suffix(".db")
        try:
            if legacy_db.exists() and (not db_path.exists()):
                os.replace(str(legacy_db), str(db_path))
                log_warn(
                    "MASTER_DB_LEGACY_MIGRATED",
                    module=__name__,
                    fn="_ensure_sqlite_from_csv",
                    extra={"from": str(legacy_db), "to": str(db_path)},
                )
        except Exception as e:
            log_warn(
                "MASTER_DB_LEGACY_MIGRATION_FAILED",
                module=__name__,
                fn="_ensure_sqlite_from_csv",
                extra={"error": str(e), "from": str(legacy_db), "to": str(db_path)},
            )

        needs_rebuild = (not db_path.exists() or csv_path.stat().st_mtime > db_path.stat().st_mtime)
        if not needs_rebuild:
            stage(
                "Master DB up-to-date (no rebuild)",
                module=__name__,
                fn="_ensure_sqlite_from_csv",
                extra={"csv": str(csv_path), "db": str(db_path)},
            )
            return

        stage(
            "Rebuilding Master DB from CSV",
            module=__name__,
            fn="_ensure_sqlite_from_csv",
            extra={"csv": str(csv_path), "db": str(db_path)},
        )

        # timeout prevents “silent hang” when DB is locked (OneDrive/AV/another run)
        conn = sqlite3.connect(str(db_path), timeout=30.0)
        try:
            cur = conn.cursor()

            # Optional perf/lock improvements (safe defaults)
            try:
                cur.execute("PRAGMA journal_mode=WAL;")
                cur.execute("PRAGMA synchronous=NORMAL;")
                cur.execute("PRAGMA temp_store=MEMORY;")
            except Exception:
                pass

            cur.execute("DROP TABLE IF EXISTS addresses")
            cur.execute("""
                CREATE TABLE addresses(
                    ApartmentNumber TEXT,
                    Number          TEXT,
                    Street          TEXT,
                    Suburb          TEXT
                )
            """)

            inserted = 0

            # ✅ Use encoding fallbacks (matches your header logic + avoids Windows CSV failures)
            f = _open_csv_text_best_effort(csv_path)
            try:
                r = csv.DictReader(f)
                rows = []
                for row in r:
                    rows.append((
                        row.get("ApartmentNumber", "") or "",
                        row.get("Number", "") or "",
                        row.get("Street", "") or "",
                        row.get("Suburb", "") or "",
                    ))
                    if len(rows) >= 50_000:
                        cur.executemany("INSERT INTO addresses VALUES (?,?,?,?)", rows)
                        inserted += len(rows)
                        rows.clear()

                        stage(
                            "Master DB rebuild progress",
                            module=__name__,
                            fn="_ensure_sqlite_from_csv",
                            extra={"inserted": int(inserted)},
                        )

                if rows:
                    cur.executemany("INSERT INTO addresses VALUES (?,?,?,?)", rows)
                    inserted += len(rows)

                    stage(
                        "Master DB rebuild progress",
                        module=__name__,
                        fn="_ensure_sqlite_from_csv",
                        extra={"inserted": int(inserted)},
                    )
            finally:
                try:
                    f.close()
                except Exception:
                    pass

            cur.execute("CREATE INDEX IF NOT EXISTS idx_ans       ON addresses(ApartmentNumber, Number, Street)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_all       ON addresses(ApartmentNumber, Number, Street, Suburb)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_st_suburb ON addresses(Street, Suburb)")
            conn.commit()

            stage(
                "Master DB rebuild complete",
                module=__name__,
                fn="_ensure_sqlite_from_csv",
                extra={"rows": int(inserted), "db": str(db_path)},
            )
        finally:
            try:
                conn.close()
            except Exception:
                pass

    except Exception:
        log_exception("MASTER_DB_REBUILD_FAILED", module=__name__, fn="_ensure_sqlite_from_csv")
        return






@lru_cache(maxsize=1)
def _load_master_index():
    """
    Loads master index into memory and populates globals.

    Console policy:
    - Only STAGE + ERROR print (via GoogleSheets_Log)
    - No direct print() calls here
    """
    from GoogleSheets_Log import stage, log_warn, log_exception, decision

    # Always re-resolve at runtime (portable)
    csv_path, db_path = resolve_master_paths()

    exact_set: set[tuple[str, str, str, str]] = set()
    triplet_to_suburbs: dict[tuple[str, str, str], set[str]] = {}

    # reset/refresh globals
    _MASTER_STREET_SUBURB_SET.clear()
    _MASTER_STSUB_TO_HOUSES.clear()
    _MASTER_HOUSEONLY_TO_ADDRS.clear()
    _MASTER_TRIPLET_SET.clear()

    def add(ap, num, st, sub):
        k3 = _canon_triplet(ap, num, st)
        cs = _canon_text_cached((sub or "").strip())

        exact_set.add((k3[0], k3[1], k3[2], cs))
        triplet_to_suburbs.setdefault(k3, set()).add(cs)

        _MASTER_TRIPLET_SET.add(k3)

        st_sub_key = _canon_street_suburb(st, sub)
        _MASTER_STREET_SUBURB_SET.add(st_sub_key)

    stage(
        "Loading master index",
        module=__name__,
        fn="_load_master_index",
        extra={"csv": str(csv_path), "db": str(db_path)},
    )

    try:
        # Ensure DB is built/updated (portable; may log stages)
        _ensure_sqlite_from_csv()

        # Re-resolve in case CSV choice changed
        csv_path, db_path = resolve_master_paths()

        loaded_from = None

        if db_path.exists():
            try:
                # ✅ timeout prevents “silent hang” on locked DB
                conn = sqlite3.connect(str(db_path), timeout=30.0)
                try:
                    cur = conn.cursor()
                    for ap, num, st, sub in cur.execute(
                        "SELECT ApartmentNumber, Number, Street, Suburb FROM addresses"
                    ):
                        add(ap or "", num or "", st or "", sub or "")
                    loaded_from = "db"
                finally:
                    conn.close()
            except Exception as e:
                log_warn(
                    "MASTER_INDEX_DB_LOAD_FAILED_FALLING_BACK_TO_CSV",
                    module=__name__,
                    fn="_load_master_index",
                    extra={"error": str(e), "db": str(db_path)},
                )

        # CSV fallback (now encoding-robust)
        if not exact_set and csv_path.exists():
            try:
                f = _open_csv_text_best_effort(csv_path)
                try:
                    r = csv.DictReader(f)
                    for row in r:
                        add(
                            row.get("ApartmentNumber", "") or "",
                            row.get("Number", "") or "",
                            row.get("Street", "") or "",
                            row.get("Suburb", "") or "",
                        )
                finally:
                    try:
                        f.close()
                    except Exception:
                        pass

                loaded_from = loaded_from or "csv"
            except Exception as e:
                log_warn(
                    "MASTER_INDEX_CSV_LOAD_FAILED",
                    module=__name__,
                    fn="_load_master_index",
                    extra={"error": str(e), "csv": str(csv_path)},
                )

        if not exact_set:
            log_warn(
                "MASTER_INDEX_EMPTY",
                module=__name__,
                fn="_load_master_index",
                extra={"csv": str(csv_path), "db": str(db_path)},
            )

        decision(
            "MASTER_INDEX_LOADED",
            module=__name__,
            fn="_load_master_index",
            extra={
                "loaded_from": loaded_from,
                "exact_set": len(exact_set),
                "triplets": len(_MASTER_TRIPLET_SET),
                "street_suburb": len(_MASTER_STREET_SUBURB_SET),
            },
        )

    except Exception:
        log_exception("MASTER_INDEX_INIT_FAILED", module=__name__, fn="_load_master_index")

    return exact_set, triplet_to_suburbs





def _duplicate_status_against_master(cleaned: dict, *, return_basis: bool = False):
    """
    Duplicate gating against the master list.

    RULE:
      duplicate ⇔ same canonical (ApartmentNumber, Number, Street) triplet in master.

    Parity fix:
    - Always normalize "Unit" prefixes (UnitA == A)
    - Always normalize merged Number forms ("UnitA/12" or "12/UnitA") into ap+house
    - Use _canon_triplet() as the single source of truth for triplet normalization.
    """
    ap = (cleaned.get("ApartmentNumber") or "").strip()
    num = (cleaned.get("Number") or "").strip()
    st  = (cleaned.get("Street") or "").strip()

    if not (st and num):
        return (None, None, None) if return_basis else None

    # Normalize ap/unit prefix early
    try:
        ap = _strip_unit_prefix_for_match(ap)
    except Exception:
        pass

    # Normalize merged Number forms into (ap, house) when possible
    try:
        ap_guess, num_guess = _split_unit_house(num)
    except Exception:
        ap_guess = num_guess = None

    if num_guess:
        try:
            ap_guess_norm = _strip_unit_prefix_for_match(ap_guess or "")
        except Exception:
            ap_guess_norm = (ap_guess or "")

        if (not ap) and ap_guess_norm:
            ap = ap_guess_norm
            num = num_guess
        elif ap and ap_guess_norm and _canon_text_cached(ap) == _canon_text_cached(ap_guess_norm):
            num = num_guess

    _load_master_index()
    trip = _canon_triplet(ap, num, st)

    if trip in _MASTER_TRIPLET_SET:
        if return_basis:
            return ("Duplicate", "exact-triplet", None)
        return "Duplicate"

    return (None, None, None) if return_basis else None




def _debug_probe_against_master(ap, num, street, suburb):
    """
    Debug helper: logs probe result (no console prints).
    """
    from GoogleSheets_Log import log_info

    rec = {
        "ApartmentNumber": ap,
        "Number": num,
        "Street": street,
        "Suburb": suburb,
        "Status": "At Home",
        "Notes": "",
    }
    status = _duplicate_status_against_master(rec)
    log_info(
        "MASTER_DUPLICATE_PROBE",
        module=__name__,
        fn="_debug_probe_against_master",
        extra={"ap": ap, "num": num, "street": street, "suburb": suburb, "status": status},
    )



def run_master_db_duplicate_audit(out_fail: str = "output_fail.csv") -> None:
    """
    Option 5: internal audit of duplicates INSIDE master DB.

    STRICT RULE (matches your current duplicate gating):
      duplicate ⇔ same canonical (ApartmentNumber, Number, Street)

    Console policy:
    - Only STAGE + ERROR print (via GoogleSheets_Log)
    - No direct print() calls here

    PATCH (legacy output parity):
    - Ensure BOTH 'PostalCode' and legacy 'Postcode' columns exist in audit output schema.
    - Mirror values: Postcode == PostalCode on every written row.

    Correctness fix:
    - Count duplicates using _canon_triplet(), not raw canon(ap/num/st),
      so UnitA == A and merged number normalization stays consistent with gating.
    """
    from GoogleSheets_Log import stage, log_error, log_warn, log_exception, decision

    stage(
        "Master DB duplicate audit started",
        module=__name__,
        fn="run_master_db_duplicate_audit",
        extra={"out_fail": out_fail},
    )

    try:
        # Resolve runtime-safe master paths
        csv_path, db_path = resolve_master_paths()

        # Ensure DB exists / updated
        _ensure_sqlite_from_csv()

        # Re-resolve in case the CSV choice changed
        csv_path, db_path = resolve_master_paths()

        if not db_path.exists():
            log_error(
                "MASTER_DB_NOT_FOUND",
                module=__name__,
                fn="run_master_db_duplicate_audit",
                extra={"db": str(db_path), "csv": str(csv_path)},
            )
            return

        # Collect master rows
        rows: list[dict] = []
        try:
            conn = sqlite3.connect(str(db_path), timeout=30.0)
            try:
                cur = conn.cursor()
                for ap, num, st, sub in cur.execute(
                    "SELECT ApartmentNumber, Number, Street, Suburb FROM addresses"
                ):
                    rows.append({
                        "ApartmentNumber": ap or "",
                        "Number": (num or "").strip(),
                        "Street": (st or "").strip(),
                        "Suburb": (sub or "").strip(),
                    })
            finally:
                conn.close()
        except Exception as e:
            log_error(
                "MASTER_DB_READ_FAILED",
                module=__name__,
                fn="run_master_db_duplicate_audit",
                extra={"error": str(e), "db": str(db_path)},
            )
            return

        if not rows:
            log_warn(
                "MASTER_DB_EMPTY",
                module=__name__,
                fn="run_master_db_duplicate_audit",
                extra={"db": str(db_path)},
            )
            return

        # Build duplicate signals using strict canonical triplet
        from collections import Counter as _Counter
        trip_counts = _Counter()

        trip_of_idx: list[tuple[str, str, str]] = []
        for r in rows:
            k3 = _canon_triplet(r.get("ApartmentNumber", ""), r.get("Number", ""), r.get("Street", ""))
            trip_of_idx.append(k3)
            trip_counts[k3] += 1

        fieldnames = [
            "Old Number", "Unit",
            "Old Street",
            "ApartmentNumber", "Number", "Street",
            "Suburb", "PostalCode", "Postcode", "State",
            "Status", "Final Status",
            "Latitude", "Longitude",
            "Type", "Language", "Notes", "Other Notes",
        ]

        dup_total = 0

        stage(
            "Writing master audit duplicates",
            module=__name__,
            fn="run_master_db_duplicate_audit",
            extra={"out_fail": out_fail},
        )

        with open(out_fail, "w", newline="", encoding="utf-8", buffering=1024 * 1024) as fout_f:
            wf = csv.DictWriter(fout_f, fieldnames=fieldnames)
            wf.writeheader()

            for idx, r in enumerate(rows):
                k3 = trip_of_idx[idx]
                if trip_counts[k3] <= 1:
                    continue

                suburb_c = _canon_suburb_sheets(r["Suburb"])
                pc = _postal_for_suburb_sheets(suburb_c)

                merged_number = _combine_unit_and_number(r["ApartmentNumber"], r["Number"])
                street_fixed = gs_strip_leading_duplicate_number_from_street(merged_number, r["Street"])

                rec = {
                    "Old Number": "",
                    "Unit": "",
                    "Old Street": "",
                    "ApartmentNumber": r["ApartmentNumber"],
                    "Number": merged_number,
                    "Street": street_fixed,
                    "Suburb": suburb_c,
                    "PostalCode": pc,
                    "Postcode": pc,  # mirror for legacy parity
                    "State": "Auckland",
                    "Status": "",
                    "Final Status": "Duplicate",
                    "Latitude": "",
                    "Longitude": "",
                    "Type": "",
                    "Language": "",
                    "Notes": "",
                    "Other Notes": "Dup basis: exact-triplet",
                }

                # Keep legacy "Unit flip" formatting normalization
                num = (rec.get("Number") or "").strip()
                if num:
                    m = HOUSE_FLIP_A.match(num)
                    if m:
                        rec["Number"] = f"{m.group(2)}/Unit{m.group(1).upper()}"
                    else:
                        m = HOUSE_FLIP_B.match(num)
                        if m:
                            rec["Number"] = f"Unit{m.group(2).upper()}/{m.group(1)}"

                wf.writerow({k: rec.get(k, "") for k in fieldnames})
                dup_total += 1

        decision(
            "MASTER_AUDIT_DONE",
            module=__name__,
            fn="run_master_db_duplicate_audit",
            extra={"duplicates_written": dup_total, "out_fail": out_fail},
        )

        stage(
            "Master DB duplicate audit finished",
            module=__name__,
            fn="run_master_db_duplicate_audit",
            extra={"duplicates_written": dup_total, "out_fail": out_fail},
        )

    except Exception:
        log_exception("MASTER_AUDIT_EXCEPTION", module=__name__, fn="run_master_db_duplicate_audit")
        raise




def _open_csv_text_best_effort(p: Path | str):
    """
    Open CSV text with encoding fallbacks.
    Returns an open file handle (caller must close).

    Robustness:
    - Accepts Path OR str (older callers sometimes pass strings).
    - Tries utf-8-sig/utf-8 first, then common Windows exports (cp1252/latin-1).
    """
    encodings = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
    last_err = None

    path = str(p)

    for enc in encodings:
        try:
            return open(path, newline="", encoding=enc)
        except Exception as e:
            last_err = e

    raise last_err  # type: ignore[misc]


def run_final_master_duplicate_filter(
    clean_csv: str = "output_clean.csv",
    fail_csv: str = "output_fail.csv",
) -> None:
    """
    FINAL STEP:
      Compare output_clean.csv rows against the master DB and:
        - If (ApartmentNumber, Number, Street) triplet matches master → move to fail_csv as Duplicate
        - Otherwise keep in clean_csv

    Fix:
      Normalize merged sheet Number forms ("UnitA/12") so they match master triplets ("A","12").

    AUDIT PATCH:
      - Populate audit log event (via add_row_audit_fields) but DO NOT allow log-only columns
        to persist in output headers (even if older CSV headers had them).
      - Never write private/internal keys (anything starting with "_", e.g. _geocode_meta).
    """
    from GoogleSheets_Log import stage, log_warn, log_exception, decision

    try:
        # Local import to avoid import-order issues
        try:
            from GoogleSheets_Utils import add_row_audit_fields, _AUDIT_LOG_ONLY_KEYS  # type: ignore
        except Exception:
            add_row_audit_fields = None  # type: ignore
            _AUDIT_LOG_ONLY_KEYS = set()  # type: ignore

        stage(
            "Final master duplicate filter started",
            module=__name__,
            fn="run_final_master_duplicate_filter",
            extra={"clean_csv": clean_csv, "fail_csv": fail_csv},
        )

        try:
            _load_master_index.cache_clear()
        except Exception:
            pass

        _load_master_index()
        if not _MASTER_TRIPLET_SET:
            log_warn(
                "MASTER_INDEX_EMPTY_SKIPPING_FINAL_DUP_FILTER",
                module=__name__,
                fn="run_final_master_duplicate_filter",
                extra={"clean_csv": clean_csv, "fail_csv": fail_csv},
            )
            return

        if not os.path.exists(clean_csv):
            log_warn(
                "CLEAN_CSV_MISSING_SKIPPING_FINAL_DUP_FILTER",
                module=__name__,
                fn="run_final_master_duplicate_filter",
                extra={"clean_csv": clean_csv},
            )
            return

        with open(clean_csv, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            rows = list(reader)

        if not fieldnames:
            log_warn(
                "CLEAN_CSV_NO_HEADER_SKIPPING_FINAL_DUP_FILTER",
                module=__name__,
                fn="run_final_master_duplicate_filter",
                extra={"clean_csv": clean_csv},
            )
            return

        # --- Header safety: never persist log-only/audit/internal columns ---
        deny = set()
        try:
            deny.update(_AUDIT_LOG_ONLY_KEYS)  # type: ignore[arg-type]
        except Exception:
            pass
        deny.update({"_geocode_meta"})  # internal blob key (in case it ever landed in a header)

        safe_fieldnames = [
            k for k in fieldnames
            if k
            and not str(k).startswith("_")
            and k not in deny
        ]

        survivors: list[dict] = []
        dupes: list[dict] = []

        def _normalize_ap_num(ap: str, num: str) -> tuple[str, str]:
            ap = (ap or "").strip()
            num = (num or "").strip()
            if not num:
                return ap, num

            try:
                ap_guess, num_guess = _split_unit_house(num)
            except Exception:
                ap_guess = num_guess = None

            if num_guess:
                if (not ap) and ap_guess:
                    return ap_guess, num_guess
                try:
                    ap_norm = _strip_unit_prefix_for_match(ap)
                except Exception:
                    ap_norm = ap
                try:
                    ap_guess_norm = _strip_unit_prefix_for_match(ap_guess or "")
                except Exception:
                    ap_guess_norm = (ap_guess or "")
                if ap and ap_guess_norm and _canon_text_cached(ap_norm) == _canon_text_cached(ap_guess_norm):
                    return ap, num_guess

            return ap, num

        # Split survivors/dupes
        for row in rows:
            ap = (row.get("ApartmentNumber") or "").strip()
            num = (row.get("Number") or "").strip()
            st = (row.get("Street") or "").strip()

            if not (st and num):
                survivors.append(row)
                continue

            ap2, num2 = _normalize_ap_num(ap, num)
            trip = _canon_triplet(ap2, num2, st)

            if trip in _MASTER_TRIPLET_SET:
                r = dict(row)
                r["Final Status"] = "Duplicate"
                dupes.append(r)
            else:
                survivors.append(row)

        if not dupes:
            stage(
                "Final master duplicate filter finished (no duplicates)",
                module=__name__,
                fn="run_final_master_duplicate_filter",
                extra={"clean_csv": clean_csv, "fail_csv": fail_csv, "dupes": 0},
            )
            return

        # Populate audit fields just before write (safe even if already present)
        if callable(add_row_audit_fields):
            for r in survivors:
                try:
                    add_row_audit_fields(r)
                except Exception:
                    pass
            for r in dupes:
                try:
                    add_row_audit_fields(r)
                except Exception:
                    pass

        def _sanitize(row: dict) -> dict:
            # Only write allowed columns from safe_fieldnames
            return {k: (row.get(k, "") if k is not None else "") for k in safe_fieldnames}

        # Rewrite clean with survivors
        with open(clean_csv, "w", newline="", encoding="utf-8", buffering=1024 * 1024) as f:
            writer = csv.DictWriter(f, fieldnames=safe_fieldnames)
            writer.writeheader()
            for row in survivors:
                writer.writerow(_sanitize(row))

        # Append to fail (or create with header)
        write_header = True
        if os.path.exists(fail_csv) and os.path.getsize(fail_csv) > 0:
            write_header = False

        with open(
            fail_csv,
            "a" if not write_header else "w",
            newline="",
            encoding="utf-8",
            buffering=1024 * 1024,
        ) as f:
            writer = csv.DictWriter(f, fieldnames=safe_fieldnames)
            if write_header:
                writer.writeheader()
            for row in dupes:
                writer.writerow(_sanitize(row))

        decision(
            "FINAL_DUP_FILTER_MOVED",
            module=__name__,
            fn="run_final_master_duplicate_filter",
            extra={"moved": len(dupes), "clean_csv": clean_csv, "fail_csv": fail_csv},
        )

        stage(
            "Final master duplicate filter finished",
            module=__name__,
            fn="run_final_master_duplicate_filter",
            extra={"moved": len(dupes), "clean_csv": clean_csv, "fail_csv": fail_csv},
        )

    except Exception:
        log_exception(
            "FINAL_DUP_FILTER_EXCEPTION",
            module=__name__,
            fn="run_final_master_duplicate_filter",
            extra={"clean_csv": clean_csv, "fail_csv": fail_csv},
        )
        raise



def run_verify_fail_against_master(clean_csv="output_clean.csv",
                                   fail_csv="output_fail.csv"):
    """
    After run_final_master_duplicate_filter:
    - Re-check output_fail.csv against master DB.
    - Keep only true duplicates.
    - Any row that is NOT a true duplicate → move back to clean_csv.

    Parity fix:
    - Normalize merged Number forms ("UnitA/12") so they match master triplets ("A","12").
    - Normalize unit-prefix matching consistently (UnitA == A).

    AUDIT PATCH:
      - Populate audit log event (via add_row_audit_fields) but DO NOT allow log-only columns
        to persist in output headers (even if older CSV headers had them).
      - Never write private/internal keys (anything starting with "_", e.g. _geocode_meta).
    """
    from GoogleSheets_Log import stage, log_warn, log_exception, decision

    try:
        # Local import to avoid import-order issues
        try:
            from GoogleSheets_Utils import add_row_audit_fields, _AUDIT_LOG_ONLY_KEYS  # type: ignore
        except Exception:
            add_row_audit_fields = None  # type: ignore
            _AUDIT_LOG_ONLY_KEYS = set()  # type: ignore

        stage(
            "Verify-fail against master started",
            module=__name__,
            fn="run_verify_fail_against_master",
            extra={"clean_csv": clean_csv, "fail_csv": fail_csv},
        )

        try:
            _load_master_index.cache_clear()
        except Exception:
            pass
        _load_master_index()

        if not os.path.exists(fail_csv):
            log_warn(
                "VERIFY_FAIL_FAILCSV_MISSING",
                module=__name__,
                fn="run_verify_fail_against_master",
                extra={"fail_csv": fail_csv},
            )
            return

        with open(fail_csv, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            fieldnames = r.fieldnames or []
            fail_rows = list(r)

        if not fieldnames:
            log_warn(
                "VERIFY_FAIL_FAILCSV_NO_HEADER",
                module=__name__,
                fn="run_verify_fail_against_master",
                extra={"fail_csv": fail_csv},
            )
            return

        # --- Header safety: never persist log-only/audit/internal columns ---
        deny = set()
        try:
            deny.update(_AUDIT_LOG_ONLY_KEYS)  # type: ignore[arg-type]
        except Exception:
            pass
        deny.update({"_geocode_meta"})

        safe_fieldnames = [
            k for k in fieldnames
            if k
            and not str(k).startswith("_")
            and k not in deny
        ]

        def _normalize_ap_num(ap: str, num: str) -> tuple[str, str]:
            ap = (ap or "").strip()
            num = (num or "").strip()

            try:
                ap = _strip_unit_prefix_for_match(ap)
            except Exception:
                pass

            if not num:
                return ap, num

            try:
                ap_guess, num_guess = _split_unit_house(num)
            except Exception:
                ap_guess = num_guess = None

            if num_guess:
                try:
                    ap_guess_norm = _strip_unit_prefix_for_match(ap_guess or "")
                except Exception:
                    ap_guess_norm = (ap_guess or "")

                if (not ap) and ap_guess_norm:
                    return ap_guess_norm, num_guess

                if ap and ap_guess_norm and _canon_text_cached(ap) == _canon_text_cached(ap_guess_norm):
                    return ap, num_guess

            return ap, num

        keep_fail: list[dict] = []
        return_to_clean: list[dict] = []

        for row in fail_rows:
            ap = (row.get("ApartmentNumber") or "").strip()
            num = (row.get("Number") or "").strip()
            st = (row.get("Street") or "").strip()

            if not (st and num):
                return_to_clean.append(row)
                continue

            ap2, num2 = _normalize_ap_num(ap, num)
            trip = _canon_triplet(ap2, num2, st)

            if trip in _MASTER_TRIPLET_SET:
                keep_fail.append(row)
            else:
                return_to_clean.append(row)

        # Populate audit fields before write (safe even if already present)
        if callable(add_row_audit_fields):
            for r in keep_fail:
                try:
                    add_row_audit_fields(r)
                except Exception:
                    pass
            for r in return_to_clean:
                try:
                    add_row_audit_fields(r)
                except Exception:
                    pass

        def _sanitize(row: dict, fns: list[str]) -> dict:
            return {k: (row.get(k, "") if k is not None else "") for k in fns}

        # Write updated fail file (kept duplicates only)
        with open(fail_csv, "w", newline="", encoding="utf-8", buffering=1024 * 1024) as f:
            w = csv.DictWriter(f, fieldnames=safe_fieldnames)
            w.writeheader()
            for row in keep_fail:
                w.writerow(_sanitize(row, safe_fieldnames))

        # Append returned rows back to clean file
        if return_to_clean:
            clean_rows: list[dict] = []
            if os.path.exists(clean_csv):
                with open(clean_csv, newline="", encoding="utf-8") as f:
                    r = csv.DictReader(f)
                    clean_fieldnames = r.fieldnames or safe_fieldnames
                    clean_rows = list(r)
            else:
                clean_fieldnames = safe_fieldnames

            # Clean file should also never emit private/internal keys or audit-only keys
            clean_deny = set(deny)
            clean_safe_fieldnames = [
                k for k in clean_fieldnames
                if k
                and not str(k).startswith("_")
                and k not in clean_deny
            ]

            if callable(add_row_audit_fields):
                for r in clean_rows:
                    try:
                        add_row_audit_fields(r)
                    except Exception:
                        pass

            with open(clean_csv, "w", newline="", encoding="utf-8", buffering=1024 * 1024) as f:
                w = csv.DictWriter(f, fieldnames=clean_safe_fieldnames)
                w.writeheader()
                for row in clean_rows:
                    w.writerow(_sanitize(row, clean_safe_fieldnames))
                for row in return_to_clean:
                    w.writerow(_sanitize(row, clean_safe_fieldnames))

        decision(
            "VERIFY_FAIL_DONE",
            module=__name__,
            fn="run_verify_fail_against_master",
            extra={"kept_fail": len(keep_fail), "returned_to_clean": len(return_to_clean)},
        )

        stage(
            "Verify-fail against master finished",
            module=__name__,
            fn="run_verify_fail_against_master",
            extra={"kept_fail": len(keep_fail), "returned_to_clean": len(return_to_clean)},
        )

    except Exception:
        log_exception(
            "VERIFY_FAIL_EXCEPTION",
            module=__name__,
            fn="run_verify_fail_against_master",
            extra={"clean_csv": clean_csv, "fail_csv": fail_csv},
        )
        raise





def _init_street_whitelist_from_master():
    """
    Build a whitelist of known Street names from the master DB/CSV.

    IMPORTANT (behavior fix):
    - Attempt this at most once per process, even if master files are missing.
      Otherwise _repair_corrupted_street() can call this for every row and spam logs.

    Portable: uses resolved master paths under APP_ROOT/Master.
    Safe: if master files aren't present yet, it logs a warning once and returns.

    Robustness fix:
    - CSV fallback uses encoding fallbacks via _open_csv_text_best_effort()
      (so cp1252/latin-1 master exports don't break).
    """
    global _STREET_WHITELIST_INIT_ATTEMPTED

    # One-time attempt guard (prevents per-row rebuild attempts)
    if _STREET_WHITELIST_INIT_ATTEMPTED:
        return
    _STREET_WHITELIST_INIT_ATTEMPTED = True

    try:
        from GoogleSheets_Log import stage, log_warn

        stage(
            "Building street whitelist from master",
            module=__name__,
            fn="_init_street_whitelist_from_master",
        )

        # Resolve runtime-safe paths
        csv_path, db_path = resolve_master_paths()

        # Ensure DB exists if CSV exists (portable behavior)
        try:
            _ensure_sqlite_from_csv()
        except Exception:
            pass

        # Re-resolve again in case the CSV choice changed
        csv_path, db_path = resolve_master_paths()

        added = 0

        # Prefer the DB; fallback to CSV
        if db_path.exists():
            conn = sqlite3.connect(str(db_path), timeout=30.0)
            try:
                cur = conn.cursor()
                for (st,) in cur.execute("SELECT DISTINCT Street FROM addresses"):
                    if st:
                        v = _strip_macrons(st).title().strip()
                        if v and v not in _STREET_WHITELIST:
                            _STREET_WHITELIST.add(v)
                            added += 1
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

        elif csv_path.exists():
            f = None
            try:
                f = _open_csv_text_best_effort(csv_path)
                r = csv.DictReader(f)
                for row in r:
                    st = (row.get("Street") or "").strip()
                    if st:
                        v = _strip_macrons(st).title().strip()
                        if v and v not in _STREET_WHITELIST:
                            _STREET_WHITELIST.add(v)
                            added += 1
            finally:
                try:
                    if f is not None:
                        f.close()
                except Exception:
                    pass

        else:
            # This matches what your log shows: master not found.
            log_warn(
                "MASTER_CSV_NOT_FOUND_FOR_STREET_WHITELIST",
                module=__name__,
                fn="_init_street_whitelist_from_master",
                extra={"expected_csv": str(csv_path), "expected_db": str(db_path)},
            )

        stage(
            "Street whitelist ready",
            module=__name__,
            fn="_init_street_whitelist_from_master",
            extra={"count": len(_STREET_WHITELIST), "added": int(added)},
        )

    except Exception:
        # Never let whitelist building break runs
        try:
            from GoogleSheets_Log import log_exception
            log_exception("STREET_WHITELIST_INIT_FAILED", module=__name__, fn="_init_street_whitelist_from_master")
        except Exception:
            pass
        return




def _repair_corrupted_street(s: str) -> str:
    """
    Repair street text using:
      1) explicit corruption map
      2) character cleanup + macron stripping
      3) close-match against a whitelist built from the master list

    Behavior fix vs current split version:
    - Only attempt whitelist initialization once per process (guarded by
      _STREET_WHITELIST_INIT_ATTEMPTED), so missing master files don't cause
      per-row slowdowns/log spam.
    """
    if not s:
        return ""

    s = s.strip()
    if s in _STREET_CORRUPTION_MAP:
        return _STREET_CORRUPTION_MAP[s]

    # One-time lazy init (won't repeat per row if master missing)
    if not _STREET_WHITELIST_INIT_ATTEMPTED and not _STREET_WHITELIST:
        try:
            _init_street_whitelist_from_master()
        except Exception:
            # Never block repairs if master isn't available
            pass

    cleaned = _BAD_STREET_CHARS_RX.sub("", s)
    cleaned = _strip_macrons(cleaned).strip()
    if not cleaned:
        return ""

    if _STREET_WHITELIST:
        cand = difflib.get_close_matches(cleaned.title(), _STREET_WHITELIST, n=1, cutoff=0.92)
        if cand:
            return cand[0]

    return cleaned.title()



# --- Logging: wrap functions defined in THIS module (CALL/RETURN/EXCEPTION) ---
from GoogleSheets_Log import autowrap_module  # noqa: E402

try:
    autowrap_module(__name__, include_private=True, only_defined_here=True)
except TypeError:
    # Backward compatible with older GoogleSheets_Log.autowrap_module signatures
    autowrap_module(__name__, include_private=True)
