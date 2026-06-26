# Python Expert
# Clean_GoogleSheets.py
# ------------------------------------------------------
# Google Sheets flows split from main, with a small submenu
# ------------------------------------------------------

import os
import re
import threading
import unicodedata
import csv
from pathlib import Path
from functools import lru_cache
import shutil
from datetime import datetime
from collections import Counter
import sqlite3  # <-- added
import difflib

# Progress bars (tqdm); safe fallback if not installed
try:
    from tqdm import tqdm
except Exception:  # pragma: no cover
    def tqdm(iterable=None, **kwargs):
        return iterable if iterable is not None else range(0)

# Also index house-only numbers per (Street, Suburb) for fallback duplicate checks
_MASTER_STSUB_TO_HOUSES: dict[tuple[str, str], set[str]] = {}

# --- Small regex helpers used in hot paths ---
HOUSE_ONLY_HEAD_RX = re.compile(r'^\s*(\d+[A-Za-z]?)')
SLASH_DIGITS_RX    = re.compile(r'/\s*(\d+)')

# Display strings for house-only matches → used to explain which master row we matched
# Key: (canon(Street), canon(Suburb), canon(house_only))  Value: set[str display]
_MASTER_HOUSEONLY_TO_ADDRS: dict[tuple[str, str, str], set[str]] = {}

# ---- Master-index helpers / globals ---------------------------------
# (Street, Suburb) presence set
_MASTER_STREET_SUBURB_SET: set[tuple[str, str]] = set()

# Canonical (ApartmentNumber, Number, Street) triplets present in master DB/CSV
# This is what we now use for strict duplicate detection:
#   duplicate ⇔ same ApartmentNumber + Number + Street (after canonicalisation)
_MASTER_TRIPLET_SET: set[tuple[str, str, str]] = set()


def _canon_street_suburb(street: str, suburb: str) -> tuple[str, str]:
    c = _canon_text_cached
    return (c((street or "").strip()), c((suburb or "").strip()))

# 👇 Robust import of the core module (Clean_NewWorldScheduler)
try:
    import Clean_NewWorldScheduler as core
except ModuleNotFoundError:
    # Fallback: load by explicit path next to this file
    import importlib.util, sys
    _here = os.path.dirname(__file__)
    _path = os.path.join(_here, "Clean_NewWorldScheduler.py")
    spec = importlib.util.spec_from_file_location("Clean_NewWorldScheduler", _path)
    if not spec or not spec.loader:
        raise
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
    sys.modules["Clean_NewWorldScheduler"] = core

_COMMON_SUFFIX = {
    "road","rd","street","st","avenue","ave","drive","dr","place","pl","terrace","ter","way","lane","ln",
    "court","ct","crescent","cres","boulevard","blvd","close","cl","grove","gr","heights","hts","parade","pde",
    "green","parkway","pkwy","highway","hwy","gully","gl","walk","wk","trail","trl","square","sq","quay","qy","point","pt"
}

# ---------------------------------------------------------------------
# Performance additions: precompiled regex + cached helpers
# ---------------------------------------------------------------------
TOKEN_RX = re.compile(r"[A-Za-z0-9']+")
COORD_RX = re.compile(r"-?\d+(?:\.\d+)?")
TRAILING_NZ_POSTCODE_RX = re.compile(r"\b\d{4}\s*$")
SEP_SQUASH_RX_1 = re.compile(r'\s*([/|])\s*(?=[/|])')
SEP_SQUASH_RX_2 = re.compile(r'^\s*[/|]+\s*')
SEP_SQUASH_RX_3 = re.compile(r'\s*[/|]+\s*$')
LANG_LETTERS_ONLY_RX = re.compile(r'[^a-z]+')

# ✅ New: robust "New Street(s)" detector
NEW_STREET_DETECT_RX = re.compile(r"\bnew\s*street(s)?\b", re.IGNORECASE)

# --- add near the other module-level constants ---
_SUPPRESS_TEMP_DIR_WARNINGS = True

# Unit flip patterns
HOUSE_FLIP_A = re.compile(r'^\s*unit\s*([A-Za-z0-9]+)\s*/\s*(\d+[A-Za-z]?)\s*$', flags=re.IGNORECASE)
HOUSE_FLIP_B = re.compile(r'^\s*(\d+[A-Za-z]?)\s*/\s*unit\s*([A-Za-z0-9]+)\s*$', flags=re.IGNORECASE)


COMMON_SUFFIX_LOWER = _COMMON_SUFFIX  # already lowercased entries


def _strip_macrons(s: str) -> str:
    """
    Strip macrons/diacritics from text so 'Tāmaki' -> 'Tamaki'.
    """
    if not s:
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )

@lru_cache(maxsize=8192)
def _canon_text_cached(s: str) -> str:
    s = (s or "").strip().lower()
    s = TRAILING_NZ_POSTCODE_RX.sub("", s)
    s = _strip_macrons(s)
    return re.sub(r"[^a-z0-9]+", "", s)

def _looks_like_just_suburb(geo_street: str, geo_suburb: str) -> bool:
    """True when geocoded street is effectively the same as the suburb name."""
    return _canon_text_cached(geo_street) == _canon_text_cached(geo_suburb)

# --- Routing helpers (updated) ------------------------------------------------
def _notes_has_new_street_ci(s: str) -> bool:
    return bool(NEW_STREET_DETECT_RX.search(s or ""))

def _stemmed_outputs_for(input_path: str | Path):
    """
    Returns (output_clean, output_fail) derived from the input filename stem.
    e.g., input_googlesheets.new.csv -> output_clean.new.csv / output_fail.new.csv
    """
    p = Path(input_path)
    if p.stem == "input_googlesheets":
        stem = "full"
    else:
        stem = p.stem.split("input_googlesheets.", 1)[-1] if p.stem.startswith("input_googlesheets.") else p.stem
    return (f"output_clean.{stem}.csv", f"output_fail.{stem}.csv")


def _split_input_by_new_street(input_file: str = "input_googlesheets.csv"):
    """
    (Legacy helper; not used by routed flows anymore)
    Produces two CSVs next to input:
      - input_googlesheets.new.csv   (Notes contains 'New Street')
      - input_googlesheets.other.csv (everyone else)
    Returns tuple(paths). If input missing, returns (None, None).
    """
    if not os.path.exists(input_file):
        return None, None

    base = Path(input_file)
    new_path   = str(base.with_name("input_googlesheets.new.csv"))
    other_path = str(base.with_name("input_googlesheets.other.csv"))

    with open(input_file, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        rows = list(r)
        fieldnames = r.fieldnames or []

    with open(new_path, "w", newline="", encoding="utf-8") as fn, \
         open(other_path, "w", newline="", encoding="utf-8") as fo:
        wn = csv.DictWriter(fn, fieldnames=fieldnames); wn.writeheader()
        wo = csv.DictWriter(fo, fieldnames=fieldnames); wo.writeheader()
        for row in rows:
            (wn if _notes_has_new_street_ci(row.get("Notes")) else wo).writerow(row)

    return new_path, other_path
# -----------------------------------------------------------------------------


# --- Final-number flip (use core's helper if available) -----------------------
def _flip_units_inplace(rows: list[dict]) -> int:
    """
    Flip 'Number' values just before writing.
      • Case A:  UnitX/NN   →  NN/UnitX
      • Case B:  NN/UnitX   →  UnitX/NN
    Handles lettered house numbers (e.g., 61A), extra spaces, and hyphen variants.
    Uses core.flip_units_for_rows if available.
    Returns the number of flipped rows.
    """
    if hasattr(core, "flip_units_for_rows"):
        try:
            return core.flip_units_for_rows(rows)  # mutates in-place, returns count
        except Exception:
            pass

    flipped = 0
    if not rows:
        return 0

    for r in rows:
        num = (r.get("Number") or "").strip()
        if not num:
            continue

        m = HOUSE_FLIP_A.match(num)
        if m:
            unit, house = m.group(1), m.group(2)
            r["Number"] = f"{house}/Unit{unit.upper()}"
            flipped += 1
            continue

        m = HOUSE_FLIP_B.match(num)
        if m:
            house, unit = m.group(1), m.group(2)
            r["Number"] = f"Unit{unit.upper()}/{house}"
            flipped += 1
            continue

    return flipped


def _tokens_core(s: str) -> set:
    toks = {t for t in re.findall(r"[A-Za-z0-9]+", (s or "").lower()) if len(t) > 2}
    return {t for t in toks if not t.isdigit() and t not in _COMMON_SUFFIX}

# ---- Shared helpers (coords + notes merge) -----------------------------------
_COORD_RX = COORD_RX

def _has_digits(s: str) -> bool:
    return bool(_COORD_RX.search((s or "")))

def _coords_in_auckland(lat_str: str, lon_str: str) -> bool:
    try:
      if not (lat_str and lon_str and _has_digits(lat_str) and _has_digits(lon_str)):
          return False
      la, lo = float(lat_str), float(lon_str)
      if hasattr(core, "is_in_auckland"):
          return core.is_in_auckland(la, lo)
      return True  # accept numeric coords if checker not available
    except Exception:
      return False

# 1) Build street whitelist after master index loads
_STREET_WHITELIST = set()

def _init_street_whitelist_from_master():
    try:
        # Prefer the DB; fallback to CSV
        if MASTER_DB_PATH.exists():
            import sqlite3
            conn = sqlite3.connect(str(MASTER_DB_PATH))
            try:
                cur = conn.cursor()
                for (st,) in cur.execute("SELECT DISTINCT Street FROM addresses"):
                    if st:
                        _STREET_WHITELIST.add(_strip_macrons(st).title().strip())
            finally:
                conn.close()
        elif MASTER_CSV_PATH.exists():
            import csv
            with open(MASTER_CSV_PATH, newline="", encoding="utf-8") as f:
                r = csv.DictReader(f)
                for row in r:
                    st = (row.get("Street") or "").strip()
                    if st:
                        _STREET_WHITELIST.add(_strip_macrons(st).title().strip())
    except Exception:
        pass

_init_street_whitelist_from_master()

_STREET_CORRUPTION_MAP = {
    # Add any known 1:1 street fixes you encounter
    # "Fencotie Place": "Fencottie Place",
}

_BAD_STREET_CHARS_RX = re.compile(r"[^A-Za-z0-9'\-\s]")

def _repair_corrupted_street(s: str) -> str:
    if not s:
        return ""
    s = s.strip()
    if s in _STREET_CORRUPTION_MAP:
        return _STREET_CORRUPTION_MAP[s]

    cleaned = _BAD_STREET_CHARS_RX.sub("", s)
    cleaned = _strip_macrons(cleaned).strip()
    if not cleaned:
        return ""

    if _STREET_WHITELIST:
        cand = difflib.get_close_matches(cleaned.title(), _STREET_WHITELIST, n=1, cutoff=0.92)
        if cand:
            return cand[0]

    return cleaned.title()


def _merge_notes(notes: str, notes_from_pub: str) -> str:
    a = (notes or "").strip()
    b = (notes_from_pub or "").strip()
    if not b:
        return a
    canon = lambda s: re.sub(r"\s+", " ", s).strip().lower()
    if a and canon(b) in canon(a):
        return a
    return f"{a} / {b}" if a else b
# ------------------------------------------------------------------------------


def _notes_has_new_street(notes: str) -> bool:
    """True if 'New Street' phrase appears in Notes (case-insensitive)."""
    return bool(NEW_STREET_DETECT_RX.search(notes or ""))

def _invoke_core_option7_new_streets(clean_path: str, fail_path: str):
    """
    Try to call New World Scheduler.py 'Option 7' entry point with (clean, fail) paths.
    Tries several common function names; falls back to the polygon split with a flag.
    """
    candidate_names = [
        "run_clean_split_new_streets_full_geocode",
        "clean_split_new_streets_full_geocode",
        "option7_clean_split_new_streets",
        "run_option_7_new_streets",
        "run_new_streets_full_geocode",
    ]

    for name in candidate_names:
        fn = getattr(core, name, None)
        if callable(fn):
            try:
                return fn(clean_path, fail_path)
            except TypeError:
                try:
                    return fn()
                except Exception:
                    pass
            except Exception:
                pass

    # Fallback: try standard splitter with a feature flag if your core supports it
    split = getattr(core, "split_cleaned_by_polygon_and_include_failed", None)
    if callable(split):
        try:
            return split(clean_path, fail_path, kml_dir="KML Boundaries", new_streets_only=True)
        except TypeError:
            return split(clean_path, fail_path, kml_dir="KML Boundaries")

    print("❌ Could not find a core handler for 'Option 7 — New Streets'. "
          "Please expose one of the expected functions in Clean_NewWorldScheduler.py.")


_SUBURB_BASE = Path("New_Addresses_By_Suburb")

def _run_split_to_dir(out_clean: str, out_fail: str, *, label: str, kml_dir: str = "KML Boundaries") -> Path:
    """
    Runs the core split (writing into New_Addresses_By_Suburb), then moves that folder
    to a stable temp folder based on `label`. For label NEW/OTHER we *clear and reuse*
    'New_Addresses_By_Suburb__NEW' / '__OTHER' (no timestamp). For any other label,
    we keep your previous timestamp fallback.
    Returns the path of the destination folder.
    """
    # 1) Run the core split (writes into New_Addresses_By_Suburb)
    core.split_cleaned_by_polygon_and_include_failed(out_clean, out_fail, kml_dir=kml_dir)

    src = _SUBURB_BASE
    if not src.exists():
        # Nothing to move; return the intended dst path for the caller’s awareness
        return Path(f"{_SUBURB_BASE}__{label}")

    # 2) Decide destination
    if label.upper() == "NEW":
        dst = _SUBURB_DIR_NEW
        _clear_dir_contents(dst)  # clear contents before moving fresh results in
    elif label.upper() == "OTHER":
        dst = _SUBURB_DIR_OTHER
        _clear_dir_contents(dst)
    else:
        dst = Path(f"{_SUBURB_BASE}__{label}")
        if dst.exists():
            # For non-NEW/OTHER keep your timestamp strategy
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dst = Path(f"{_SUBURB_BASE}__{label}__{stamp}")

    # 3) Move fresh results in
    # If dst exists, ensure it's truly empty and removed so move can succeed
    if dst.exists():
        _clear_dir_contents(dst)
        try:
            dst.rmdir()
        except Exception:
            pass

    # Fast path: try a plain move
    try:
        shutil.move(str(src), str(dst))
        return dst
    except Exception:
        # Fallback: copy contents, then remove the source
        shutil.copytree(src, dst, dirs_exist_ok=True)
        shutil.rmtree(src, ignore_errors=True)
        return dst


def _merge_suburb_dirs(sources: list[Path], dest: Path) -> None:
    """
    Merge multiple 'New_Addresses_By_Suburb__*' folders into a final 'New_Addresses_By_Suburb'.
    - Combines CSVs by filename; if the same suburb file exists in multiple sources,
      rows are appended into the one in `dest`.
    - 'Failed_Output.csv' files are appended into a single file in `dest`.
    """
    dest.mkdir(exist_ok=True)
    for src in sources:
        if not src.exists():
            continue
        for p in src.glob("*.csv"):
            target = dest / p.name
            if not target.exists():
                shutil.copy2(p, target)
            else:
                # append rows (skip header)
                with open(target, "a", newline="", encoding="utf-8") as fout, \
                     open(p, "r", newline="", encoding="utf-8") as fin:
                    rin = csv.reader(fin)
                    rout = csv.writer(fout)
                    try:
                        _ = next(rin)  # consume header
                    except StopIteration:
                        continue
                    for row in rin:
                        rout.writerow(row)

# ---------------------------------------------------------------------
# Geocoder memoization (biggest CPU/network win with repeated addresses)
# ---------------------------------------------------------------------
@lru_cache(maxsize=8192)
def _gl_cached(addr: str):
    try:
        return core.get_lat_long(addr)
    except Exception:
        return None

@lru_cache(maxsize=8192)
def _nominatim_cached(addr: str):
    try:
        fn = getattr(core, "forward_geocode_nominatim", None)
        return fn(addr) if callable(fn) else None
    except Exception:
        return None

@lru_cache(maxsize=8192)
def _photon_cached(addr: str):
    try:
        fn = getattr(core, "forward_geocode_photon", None)
        return fn(addr) if callable(fn) else None
    except Exception:
        return None

def run_master_db_duplicate_audit(out_fail: str = "output_fail.csv") -> None:
    """
    Option 5: 📚 Check Master DB For Duplicates (internal audit)
    - Reads Auckland_East_Mandarin_Addresses.db (or rebuilds it from CSV if needed)
    - Flags duplicates using same rules as options 1–4, but *within the master DB*:
        • (ApartmentNumber, Number, Street, Suburb) appears >1 → "Duplicate"
        • Same (ApartmentNumber, Number, Street) across >1 suburb → "Duplicate - Different Suburb"
    - Writes ONLY duplicates to output_fail.csv. Does NOT write output_clean.csv.
    """
    # Ensure DB exists / rebuilt from CSV if newer
    _ensure_sqlite_from_csv(MASTER_CSV_PATH, MASTER_DB_PATH)
    if not MASTER_DB_PATH.exists():
        print(f"❌ Master DB not found: {MASTER_DB_PATH}")
        return

    # Collect master rows
    rows: list[dict] = []
    try:
        conn = sqlite3.connect(str(MASTER_DB_PATH))
        try:
            cur = conn.cursor()
            for ap, num, st, sub in cur.execute("SELECT ApartmentNumber, Number, Street, Suburb FROM addresses"):
                rows.append({
                    "ApartmentNumber": ap or "",
                    "Number": (num or "").strip(),
                    "Street": (st or "").strip(),
                    "Suburb": (sub or "").strip(),
                })
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Could not read master DB: {e}")
        return

    if not rows:
        print("ℹ️ Master DB has no rows to audit.")
        return

    # Build duplicate signals (canonicalized)
    c = _canon_text_cached
    from collections import Counter as _Counter, defaultdict
    k4_counts = _Counter()
    triplet_to_suburbs: dict[tuple[str,str,str], set[str]] = defaultdict(set)
    triplet_to_rows: dict[tuple[str,str,str], list[int]] = defaultdict(list)

    for idx, r in enumerate(rows):
        k3 = (_canon_text_cached((r["ApartmentNumber"] or "").strip()),
              _canon_text_cached((r["Number"]          or "").strip()),
              _canon_text_cached((r["Street"]          or "").strip()))
        csub = _canon_text_cached((r["Suburb"] or "").strip())
        k4 = (k3[0], k3[1], k3[2], csub)
        k4_counts[k4] += 1
        triplet_to_suburbs[k3].add(csub)
        triplet_to_rows[k3].append(idx)

    # Prepare writer
    fieldnames = [
        "Old Number", "Unit",
        "Old Street",
        "ApartmentNumber", "Number", "Street",
        "Suburb", "PostalCode", "State",
        "Status", "Final Status",
        "Latitude", "Longitude",
        "Type", "Language", "Notes", "Other Notes",
    ]
    written_idx: set[int] = set()
    dup_total = 0

    with open(out_fail, "w", newline="", encoding="utf-8", buffering=1024*1024) as fout_f:
        wf = csv.DictWriter(fout_f, fieldnames=fieldnames); wf.writeheader()

        # 1) Exact duplicates on (AP, Number, Street, Suburb) → "Duplicate"
        for idx, r in enumerate(rows):
            k3 = (c(r["ApartmentNumber"]), c(r["Number"]), c(r["Street"]))
            csub = c(r["Suburb"])
            k4 = (k3[0], k3[1], k3[2], csub)
            if k4_counts[k4] > 1:
                rec = {
                    "Old Number": "",
                    "Unit": "",
                    "Old Street": "",
                    "ApartmentNumber": r["ApartmentNumber"],
                    "Number": _combine_unit_and_number(r["ApartmentNumber"], r["Number"]),
                    "Street": gs_strip_leading_duplicate_number_from_street(
                        _combine_unit_and_number(r["ApartmentNumber"], r["Number"]),
                        r["Street"]
                    ),
                    "Suburb": _canon_suburb_sheets(r["Suburb"]),
                    "PostalCode": _postal_for_suburb_sheets(r["Suburb"]),
                    "State": "Auckland",
                    "Status": "",
                    "Final Status": "Duplicate",
                    "Latitude": "",
                    "Longitude": "",
                    "Type": "",
                    "Language": "",
                    "Notes": "",
                    "Other Notes": "Dup basis: exact",
                }
                # Keep number formatting consistent (flip before write)
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
                written_idx.add(idx)
                dup_total += 1

        # 2) Different-suburb duplicates on (AP, Number, Street) → "Duplicate - Different Suburb"
        for k3, sub_set in triplet_to_suburbs.items():
            if len([s for s in sub_set if s]) > 1:
                for idx in triplet_to_rows[k3]:
                    if idx in written_idx:
                        continue  # already written as exact duplicate
                    r = rows[idx]
                    rec = {
                        "Old Number": "",
                        "Unit": "",
                        "Old Street": "",
                        "ApartmentNumber": r["ApartmentNumber"],
                        "Number": _combine_unit_and_number(r["ApartmentNumber"], r["Number"]),
                        "Street": gs_strip_leading_duplicate_number_from_street(
                            _combine_unit_and_number(r["ApartmentNumber"], r["Number"]),
                            r["Street"]
                        ),
                        "Suburb": _canon_suburb_sheets(r["Suburb"]),
                        "PostalCode": _postal_for_suburb_sheets(r["Suburb"]),
                        "State": "Auckland",
                        "Status": "",
                        "Final Status": "Duplicate - Different Suburb",
                        "Latitude": "",
                        "Longitude": "",
                        "Type": "",
                        "Language": "",
                        "Notes": "",
                        "Other Notes": "Dup basis: exact-triplet",
                    }
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
                    written_idx.add(idx)
                    dup_total += 1

    if dup_total:
        print(f"✅ Master Database Audit Complete. {dup_total} duplicate row(s) written to '{out_fail}'.")
    else:
        print("✅ Master Database Audit Complete. No Duplicates Found.")


def _summarize_final_status(clean_csv: str = "output_clean.csv",
                            fail_csv: str = "output_fail.csv",
                            *,
                            print_breakdown: bool = True) -> dict:
    """
    Print + return a compact summary of Final Status results based on the merged outputs.
      - 'Pass' is counted from output_clean.csv
      - All other statuses are counted from output_fail.csv
    Returns a dict: {"total": int, "pass": int, "failed": int, "by_status": dict[str,int]}
    """
    from collections import Counter as _Counter

    counts = _Counter()
    total_clean = total_fail = 0

    # Passes (clean)
    if os.path.exists(clean_csv):
        try:
            with open(clean_csv, newline="", encoding="utf-8") as f:
                r = csv.DictReader(f)
                for _ in r:
                    total_clean += 1
            counts["Pass"] = total_clean
        except Exception:
            pass

    # Fails (by Final Status)
    if os.path.exists(fail_csv):
        try:
            with open(fail_csv, newline="", encoding="utf-8") as f:
                r = csv.DictReader(f)
                for row in r:
                    total_fail += 1
                    status = (row.get("Final Status") or "Fail").strip() or "Fail"
                    counts[status] += 1
        except Exception:
            pass

    total_all = total_clean + total_fail

    if print_breakdown:
        print("\n📊 Run Summary:")
        print(f"Total Rows: {total_all}")
        if total_clean:
            print(f"✅ Pass (Clean): {counts.get('Pass', 0)}")
        print(f"❌ Total Failed: {total_fail}")  # <-- ✅ NEW

        if total_fail:
            # in _summarize_final_status
            ordered = [
                "Duplicate",
                "Duplicate - input_googlesheets",
                "Duplicate - Different Suburb",
                "Bad Geocode",
                "Fail",
            ]

            seen = set()
            for key in ordered:
                if counts.get(key):
                    print(f"• {key}: {counts[key]}")
                    seen.add(key)
            # any other fail statuses not in the preferred order
            for key, val in sorted(counts.items()):
                if key in seen or key == "Pass":
                    continue
                if val:
                    print(f"• {key}: {val}")
        print()

    # structured return is handy for tests / logs
    by_status = dict(counts)
    return {
        "total": total_all,
        "pass": total_clean,
        "failed": total_fail,
        "by_status": by_status,
    }

_UNIT_FIRST_RX = re.compile(r'^\s*unit\s*([A-Za-z0-9]+)\s*/\s*(\d+[A-Za-z]?)\s*$', re.IGNORECASE)
_HOUSE_FIRST_RX = re.compile(r'^\s*(\d+[A-Za-z]?)\s*/\s*unit\s*([A-Za-z0-9]+)\s*$', re.IGNORECASE)

def _split_unit_house(num: str) -> tuple[str, str]:
    """
    Parse 'Number' into (ApartmentNumber, HouseNumber).
    Returns ('', house) if there's no unit. Keeps letter suffix on house (e.g., '61A').
    """
    s = (num or "").strip()
    if not s:
        return ("", "")
    m = _UNIT_FIRST_RX.match(s)
    if m:
        unit = m.group(1).upper()
        house = m.group(2)
        return (f"Unit{unit}", house)
    m = _HOUSE_FIRST_RX.match(s)
    if m:
        house = m.group(1)
        unit = m.group(2).upper()
        return (f"Unit{unit}", house)

    # Fall back: normalize then retry once
    s2 = normalize_number(s)  # your canonicalizer (may produce UnitX/NN)
    m = _UNIT_FIRST_RX.match(s2)
    if m:
        unit = m.group(1).upper()
        house = m.group(2)
        return (f"Unit{unit}", house)

    # If it's just a house number like '611' or '61A'
    if re.match(r'^\d+[A-Za-z]?$', s):
        return ("", s)

    return ("", s)  # unrecognized patterns treated as house-only


def _split_into_final_folder(out_clean: str, out_fail: str, *, kml_dir: str = "KML Boundaries") -> None:
    """
    (Kept for compatibility; routed flows below now use temp dir pattern instead.)
    Run the core splitter so that all results end up in the single
    'New_Addresses_By_Suburb' folder. If the folder already exists,
    we snapshot its current CSVs in memory, run the splitter (which may
    overwrite files), then append the snapshot back so the folder contains
    BOTH old and new results. No temp directories are created.
    """
    dest = _SUBURB_BASE

    def _snapshot_folder(folder: Path):
        """
        Returns dict: {filename -> (header:list[str], rows:list[list[str]])}
        """
        snap = {}
        if not folder.exists():
            return snap
        for p in folder.glob("*.csv"):
            with open(p, "r", newline="", encoding="utf-8") as f:
                r = csv.reader(f)
                try:
                    header = next(r)
                except StopIteration:
                    header, rows = [], []
                else:
                    rows = [row for row in r]
            snap[p.name] = (header, rows)
        return snap

    snapshot = _snapshot_folder(dest)
    core.split_cleaned_by_polygon_and_include_failed(out_clean, out_fail, kml_dir=kml_dir)

    for fname, (header, rows) in snapshot.items():
        target = dest / fname
        if not rows and not header:
            continue
        if target.exists():
            with open(target, "a", newline="", encoding="utf-8") as fout:
                w = csv.writer(fout)
                for row in rows:
                    w.writerow(row)
        else:
            with open(target, "w", newline="", encoding="utf-8") as fout:
                w = csv.writer(fout)
                if header:
                    w.writerow(header)
                for row in rows:
                    w.writerow(row)


# ---------------------------------------------------------------------
# Master list (Auckland East Mandarin Territory Addresses) integration
# ---------------------------------------------------------------------
MASTER_CSV_DIR = Path(r"C:\script\Auckland East Mandarin Territory Addresses")
MASTER_CSV_PATH = MASTER_CSV_DIR / "Auckland East Mandarin Territory Addresses.csv"
MASTER_DB_PATH  = MASTER_CSV_DIR / "Auckland_East_Mandarin_Addresses.db"

def _canon_triplet(ap_num: str, number: str, street: str) -> tuple[str, str, str]:
    """Canonical triplet for (ApartmentNumber, Number, Street)."""
    c = _canon_text_cached
    return (c((ap_num or "").strip()),
            c((number or "").strip()),
            c((street or "").strip()))

def _ensure_sqlite_from_csv(csv_path: Path = MASTER_CSV_PATH, db_path: Path = MASTER_DB_PATH) -> None:
    """
    Build/update a small SQLite DB from the master CSV if needed.
    Rebuild when DB missing or CSV is newer.
    Expected columns (case-insensitive): ApartmentNumber, Number, Street, Suburb
    Now prints progress so you can see what's happening.
    """
    try:
        if not csv_path.exists():
            print(f"ℹ️  Master CSV not found: {csv_path}")
            return

        needs_rebuild = (not db_path.exists() or csv_path.stat().st_mtime > db_path.stat().st_mtime)
        if not needs_rebuild:
            # No rebuild required, but we still report status for visibility
            try:
                rows_hint = sum(1 for _ in open(csv_path, newline="", encoding="utf-8")) - 1
            except Exception:
                rows_hint = "?"
            print(f"📚 Master Database Up-To-Date")
            return

        db_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"🛠️  Rebuilding Master DB from CSV\n    CSV: {csv_path}\n    DB : {db_path}")

        conn = sqlite3.connect(str(db_path))
        try:
            cur = conn.cursor()
            print("   • Dropping Old Table (if exists)…")
            cur.execute("DROP TABLE IF EXISTS addresses")

            print("   • Creating Table…")
            cur.execute("""
                CREATE TABLE addresses(
                    ApartmentNumber TEXT,
                    Number          TEXT,
                    Street          TEXT,
                    Suburb          TEXT
                )
            """)

            # Bulk insert from CSV (with a tiny progress print)
            inserted = 0
            print("   • Reading CSV & Inserting…")
            with open(csv_path, newline="", encoding="utf-8") as f:
                r = csv.DictReader(f)
                rows = []
                for row in r:
                    rows.append((
                        row.get("ApartmentNumber",""),
                        row.get("Number",""),
                        row.get("Street",""),
                        row.get("Suburb",""),
                    ))
                    if len(rows) >= 50_000:
                        cur.executemany("INSERT INTO addresses VALUES (?,?,?,?)", rows)
                        inserted += len(rows)
                        print(f"     - Inserted {inserted} rows…")
                        rows.clear()
                if rows:
                    cur.executemany("INSERT INTO addresses VALUES (?,?,?,?)", rows)
                    inserted += len(rows)
                    print(f"     - Inserted {inserted} rows (final batch).")

            print("   • Creating Indexes…")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ans       ON addresses(ApartmentNumber, Number, Street)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_all       ON addresses(ApartmentNumber, Number, Street, Suburb)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_st_suburb ON addresses(Street, Suburb)")
            conn.commit()
            print("✅ Master Database Rebuild Complete.")
        finally:
            conn.close()
    except Exception as e:
        # Non-fatal: if DB build fails, we simply skip duplicate gating against master list
        print(f"⚠️  Master DB rebuild failed (continuing without it): {e}")

def _debug_probe_against_master(ap, num, street, suburb):
    rec = {
        "ApartmentNumber": ap,
        "Number": num,
        "Street": street,
        "Suburb": suburb,
        "Status": "At Home",
        "Notes": "",
    }
    status = _duplicate_status_against_master(rec)
    print(f"🔎 Probe: ({ap!r}, {num!r}, {street!r}, {suburb!r}) -> {status}")

# ---------------------------------------------------------------------------
# Optional debug probes (SAFE on import)
#   Enable by running the module directly with GS_DEBUG_PROBES=1
#   Example:  GS_DEBUG_PROBES=1 python Clean_GoogleSheets.py
# ---------------------------------------------------------------------------
if __name__ == "__main__" and os.environ.get("GS_DEBUG_PROBES") == "1":
    # Probes run only after all defs exist, so they won't break import
    _debug_probe_against_master("", "UnitB/10", "Fencotie Place", "Northpark")
    _debug_probe_against_master("", "Unit2/2",  "Anthony Place", "Pakuranga")



@lru_cache(maxsize=1)
@lru_cache(maxsize=1)
def _load_master_index(csv_path: Path = MASTER_CSV_PATH, db_path: Path = MASTER_DB_PATH):
    """
    Returns:
      - exact_set: set of canon (ApartmentNumber, Number, Street, Suburb)
      - triplet_to_suburbs: dict of canon (ApartmentNumber, Number, Street) -> set of canon suburbs
    Also populates module-global:
      - _MASTER_STREET_SUBURB_SET with canon (Street, Suburb)
      - _MASTER_STSUB_TO_HOUSES with canon house-only numbers per (Street, Suburb)
      - _MASTER_HOUSEONLY_TO_ADDRS with pretty display strings for house-only hits
      - _MASTER_TRIPLET_SET with canon (ApartmentNumber, Number, Street)

    Prefers SQLite; falls back to reading CSV directly if DB missing.
    """
    exact_set: set[tuple[str, str, str, str]] = set()
    triplet_to_suburbs: dict[tuple[str, str, str], set[str]] = {}

    # reset/refresh the globals
    _MASTER_STREET_SUBURB_SET.clear()
    _MASTER_STSUB_TO_HOUSES.clear()
    _MASTER_HOUSEONLY_TO_ADDRS.clear()
    _MASTER_TRIPLET_SET.clear()

    def add(ap, num, st, sub):
        # Canonical triplet: (ApartmentNumber, Number, Street)
        k3 = _canon_triplet(ap, num, st)
        cs = _canon_text_cached((sub or "").strip())

        # Full 4-tuple (kept for backward compatibility / debugging)
        exact_set.add((k3[0], k3[1], k3[2], cs))
        triplet_to_suburbs.setdefault(k3, set()).add(cs)

        # Store the triplet for strict duplicate detection
        _MASTER_TRIPLET_SET.add(k3)

        # (Street, Suburb) presence set (still built, even though not used for dup rule now)
        st_sub_key = _canon_street_suburb(st, sub)
        _MASTER_STREET_SUBURB_SET.add(st_sub_key)

    # --- Prefer SQLite DB; rebuild from CSV if needed ---
    try:
        _ensure_sqlite_from_csv(csv_path, db_path)

        if db_path.exists():
            # Load from DB
            try:
                conn = sqlite3.connect(str(db_path))
                try:
                    cur = conn.cursor()
                    for ap, num, st, sub in cur.execute(
                        "SELECT ApartmentNumber, Number, Street, Suburb FROM addresses"
                    ):
                        add(ap or "", num or "", st or "", sub or "")
                finally:
                    conn.close()
            except Exception as e:
                print(f"⚠️  Master index load from DB failed, trying CSV instead: {e}")

        # If DB didn’t exist or failed, try CSV directly
        if not exact_set and csv_path.exists():
            try:
                with open(csv_path, newline="", encoding="utf-8") as f:
                    r = csv.DictReader(f)
                    for row in r:
                        add(
                            row.get("ApartmentNumber", "") or "",
                            row.get("Number", "") or "",
                            row.get("Street", "") or "",
                            row.get("Suburb", "") or "",
                        )
            except Exception as e:
                print(f"⚠️  Master index load from CSV failed: {e}")

        if not exact_set:
            print("ℹ️  Master index is empty (no rows loaded from DB/CSV).")

    except Exception as e:
        print(f"⚠️  Master index initialisation failed: {e}")

    return exact_set, triplet_to_suburbs




def _duplicate_status_against_master(cleaned: dict, *, return_basis: bool = False):
    """
    Duplicate gating against the master list.

    NEW RULE (per Brook):
      A row is a duplicate ONLY if the canonical
          (ApartmentNumber, Number, Street)
      triplet is IDENTICAL to a triplet in the master DB/CSV.

    • Suburb is ignored for the duplicate rule.
    • No more "Different Suburb" or house-only fallbacks.
    • No more Custom3 special case.

    Returns:
      - If return_basis=False (default): "Duplicate" or None
      - If return_basis=True: (status_or_None, basis_or_None, matched_display_or_None)
            basis is always "exact-triplet" when duplicate.
            matched_display is always None for this rule.
    """
    ap = (cleaned.get("ApartmentNumber") or "").strip()
    num = (cleaned.get("Number") or "").strip()
    st  = (cleaned.get("Street") or "").strip()

    # If we don't even have Street + Number, we can't test for duplicate.
    if not (st and num):
        return (None, None, None) if return_basis else None

    # If ApartmentNumber is empty but Number looks like "UnitX/NN", try to split it.
    # This allows a merged "UnitX/NN" format in the sheet to match separated
    # ApartmentNumber/Number in the master DB.
    if not ap and num:
        try:
            ap_guess, num_guess = _split_unit_house(num)
        except Exception:
            ap_guess = num_guess = None
        if ap_guess:
            ap = ap_guess
        if num_guess:
            num = num_guess

    # Build / refresh the master index (this also populates _MASTER_TRIPLET_SET)
    _load_master_index()
    # Canonical triplet for this cleaned row
    trip = _canon_triplet(ap, num, st)

    if trip in _MASTER_TRIPLET_SET:
        # Strict duplicate: ApartmentNumber + Number + Street are identical
        if return_basis:
            return ("Duplicate", "exact-triplet", None)
        return "Duplicate"

    # Not a duplicate
    return (None, None, None) if return_basis else None


def run_final_master_duplicate_filter(
    clean_csv: str = "output_clean.csv",
    fail_csv: str = "output_fail.csv",
) -> None:
    """
    FINAL STEP:
      Compare output_clean.csv rows against the master DB
      (Auckland_East_Mandarin_Addresses.db) and:
        - If (ApartmentNumber, Number, Street) triplet matches master
          → mark as Duplicate, move to fail_csv
        - Otherwise keep in clean_csv

    Matching is done on canonical triplets, same rule as elsewhere:
      duplicate ⇔ _canon_triplet(ApartmentNumber, Number, Street)
                  exists in _MASTER_TRIPLET_SET.
    """

    # Make sure master index is loaded and _MASTER_TRIPLET_SET is populated
    try:
        _load_master_index.cache_clear()
    except Exception:
        # cache_clear not critical; ignore if missing
        pass

    _load_master_index()
    if not _MASTER_TRIPLET_SET:
        print("ℹ️ Final master duplicate filter: master index is empty; skipping.")
        return

    if not os.path.exists(clean_csv):
        print(f"ℹ️ Final master duplicate filter: '{clean_csv}' not found; skipping.")
        return

    # --- Read all clean rows ---
    with open(clean_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    if not fieldnames:
        print(f"ℹ️ Final master duplicate filter: '{clean_csv}' has no header; skipping.")
        return

    survivors: list[dict] = []
    dupes: list[dict] = []

    for row in rows:
        ap = (row.get("ApartmentNumber") or "").strip()
        num = (row.get("Number") or "").strip()
        st  = (row.get("Street") or "").strip()

        # If no Street/Number, we can't compare → keep as non-duplicate
        if not (st and num):
            survivors.append(row)
            continue

        trip = _canon_triplet(ap, num, st)

        if trip in _MASTER_TRIPLET_SET:
            r = dict(row)  # copy so we can safely tweak
            # Mark reason but keep ALL coords and other fields
            r["Final Status"] = "Duplicate"
            dupes.append(r)
        else:
            survivors.append(row)

    if not dupes:
        print("✅ Final master duplicate filter: no duplicates found in clean output.")
        return

    # Helper to sanitize rows before writing (drop None and unknown keys)
    def _sanitize(row: dict) -> dict:
        return {k: (row.get(k, "") if k is not None else "")
                for k in fieldnames}

    # --- Overwrite clean_csv with survivors ---
    with open(clean_csv, "w", newline="", encoding="utf-8", buffering=1024 * 1024) as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in survivors:
            writer.writerow(_sanitize(row))

    # --- Append duplicates into fail_csv (same format as clean) ---
    write_header = True
    if os.path.exists(fail_csv) and os.path.getsize(fail_csv) > 0:
        # Assume header already exists if file is non-empty
        write_header = False

    with open(
        fail_csv,
        "a" if not write_header else "w",
        newline="",
        encoding="utf-8",
        buffering=1024 * 1024,
    ) as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        for row in dupes:
            writer.writerow(_sanitize(row))

    print(
        f"✅ Final master duplicate filter: moved {len(dupes)} duplicate row(s) "
        f"from '{clean_csv}' to '{fail_csv}'."
    )

def run_verify_fail_against_master(clean_csv="output_clean.csv",
                                   fail_csv="output_fail.csv"):
    """
    After run_final_master_duplicate_filter:
    - Re-check output_fail.csv against master DB.
    - Keep only true duplicates.
    - Any row that is NOT a true duplicate → move back to clean_csv.
    """

    # Ensure master index is refreshed
    try:
        _load_master_index.cache_clear()
    except Exception:
        pass
    _load_master_index()

    if not os.path.exists(fail_csv):
        print("ℹ️ Verify-fail: fail file missing → nothing to do")
        return

    # Read fail rows
    with open(fail_csv, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        fieldnames = r.fieldnames or []
        fail_rows = list(r)

    if not fieldnames:
        print("ℹ️ Verify-fail: fail file has no header → nothing to do")
        return

    keep_fail = []   # true duplicates only
    return_to_clean = []  # false duplicates (send back to clean)

    for row in fail_rows:
        ap = (row.get("ApartmentNumber") or "").strip()
        num = (row.get("Number") or "").strip()
        st  = (row.get("Street") or "").strip()

        if not (st and num):
            # Cannot confirm as duplicate → return to clean
            return_to_clean.append(row)
            continue

        trip = _canon_triplet(ap, num, st)

        if trip in _MASTER_TRIPLET_SET:
            # TRUE duplicate → keep in fail
            keep_fail.append(row)
        else:
            # FALSE duplicate → return to clean
            row["Final Status"] = "Pass"
            return_to_clean.append(row)

    # Write updated fail file
    with open(fail_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in keep_fail:
            w.writerow({k: row.get(k, "") for k in fieldnames})

    # Append returned rows back to clean file
    if return_to_clean:
        # Read clean rows
        clean_rows = []
        if os.path.exists(clean_csv):
            with open(clean_csv, newline="", encoding="utf-8") as f:
                r = csv.DictReader(f)
                clean_fieldnames = r.fieldnames or fieldnames
                clean_rows = list(r)
        else:
            clean_fieldnames = fieldnames

        # Overwrite clean file with combined data
        with open(clean_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=clean_fieldnames)
            w.writeheader()
            for row in clean_rows:
                w.writerow({k: row.get(k, "") for k in clean_fieldnames})
            for row in return_to_clean:
                w.writerow({k: row.get(k, "") for k in clean_fieldnames})

    print(
        f"🔄 Verify-fail complete: "
        f"{len(keep_fail)} true duplicates kept, "
        f"{len(return_to_clean)} rows returned to clean."
    )



def run_sheets_clean_and_split_after_purge_verify(
    input_file: str = "input_googlesheets.csv",
    *,
    do_split: bool = True,
    out_clean: str | None = None,
    out_fail: str | None = None,
    include_only_new: bool = False,
    exclude_new: bool = False,
    ensure_clear_dir: bool = True,
):
    """
    Option 6 (moved): Clean & Split Into Different Suburbs
    (Forward-geocode refinement only; all reverse geocoding removed)
    """
    if include_only_new and exclude_new:
        raise ValueError("include_only_new and exclude_new are mutually exclusive")

    if not os.path.exists(input_file):
        print("❌ input_googlesheets.csv not found.")
        return

    # Prime master index once
    _load_master_index.cache_clear()
    _exact, _trip = _load_master_index()
    print(f"🧭 Master Index Loaded: exact={len(_exact):,} rows, triplets={len(_trip):,}")
    if not _exact:
        print("⚠️ Master index is EMPTY — duplicates against master will not be detected.")

    # If we plan to split, clear only the files inside the final export folder.
    if do_split and ensure_clear_dir:
        _clear_files_only(_SUBURB_BASE, "*")

    # Decide outputs without creating temp inputs
    if out_clean is None or out_fail is None:
        _oc, _of = _stemmed_outputs_for(input_file)
        out_clean = out_clean or _oc
        out_fail  = out_fail  or _of

    def _extract_house_digits(number_str: str) -> str:
        if not number_str:
            return ""
        m = SLASH_DIGITS_RX.search(number_str)
        if m:
            return m.group(1)
        return re.sub(r"\D", "", number_str or "")

    fieldnames = [
        "Old Number", "Unit",
        "Old Street",
        "ApartmentNumber", "Number", "Street",
        "Suburb", "PostalCode", "State",
        "Status", "Final Status",
        "Latitude", "Longitude",
        "Type", "Language", "Notes", "Other Notes",
    ]

    clean_count = fail_count = 0
    seen_dupe_keys: set[tuple[str, str, str, str]] = set()
    dup_count = 0

    with open(out_clean, "w", newline="", encoding="utf-8", buffering=1024*1024) as fout_c, \
         open(out_fail,  "w", newline="", encoding="utf-8", buffering=1024*1024) as fout_f, \
         open(input_file, newline="", encoding="utf-8") as fin:

        wc = csv.DictWriter(fout_c, fieldnames=fieldnames); wc.writeheader()
        wf = csv.DictWriter(fout_f, fieldnames=fieldnames); wf.writeheader()

        def _flip_before_write(rec: dict):
            num = (rec.get("Number") or "").strip()
            if not num:
                return
            m = HOUSE_FLIP_A.match(num)
            if m:
                rec["Number"] = f"{m.group(2)}/Unit{m.group(1).upper()}"
                return
            m = HOUSE_FLIP_B.match(num)
            if m:
                rec["Number"] = f"Unit{m.group(2).upper()}/{m.group(1)}"

        reader = csv.DictReader(fin)
        for row in tqdm(reader, desc="✅ Stage 1: Cleaning/Geocoding", unit="row"):
            if core.cancel_flag.is_set():
                print("❌ Cancelled during sheets processing.")
                break

            old_unit    = (row.get("Unit") or "").strip()
            old_number  = (row.get("Number") or "").strip()
            old_street  = (row.get("Street") or "").strip()
            suburb_in   = (row.get("Suburb") or "").strip()
            old_lat     = (row.get("Latitude") or "").strip()
            old_lon     = (row.get("Longitude") or "").strip()

            apartment_number = (row.get("Apartment/Business") or "").strip()
            notes_val        = (row.get("Notes") or "").strip()
            language_val     = (row.get("Language") or "").strip()
            type_val         = (row.get("Type") or "").strip()

            # Optional filtering
            if include_only_new and not _notes_has_new_street_ci(notes_val):
                continue
            if exclude_new and _notes_has_new_street_ci(notes_val):
                continue

            merged_number = _combine_unit_and_number(old_unit, old_number)

            # Prefer provided Suburb; else try "Street, Suburb" in Old Street
            street_val = old_street
            if suburb_in:
                suburb_val = _canon_suburb_sheets(suburb_in)
            else:
                if "," in old_street:
                    left, right = old_street.split(",", 1)
                    street_val = left.strip()
                    suburb_val = _canon_suburb_sheets(right.strip())
                else:
                    suburb_val = ""

            # Street cleanup
            street_val = gs_strip_leading_duplicate_number_from_street(merged_number, street_val)
            street_val = _strip_trailing_postcode(street_val)
            street_val = _repair_corrupted_street(street_val)

            # Lat/Lon keep only if numeric-ish
            lat_val = old_lat if _has_digits(old_lat) else ""
            lon_val = old_lon if _has_digits(old_lon) else ""

            # Strict PostalCode lookup
            postal_code = _postal_for_suburb_sheets(suburb_val)

            # Normalize status ("Home" -> "At Home"; default "At Home")
            incoming_status = (row.get("Status") or "").strip()
            status_val = "At Home" if incoming_status.lower() == "home" else incoming_status or "At Home"

            cleaned = {
                "Old Number": old_number,
                "Unit": old_unit,
                "Old Street": old_street,
                "ApartmentNumber": apartment_number,
                "Number": merged_number,
                "Street": street_val,
                "Suburb": suburb_val,
                "PostalCode": postal_code,
                "State": "Auckland",
                "Status": status_val,
                "Final Status": "Pass",
                "Latitude": lat_val,
                "Longitude": lon_val,
                "Type": type_val,
                "Language": language_val,
                "Notes": notes_val,
                "Other Notes": "",
            }

            _clean_notes_and_language(cleaned)
            _apply_new_street_overrides(cleaned, notes_val)
            geocode_bad = False
            geocode_guess = ""

            # 1) Forward geocode -> adopt if clearly same
            try:
                digits = _extract_house_digits(merged_number)
                suburb_for_query = cleaned["Suburb"] or "Auckland"
                addr_query = core.fmt_addr_parts(digits or merged_number, cleaned["Street"], suburb_for_query)

                g = _gl_cached(addr_query) or (None, None, None, "")
                g_full, g_lat, g_lon, _ = g

                if g_full and g_lat and g_lon and core.is_in_auckland(float(g_lat), float(g_lon)):
                    parts = [p.strip() for p in (g_full or "").split(",")]
                    g_street = parts[0] if parts else cleaned["Street"]
                    g_suburb = parts[1] if len(parts) > 1 else cleaned["Suburb"]
                    g_suburb = _strip_trailing_postcode(g_suburb)

                    if _looks_like_just_suburb(g_street, g_suburb or cleaned["Suburb"]):
                        geocode_bad = True
                        geocode_guess = f"{g_street}, {g_suburb}".strip(", ")

                    if not geocode_bad and _accept_geocode_update(street_val, g_street, suburb_val, g_suburb):
                        g_street = gs_strip_leading_duplicate_number_from_street(cleaned.get("Number", ""), g_street)
                        g_street = _strip_trailing_postcode(g_street)

                        cleaned["Street"] = g_street or cleaned["Street"]
                        cleaned["Suburb"] = _canon_suburb_sheets(g_suburb or cleaned["Suburb"])

                        better = _choose_best_coordinate(
                            core.fmt_addr_parts(digits or merged_number, cleaned["Street"], cleaned["Suburb"] or suburb_for_query),
                            cleaned
                        )
                        if better:
                            b_lat, b_lon, prov = better
                            cleaned["Latitude"] = f"{float(b_lat):.8f}"
                            cleaned["Longitude"] = f"{float(b_lon):.8f}"
                            if not (prov and "fallback" in (prov or "").lower()):
                                _append_other_notes(cleaned, f"Coords from {prov}")
                        else:
                            cleaned["Latitude"] = f"{float(g_lat):.8f}"
                            cleaned["Longitude"] = f"{float(g_lon):.8f}"

                        # Postal lookup strictly by canonical suburb
                        canon_suburb = _canon_suburb_sheets(cleaned["Suburb"])
                        cleaned["PostalCode"] = core.nz_postal_lookup.get(canon_suburb, "")

                        cleaned["Final Status"] = "Pass"
            except Exception:
                pass

            if geocode_bad:
                _append_other_notes(cleaned, f"Geocode hint: suburb-as-street -> {geocode_guess}")

            # Coordinate sanity
            try:
                if cleaned.get("Latitude") and cleaned.get("Longitude"):
                    la = float(cleaned["Latitude"]); lo = float(cleaned["Longitude"])
                    if hasattr(core, "is_in_auckland") and not core.is_in_auckland(la, lo):
                        cleaned["Final Status"] = "Bad Geocode"
                        _append_other_notes(cleaned, "Bad Geocode: outside Auckland bounds")
                        _flip_before_write(cleaned)
                        wf.writerow({k: cleaned.get(k, "") for k in fieldnames})
                        fail_count += 1
                        continue
            except Exception:
                pass


            reasons = _should_fail_row(cleaned, old_unit, old_number, old_street)
            if reasons:
                cleaned["Final Status"] = "Fail"
                cleaned["Notes"] = (cleaned.get("Notes", "") + (" | " if cleaned.get("Notes") else "") +
                                    "; ".join(reasons))
                _clean_notes_and_language(cleaned)
                _flip_before_write(cleaned)
                wf.writerow({k: cleaned.get(k, "") for k in fieldnames})
                fail_count += 1
            else:
                cleaned["Final Status"] = "Pass"
                _flip_before_write(cleaned)
                wc.writerow({k: cleaned.get(k, "") for k in fieldnames})
                clean_count += 1

    # ✅ NEW: final strict duplicate filter vs master DB
    run_final_master_duplicate_filter(out_clean, out_fail)
    run_verify_fail_against_master(out_clean, out_fail)

    # --- Stage 3: Split by KML polygons/territories
    if do_split:
        print("✅ Stage 3: Splitting By Territory Boundaries")
        try:
            core.split_cleaned_by_polygon_and_include_failed(out_clean, out_fail, kml_dir="KML Boundaries")
        except Exception as e:
            print(f"❌ Split failed: {e}")



# replace the body of _warn_if_temp_dirs_have_files with this
def _warn_if_temp_dirs_have_files():
    if _SUPPRESS_TEMP_DIR_WARNINGS:
        return
    stray = []
    for d in (_SUBURB_DIR_NEW, _SUBURB_DIR_OTHER):
        if d.exists() and any(d.glob("*.csv")):
            stray.append(d.name)
    if stray:
        print(f"⚠️ Temp folders contain CSVs (should be empty after merge): {', '.join(stray)}")



def run_sheets_clean_and_split_new_streets_verify(
    input_file: str = "input_googlesheets.csv",
    *,
    do_split: bool = True,
    out_clean: str | None = None,
    out_fail: str | None = None,
):
    """
    Option 3: Clean & Split Into Different Suburbs (New Streets + Full Geocode Check)
    Same as option 2 but ONLY processes rows whose Notes contains 'New Street'.
    After cleaning, delegates to New World Scheduler Option 7 path.
    """
    if not os.path.exists(input_file):
        print("❌ input_googlesheets.csv not found.")
        return

    # Prime master index (safe no-op if source missing)
    _load_master_index.cache_clear()
    _load_master_index()

    # decide outputs without creating temp inputs
    if out_clean is None or out_fail is None:
        _oc, _of = _stemmed_outputs_for(input_file)
        out_clean = out_clean or _oc
        out_fail  = out_fail  or _of

    def _extract_house_digits(number_str: str) -> str:
        if not number_str:
            return ""
        m = SLASH_DIGITS_RX.search(number_str)
        if m:
            return m.group(1)
        return re.sub(r"\D", "", number_str or "")

    fieldnames = [
        "Old Number", "Unit",
        "Old Street",
        "ApartmentNumber", "Number", "Street",
        "Suburb", "PostalCode", "State",
        "Status", "Final Status",
        "Latitude", "Longitude",
        "Type", "Language", "Notes", "NotesFromPublisher", "Other Notes",
    ]

    clean_count = fail_count = 0
    seen_dupe_keys: set[tuple[str, str, str, str]] = set()
    dup_count = 0

    with open(out_clean, "w", newline="", encoding="utf-8", buffering=1024*1024) as fout_c, \
         open(out_fail,  "w", newline="", encoding="utf-8", buffering=1024*1024) as fout_f, \
         open(input_file, newline="", encoding="utf-8") as f:

        wc = csv.DictWriter(fout_c, fieldnames=fieldnames); wc.writeheader()
        wf = csv.DictWriter(fout_f,  fieldnames=fieldnames); wf.writeheader()

        def _flip_before_write(rec: dict):
            num = (rec.get("Number") or "").strip()
            if not num:
                return
            m = HOUSE_FLIP_A.match(num)
            if m:
                rec["Number"] = f"{m.group(2)}/Unit{m.group(1).upper()}"
                return
            m = HOUSE_FLIP_B.match(num)
            if m:
                rec["Number"] = f"Unit{m.group(2).upper()}/{m.group(1)}"

        reader = csv.DictReader(f)
        for row in tqdm(reader, desc="✅ Stage 1/2: Cleaning/Geocoding (New Streets)/Write", unit="row"):
            if core.cancel_flag.is_set():
                print("❌ Cancelled during sheets processing.")
                break

            old_unit    = (row.get("Unit") or "").strip()
            old_number  = (row.get("Number") or "").strip()
            old_street  = (row.get("Street") or "").strip()
            suburb_in   = (row.get("Suburb") or "").strip()
            postal_in   = (row.get("PostalCode") or row.get("Postcode") or row.get("Postal") or "").strip()
            old_lat     = (row.get("Latitude") or "").strip()
            old_lon     = (row.get("Longitude") or "").strip()

            apartment_number = (row.get("Apartment/Business") or "").strip()
            notes_val        = (row.get("Notes") or "").strip()
            notes_pub_val    = (row.get("NotesFromPublisher") or "").strip()
            language_val     = (row.get("Language") or "").strip()
            type_val         = (row.get("Type") or "").strip()

            # New Streets filter
            if not _notes_has_new_street(notes_val):
                continue

            merged_number = _combine_unit_and_number(old_unit, old_number)

            # Prefer provided Suburb/PostalCode; else split from Street if present
            street_val = old_street
            if suburb_in:
                suburb_val = _canon_suburb_sheets(suburb_in)
            else:
                if "," in old_street:
                    left, right = old_street.split(",", 1)
                    street_val = left.strip()
                    suburb_val = _canon_suburb_sheets(right.strip())
                else:
                    suburb_val = ""

            # Street cleanup (+ repair)
            street_val = gs_strip_leading_duplicate_number_from_street(merged_number, street_val)
            street_val = _strip_trailing_postcode(street_val)
            street_val = _repair_corrupted_street(street_val)  # ✅ NEW

            # Lat/Lon keep only if numeric-ish
            lat_val = old_lat if _has_digits(old_lat) else ""
            lon_val = old_lon if _has_digits(old_lon) else ""

            # Strict: ignore incoming PostalCode, trust our lookup
            postal_code = _postal_for_suburb_sheets(suburb_val)

            # Preserve incoming Status, but map literal 'Home' to 'At Home'
            incoming_status = (row.get("Status") or "").strip()
            status_val = "At Home" if incoming_status.lower() == "home" else incoming_status or "At Home"

            # Notes merging (keep source column as well)
            notes_merged = _merge_notes(notes_val, notes_pub_val)

            cleaned = {
                "Old Number": old_number,
                "Unit": old_unit,
                "Old Street": old_street,
                "ApartmentNumber": apartment_number,
                "Number": merged_number,
                "Street": street_val,
                "Suburb": suburb_val,
                "PostalCode": postal_code,
                "State": "Auckland",
                "Status": status_val,
                "Final Status": "Pass",
                "Latitude": lat_val,
                "Longitude": lon_val,
                "Type": type_val,
                "Language": language_val,
                "Notes": notes_merged,
                "NotesFromPublisher": notes_pub_val,
                "Other Notes": "",
            }

            _clean_notes_and_language(cleaned)
            _apply_new_street_overrides(cleaned, notes_val, notes_pub_val)



            geocode_bad = False
            geocode_guess = ""

            # If incoming coords are not valid in Auckland → try geocoding
            if not _coords_in_auckland(cleaned.get("Latitude",""), cleaned.get("Longitude","")):
                try:
                    digits = _extract_house_digits(merged_number)
                    suburb_for_query = cleaned["Suburb"] or "Auckland"
                    addr_query = core.fmt_addr_parts(digits or merged_number, cleaned["Street"], suburb_for_query)

                    g = _gl_cached(addr_query) or (None, None, None, "")
                    g_full, g_lat, g_lon, g_postal = g

                    if g_full and g_lat and g_lon and core.is_in_auckland(float(g_lat), float(g_lon)):
                        parts = [p.strip() for p in (g_full or "").split(",")]
                        g_street = parts[0] if parts else cleaned["Street"]
                        g_suburb = parts[1] if len(parts) > 1 else cleaned["Suburb"]
                        g_suburb = _strip_trailing_postcode(g_suburb)

                        gs_tokens   = _tokens_core(g_street)
                        gsub_tokens = _tokens_core(g_suburb or cleaned["Suburb"])
                        if gs_tokens and (gs_tokens <= gsub_tokens):
                            geocode_bad = True
                            geocode_guess = f"{g_street}, {g_suburb}".strip(", ")

                        if not geocode_bad and _accept_geocode_update(street_val, g_street, suburb_val, g_suburb):
                            g_street = gs_strip_leading_duplicate_number_from_street(cleaned.get("Number", ""), g_street)
                            g_street = _strip_trailing_postcode(g_street)

                            cleaned["Street"] = g_street or cleaned["Street"]
                            cleaned["Suburb"] = _canon_suburb_sheets(g_suburb or cleaned["Suburb"])

                            better = _choose_best_coordinate(
                                core.fmt_addr_parts(digits or merged_number, cleaned["Street"], cleaned["Suburb"] or suburb_for_query),
                                cleaned
                            )
                            if better:
                                b_lat, b_lon, prov = better
                                cleaned["Latitude"] = f"{float(b_lat):.8f}"
                                cleaned["Longitude"] = f"{float(b_lon):.8f}"
                                if not (prov and "fallback" in (prov or "").lower()):
                                    _append_other_notes(cleaned, f"Coords from {prov}")
                            else:
                                cleaned["Latitude"] = f"{float(g_lat):.8f}"
                                cleaned["Longitude"] = f"{float(g_lon):.8f}"

                            # STRICT NZ POSTAL LOOKUP ONLY
                            canon_suburb = _canon_suburb_sheets(cleaned["Suburb"])
                            cleaned["PostalCode"] = core.nz_postal_lookup.get(canon_suburb, "")

                            cleaned["Final Status"] = "Pass"
                except Exception:
                    pass

            if geocode_bad:
                _append_other_notes(cleaned, f"Geocode hint: suburb-as-street -> {geocode_guess}")


            reasons = _should_fail_row(cleaned, old_unit, old_number, old_street)
            if reasons:
                cleaned["Final Status"] = "Fail"
                cleaned["Notes"] = (cleaned.get("Notes", "") + (" | " if cleaned.get("Notes") else "") +
                                    "; ".join(reasons))
                _clean_notes_and_language(cleaned)
                _flip_before_write(cleaned)
                wf.writerow({k: cleaned.get(k, "") for k in fieldnames})
                fail_count += 1
            else:
                cleaned["Final Status"] = "Pass"
                _flip_before_write(cleaned)
                wc.writerow({k: cleaned.get(k, "") for k in fieldnames})
                clean_count += 1

    # --- Stage 4: Hand off to New World Scheduler Option 7 path
    if do_split:
        print("✅ Stage 4: Delegating to New World Scheduler → Option 7 (New Streets path)")
        _invoke_core_option7_new_streets(out_clean, out_fail)



# Optional: seed with trusted suburb names if you have them
_SUBURB_WHITELIST = set()

def _init_suburb_whitelist(core_ref=core):
    """
    Build a whitelist of valid suburb names to snap corrupted input to.
    Pulls from core.macron_suburb_map (values + keys), and any core.suburb_list if present.
    """
    vals = set()
    m = getattr(core_ref, "macron_suburb_map", None)
    if isinstance(m, dict):
        vals.update(m.keys())
        vals.update(m.values())
    if hasattr(core_ref, "suburb_list") and isinstance(core_ref.suburb_list, (list, set, tuple)):
        vals.update(core_ref.suburb_list)
    vals.update({"Pakuranga", "Botany Downs", "Howick", "Flat Bush", "Manukau", "Panmure",
                 "Half Moon Bay", "Golflands", "Highland Park", "Bucklands Beach"})
    _SUBURB_WHITELIST.update({_strip_macrons(v).title().strip() for v in vals if v})

_init_suburb_whitelist()

# Specific known corruption fixes (expand as you encounter more)
_SUBURB_CORRUPTION_MAP = {
    "Pak奴ranga": "Pakuranga",
}

_BAD_CHARS_RX = re.compile(r"[^A-Za-z'\-\s]")


def _repair_corrupted_suburb(s: str) -> str:
    """
    Repairs suburb strings containing non-Latin characters (e.g., OCR/IME noise).
    Strategy:
      1) Exact known-corruption map.
      2) Strip non-letters and try fuzzy match to a whitelist.
      3) Fallback to 'title' of the cleaned text.
    """
    if not s:
        return ""
    s = s.strip()

    if s in _SUBURB_CORRUPTION_MAP:
        return _SUBURB_CORRUPTION_MAP[s]

    cleaned = _BAD_CHARS_RX.sub("", s)
    cleaned = _strip_macrons(cleaned).strip()

    if not cleaned:
        return ""

    if _SUBURB_WHITELIST:
        cand = difflib.get_close_matches(cleaned.title(), _SUBURB_WHITELIST, n=1, cutoff=0.86)
        if cand:
            return cand[0]

    return cleaned.title()


def _strip_trailing_postcode(s: str) -> str:
    # remove a trailing 4-digit NZ postcode if someone typed it into Street
    return TRAILING_NZ_POSTCODE_RX.sub("", (s or "").strip())

def _canon_suburb_local(s: str, core_ref=core) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    s = _repair_corrupted_suburb(s)
    s_title = _strip_macrons(s.title())
    m = getattr(core_ref, "macron_suburb_map", None)
    if isinstance(m, dict):
        return m.get(s_title, s_title)
    return s_title


# ---- Canonization for Google Sheets flows (unified + corruption-repair) ----

def _canon_suburb_sheets(s: str, core_ref=core) -> str:
    """
    Canonize a suburb value for the Google Sheets flows:
      • Repairs OCR/IME noise
      • Strips macrons consistently
      • Applies core.macron_suburb_map when present
    """
    return _canon_suburb_local(s, core_ref=core_ref)


def _postal_for_suburb_sheets(s: str, core_ref=core) -> str:
    """
    Postal lookup that uses the same repaired/canonical suburb
    as _canon_suburb_sheets, so lookups stay consistent.
    """
    canon = _canon_suburb_sheets(s, core_ref=core_ref)
    m = getattr(core_ref, "nz_postal_lookup", None)
    if isinstance(m, dict):
        return m.get(canon, "")
    return ""

def _enforce_postcode_whitelist(rows):
    for r in rows:
        canon = _canon_suburb_sheets(r.get("Suburb", ""))
        r["PostalCode"] = core.nz_postal_lookup.get(canon, "")

def _accept_geocode_update(orig_street: str, geo_street: str, orig_suburb: str, geo_suburb: str) -> bool:
    """
    Accept only if:
      • non-empty token overlap between original and geocoded street, AND
      • at least one *street-specific* token (not part of the suburb) overlaps, OR
        streets match when ignoring common suffixes, AND
      • suburb matches (canonically) when an original suburb exists, AND
      • geocoded street is not just the suburb name.
    """
    os = _tokens_core(orig_street)
    gs = _tokens_core(geo_street)
    if not os or not gs or not (os & gs):
        return False

    ss = _tokens_core(orig_suburb)

    os_no_suf = _strip_common_suffix_word(orig_street)
    gs_no_suf = _strip_common_suffix_word(geo_street)
    same_ign_suffix = _canon_text_cached(os_no_suf) == _canon_text_cached(gs_no_suf)

    street_specific_overlap = ((os - ss) & gs)
    if not street_specific_overlap and not same_ign_suffix:
        return False

    if _looks_like_just_suburb(geo_street, geo_suburb) or _looks_like_just_suburb(geo_street, orig_suburb):
        return False

    o_sub = _canon_suburb_local(_strip_trailing_postcode(orig_suburb))
    g_sub = _canon_suburb_local(_strip_trailing_postcode(geo_suburb))
    if o_sub and g_sub and (o_sub != g_sub):
        return False

    return True


def _strip_common_suffix_word(s: str) -> str:
    """
    Remove a single trailing suffix like 'Drive/Street/Road' etc., if present.
    Keeps everything else intact so we can compare street identity sans suffix.
    """
    t = (s or "").strip()
    if not t:
        return t
    parts = TOKEN_RX.findall(t)
    if not parts:
        return t
    if parts[-1].lower() in COMMON_SUFFIX_LOWER:
        core_part = " ".join(parts[:-1]).strip()
        return core_part if core_part else t
    return t


# ---- Local helpers kept here so this file is self-contained ----

def normalize_number(number_val: str) -> str:
    """
    Normalizes NZ unit/house numbers consistently.
    (Copied from main to avoid circular dependency)
    """
    number = (number_val or "").strip()
    number = re.sub(r"\s+", "", number)

    month_map = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5,
        'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10,
        'nov': 11, 'dec': 12
    }

    m = re.match(r'^(?P<house>\d+)\s*/\s*(?:Unit)?(?P<unit>[A-Za-z0-9]+)$', number, re.IGNORECASE)
    if m:
        house = m.group('house')
        unit  = m.group('unit').upper()
        return f"Unit{unit}/{house}"

    m = re.match(r'^(\d*)[-_/]*([A-Za-z]{3})(?:[-_/]*(\d+))?$', number, re.IGNORECASE)
    if m:
        unit_part, month_abbr, trailing_num = m.groups()
        month_num = month_map.get(month_abbr.lower(), 1)
        if unit_part:
            return f"Unit{unit_part}/{month_num}"
        elif trailing_num:
            return f"Unit{month_num}/{trailing_num}"
        else:
            return f"Unit{month_num}"

    m = re.match(r'^(\d+)([A-Za-z])$', number)
    if m:
        return f"Unit{m.group(2).upper()}/{m.group(1)}"

    number = re.sub(r'[~_\-,.\\:;!\=\+\"\'\(\)]', '/', number)

    if '/' in number and not number.lower().startswith('unit'):
        parts = number.split('/', 1)
        number = f"Unit{parts[0]}/{parts[1]}"

    if number.lower().startswith("unit"):
        prefix = "Unit"
        remainder = ''.join(ch.upper() if ch.isalpha() else ch for ch in number[4:])
        number = prefix + remainder
    else:
        number = ''.join(ch.upper() if ch.isalpha() else ch for ch in number)

    return number

def _canon_text(s: str) -> str:
    """Lowercase and strip non-alphanumerics to compare addresses robustly."""
    return _canon_text_cached(s)

def _numbers_match(old_unit: str, old_number: str, new_number: str) -> bool:
    """Does new Number equal the normalized combination of old Unit+Number?"""
    expected = _combine_unit_and_number(old_unit, old_number)
    lhs = normalize_number(expected)
    rhs = normalize_number(new_number or "")
    return lhs == rhs

def _append_other_notes(cleaned: dict, msg: str):
    """Append a system-generated comment into 'Other Notes' (pipe-delimited)."""
    if not msg:
        return
    existing = cleaned.get("Other Notes", "")
    cleaned["Other Notes"] = (existing + (" | " if existing else "") + msg)

def _merge_csvs(sources: list[str], dest: str, delete_sources: bool = True):
    """
    Concatenate multiple CSVs (same headers) into `dest`.
    Writes header once; skips missing sources. Optionally deletes sources.
    """
    writer = None
    fieldnames = None

    with open(dest, "w", newline="", encoding="utf-8", buffering=1024*1024) as fout:
        for src in sources:
            if not src or not os.path.exists(src):
                continue
            with open(src, newline="", encoding="utf-8") as fin:
                r = csv.DictReader(fin)
                if writer is None:
                    fieldnames = r.fieldnames or []
                    writer = csv.DictWriter(fout, fieldnames=fieldnames)
                    writer.writeheader()
                for row in r:
                    writer.writerow({k: row.get(k, "") for k in fieldnames})
            if delete_sources:
                try:
                    os.remove(src)
                except OSError:
                    pass

# Delete temp dirs even if verification is NOT a perfect match?
_ALWAYS_DELETE_TEMP_DIRS = True

def _delete_temp_suburb_dirs() -> None:
    """
    Remove the temp split folders entirely when we're done:
    New_Addresses_By_Suburb__NEW and New_Addresses_By_Suburb__OTHER.
    """
    for d in (_SUBURB_DIR_NEW, _SUBURB_DIR_OTHER):
        try:
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
        except Exception:
            # Non-fatal cleanup
            pass


def _street_suburb_matches_old(old_street: str, new_street: str, new_suburb: str) -> bool:
    """
    True if 'new_street, new_suburb' equals the old street string (ignoring case/punct/postcode).
    If old_street only contained a street (no suburb), allow a match to just the street too.
    """
    old_norm = _canon_text(old_street)
    if not old_norm:
        return True  # nothing to compare against

    new_both = _canon_text(f"{new_street}, {new_suburb}".strip(", "))
    new_only = _canon_text(new_street)

    return old_norm == new_both or old_norm == new_only

def _clear_files_only(p: Path, pattern: str = "*") -> None:
    """
    Delete only files directly inside folder `p` (no subfolder deletion).
    Keeps the folder itself intact.
    Creates the folder if it doesn't exist.
    """
    p.mkdir(parents=True, exist_ok=True)
    try:
        for child in p.iterdir():
            # Only remove files; leave directories alone
            if child.is_file():
                try:
                    child.unlink()
                except FileNotFoundError:
                    pass
    except Exception:
        # Non-fatal; continue
        pass

def _should_fail_row(cleaned: dict, old_unit: str, old_number: str, old_street: str) -> list[str]:
    reasons = []

    is_new_street = (cleaned.get("Status") == "Custom3" and cleaned.get("Notes") == NEW_STREET_MSG)

    if not (cleaned.get("Number") or "").strip():
        if not is_new_street:
            reasons.append("missing Number")
    if not (cleaned.get("Street") or "").strip():
        reasons.append("missing Street")

    if (cleaned.get("Street") or "").strip():
        if not _street_suburb_matches_old(old_street, cleaned.get("Street", ""), cleaned.get("Suburb", "")):
            reasons.append("Street+Suburb does not match Old Street")

    if (cleaned.get("Number") or "").strip():
        if not _numbers_match(old_unit, old_number, cleaned.get("Number", "")):
            reasons.append("Number does not match Old Number+Unit")

    return reasons


def _clean_notes_and_language(rec: dict) -> None:
    """
    Mutates `rec` in-place:
      • Remove 'Check If Chinese', 'Please Check If Chinese',
        'Should be Chinese', 'Speaks Mandarin' from Notes (case-insensitive).
      • If Language is 'Mandarin', 'Chinese', or 'Chinese Mandarin'
        (any case/whitespace/punct), clear it.
      • Cleans up dangling separators ('/', '|') left behind.
    """
    notes = (rec.get("Notes") or "")
    if notes:
        # Patterns to strip from Notes (case-insensitive)
        strip_patterns = [
            r'\bplease\s*check\s*if\s*chinese\b',
            r'\bcheck\s*if\s*chinese\b',
            r'\bshould\s*be\s*chinese\b',
            r'\bspeaks\s*mandarin\b',
        ]
        for pat in strip_patterns:
            notes = re.sub(pat, "", notes, flags=re.IGNORECASE)

        # Tidy whitespace and separators after removals
        notes = re.sub(r'\s+', ' ', notes).strip()
        notes = SEP_SQUASH_RX_1.sub(r'\1', notes)
        notes = SEP_SQUASH_RX_2.sub('', notes)
        notes = SEP_SQUASH_RX_3.sub('', notes)

        rec["Notes"] = notes

    # ----- Language cleanup -----
    lang_raw = (rec.get("Language") or "")
    lang_norm = LANG_LETTERS_ONLY_RX.sub('', lang_raw.strip().lower())

    clear_set = {"mandarin", "chinese", "chinese mandarin", "mandarin chinese"}
    if lang_norm in clear_set:
        rec["Language"] = ""


# --- Temp dirs for routed runs ---
_SUBURB_DIR_NEW   = Path("New_Addresses_By_Suburb__NEW")
_SUBURB_DIR_OTHER = Path("New_Addresses_By_Suburb__OTHER")

def _clear_dir_contents(p: Path) -> None:
    """
    Remove all files/dirs inside 'p' (but keep the folder itself).
    If 'p' does not exist, create it.
    """
    try:
        if p.exists():
            for child in p.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    try:
                        child.unlink()
                    except FileNotFoundError:
                        pass
        else:
            p.mkdir(parents=True, exist_ok=True)
    except Exception:
        # Non-fatal; keep going
        pass

def _ensure_temp_dirs_cleared_for_routed() -> None:
    """
    For Options 3 & 4 runs:
    - Clear the contents of __NEW and __OTHER so we never accumulate old files.
    - Also clear the final output folder (the main `ensure_delete_suburb_dir_interactive` does this),
      but we keep this here to be explicit when calling the split steps individually.
    """
    _clear_dir_contents(_SUBURB_DIR_NEW)
    _clear_dir_contents(_SUBURB_DIR_OTHER)

def _dedupe_suburb_folder(folder: Path) -> tuple[int, int]:
    files_touched = 0
    rows_removed_total = 0
    if not folder.exists():
        return (0, 0)

    for p in folder.glob("*.csv"):
        if "failed" in p.stem.lower():
            continue

        removed_this_file = 0
        try:
            with open(p, newline="", encoding="utf-8") as f:
                r = csv.DictReader(f)
                header = r.fieldnames or []
                seen = set()
                kept_rows = []
                for row in r:
                    k = _addr_key(row)
                    if k in seen:
                        removed_this_file += 1
                        continue
                    seen.add(k)
                    kept_rows.append(row)

            if removed_this_file > 0:
                files_touched += 1
                rows_removed_total += removed_this_file
                with open(p, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=header or list(kept_rows[0].keys()))
                    w.writeheader()
                    for row in kept_rows:
                        w.writerow({k: row.get(k, "") for k in w.fieldnames})
        except Exception:
            continue

    return (files_touched, rows_removed_total)



def _house_digits_from_number(num: str) -> str:
    """Extract the house digits (e.g., 'Unit5A/2' -> '2', '611' -> '611')."""
    s = (num or "").strip()
    if not s:
        return ""
    m = re.search(r"/\s*(\d+)", s)
    if m:
        return m.group(1)
    m = re.match(r"^\d+", s)
    return m.group(0) if m else ""

def gs_strip_leading_duplicate_number_from_street(number_val: str, street_val: str) -> str:
    """
    If Street accidentally starts with the current house number, strip it.
    e.g., Number='Unit1/61' or '611' and Street='611 Clydesdale Avenue' -> 'Clydesdale Avenue'
    """
    s = (street_val or "").strip()
    if not s:
        return s
    digits = _house_digits_from_number(number_val)
    if digits and s.lower().startswith(digits.lower() + " "):
        return s[len(digits):].lstrip()
    return s

def _combine_unit_and_number(unit_val: str, number_val: str) -> str:
    """
    GS-only: Combine Unit + Number safely.
      • If BOTH present -> Unit{Unit}/{Number}
      • If Number already looks like UnitX/NN -> keep as-is
      • Else if only Number -> normalize_number(Number)
      • Else if only Unit   -> 'UnitX'
    """
    u = (unit_val or "").strip()
    n = (number_val or "").strip()

    if u and n:
        u_clean = re.sub(r"\s+", "", u).upper()
        n_clean = re.sub(r"\s+", "", n)
        return f"Unit{u_clean}/{n_clean}"

    if n and n.strip().lower().startswith("unit"):
        return normalize_number(n)

    if n:
        return normalize_number(n)

    if u:
        u_clean = re.sub(r"\s+", "", u).upper()
        return f"Unit{u_clean}"

    return ""

def _count_data_rows(csv_path: str) -> int:
    """Count data lines (excluding header) for progress bars."""
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            total_lines = sum(1 for _ in f)
        return max(0, total_lines - 1)
    except Exception:
        return 0

# ---- Forward-geocode helpers only (reverse removed) ----

def _distance_meters(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, sqrt, atan2
    R = 6371000.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    c = 2 * atan2(sqrt(1-a), sqrt(a))
    return R * c

NEW_STREET_MSG = 'Please refer to "New Streets" for more information'

def _apply_new_street_overrides(rec: dict, *notes_sources: str) -> bool:
    """
    If any notes source contains 'New Street' (CI), then:
      - Notes -> NEW_STREET_MSG
      - Status -> Custom3
      - Number -> '' (clear)
    Returns True if applied.
    """
    for ns in notes_sources:
        if _notes_has_new_street_ci(ns or ""):
            rec["Notes"] = NEW_STREET_MSG
            rec["Status"] = "Custom3"
            rec["Number"] = ""
            return True
    return False

def _safe_forward_both(addr: str):
    """
    Try forward geocoding with both providers if available on core.
    Returns list of (provider_name, lat, lon, full_string, postal) for successes.
    """
    out = []
    try:
        r = _nominatim_cached(addr)
        if r and r[1] and r[2]:
            out.append(("nominatim", float(r[1]), float(r[2]), r[0], r[3] if len(r) > 3 else ""))
    except Exception:
        pass
    try:
        r = _photon_cached(addr)
        if r and r[1] and r[2]:
            out.append(("photon", float(r[1]), float(r[2]), r[0], r[3] if len(r) > 3 else ""))
    except Exception:
        pass
    if not out:
        try:
            gf, la, lo, po = _gl_cached(addr) or (None, None, None, None)
            if gf and la and lo:
                out.append(("fallback", float(la), float(lo), gf, po))
        except Exception:
            pass
    return out

def _choose_best_coordinate(addr_query: str, cleaned: dict):
    """
    Forward-only selection:
      1) If two providers agree within 25m, average them.
      2) Else pick the first candidate inside Auckland (if checker exists).
      3) Else pick the first candidate.
    Returns (lat, lon, chosen_provider) or None.
    """
    cands = _safe_forward_both(addr_query)
    if not cands:
        return None

    agree_thresh = 25.0
    for i in range(len(cands)):
        for j in range(i + 1, len(cands)):
            di = _distance_meters(cands[i][1], cands[i][2], cands[j][1], cands[j][2])
            if di <= agree_thresh:
                lat = (cands[i][1] + cands[j][1]) / 2.0
                lon = (cands[i][2] + cands[j][2]) / 2.0
                return (lat, lon, f"{cands[i][0]}+{cands[j][0]}")

    for prov, la, lo, full, postal in cands:
        try:
            if hasattr(core, "is_in_auckland") and core.is_in_auckland(float(la), float(lo)):
                return (float(la), float(lo), prov)
        except Exception:
            pass

    prov, la, lo, _, _ = cands[0]
    return (float(la), float(lo), prov)

def _cleanup_temp_dirs_after_verify(ok: bool) -> None:
    """
    Delete temp dirs based on verification result and global toggle.
    """
    if ok:
        _delete_temp_suburb_dirs()
        print("🗑️ Temp Dirs Removed (Verification Matched).")
    elif _ALWAYS_DELETE_TEMP_DIRS:
        _delete_temp_suburb_dirs()
        print("🗑️ Temp dirs removed (verification mismatch; configured to always delete).")
    else:
        # Keep for inspection; optionally warn (respecting suppression flag)
        if not _SUPPRESS_TEMP_DIR_WARNINGS:
            print("⚠️ Temp dirs kept for inspection due to verification mismatch.")

# ---- The two Google Sheets flows (moved from main) ----

def run_sheets_clean_and_split_after_purge(
    input_file: str = "input_googlesheets.csv",
    *,
    do_split: bool = True,
    out_clean: str | None = None,
    out_fail: str | None = None,
    include_only_new: bool = False,
    exclude_new: bool = False,
    ensure_clear_dir: bool = True,
):
    """
    Option 5 (moved): Clean & Split Into Different Suburbs (Google Sheets)
    """
    if include_only_new and exclude_new:
        raise ValueError("include_only_new and exclude_new are mutually exclusive")

    # If we plan to split, optionally ensure the suburb export dirs are clean.
    if do_split and ensure_clear_dir:
        _clear_files_only(_SUBURB_BASE, "*")
        _ensure_temp_dirs_cleared_for_routed()

    # Prime master index (safe no-op if source missing)
    _load_master_index.cache_clear()
    _load_master_index()

    if not os.path.exists(input_file):
        print("❌ input_googlesheets.csv not found.")
        return

    # decide outputs without creating temp inputs
    if out_clean is None or out_fail is None:
        _oc, _of = _stemmed_outputs_for(input_file)
        out_clean = out_clean or _oc
        out_fail  = out_fail  or _of

    fieldnames = [
        "Old Number", "Unit",
        "Old Street",
        "ApartmentNumber", "Number", "Street",
        "Suburb", "PostalCode", "State",
        "Status", "Final Status",
        "Latitude", "Longitude",
        "Type", "Language", "Notes", "Other Notes",
    ]

    def _flip_before_write(rec: dict):
        num = (rec.get("Number") or "").strip()
        if not num:
            return
        m = HOUSE_FLIP_A.match(num)
        if m:
            rec["Number"] = f"{m.group(2)}/Unit{m.group(1).upper()}"
            return
        m = HOUSE_FLIP_B.match(num)
        if m:
            rec["Number"] = f"Unit{m.group(2).upper()}/{m.group(1)}"

    clean_count = fail_count = 0

    # in-file duplicate tracking
    seen_dupe_keys: set[tuple[str, str, str, str]] = set()
    dup_count = 0

    with open(out_clean, "w", newline="", encoding="utf-8", buffering=1024*1024) as fout_c, \
         open(out_fail,  "w", newline="", encoding="utf-8", buffering=1024*1024) as fout_f, \
         open(input_file, "r", newline="", encoding="utf-8") as f:

        wc = csv.DictWriter(fout_c, fieldnames=fieldnames); wc.writeheader()
        wf = csv.DictWriter(fout_f,  fieldnames=fieldnames); wf.writeheader()

        reader = csv.DictReader(f)
        for row in tqdm(reader, desc="✅ Stage 1/2: Cleaning/Write", unit="row"):
            if core.cancel_flag.is_set():
                print("⚠️ Cancelled during Google Sheets processing.")
                break

            old_unit    = (row.get("Unit") or "").strip()
            old_number  = (row.get("Number") or "").strip()
            old_street  = (row.get("Street") or "").strip()
            suburb_in   = (row.get("Suburb") or "").strip()
            old_lat     = (row.get("Latitude") or "").strip()
            old_lon     = (row.get("Longitude") or "").strip()

            apartment_number = (row.get("Apartment/Business") or "").strip()
            notes_val        = (row.get("Notes") or "").strip()
            language_val     = (row.get("Language") or "").strip()
            type_val         = (row.get("Type") or "").strip()

            # Optional filtering
            if include_only_new and not _notes_has_new_street_ci(notes_val):
                continue
            if exclude_new and _notes_has_new_street_ci(notes_val):
                continue

            merged_number = _combine_unit_and_number(old_unit, old_number)

            # Prefer provided Suburb/PostalCode; else parse "Street, Suburb"
            street_val = old_street
            if suburb_in:
                suburb_val = _canon_suburb_sheets(suburb_in)
            else:
                if "," in old_street:
                    left, right = old_street.split(",", 1)
                    street_val = left.strip()
                    suburb_val = _canon_suburb_sheets(right.strip())
                else:
                    suburb_val = ""

            # Street cleanup
            street_val = gs_strip_leading_duplicate_number_from_street(merged_number, street_val)
            street_val = _strip_trailing_postcode(street_val)
            street_val = _repair_corrupted_street(street_val)

            # Latitude/Longitude (only keep numeric-looking)
            lat_val = old_lat if _has_digits(old_lat) else ""
            lon_val = old_lon if _has_digits(old_lon) else ""

            # Strict: ignore incoming PostalCode, trust our lookup
            postal_code = _postal_for_suburb_sheets(suburb_val)

            # Normalize status
            incoming_status = (row.get("Status") or "").strip()
            status_val = "At Home" if incoming_status.lower() == "home" else incoming_status or "At Home"

            cleaned = {
                "Old Number": old_number,
                "Unit": old_unit,
                "Old Street": old_street,
                "ApartmentNumber": apartment_number,
                "Number": merged_number,
                "Street": street_val,
                "Suburb": suburb_val,
                "PostalCode": postal_code,
                "State": "Auckland",
                "Status": status_val,
                "Final Status": "Pass",
                "Latitude": lat_val,
                "Longitude": lon_val,
                "Type": type_val,
                "Language": language_val,
                "Notes": notes_val,
                "Other Notes": "",
            }

            _clean_notes_and_language(cleaned)
            _apply_new_street_overrides(cleaned, notes_val)



            # Fail rules (content-only)
            reasons = _should_fail_row(cleaned, old_unit, old_number, old_street)
            if reasons:
                cleaned["Final Status"] = "Fail"
                cleaned["Notes"] = (
                    cleaned.get("Notes", "") + (" | " if cleaned.get("Notes") else "") + "; ".join(reasons)
                )
                _clean_notes_and_language(cleaned)
                _flip_before_write(cleaned)
                wf.writerow({k: cleaned.get(k, "") for k in fieldnames})
                fail_count += 1
            else:
                cleaned["Final Status"] = "Pass"
                _flip_before_write(cleaned)
                wc.writerow({k: cleaned.get(k, "") for k in fieldnames})
                clean_count += 1

    # --- Stage 3: Split by KML polygons/territories
    if do_split:
        print("✅ Stage 3: Splitting By Territory Boundaries")
        core.split_cleaned_by_polygon_and_include_failed(
            out_clean, out_fail, kml_dir="KML Boundaries"
        )

    print(f"✅ Google Sheets Clean & Split complete. {clean_count} clean, {fail_count} failed.")



# ---------------------------------------------------------------------------
# 🔎 Verification: check New_Addresses_By_Suburb vs output_clean.csv
# ---------------------------------------------------------------------------
def _addr_key(row: dict) -> tuple[str, str, str]:
    """
    Unique-ish key for comparison: (Number, Street, Suburb) after simple canonicalization.
    """
    def canon(x: str) -> str:
        return _canon_text_cached((x or "").strip())
    return (canon(row.get("Number", "")), canon(row.get("Street", "")), canon(row.get("Suburb", "")))

def _dup_key_from_cleaned(rec: dict) -> tuple[str, str, str, str]:
    """
    Duplicate key for Sheets runs (pre-write), based on the *cleaned* values.
    Fields must match: ApartmentNumber, Number, Street, Suburb (canonicalized).
    """
    canon = _canon_text_cached
    return (
        canon((rec.get("ApartmentNumber") or "").strip()),
        canon((rec.get("Number")          or "").strip()),
        canon((rec.get("Street")          or "").strip()),
        canon((rec.get("Suburb")          or "").strip()),
    )

def _read_clean_keys(clean_csv: str) -> set[tuple[str, str, str]]:
    keys = set()
    if not os.path.exists(clean_csv):
        return keys
    with open(clean_csv, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            keys.add(_addr_key(row))
    return keys

def _read_suburb_keys_and_counts(suburb_dir: Path) -> tuple[set[tuple[str,str,str]], Counter]:
    keys: set[tuple[str,str,str]] = set()
    counts = Counter()
    if not suburb_dir.exists():
        return set(), counts
    for p in suburb_dir.glob("*.csv"):
        # Ignore failed files when matching against output_clean.csv
        if "failed" in p.stem.lower():
            continue
        with open(p, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                k = _addr_key(row)
                keys.add(k)
                counts[k] += 1
    return keys, counts


def verify_split_matches_clean(
    clean_csv: str = "output_clean.csv",
    suburb_dir: str | Path = "New_Addresses_By_Suburb"
) -> bool:
    """
    Compares output_clean.csv to merged suburb CSVs.
    Also scans __NEW and __OTHER for stray rows and reports them.
    Returns True only when counts and address sets match exactly and no duplicates are found.
    """
    suburb_dir = Path(suburb_dir)
    clean_keys = _read_clean_keys(clean_csv)
    suburb_keys, suburb_counts = _read_suburb_keys_and_counts(suburb_dir)

    ok = False  # default to not-ok; flip to True on perfect match

    if not clean_keys:
        print("⚠️ No rows found in output_clean.csv (or file missing).")
    if not suburb_dir.exists():
        print(f"⚠️ Suburb folder not found: {suburb_dir}")

    # --- Main report against final folder ---
    if clean_keys and suburb_dir.exists():
        missing = clean_keys - suburb_keys
        extras  = suburb_keys - clean_keys
        dups    = {k for k, c in suburb_counts.items() if c > 1}

        print("\n🔎 Verification report (output_clean.csv ↔ New_Addresses_By_Suburb)")
        print(f"• Clean rows:  {len(clean_keys)}")
        print(f"• Suburb rows: {sum(suburb_counts.values())} (unique {len(suburb_keys)})")

        if not missing and not extras and not dups and len(clean_keys) == len(suburb_keys):
            print("✅ Correct: Counts And Address Sets Match.")
            ok = True
        else:
            if missing:
                print(f"❌ Missing in suburb folder (not exported): {len(missing)}")
                for k in list(missing)[:50]:
                    print("   - (Number, Street, Suburb):", k)
                if len(missing) > 50:
                    print(f"   ... and {len(missing)-50} more")
            if extras:
                print(f"❌ Extra in suburb folder (not in clean): {len(extras)}")
                for k in list(extras)[:50]:
                    print("   - (Number, Street, Suburb):", k)
                if len(extras) > 50:
                    print(f"   ... and {len(extras)-50} more")
            if dups:
                print(f"❌ Duplicated in suburb folder (appears in >1 row/file): {len(dups)}")
                for k in list(dups)[:50]:
                    print(f"   - {k}  (count={suburb_counts[k]})")
                if len(dups) > 50:
                    print(f"   ... and {len(dups)-50} more")

        # --- Secondary: check temp folders for leftover CSVs (respects suppression flag) ---
        if not _SUPPRESS_TEMP_DIR_WARNINGS:
            for d in (_SUBURB_DIR_NEW, _SUBURB_DIR_OTHER):
                if d.exists():
                    _, counts = _read_suburb_keys_and_counts(d)
                    total = sum(counts.values())
                    if total > 0:
                        print(
                            f"⚠️ Temp folder '{d.name}' contains {total} row(s) across {len(list(d.glob('*.csv')))} file(s).")
                        print("   These should normally be empty after a run of Options 3 or 4.")

    return ok

# ---- Routed wrappers (updated to temp-dir pattern + verification) ------------

def _run_option1_routed():
    """
    Option 3 in menu: Clean & Split Into Different Suburbs (light OTHER + full NEW),
    using temp dirs per half and a single merge at the end.
    """
    src = "input_googlesheets.csv"
    if not os.path.exists(src):
        print("❌ input_googlesheets.csv not found.")
        return

    # Ensure destination is empty once at the start
    _clear_files_only(_SUBURB_BASE, "*")


    print("📦 Option 1 routing (no temp inputs): OTHER → Opt1, NEW → Opt3")

    # OTHER (light clean, no full verify)
    run_sheets_clean_and_split_after_purge(
        input_file=src,
        do_split=False,
        out_clean="output_clean.other.csv",
        out_fail="output_fail.other.csv",
        exclude_new=True,
        ensure_clear_dir=False,
    )
    dir_other = _run_split_to_dir("output_clean.other.csv", "output_fail.other.csv", label="OTHER", kml_dir="KML Boundaries")

    # NEW (full geocode verify)
    run_sheets_clean_and_split_new_streets_verify(
        input_file=src,
        do_split=False,
        out_clean="output_clean.new.csv",
        out_fail="output_fail.new.csv",
    )
    dir_new = _run_split_to_dir("output_clean.new.csv", "output_fail.new.csv", label="NEW", kml_dir="KML Boundaries")

    # Merge temp dirs into the final folder
    final_dir = _SUBURB_BASE
    _clear_files_only(final_dir, "*")  # keep folder, just empty its files
    _merge_suburb_dirs([dir_other, dir_new], final_dir)
    # Duplicate de-duplication in final suburb folder disabled.

    _merge_csvs(["output_clean.other.csv", "output_clean.new.csv"], "output_clean.csv")
    _merge_csvs(["output_fail.other.csv", "output_fail.new.csv"], "output_fail.csv")
    _summarize_final_status("output_clean.csv", "output_fail.csv")


    ok = verify_split_matches_clean("output_clean.csv", final_dir)
    _cleanup_temp_dirs_after_verify(ok)
    _warn_if_temp_dirs_have_files()


def _run_option2_routed():
    """
    Option 4 in menu: Clean & Split Into Different Suburbs (Full Geocode Check for both),
    using temp dirs then a single merge.
    """
    src = "input_googlesheets.csv"
    if not os.path.exists(src):
        print("❌ input_googlesheets.csv not found.")
        return

    # Keep folder; just empty its files at the start
    _clear_files_only(_SUBURB_BASE, "*")

    print("📦 Option 2 routing (no temp inputs): OTHER → Opt2, NEW → Opt3")

    run_sheets_clean_and_split_after_purge_verify(
        input_file=src,
        do_split=False,
        out_clean="output_clean.other.csv",
        out_fail="output_fail.other.csv",
        exclude_new=True,
    )
    print("✅ Stage 3: Splitting By Territory Boundaries (OTHER → Opt2)")
    dir_other = _run_split_to_dir("output_clean.other.csv", "output_fail.other.csv", label="OTHER", kml_dir="KML Boundaries")

    run_sheets_clean_and_split_new_streets_verify(
        input_file=src,
        do_split=False,
        out_clean="output_clean.new.csv",
        out_fail="output_fail.new.csv",
    )
    print("✅ Stage 4: Splitting By Territory Boundaries (NEW → Opt3)")
    dir_new = _run_split_to_dir("output_clean.new.csv", "output_fail.new.csv", label="NEW", kml_dir="KML Boundaries")

    final_dir = _SUBURB_BASE
    _clear_files_only(final_dir, "*")  # keep folder, just empty its files
    _merge_suburb_dirs([dir_other, dir_new], final_dir)

    # De-dupe within final folder to remove duplicate address rows
    touched, removed = _dedupe_suburb_folder(final_dir)
    if removed:
        print(f"🧹 De-duplicated suburb exports: files touched={touched}, rows removed={removed}")

    _merge_csvs(["output_clean.other.csv", "output_clean.new.csv"], "output_clean.csv")
    _merge_csvs(["output_fail.other.csv", "output_fail.new.csv"], "output_fail.csv")
    _summarize_final_status("output_clean.csv", "output_fail.csv")


    print("🧩 Merged suburb files → New_Addresses_By_Suburb (single folder, temp dirs)")


    ok = verify_split_matches_clean("output_clean.csv", final_dir)
    _cleanup_temp_dirs_after_verify(ok)
    _warn_if_temp_dirs_have_files()

def _run_option3_routed():
    """
    Option 3 sequence flipped: NEW first (Opt3 full verify), then OTHER (Opt2/Opt1).
    """
    src = "input_googlesheets.csv"
    if not os.path.exists(src):
        print("❌ input_googlesheets.csv not found.")
        return

    # Keep folder; just empty its files at the start
    _clear_files_only(_SUBURB_BASE, "*")

    print("📦 Option 3 routing (no temp inputs): NEW → Opt3, OTHER → Opt2")

    # NEW first
    run_sheets_clean_and_split_new_streets_verify(
        input_file=src,
        do_split=False,
        out_clean="output_clean.new.csv",
        out_fail="output_fail.new.csv",
    )
    dir_new = _run_split_to_dir("output_clean.new.csv", "output_fail.new.csv", label="NEW", kml_dir="KML Boundaries")

    # OTHER next
    run_sheets_clean_and_split_after_purge_verify(
        input_file=src,
        do_split=False,
        out_clean="output_clean.other.csv",
        out_fail="output_fail.other.csv",
        exclude_new=True,
    )
    dir_other = _run_split_to_dir("output_clean.other.csv", "output_fail.other.csv", label="OTHER", kml_dir="KML Boundaries")

    final_dir = _SUBURB_BASE
    _clear_files_only(final_dir, "*")  # keep folder, just empty its files
    _merge_suburb_dirs([dir_new, dir_other], final_dir)
    # Duplicate de-duplication in final suburb folder disabled.

    _merge_csvs(["output_clean.other.csv", "output_clean.new.csv"], "output_clean.csv")
    _merge_csvs(["output_fail.other.csv", "output_fail.new.csv"], "output_fail.csv")
    _summarize_final_status("output_clean.csv", "output_fail.csv")


    ok = verify_split_matches_clean("output_clean.csv", final_dir)
    _cleanup_temp_dirs_after_verify(ok)
    _warn_if_temp_dirs_have_files()



# ---- Clean-only routed wrappers (unchanged outputs, no split) ---------------

def _run_option1_clean_only():
    """
    Option 1: ✨ Clean Google Sheets  (no split)
      OTHER rows  → light clean (no full geocode verify)
      NEW STREET  → full geocode verify + overrides

    Final step:
      - Merge OTHER + NEW outputs into output_clean.csv / output_fail.csv
      - Run run_final_master_duplicate_filter(...) so any address whose
        (ApartmentNumber, Number, Street) triplet exists in the master DB
        is moved from clean → fail as "Duplicate".
    """
    src = "input_googlesheets.csv"
    if not os.path.exists(src):
        print("❌ input_googlesheets.csv not found.")
        return

    print("📦 Option 1 (no split, no temp inputs): OTHER → Opt1, NEW → Opt3")

    # ------------------------------------------------------------------
    # 1) Run light clean for OTHER rows (no full geocode verify)
    # ------------------------------------------------------------------
    other_clean = "output_clean.other.csv"
    other_fail  = "output_fail.other.csv"

    run_sheets_clean_and_split_after_purge(
        input_file=src,
        do_split=False,
        out_clean=other_clean,
        out_fail=other_fail,
        exclude_new=True,   # skip "New Street" notes
    )

    # ------------------------------------------------------------------
    # 2) Run full verify for NEW STREET rows
    # ------------------------------------------------------------------
    new_clean = "output_clean.new.csv"
    new_fail  = "output_fail.new.csv"

    run_sheets_clean_and_split_new_streets_verify(
        input_file=src,
        do_split=False,
        out_clean=new_clean,
        out_fail=new_fail,
    )

    # ------------------------------------------------------------------
    # 3) Merge OTHER + NEW into unified outputs
    # ------------------------------------------------------------------
    def _merge_two_csvs(src_a: str, src_b: str, dest: str) -> None:
        """
        Merge src_a and src_b into dest:
          - If both exist, dest gets header from the first non-empty file,
            then all data rows from both (no duplicate header lines).
          - If only one exists, dest is just a copy of that one.
        """
        # Remove old dest so we always recreate it cleanly
        if os.path.exists(dest):
            try:
                os.remove(dest)
            except Exception:
                pass

        header_written = False
        dest_fp = None
        writer = None

        try:
            for src_path in (src_a, src_b):
                if not os.path.exists(src_path):
                    continue

                with open(src_path, newline="", encoding="utf-8") as fin:
                    reader = csv.reader(fin)
                    try:
                        header = next(reader)
                    except StopIteration:
                        continue  # empty file

                    # Open dest on first non-empty source
                    if not header_written:
                        dest_fp = open(dest, "w", newline="", encoding="utf-8")
                        writer = csv.writer(dest_fp)
                        writer.writerow(header)
                        header_written = True

                    # Append all data rows
                    for row in reader:
                        writer.writerow(row)
        finally:
            if dest_fp is not None:
                dest_fp.close()

        # If we never wrote a header, dest should not exist
        if not header_written and os.path.exists(dest):
            try:
                os.remove(dest)
            except Exception:
                pass

    # Unified outputs for downstream tools / final filter
    final_clean = "output_clean.csv"
    final_fail  = "output_fail.csv"

    _merge_two_csvs(other_clean, new_clean, final_clean)
    _merge_two_csvs(other_fail,  new_fail,  final_fail)

    # ------------------------------------------------------------------
    # 4) FINAL strict duplicate filter vs master DB
    #    (Street + Number + ApartmentNumber identical after canonicalisation)
    # ------------------------------------------------------------------
    run_final_master_duplicate_filter(final_clean, final_fail)
    run_verify_fail_against_master(final_clean, final_fail)

    # ------------------------------------------------------------------
    # 5) Print run summary
    # ------------------------------------------------------------------
    _summarize_final_status(final_clean, final_fail)




def _run_option2_clean_only():
    """
    Option 2: ✨ Clean Google Sheets (Full Geocode Check)  (no split)
      OTHER rows → full geocode verify
      NEW STREET rows → full geocode verify + overrides
    """
    src = "input_googlesheets.csv"
    if not os.path.exists(src):
        print("❌ input_googlesheets.csv not found.")
        return

    print("📦 Option 2 (No Split, No Temp Inputs): OTHER → Opt2, NEW → Opt3")

    # Run without splitting
    run_sheets_clean_and_split_after_purge_verify(
        input_file=src,
        do_split=False,
        out_clean="output_clean.other.csv",
        out_fail="output_fail.other.csv",
        exclude_new=True,
    )
    run_sheets_clean_and_split_new_streets_verify(
        input_file=src,
        do_split=False,
        out_clean="output_clean.new.csv",
        out_fail="output_fail.new.csv",
    )

    # Merge outputs
    _merge_csvs(["output_clean.other.csv", "output_clean.new.csv"], "output_clean.csv")
    _merge_csvs(["output_fail.other.csv",  "output_fail.new.csv"],  "output_fail.csv")

    # 🔎 Final strict duplicate check on merged outputs
    run_final_master_duplicate_filter("output_clean.csv", "output_fail.csv")
    run_verify_fail_against_master("output_clean.csv", "output_fail.csv")

    # Final summary
    _summarize_final_status("output_clean.csv", "output_fail.csv")




# -----------------------------------------------------------------------------


# ---- Submenu exposed to main

def render_menu():
    print("\n\033[4mGoogle Sheets (input_googlesheets)\033[0m")
    print("1 - ✨ Clean Google Sheets")
    print("2 - ✨ Clean Google Sheets (Full Geocode Check)")
    print("3 - ✨ Clean & Split Into Different Suburbs")
    print("4 - ✨ Clean & Split Into Different Suburbs (Full Geocode Check)")
    print("5 - 📚 Check Master Database For Duplicates")
    print("0 - Back to Main Menu")



def open_menu():
    while True:
        render_menu()
        choice = (input("\nChoose an option (0/1/2/3/4/5): ") or "").strip()
        if choice == "0":
            print("↩️  Returning to main menu...\n")
            return

        if choice not in {"1", "2", "3", "4", "5"}:
            print("❌ Invalid choice.\n")
            continue

        confirm = input("Proceed? (y to continue / any other key to cancel): ").strip().lower()
        if confirm != "y":
            print("❌ Cancelled.\n")
            continue

        print("⏳ Process starting... Press 'q' at any time to cancel.\n")
        core.cancel_flag.clear()
        listener_thread = threading.Thread(target=core.listen_for_quit_key, daemon=True)
        listener_thread.start()

        try:
            if choice == "1":
                core.run_with_cancel(_run_option1_clean_only)       # no split
            elif choice == "2":
                core.run_with_cancel(_run_option2_clean_only)       # no split
            elif choice == "3":
                core.run_with_cancel(_run_option1_routed)           # split (temp dirs + merge + verify)
            elif choice == "4":
                core.run_with_cancel(_run_option2_routed)           # split (temp dirs + merge + verify)
            else:  # "5"
                core.run_with_cancel(run_master_db_duplicate_audit) # fail-only; no clean
        finally:
            core.cancel_flag.set()
            try:
                listener_thread.join(timeout=0.25)
            except Exception:
                pass




