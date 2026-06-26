# Clean_NewWorldScheduler.py

import json
import logging
import nest_asyncio
from datetime import datetime
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from random import uniform
from typing import Optional
from tqdm import tqdm
import threading
import requests
import concurrent.futures as concurrent
import asyncio
import threading
from collections import defaultdict
import asyncio
import concurrent.futures
import threading
import requests
import sqlite3
import pandas as pd
import aiohttp
from datetime import datetime
import re
import csv
import shutil
import subprocess
import shlex
import importlib.util
import types
import importlib, sys
import Other_Functions as oth
from Other_Functions import remove_files, remove_files_in_folder  # if you want direct names
import asyncio
import aiohttp
import os, csv, math, shutil
from xml.etree import ElementTree as ET
from datetime import datetime
import concurrent.futures
import aiohttp

# globals that other parts might not have set yet
geocode_lock = globals().get("geocode_lock", threading.Lock())
geocode_sources_used = globals().get("geocode_sources_used", defaultdict(int))
VERBOSE_PRE = globals().get("VERBOSE_PRE", False)

# ---- Input sources ----
INPUT_NWS = "input_nws.csv"                # New World Scheduler

# Default output file paths
output_clean = "output_clean.csv"
output_fail  = "output_fail.csv"


SUBURB_RESOLVE_MAX_PTS_PER_STREET = 80      # from §1
SUBURB_RESOLVE_PROBE_BUDGET = 50            # fewer network enrichments in §1
RESULT_ONLY_LOGS = True                     # you already have this; keep it to reduce I/O

# Free-form text fields we must not alter
PRESERVE_FREEFORM_FIELDS = {"Notes", "NotesFromPublisher"}

# --- Global toggle ---
USE_LINZ_MEMORY = True   # <-- set True to enable, False to disable


# Thread-safe writes
_log_lock = threading.Lock()

def _log_header_has_street(path: str = "corrections_log.csv") -> bool:
    """True if the file exists and has a 'Street' header column."""
    if not os.path.exists(path):
        return False
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            r = csv.reader(f)
            header = next(r, [])
        return any((h or "").strip().lower() == "street" for h in header)
    except Exception:
        return False

def log_correction(event: str, details: str = "", street: Optional[str] = None) -> None:
    """
    Append: Timestamp, Street, Event, Details to corrections_log.csv.
    Creates/repairs header when missing. Thread-safe.
    """
    log_file = "corrections_log.csv"
    with _log_lock:
        need_header = (not os.path.exists(log_file)) or (not _log_header_has_street(log_file))
        with open(log_file, "a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if need_header:
                w.writerow(["Timestamp", "Street", "Event", "Details"])
            w.writerow([datetime.now().isoformat(), (street or "").strip(), event, details])

import os, csv, math, shutil
from xml.etree import ElementTree as ET

def _safe_float(v, default=None):
    try:
        s = str(v).strip()
        if s == "": return default
        return float(s)
    except Exception:
        return default

def _digits_int(s):
    import re
    ds = re.sub(r"\D", "", str(s or ""))
    return int(ds) if ds.isdigit() else None

# --- geometry helpers ---
def _point_in_poly(lon, lat, poly):
    """Ray casting (lon,lat). poly = [(lon,lat), ...] closed or open."""
    inside = False
    n = len(poly)
    if n < 3:
        return False
    for i in range(n):
        x1,y1 = poly[i]
        x2,y2 = poly[(i+1) % n]
        # check if point is exactly on a segment (treat as inside)
        if _point_on_segment(lon, lat, x1, y1, x2, y2):
            return True
        # ray cast
        cond = ((y1 > lat) != (y2 > lat)) and (lon < (x2-x1)*(lat-y1)/(y2-y1 + 1e-16) + x1)
        if cond:
            inside = not inside
    return inside


def merge_publisher_notes_into_notes(rows, sep=" /  "):
    """
    Move NotesFromPublisher into Notes (in place).
    If Notes already has text, append:  <existing><sep><publisher>.
    Always clear NotesFromPublisher after merging.
    Returns the count of rows changed.
    """
    changed = 0
    for r in rows or []:
        notes = (r.get("Notes") or "").strip()
        pub   = (r.get("NotesFromPublisher") or "").strip()
        if not pub:
            continue
        r["Notes"] = f"{notes}{sep}{pub}" if notes else pub
        r["NotesFromPublisher"] = ""
        changed += 1
    return changed

def _point_on_segment(x, y, x1, y1, x2, y2, eps=1e-9):
    # distance to segment < tiny threshold
    # quick bbox
    if min(x1,x2)-eps <= x <= max(x1,x2)+eps and min(y1,y2)-eps <= y <= max(y1,y2)+eps:
        # colinearity check via area
        area = abs((x2-x1)*(y-y1) - (y2-y1)*(x-x1))
        if area <= eps * max(1.0, math.hypot(x2-x1, y2-y1)):
            return True
    return False

def _dist_point_to_segment(px, py, x1, y1, x2, y2):
    vx, vy = x2-x1, y2-y1
    wx, wy = px-x1, py-y1
    seglen2 = vx*vx + vy*vy
    if seglen2 <= 0:
        return math.hypot(px-x1, py-y1)
    t = max(0.0, min(1.0, (wx*vx + wy*vy) / seglen2))
    cx, cy = x1 + t*vx, y1 + t*vy
    return math.hypot(px-cx, py-cy)

def _min_dist_to_polygon(lon, lat, poly):
    if _point_in_poly(lon, lat, poly):
        return 0.0
    n = len(poly)
    if n < 2:
        return float("inf")
    return min(_dist_point_to_segment(lon, lat, poly[i][0], poly[i][1], poly[(i+1)%n][0], poly[(i+1)%n][1]) for i in range(n))

def _load_kml_polygons(kml_dir="KML Boundaries"):
    """
    Return dict: suburb_name -> [poly1, poly2, ...]
    Where a poly is a list of (lon, lat) tuples.
    Uses KML filename (without extension) as suburb_name.
    """
    polys = {}
    if not os.path.isdir(kml_dir):
        print(f"⚠️ KML folder not found: {kml_dir}")
        return polys

    for fname in os.listdir(kml_dir):
        if not fname.lower().endswith(".kml"):
            continue
        path = os.path.join(kml_dir, fname)
        name = os.path.splitext(fname)[0]  # suburb name
        try:
            tree = ET.parse(path)
            root = tree.getroot()
            # KML can have namespaces; find them loosely
            ns = {}
            if root.tag.startswith("{"):
                uri = root.tag.split("}")[0][1:]
                ns["k"] = uri
            coords_texts = []
            # Polygons & MultiGeometry
            for elem in root.findall(".//k:Polygon", ns) + root.findall(".//Polygon", ns):
                for ring in elem.findall(".//k:outerBoundaryIs/k:LinearRing/k:coordinates", ns) + \
                            elem.findall(".//outerBoundaryIs/LinearRing/coordinates", ns):
                    if ring.text:
                        coords_texts.append(ring.text)
            if not coords_texts:
                # try simple coordinates under <coordinates> directly
                for ring in root.findall(".//k:coordinates", ns) + root.findall(".//coordinates", ns):
                    if ring.text: coords_texts.append(ring.text)

            list_polys = []
            for text in coords_texts:
                pts = []
                for triplet in text.strip().split():
                    parts = triplet.split(",")
                    if len(parts) >= 2:
                        lon = _safe_float(parts[0])
                        lat = _safe_float(parts[1])
                        if lon is not None and lat is not None:
                            pts.append((lon, lat))
                if len(pts) >= 3:
                    list_polys.append(pts)
            if list_polys:
                polys[name] = list_polys
        except Exception as e:
            print(f"⚠️ KML parse failed for {fname}: {e}")
    return polys

def _assign_point_to_polygons(lon, lat, polygons_by_name):
    """
    Return assignment info:
      ("IN", name)        if inside exactly one polygon
      ("BORDER", names)   if inside >1 or on boundaries
      ("NEAREST", name)   if in none -> nearest by edge distance
      None                if no polygons available
    """
    if not polygons_by_name:
        return None
    inside = []
    for name, polys in polygons_by_name.items():
        for poly in polys:
            if _point_in_poly(lon, lat, poly):
                inside.append(name)
                break
    inside = list(dict.fromkeys(inside))  # dedupe preserve order
    if len(inside) == 1:
        return ("IN", inside[0])
    if len(inside) > 1:
        return ("BORDER", inside)

    # nearest
    best_name, best_d = None, float("inf")
    for name, polys in polygons_by_name.items():
        for poly in polys:
            d = _min_dist_to_polygon(lon, lat, poly)
            if d < best_d:
                best_d, best_name = d, name
    return ("NEAREST", best_name) if best_name else None


def _pick_nearest_number_target(this_num, candidates):
    """
    candidates: list of (num_int, assigned_name)
    Returns assigned_name with smallest |num - this_num|.
    """
    if this_num is None or not candidates:
        return None
    best = None
    best_gap = None
    for n, nm in candidates:
        if n is None:
            continue
        gap = abs(n - this_num)
        if best_gap is None or gap < best_gap:
            best_gap, best = gap, nm
    return best


def split_cleaned_by_polygon_and_include_failed(clean_file, fail_file, kml_dir="KML Boundaries"):
    """
    Split using KML polygons with suburb-priority + street-level reconciliation:

      Priority search (must be INSIDE a polygon):
        A) Same-suburb KML names first (e.g., 'Flatbush', 'Flatbush 1', 'Flat Bush 2', 'Flatbush2' ...)
        B) Then 'nearby' suburbs from NEARBY_SUBURBS (their numbered KMLs too)

      If still undecided:
        C) Per-row assignment (IN/BORDER/NEAREST) like before
        D) Resolve BORDER/no-geocode via same-street nearest number
        E) Street-level reconciliation: dominant polygon per street pulls ambiguous rows
    """
    import os, re, csv, shutil

    out_dir = "New_Addresses_By_Suburb"
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    polygons_by_name = _load_kml_polygons(kml_dir)
    if not polygons_by_name:
        print("⚠️ No polygons loaded — falling back to old suburb split by CSV 'Suburb' column.")
        return split_cleaned_by_suburb_and_include_failed(clean_file, fail_file)

    # ---------- helpers ----------
    def _norm_token(s):
        s = (s or "").strip().title()
        s = re.sub(r"\s+", " ", s)
        return s

    def _slug(s):
        # lower, strip spaces/hyphens/emdash so "Flat Bush-2" -> "flatbush2"
        s = (s or "").strip().lower()
        s = re.sub(r"[\s\-–—]+", "", s)
        return s

    def _base_suburb_name(s):
        s = _norm_token(s)
        s = re.sub(r"[\-–—]\s*\d+$", "", s)
        s = re.sub(r"\s+\d+$", "", s)
        return s

    def _kml_names_for_suburb(suburb_name, polygons_dict):
        """
        Match KMLs by slug so 'Flat Bush 2', 'Flatbush-2', 'Flatbush2' all match 'Flatbush'.
        Order: exact base first, then numbered variants, then other prefixed forms.
        """
        base = _base_suburb_name(suburb_name)
        if not base:
            return []
        base_slug = _slug(base)
        exact, numbered, others = [], [], []
        for nm in polygons_dict.keys():
            nm_slug = _slug(nm)
            if nm_slug == base_slug:
                exact.append(nm)
            elif nm_slug.startswith(base_slug):
                tail = nm_slug[len(base_slug):]
                if re.fullmatch(r"\d+", tail):
                    numbered.append(nm)
                else:
                    others.append(nm)
        return exact + sorted(numbered) + sorted(others)

    def _priority_inside_match(lon, lat, suburb_name, polygons_dict):
        """Try SAME-SUBURB KMLs only; assign only if INSIDE."""
        if suburb_name:
            candidates = _kml_names_for_suburb(suburb_name, polygons_dict)
        else:
            candidates = []
        if not candidates:
            return None
        inside_hits = []
        for nm in candidates:
            for poly in polygons_dict.get(nm, []):
                if _point_in_poly(lon, lat, poly):
                    inside_hits.append(nm); break
        inside_hits = list(dict.fromkeys(inside_hits))
        if len(inside_hits) == 1:
            return ("IN", inside_hits[0])
        if len(inside_hits) > 1:
            return ("BORDER", inside_hits)
        return None

    def _priority_inside_match_nearby(lon, lat, suburb_name, polygons_dict):
        """Try NEARBY_SUBURBS of the given suburb; assign only if INSIDE."""
        if not suburb_name:
            return None
        base = _base_suburb_name(suburb_name)
        nearby = []
        try:
            cand = canon_suburb(base) if "canon_suburb" in globals() else base
            nearby = list(NEARBY_SUBURBS.get(cand, []))
        except Exception:
            nearby = []
        inside_hits = []
        for nb in nearby:
            cand_names = _kml_names_for_suburb(nb, polygons_dict)
            for nm in cand_names:
                for poly in polygons_dict.get(nm, []):
                    if _point_in_poly(lon, lat, poly):
                        inside_hits.append(nm); break
        inside_hits = list(dict.fromkeys(inside_hits))
        if len(inside_hits) == 1:
            return ("IN", inside_hits[0])
        if len(inside_hits) > 1:
            return ("BORDER", inside_hits)
        return None

    def _nz_fix_coords(lat, lon):
        """
        Fix obvious lat/lon swaps using NZ-ish bounds:
          lat ~ [-48, -33], lon ~ [165, 180]
        """
        try:
            if lat is None or lon is None:
                return lat, lon
            if -48 <= lat <= -33 and 165 <= lon <= 180:
                return lat, lon
            # swapped?
            if -48 <= lon <= -33 and 165 <= lat <= 180:
                return lon, lat
        except Exception:
            pass
        return lat, lon  # leave as-is if unsure

    # NEW: filename safety (handles strings or lists)
    def _safe_filename(name_or_list):
        """
        Convert a polygon/suburb name (str or list) into a safe filename stem.
        - If list, join unique non-empty items with '_'
        - Keep only [A-Za-z0-9_], collapse spaces to '_'
        - Default to 'Unassigned' if empty after cleaning
        """
        if isinstance(name_or_list, list):
            parts = [str(x).strip() for x in name_or_list if str(x).strip()]
            stem = "_".join(sorted(set(parts)))
        else:
            stem = str(name_or_list or "").strip()
        stem = re.sub(r"\s+", "_", stem)
        stem = re.sub(r"[^A-Za-z0-9_]", "", stem)
        return stem or "Unassigned"

    from collections import defaultdict, Counter

    # Read rows
    rows = []
    fieldnames = None
    if os.path.exists(clean_file):
        with open(clean_file, "r", encoding="utf-8") as f:
            r = csv.DictReader(f)
            fieldnames = r.fieldnames
            rows = list(r)
    else:
        print(f"⚠️ Clean file not found: {clean_file}")

    total_rows = len(rows)
    if not fieldnames:
        print("⚠️ No rows to split.")
        return

    # Group by street
    street_rows = defaultdict(list)
    for i, row in enumerate(rows):
        st = (row.get("Street") or "").strip().title()
        street_rows[st].append(i)

    # Per-street number → polygon hints
    street_number_candidates = defaultdict(list)  # street -> list[(num_int, polygon_name)]

    # Per-row assignment & meta
    row_assign_name = [None] * total_rows
    row_assign_kind = [None] * total_rows  # "IN" | "BORDER" | "NEAREST" | "DOMINANT" | None

    # ---------- Pass 0: PRIORITY by SAME SUBURB / NEARBY (INSIDE ONLY) ----------
    for idx, row in enumerate(rows):
        st  = (row.get("Street")  or "").strip().title()
        sb  = (row.get("Suburb")  or "").strip().title()
        lat = _safe_float(row.get("Latitude"))
        lon = _safe_float(row.get("Longitude"))
        lat, lon = _nz_fix_coords(lat, lon)
        num_i = _digits_int(row.get("Number"))
        if lat is None or lon is None:
            continue

        # A) Same-suburb KML names first
        res = _priority_inside_match(lon, lat, sb, polygons_by_name)
        if res:
            kind, val = res
            row_assign_kind[idx] = kind
            if kind == "IN":
                row_assign_name[idx] = val
                if num_i is not None:
                    street_number_candidates[st].append((num_i, val))
                continue
            if kind == "BORDER":
                continue  # defer

        # B) Nearby suburbs’ KML names
        res = _priority_inside_match_nearby(lon, lat, sb, polygons_by_name)
        if res:
            kind, val = res
            row_assign_kind[idx] = kind
            if kind == "IN":
                row_assign_name[idx] = val
                if num_i is not None:
                    street_number_candidates[st].append((num_i, val))
            continue  # BORDER deferred

    # ---------- Pass 1: Basic assignment (for unresolved) ----------
    for idx, row in enumerate(rows):
        if row_assign_name[idx] is not None or row_assign_kind[idx] == "BORDER":
            continue
        st = (row.get("Street") or "").strip().title()
        num_i = _digits_int(row.get("Number"))
        lat = _safe_float(row.get("Latitude"))
        lon = _safe_float(row.get("Longitude"))
        lat, lon = _nz_fix_coords(lat, lon)
        if lat is None or lon is None:
            continue
        res = _assign_point_to_polygons(lon, lat, polygons_by_name)
        if not res:
            continue
        kind, val = res
        row_assign_kind[idx] = kind
        if kind == "IN":
            row_assign_name[idx] = val
            if num_i is not None:
                street_number_candidates[st].append((num_i, val))
        elif kind == "NEAREST":
            row_assign_name[idx] = val
            if num_i is not None:
                street_number_candidates[st].append((num_i, val))
        # BORDER is left unresolved for now

    # ---------- Pass 2: Resolve BORDER and no-geocode via same-street nearest number; else NEAREST ----------
    for idx, row in enumerate(rows):
        if row_assign_name[idx] is not None:
            continue
        st = (row.get("Street") or "").strip().title()
        num_i = _digits_int(row.get("Number"))
        lat = _safe_float(row.get("Latitude"))
        lon = _safe_float(row.get("Longitude"))
        lat, lon = _nz_fix_coords(lat, lon)

        pick = _pick_nearest_number_target(num_i, street_number_candidates.get(st, []))
        if pick:
            row_assign_name[idx] = pick
            row_assign_kind[idx] = "NEAREST"
            continue

        if lat is not None and lon is not None:
            kind_val = _assign_point_to_polygons(lon, lat, polygons_by_name)
            if kind_val:
                kind, val = kind_val
                if kind == "BORDER":
                    # collapse to NEAREST by edge distance as final tie-break
                    kind, val = ("NEAREST", _assign_point_to_polygons(lon, lat, polygons_by_name)[1])
                row_assign_kind[idx] = kind
                row_assign_name[idx] = val

    # ---------- Pass 3: Street-level reconciliation (dominant polygon pulls ambiguous rows) ----------
    street_in_counts = defaultdict(Counter)
    street_in_total  = defaultdict(int)
    for st, idxs in street_rows.items():
        for i in idxs:
            if row_assign_kind[i] == "IN" and row_assign_name[i]:
                street_in_counts[st][row_assign_name[i]] += 1
                street_in_total[st] += 1

    street_dominant = {}
    for st, ctr in street_in_counts.items():
        total = street_in_total.get(st, 0)
        if total <= 0:
            continue
        name, cnt = ctr.most_common(1)[0]
        frac = cnt / max(1, total)
        if cnt >= 3 and frac >= 0.60:
            street_dominant[st] = (name, frac, cnt)

    for st, dom in street_dominant.items():
        dom_name, _, _ = dom
        for i in street_rows.get(st, []):
            if row_assign_kind[i] in (None, "NEAREST", "BORDER"):
                row_assign_name[i] = dom_name
                row_assign_kind[i] = "DOMINANT"

    # ---------- Write CSVs (patched for list-safe filenames) ----------
    counts = Counter()
    unassigned = 0
    for idx, row in enumerate(rows):
        suburb_name = row_assign_name[idx]
        if not suburb_name:
            unassigned += 1
            suburb_name = "Unassigned"

        # (patch) make a safe filename even if suburb_name is a list
        out_stem = _safe_filename(suburb_name)
        out_name = f"{out_stem}.csv"
        out_path = os.path.join(out_dir, out_name)

        write_header = not os.path.exists(out_path)
        with open(out_path, "a", newline="", encoding="utf-8") as sf:
            w = csv.DictWriter(sf, fieldnames=fieldnames)
            if write_header:
                w.writeheader()

            # (nice-to-have) stringify any list-ish fields for the row before writing
            row_to_write = dict(row)
            for k, v in list(row_to_write.items()):
                if isinstance(v, list):
                    row_to_write[k] = ", ".join(str(x).strip() for x in v if str(x).strip())

            w.writerow(row_to_write)

        # Store a readable key for display counts (convert list to pretty string)
        if isinstance(suburb_name, list):
            disp_key = ", ".join(str(x).strip() for x in suburb_name if str(x).strip()) or "Unassigned"
        else:
            disp_key = str(suburb_name or "Unassigned")
        counts[disp_key] += 1

    # Include failed output
    if os.path.exists(fail_file):
        shutil.copy(fail_file, os.path.join(out_dir, "Failed_Output.csv"))

    # ---------- Summary (list-safe display) ----------
    normal_keys = [k for k in counts.keys() if k != "Unassigned"]
    normal_keys.sort()
    ordered = normal_keys + (["Unassigned"] if "Unassigned" in counts else [])

    print("\n✅ Cleaned Addresses Split Into Suburbs Inside 'New_Addresses_By_Suburb' Folder")
    print(f"📁 {len(ordered) + (1 if os.path.exists(os.path.join(out_dir,'Failed_Output.csv')) else 0)} file(s) created:\n")
    for k in ordered:
        print(f"    📑 {k.replace(' ','_')}.csv — {counts[k]} row(s)")
    if os.path.exists(os.path.join(out_dir, "Failed_Output.csv")):
        print("    📑 Failed_Output.csv")

    assigned_rows = sum(counts.values()) - counts.get("Unassigned", 0)
    missing = total_rows - assigned_rows
    print("\n📊 Split Summary")
    print("===============")
    for k in normal_keys:
        print(f"• {k}: {counts[k]}")
    if "Unassigned" in counts:
        print(f"• Unassigned: {counts['Unassigned']}")

    print(f"\nTotal rows (clean): {total_rows}")
    print(f"Assigned to polygons: {assigned_rows}")
    print(f"Missing (assigned = total - missing): {missing}")

    if missing == 0 and counts.get("Unassigned", 0) == 0:
        print("\n✅ Split Successful — All Streets Assigned To Polygon Suburbs.")
    else:
        print("\n⚠️ Some rows could not be placed (see Unassigned).")



# ---- Asyncio warning suppression patch ----
import asyncio
import traceback

def _asyncio_exception_handler(loop, context):
    """

    Custom asyncio exception handler to suppress noisy warnings
    like 'Task was destroyed but it is pending!' and send them to log.
    """
    msg = context.get("message", "")
    exc = context.get("exception")

    # Suppress 'Task was destroyed but it is pending!'
    if "Task was destroyed but it is pending" in msg:
        _log_quiet("Async Warning", msg, important=False)
        return

    # Log other async exceptions quietly
    if exc:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        _log_quiet("Async Exception", tb, important=False)
    else:
        _log_quiet("Async Message", msg, important=False)

try:
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(_asyncio_exception_handler)
except RuntimeError:
    pass
# -------------------------------------------



# --- Option 9 plugin support ---
import importlib.util
import types
from pathlib import Path

# --- Option 9 plugin loader ---------------------------------------------------

def _load_module_from_path(mod_name: str, file_path: Path):
    """Load a Python module from an arbitrary file path (supports spaces)."""
    try:
        if not file_path or not file_path.exists():
            return None
        spec = importlib.util.spec_from_file_location(mod_name, str(file_path))
        if not spec or not spec.loader:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception as e:
        print(f"⚠️ Failed to load plugin at {file_path}: {e}")
        return None


def _load_option9_plugin(base_dir: Path):
    """Locate and load the Option 9 plugin once."""
    candidates = [
        base_dir / "GeoPackage Borders.py",                               # file next to 1.py
        base_dir / "GeoPackage Borders" / "GeoPackage Borders.py",        # inside folder
        base_dir / "GeoPackage Borders" / "__init__.py",                  # as a package
        base_dir / "GeoPackage Borders" / "option9.py",                   # alt name
    ]
    for p in candidates:
        mod = _load_module_from_path("geo_pkg_borders_option9", p)
        if isinstance(mod, types.ModuleType) and hasattr(mod, "extract_suburb_from_gpkg"):
            print(f"🔌 Option 9 plugin loaded from: {p}")
            return mod
    print("🔎 Option 9 plugin not found — option 9 will show a help message.")
    return None


# Load once at import time so the menu is “plugin-ready”
_BASE_DIR = Path(__file__).resolve().parent
_OPTION9_MOD = _load_option9_plugin(_BASE_DIR)


from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent





def log_field_change(stage: str, row_id, field: str, old, new, extra: str = "", street: Optional[str] = None) -> None:
    """
    Convenience: logs a specific field change with optional 'Street' context.
    No-ops if value didn't change.
    """
    o = ("" if old is None else str(old)).strip()
    n = ("" if new is None else str(new)).strip()
    if o == n:
        return
    rid = row_id if row_id is not None else "?"
    detail = f"Row {rid}: {field} '{o}' → '{n}'"
    if extra:
        detail += f" | {extra}"
    log_correction(f"{stage}: {field} Changed", detail, street=(street or ""))

# ✅ Ensure file+header exist at start (call AFTER defs)
log_correction("Session Start", "Script started and corrections_log.csv initialized.")


# Global shared counters for geocode usage
geocode_sources_used = defaultdict(int)
geocode_lock = threading.Lock()

# Global toggle to keep geocode logs lean
GEOCODE_DEBUG = False  # set True if you need a full trace

# Accepts: "12 Smith St, Remuera"  OR  "12 Smith St, Remuera, Auckland"
ADDRESS_PARSE_RX = re.compile(r"^(\S+)\s+(.+?),\s*([^,]+)(?:,\s*Auckland)?$", re.IGNORECASE)

cancel_flag = threading.Event()
MAX_ALLOWED_DISTANCE = 2000

# --- Address formatting helpers (always include number when we have it) ---
def _to_parts(address: str):
    m = ADDRESS_PARSE_RX.match((address or "").strip())
    if not m:
        # Try to peel a duplicate trailing ", Auckland"
        a = (address or "").strip()
        if a.lower().endswith(", auckland"):
            a = a[:-10].strip()
            m = ADDRESS_PARSE_RX.match(a)
    if not m:
        return "", "", ""
    num, street, suburb = [x.strip() for x in m.groups()]
    return num, street, suburb

def fmt_addr_parts(num: str, street: str, suburb: str) -> str:
    num = (num or "").strip()
    street = correct_suffix_typos((street or "").strip()).title()
    suburb = (suburb or "").strip().title() or "Auckland"
    # expand suffix e.g. "Rd" -> "Road"
    parts = street.split()
    if parts and parts[-1] in street_suffix_map:
        parts[-1] = street_suffix_map[parts[-1]]
    street = " ".join(parts)
    if num:
        return f"{num} {street}, {suburb}, Auckland"
    return f"{street}, {suburb}, Auckland"

def fmt_addr_str(address: str) -> str:
    n, s, sub = _to_parts(address)
    return fmt_addr_parts(n, s, sub)


# ---- per-field change logger (to corrections_log.csv) ----
# ===== Add once (near log_correction) =====
def log_field_change(stage: str, row_id, field: str, old, new, extra: str = "", street: Optional[str] = None) -> None:
    """
    Convenience: logs a specific field change with optional 'Street' context.
    No-ops if value didn't change.
    """
    o = ("" if old is None else str(old)).strip()
    n = ("" if new is None else str(new)).strip()
    if o == n:
        return
    rid = row_id if row_id is not None else "?"
    detail = f"Row {rid}: {field} '{o}' → '{n}'"
    if extra:
        detail += f" | {extra}"
    log_correction(f"{stage}: {field} Changed", detail, street=(street or ""))

# ✅ Ensure file+header exist at start
log_correction("Session Start", "Script started and corrections_log.csv initialized.")


def _norm_apartment_number(v: str) -> str:
    """
    Normalize ApartmentNumber for dedupe:
      - trim spaces
      - collapse internal whitespace
      - uppercase letters
      - keep digits, letters, '/', '-', and '#'
    Empty stays empty (so blank vs non-blank are different).
    """
    s = (v or "").strip()
    if not s:
        return ""
    import re
    s = re.sub(r"\s+", " ", s)              # collapse spaces
    s = re.sub(r"[^A-Za-z0-9/\-# ]", "", s) # keep simple tokens
    return s.upper()

# ==== Corrections Log: single, canonical implementation ====


def build_other_linz_memory_db():
    """
    Loads all CSVs under 'Street Database/Other/' into a thread-safe shared-memory SQLite DB.
    Returns a connection to the memory database.
    """
    memory_conn = sqlite3.connect(
        "file:linz_other_temp?mode=memory&cache=shared", uri=True, check_same_thread=False
    )
    cursor = memory_conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS other_addresses (
            number TEXT,
            street TEXT,
            suburb TEXT,
            postalcode TEXT,
            latitude TEXT,
            longitude TEXT
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_other ON other_addresses (street, suburb, number);")

    folder = os.path.join("Street Database", "Other")
    if not os.path.exists(folder):
        log_correction("Other LINZ Folder Missing", f"Folder not found: {folder}")
        return memory_conn

    def load_csv_to_df(path):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                df = pd.read_csv(f, dtype=str)
            df.columns = [col.strip().lower() for col in df.columns]
            required = ["number", "street", "suburb", "postalcode", "latitude", "longitude"]
            if not all(col in df.columns for col in required):
                log_correction("Other LINZ Skip", f"{os.path.basename(path)} — missing required columns")
                return pd.DataFrame()
            return df[required].fillna("")
        except Exception as e:
            log_correction("Other LINZ Load Error", f"{path}: {e}")
            return pd.DataFrame()

    csv_paths = [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(".csv")]
    if not csv_paths:
        log_correction("Other LINZ No CSV", f"No CSV files found in: {folder}")
        return memory_conn

    with ThreadPoolExecutor(max_workers=4) as executor:
        dfs = list(executor.map(load_csv_to_df, csv_paths))

    combined = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
    if not combined.empty:
        combined.to_sql("other_addresses", memory_conn, if_exists="append", index=False)
        row_count = len(combined)
        file_count = len(csv_paths)
        print_once_memory_loaded(row_count, file_count)  # ✅ now has values
    else:
        log_correction("Other LINZ Empty", "No valid data loaded into memory DB.")

    return memory_conn


# Rough Auckland bounding box (NZ): tweak if you want tighter
AUCKLAND_LAT_MIN, AUCKLAND_LAT_MAX = -37.30, -36.60
AUCKLAND_LON_MIN, AUCKLAND_LON_MAX = 174.40, 175.50

def is_in_auckland(lat, lon):
    try:
        lat = float(lat); lon = float(lon)
    except Exception:
        return False
    return (AUCKLAND_LAT_MIN <= lat <= AUCKLAND_LAT_MAX) and (AUCKLAND_LON_MIN <= lon <= AUCKLAND_LON_MAX)

# ---- Speed/quiet toggles (put near VERBOSE_PRE) ----
STAGE_NOISE_LOGS = False  # suppress logs that don't affect results

def _stage_log(event, details="", street=None):
    if not STAGE_NOISE_LOGS:
        return
    # only used if you flip STAGE_NOISE_LOGS=True for debugging
    try:
        log_correction(event, details, street=street or "")
    except Exception:
        pass

# tqdm defaults (less redraw, auto-disable when not a TTY)
import sys
_TQDM_OPTS = dict(dynamic_ncols=True, mininterval=0.2, disable=not sys.stdout.isatty())

# local LRU just for stage geocodes (avoids repeat external calls in 3.3/3.4)
from functools import lru_cache
@lru_cache(maxsize=5000)
def _stage_geocode_once(query: str):
    return get_lat_long(query)

# bucket key + fast similarity (keeps your threshold but prunes pairs)
def _bucket_key(s: str) -> tuple:
    s = _letters_only(s)
    return (s[:3], s[-3:], len(s))

def _fast_ratio(a: str, b: str) -> int:
    try:
        from rapidfuzz.fuzz import ratio, partial_ratio, token_set_ratio
        return max(ratio(a, b), partial_ratio(a, b), token_set_ratio(a, b))
    except Exception:
        import difflib
        return int(difflib.SequenceMatcher(None, a, b).ratio() * 100)


def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate distance between two lat/lon pairs in meters.
    """
    R = 6371000  # Earth radius in meters
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    d_phi = math.radians(float(lat2) - float(lat1))
    d_lambda = math.radians(float(lon2) - float(lon1))

    a = math.sin(d_phi / 2) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def geocode_linz_parallel(address, memory_conn=None):
    """
    Run LINZ SQLite and memory DB lookups in parallel.
    Returns a 4-tuple: (label, lat, lon, postal) with lat/lon as floats.
    Only accepts results inside Auckland. Rejects/ignores out-of-region hits.
    """

    def _normalize_and_gate(tpl):
        """
        Expect tpl like (label, lat, lon, postal). Coerce to floats, auto-swap if needed,
        and accept only if inside Auckland. Returns normalized tuple or None.
        """
        if not (isinstance(tpl, tuple) and len(tpl) == 4):
            return None
        label, lat, lon, postal = tpl
        try:
            la = float(lat); lo = float(lon)
        except Exception:
            return None
        # Fix obviously swapped pairs (uses your helper)
        la, lo = _maybe_swap_latlon(la, lo)
        if not is_in_auckland(la, lo):
            return None
        return (label, la, lo, postal or "")

    def try_sqlite():
        res = geocode_linz(address)  # falls back to global LINZ_DB
        return res, "LINZ_SQLITE"

    def try_memory():
        if memory_conn:
            res = geocode_linz(address, memory_conn=memory_conn)  # ✅ use memory cache
            return res, "LINZ_MEMORY"
        return (("", "", "", ""), "LINZ_MEMORY")

    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(fn): name
            for fn, name in [(try_sqlite, "SQLite"), (try_memory, "Memory")]
        }

        accepted = None
        accepted_source = None

        # Return the first ACCEPTABLE (Auckland) result that arrives
        for future in as_completed(futures):
            try:
                result, source = future.result()
            except Exception:
                continue

            norm = _normalize_and_gate(result)
            if norm:
                accepted = norm
                accepted_source = source
                break

        if accepted:
            # Count source usage (lazy-safe)
            try:
                with geocode_lock:
                    geocode_sources_used.setdefault(accepted_source, 0)
                    geocode_sources_used[accepted_source] += 1
            except Exception:
                pass

            # Log AFTER acceptance; keep message concise and correct
            label, la, lo, _pc = accepted
            log_correction("Geocode Success", f"{address} → matched in {accepted_source}")
            return accepted

    # If neither memory nor sqlite produced an in-Auckland hit
    log_correction("LINZ Miss", f"{address} → not found in LINZ sources (Auckland-gated)")
    return ("", "", "", "")



def log_street_fail(row, reason, addr_query=None):
    # Skip noisy cases
    status = (row.get("Status","") or "").strip().lower()
    if status in {"custom1", "donotcall"}:
        return
    if (row.get("Final Status","") or "").strip().lower() == "duplicate":
        return

    num = (row.get("Number","") or "").strip()
    st  = (row.get("Street","") or "").strip()
    sub = (row.get("Suburb","") or "").strip()
    key = addr_query or f"{num} {st}, {sub}, Auckland"
    log_correction("Street Fail", f"{key} → {reason}")


# After: lat_new = float(fresh_lat or 0); lon_new = float(fresh_lon or 0)

def maybe_swap_into_auckland(lat, lon):
    lat_f = safe_float(lat, None); lon_f = safe_float(lon, None)
    if lat_f is None or lon_f is None:
        return lat, lon
    if not is_in_auckland(lat_f, lon_f) and is_in_auckland(lon_f, lat_f):
        log_correction("Geocode Sanity Swap",
                       f"Swapped new coords to match Auckland → ({lat_f:.6f}, {lon_f:.6f}) → ({lon_f:.6f}, {lat_f:.6f})")
        return lon_f, lat_f
    return lat_f, lon_f



def listen_for_quit_key():
    if os.name == 'nt':
        import msvcrt
        while not cancel_flag.is_set():
            if msvcrt.kbhit():
                key = msvcrt.getwch()
                if key.lower() == 'q':
                    print("\n⚠️  'q' pressed — cancelling process...\n")
                    cancel_flag.set()
                    break
    else:
        import sys, select
        while not cancel_flag.is_set():
            if select.select([sys.stdin], [], [], 0.1)[0]:
                key = sys.stdin.readline().strip().lower()
                if key == 'q':
                    print("⚠️  'q' pressed — cancelling process...")
                    cancel_flag.set()
                    break

def print_created_files(folder):
    if not os.path.exists(folder):
        print(f"⚠️ Folder '{folder}' does not exist.")
        return

    files = sorted(os.listdir(folder))
    if not files:
        print(f"ℹ️ Folder '{folder}' is empty.")
        return

    print(f"\n📁 {len(files)} file(s) created:\n")
    for f in files:
        print(f"    📑 {f}")


def write_to_clean_file(row):
    """
    Writes a cleaned row to the clean output file.
    """
    fieldnames = [
        "TerritoryID", "TerritoryNumber", "CategoryCode", "Category",
        "TerritoryAddressID", "ApartmentNumber", "Number", "Street",
        "Suburb", "PostalCode", "State", "Name", "Phone", "Type", "Status",
        "NotHomeAttempt", "Date1", "Date2", "Date3", "Date4", "Date5",
        "Language", "Latitude", "Longitude", "Notes", "NotesFromPublisher",
        "Final Status"
    ]

    with open("output_clean.csv", 'a', newline='', encoding='utf-8') as cleanfile:
        writer = csv.DictWriter(cleanfile, fieldnames=fieldnames)

        # Write header only if the file is empty
        if cleanfile.tell() == 0:
            writer.writeheader()

        # Debugging the row content before writing

        writer.writerow(row)

def write_to_fail_file(row):
    fieldnames = [
        "TerritoryID", "TerritoryNumber", "CategoryCode", "Category",
        "TerritoryAddressID", "ApartmentNumber", "Number", "Street",
        "Suburb", "PostalCode", "State", "Name", "Phone", "Type", "Status",
        "NotHomeAttempt", "Date1", "Date2", "Date3", "Date4", "Date5",
        "Language", "Latitude", "Longitude", "Notes", "NotesFromPublisher",
        "Final Status"
    ]

    with open("output_fail.csv", 'a', newline='', encoding='utf-8') as failfile:
        writer = csv.DictWriter(failfile, fieldnames=fieldnames)
        if failfile.tell() == 0:
            writer.writeheader()
        writer.writerow(row)


def write_to_file(row, file_path, fieldnames=None):
    """
    Writes a row to a specified file with dynamic fieldnames if necessary.
    """
    # Ensure fieldnames are set, defaulting to keys from the row if not provided
    if fieldnames is None:
        fieldnames = list(row.keys())

    with open(file_path, 'a', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)

        # Write header only if the file is empty
        if file.tell() == 0:
            writer.writeheader()

        # Write the row to the file
        writer.writerow(row)


def linz_suffixes_for_base(base):
    """Return set of suffixes observed in LINZ for a given base, e.g. 'Arrowsmith' -> {'Drive','Road'}"""
    try:
        with _db_lock:
            conn = sqlite3.connect(LINZ_DB, check_same_thread=False)
            rows = conn.execute(
                "SELECT DISTINCT Street FROM addresses WHERE Street LIKE ? ESCAPE '\\' COLLATE NOCASE",
                (f"{base} %",)
            ).fetchall()
            conn.close()
        return {str(r[0]).split()[-1].title() for r in rows if r and r[0]}
    except Exception:
        return set()




expected = ["Number", "Street", "Suburb", "PostalCode", "Latitude", "Longitude"]


logging.getLogger().setLevel(logging.ERROR)  # suppresses FuzzyWuzzy warnings





nest_asyncio.apply()

import asyncio
import nest_asyncio
import threading

nest_asyncio.apply()

def run_async_coro(coro_func, *args, **kwargs):
    result_container = {}
    error_container = {}

    def thread_target():
        try:
            log_correction("Info", "...message text...")

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result_container['result'] = loop.run_until_complete(coro_func(*args, **kwargs))
            loop.close()
        except Exception as e:
            print(f"❌ Error inside async thread: {e}")  # ← This is crucial
            error_container['error'] = e

    log_correction("Info", "...message text...")
    thread = threading.Thread(target=thread_target)
    thread.start()
    thread.join()

    if 'error' in error_container:
        raise error_container['error']
    return result_container.get('result')




def remove_files_in_folder(folder):
    if not os.path.exists(folder):
        print(f"⚠️ Folder not found: {folder}")
        return

    deleted_files = []

    # Get a list of all files in the folder
    files = sorted(os.listdir(folder))
    if not files:
        print(f"ℹ️ Folder '{folder}' is empty.")
        return

    print(f"\n⏳ Removing files from '{folder}'...")

    # Use tqdm to show the progress bar during file removal
    for file in tqdm(files, desc="🧹 Removing Suburb Files", unit="file", dynamic_ncols=True):
        file_path = os.path.join(folder, file)
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
                deleted_files.append(file)
            else:
                print(f"⚠️ Not a file: {file}")
        except Exception as e:
            print(f"❌ Error deleting {file}: {e}")

    if deleted_files:
        print(f"\n✅ Completed. {len(deleted_files)} file(s) deleted:\n")
        for path in deleted_files:
            print(f"🗑️ Removed: {path}")
    else:
        print("ℹ️ No Files Were Deleted (Folder Empty)")


def list_created_files(output_folder):
    if not os.path.exists(output_folder):
        print(f"⚠️ Output folder not found: {output_folder}")
        return

    files = sorted(os.listdir(output_folder))
    if not files:
        print("ℹ️ No files were created.")
        return

    print(f"\n✅ Cleaned addresses split into '{output_folder}' by suburb.")
    print(f"📁 {len(files)} file(s) created:")
    for f in files:
        print(f"   - {f}")


def geocode_address_with_verification(row, verify_geocode=False):
    """
    Geocode the given address with verification for Latitude and Longitude.
    If geocode verification is enabled, verify if Latitude and Longitude are valid.
    """
    latitude = row.get("Latitude")
    longitude = row.get("Longitude")

    if verify_geocode or is_invalid_coordinates(latitude, longitude):
        # ✅ Always include number, normalize suffixes/casing
        address = fmt_addr_parts(row.get('Number',''), row.get('Street',''), row.get('Suburb',''))

        valid_geocode = get_lat_long(address)
        if valid_geocode:
            addr, lat, lon, postal = valid_geocode
            row["Latitude"] = lat
            row["Longitude"] = lon
            row["PostalCode"] = postal
            return row

        # ✅ Special handling: try again without unit number if present
        if has_unit_number(row):
            # expects patched remove_unit_from_address() to return a fully formatted string
            base_address = remove_unit_from_address(row)
            valid_geocode = get_lat_long(base_address)
            if valid_geocode:
                addr, lat, lon, postal = valid_geocode
                row["Latitude"] = lat
                row["Longitude"] = lon
                row["PostalCode"] = postal
                return row

        # ✅ Try nearby ±5 probes (these should also build with numbers internally)
        nearby_geocode = search_nearby_addresses(row)
        if nearby_geocode:
            _, lat, lon, postal = nearby_geocode  # discard addr, keep coords
            row["Latitude"] = lat
            row["Longitude"] = lon
            row["PostalCode"] = postal
            return row

        log_correction("Geocode Failed", f"All attempts failed for {address}")

    # If not verified and original coordinates are assumed okay
    return row


def _is_valid_geocode_tuple(t):
    """(addr, lat, lon, postal) with real lat/lon."""
    try:
        return (
            isinstance(t, tuple) and len(t) == 4 and
            t[0] and t[1] is not None and t[2] is not None and
            not (str(t[1]).strip() == "" or str(t[2]).strip() == "")
        )
    except Exception:
        return False



def is_invalid_coordinates(latitude, longitude):
    """True if lat/lon missing or zero-ish."""
    try:
        lat = None if latitude is None else float(str(latitude).strip() or "0")
        lon = None if longitude is None else float(str(longitude).strip() or "0")
    except ValueError:
        return True
    return lat in (None, 0.0) or lon in (None, 0.0)
# (Optionally: just return is_blank_or_zero(latitude) or is_blank_or_zero(longitude))



def has_unit_number(row):
    """Check if the address has a unit number."""
    return "Unit" in row.get("Number", "")


def remove_unit_from_address(row):
    number = (row.get("Number","") or "")
    number = number.split("/")[1] if "/" in number else number
    return fmt_addr_parts(number, row.get('Street',''), row.get('Suburb',''))




def search_nearby_addresses(row):
    """Search for nearby addresses within ±5 numbers."""
    m = re.search(r'(\d+)$', str(row.get("Number", "")).strip())
    if not m:
        return None
    base_number = int(m.group(1))

    nearby_addresses = [
        fmt_addr_parts(str(base_number + i), row['Street'], row['Suburb'])
        for i in range(-5, 6) if i != 0 and base_number + i > 0
    ]

    for address in nearby_addresses:
        geocode = get_lat_long(address)
        if geocode:
            return geocode

    return None  # No valid geocode found for nearby addresses


async def fetch_geocode(address):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, get_lat_long, address)


def run_with_cancel(func, **kwargs):
    if not cancel_flag.is_set():
        print("⏳ Process starting... Press 'q' at any time to cancel.")
    func(**kwargs)


def clean_and_split():
    if not cancel_flag.is_set():
        print("⏳ Process starting... Press 'q' at any time to cancel.")
    process_csv("input_nws.csv", "output_clean.csv", "output_fail.csv", expected)

    if cancel_flag.is_set():
        print("⚠️ Cancelled before suburb split.\n")
        return None

    if not cancel_flag.is_set():
        print("⏳ Process starting... Press 'q' at any time to cancel.")
    split_cleaned_by_suburb_and_include_failed("output_clean.csv", "output_fail.csv")


# at top once:
try:
    from rapidfuzz import process as rf_process
    _HAS_RF = True
except Exception:
    from fuzzywuzzy import process as fw_process
    _HAS_RF = False

def safe_fuzzy_match(query, choices, threshold=60):
    """
    Robust, library-agnostic fuzzy match:
      • Normalizes (case/whitespace/diacritics) for matching but returns the original choice.
      • Uses RapidFuzz if available (via `_HAS_RF` + `rf_process`), else fuzzywuzzy if `fw_process` is present,
        else falls back to difflib.
      • Returns None if no candidate meets `threshold` (0–100).

    Parameters
    ----------
    query : str
    choices : Iterable[str]
    threshold : int
        Minimum similarity score to accept (percent).

    Returns
    -------
    str | None
        The best-matching ORIGINAL choice string, or None.
    """
    # Fast guards
    if not (query or "").strip() or not choices:
        return None

    import re
    import unicodedata

    # Fold to ASCII-ish for robust matching (keeps digits/letters, collapses spaces)
    def _fold(s: str) -> str:
        s = unicodedata.normalize("NFKD", str(s or ""))
        s = "".join(ch for ch in s if not unicodedata.combining(ch))  # strip diacritics/macrons for matching
        s = re.sub(r"[^A-Za-z0-9\s]", " ", s)
        s = re.sub(r"\s+", " ", s).strip().lower()
        return s

    qf = _fold(query)
    if not qf:
        return None

    # Build a unique folded-choices map → original
    folded_to_orig = {}
    for c in choices:
        if c is None:
            continue
        orig = str(c)
        if not orig.strip():
            continue
        fc = _fold(orig)
        # Keep first-seen original for determinism
        if fc and fc not in folded_to_orig:
            folded_to_orig[fc] = orig

    if not folded_to_orig:
        return None

    keys = list(folded_to_orig.keys())

    # Preferred: RapidFuzz
    try:
        if globals().get("_HAS_RF") and "rf_process" in globals():
            # RapidFuzz accepts a processor, but we already pre-folded; compare keys directly.
            match = rf_process.extractOne(qf, keys, score_cutoff=threshold)
            return folded_to_orig[match[0]] if match else None
    except Exception:
        pass

    # Secondary: fuzzywuzzy (if available as fw_process)
    try:
        if "fw_process" in globals():
            m = fw_process.extractOne(qf, keys)
            if m and m[1] >= threshold:
                return folded_to_orig[m[0]]
            return None
    except Exception:
        pass

    # Fallback: difflib
    try:
        import difflib
        best_key = None
        best_score = -1.0
        for k in keys:
            score = difflib.SequenceMatcher(None, qf, k).ratio() * 100.0
            if score > best_score:
                best_key, best_score = k, score
        if best_key is not None and best_score >= float(threshold):
            return folded_to_orig[best_key]
        return None
    except Exception:
        return None


# ------------------- Globals -------------------
BASE_FOLDER = "Street Database"

LINZ_DB = os.path.join(BASE_FOLDER, "linz_auckland.sqlite")
LINZ_FILE = os.path.join(BASE_FOLDER, "linz_auckland_addresses.csv")
CACHE_FILE = os.path.join(BASE_FOLDER, "geocode_cache.json")

memory_conn = None  # 🌐 Global memory DB connection for LINZ_MEMORY

# Postal codes (Auckland & nearby)
nz_postal_lookup = {
    "Howick": "2010", "Botany": "2010", "Dannemora": "2016", "Manukau": "2104", "Flat Bush": "2016",
    "Panmure": "1072", "Pakuranga": "2010", "Pakuranga Heights": "2010", "Highland Park": "2010",
    "Mount Wellington": "1060", "Mt Wellington": "1060", "Onehunga": "1061", "Ellerslie": "1051", "Remuera": "1050",
    "Newmarket": "1023", "Sylvia Park": "1060", "Parnell": "1052", "Orakei": "1071",
    "Kohimarama": "1071", "Mission Bay": "1071", "St Heliers": "1071", "Glendowie": "1071",
    "Mount Eden": "1024", "Epsom": "1023", "Greenlane": "1051", "Penrose": "1061",
    "Meadowbank": "1072", "Glen Innes": "1072", "Tamaki": "1072", "Saint Johns": "1072", "St Johns": "1072",
    "Airport Oaks": "2022", "Alfriston": "2105", "Botany Downs": "2010", "Bucklands Beach": "2012",
    "Burswood": "2013", "Clendon Park": "2103", "Clover Park": "2023", "Cockle Bay": "2012",
    "Eastern Beach": "2012", "East Tāmaki": "2013", "East Tāmaki Heights": "2016",
    "Farm Cove": "2012", "Favona": "2024", "Golflands": "2013", "Goodwood Heights": "2105",
    "Half Moon Bay": "2012", "Hillpark": "2102", "Homai": "2102", "Manukau Central": "2104",
    "Manurewa": "2102", "Mellons Bay": "2012", "Middlemore": "2025", "Mission Heights": "2016",
    "Mangere": "2022", "Mangere Bridge": "2022", "Mangere East": "2024", "Northpark": "2013",
    "One Tree Hill": "1061", "Oranga": "1061", "Pahurehure": "2113", "Papatoetoe": "2025",
    "Point England": "1072", "Randwick Park": "2105", "Royal Oak": "1023", "Saint Heliers": "1071",
    "Shamrock Park": "2016", "Shelly Park": "2014", "Somerville": "2014", "Southdown": "1061",
    "Stonefields": "1072", "Sunnyhills": "2010", "Te Papapa": "1061", "The Gardens": "2105",
    "Totara Heights": "2105", "Tāmaki": "1072", "Takanini": "2112", "Wattle Downs": "2103", "Westfield": "1060",
    "Weymouth": "2103", "Wiri": "2104", "Huntington Park": "2013", "Karaka": "2113", "Karaka Lakes": "2113",
    "Papakura": "2110", "Otara": "2023", "Otahuhu": "1062",
    "Ormiston": "2016", "Conifer Grove": "2112", "Drury": "2113", "Paerata": "2676",
    "Rosehill": "2113", "Red Hill": "2110", "Opaheke": "2113", "Hingaia": "2113",
    "Maraetai": "2018", "Beachlands": "2018", "Whitford": "2576", "Karaka Harbourside": "2113",
    "Paerata Rise": "2676", "Hillsborough": "1042", "Kingsland": "1021", "Saint Heliers Bay": "1071"
}


macron_suburb_map = {"East Tamaki Heights": "East Tāmaki Heights",
                     "East Tamaki": "East Tāmaki",
    "East Tāmaki": "East Tāmaki",
                     "Tamaki": "Tāmaki",
                     "Otara": "Ōtara"
                     }


NEARBY_ALIAS = {
    "Botany": "Botany Downs",
    "East Tamaki": "East Tāmaki",
    "East Tamaki Heights": "East Tāmaki Heights",
    "Tamaki": "Tāmaki",
    "Otara": "Ōtara",
}

# ---- Performance helpers: safe hot-path caches ----
def enable_hotpath_caches():
    from functools import lru_cache
    g = globals()

    def _wrap(name, maxsize=20000):
        fn = g.get(name)
        if callable(fn) and not getattr(fn, "_is_cached", False):
            orig = fn
            @lru_cache(maxsize=maxsize)
            def cached(*args):
                return orig(*args)
            cached._is_cached = True
            g[name] = cached

    # Pure, frequently-called normalizers
    _wrap("canon_suburb", 30000)
    _wrap("canon_geocoded_suburb", 30000)
    _wrap("correct_suffix_typos", 50000)
    _wrap("expand_street_suffix_once", 50000)
    _wrap("normalize_suburb_ascii", 30000)


def canon_suburb(s: str) -> str:
    s = (s or "").strip().title()
    s = macron_suburb_map.get(s, s)
    s = NEARBY_ALIAS.get(s, s)
    return s

# put near your canon_* helpers
_AUCKLAND_NOISE = {"Auckland", "Auckland City", "Auckland Central", "Auckland Cbd", "City Centre"}

def _strip_auckland_noise(s: str) -> str:
    import re
    s = (s or "").strip()
    # drop 'Auckland' variants and postcodes like '2010'
    s = re.sub(r"\bAuckland(?: City| Central| Cbd)?\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\b\d{4}\b", "", s)  # NZ postcode
    s = re.sub(r"\s+", " ", s).strip(", ").strip()
    return s

def canon_geocoded_suburb(s: str) -> str:
    s = _strip_auckland_noise(s)
    return canon_suburb(s)  # your existing alias/macron normalizer


_db_lock = threading.Lock()
_cache_lock = threading.Lock()
_geocode_cache = {}

# --- Nearby suburb map (complete) ---
NEARBY_SUBURBS = {
    "Botany Downs": {"Highland Park", "Howick", "Flat Bush", "East Tāmaki", "Golflands", "Northpark", "Dannemora", "Burswood", "Sunnyhills", "Pakuranga"},
    "Flat Bush": {"Botany Downs", "East Tāmaki", "Manukau", "Dannemora", "Goodwood Heights", "Clover Park", "Mission Heights", "Ormiston", "East Tāmaki Heights", "Burswood", "Totara Heights", "Papatoetoe"},
    "Dannemora": {"Flat Bush", "Botany Downs", "East Tāmaki", "Northpark", "Golflands", "East Tāmaki Heights", "Pakuranga", "Burswood"},
    "East Tāmaki": {"Botany Downs", "Flat Bush", "Dannemora", "East Tāmaki Heights", "Burswood", "Pakuranga", "Northpark", "Golflands"},
    "East Tāmaki Heights": {"East Tāmaki", "Flat Bush", "Dannemora", "Botany Downs", "Burswood", "Manukau", "Totara Heights"},
    "Golflands": {"Botany Downs", "Howick", "Northpark", "Sunnyhills", "Highland Park", "Dannemora", "Pakuranga"},
    "Northpark": {"Botany Downs", "Golflands", "Dannemora", "Pakuranga", "East Tāmaki", "Highland Park"},
    "Highland Park": {"Botany Downs", "Howick", "Sunnyhills", "Golflands", "Pakuranga", "Northpark"},
    "Howick": {"Botany Downs", "Cockle Bay", "Bucklands Beach", "Highland Park", "Mellons Bay", "Golflands", "Sunnyhills"},
    "Cockle Bay": {"Howick", "Shelly Park", "Mellons Bay"},  # trimmed: removed Maraetai (too far)
    "Mellons Bay": {"Howick", "Cockle Bay", "Bucklands Beach", "Half Moon Bay"},
    "Bucklands Beach": {"Howick", "Mellons Bay", "Half Moon Bay", "Farm Cove", "Sunnyhills"},
    "Half Moon Bay": {"Bucklands Beach", "Sunnyhills", "Farm Cove", "Pakuranga"},
    "Sunnyhills": {"Farm Cove", "Pakuranga", "Highland Park", "Golflands", "Bucklands Beach", "Half Moon Bay"},
    "Farm Cove": {"Sunnyhills", "Half Moon Bay", "Pakuranga", "Bucklands Beach", "Panmure"},
    "Pakuranga": {"Sunnyhills", "Pakuranga Heights", "Panmure", "Burswood", "Highland Park", "Northpark"},
    "Pakuranga Heights": {"Pakuranga", "Highland Park", "Sunnyhills"},
    "Burswood": {"East Tāmaki", "Pakuranga", "Botany Downs", "Flat Bush", "East Tāmaki Heights"},
    "Mission Heights": {"Flat Bush", "Ormiston", "Totara Heights", "Manukau", "East Tāmaki Heights"},
    "Ormiston": {"Mission Heights", "Flat Bush", "Dannemora"},
    "Manukau": {"Manukau Central", "Wiri", "Papatoetoe", "Totara Heights", "Goodwood Heights", "Mangere East"},
    "Manukau Central": {"Manukau", "Wiri", "Totara Heights", "Goodwood Heights"},
    "Totara Heights": {"Manukau", "Goodwood Heights", "Mission Heights", "Flat Bush", "East Tāmaki Heights"},
    "Goodwood Heights": {"Totara Heights", "Hillpark", "Manurewa", "Manukau"},
    "Hillpark": {"Manurewa", "Goodwood Heights", "Totara Heights"},
    "Manurewa": {"Hillpark", "Clendon Park", "Wattle Downs", "Weymouth", "Takanini", "Conifer Grove"},
    "Clendon Park": {"Manurewa", "Wattle Downs", "Weymouth"},
    "Wattle Downs": {"Manurewa", "Clendon Park", "Weymouth", "Conifer Grove"},  # added Weymouth/Conifer Grove
    "Weymouth": {"Manurewa", "Clendon Park", "Wattle Downs"},                   # added Wattle Downs
    "Papatoetoe": {"Mangere East", "Otahuhu", "Manukau", "Middlemore", "Clover Park", "Flat Bush"},
    "Mangere": {"Mangere East", "Mangere Bridge", "Favona", "Otahuhu"},
    "Mangere East": {"Mangere", "Papatoetoe", "Middlemore", "Otahuhu", "Favona"},
    "Mangere Bridge": {"Mangere", "Onehunga", "Hillsborough"},
    "Favona": {"Mangere", "Otahuhu", "Mangere East"},
    "Otahuhu": {"Papatoetoe", "Favona", "Mangere East", "Middlemore"},
    "Middlemore": {"Mangere East", "Papatoetoe", "Otahuhu"},
    "Onehunga": {"Mangere Bridge", "One Tree Hill", "Royal Oak", "Hillsborough"},
    "One Tree Hill": {"Onehunga", "Royal Oak", "Epsom", "Greenlane"},
    "Royal Oak": {"One Tree Hill", "Epsom", "Onehunga"},
    "Epsom": {"Royal Oak", "Mount Eden", "Greenlane", "Newmarket", "Remuera"},      # +Remuera
    "Mount Eden": {"Epsom", "Greenlane", "Kingsland"},                               # dropped Mount Wellington
    "Greenlane": {"Epsom", "Ellerslie", "Mount Wellington", "One Tree Hill", "Remuera"},  # +Remuera
    "Ellerslie": {"Greenlane", "Mount Wellington", "Penrose"},
    "Mount Wellington": {"Ellerslie", "Penrose", "Panmure", "Glen Innes"},
    "Penrose": {"Mount Wellington", "Onehunga", "Ellerslie"},
    "Panmure": {"Mount Wellington", "Glen Innes", "Point England"},
    "Glen Innes": {"Panmure", "Point England", "Tamaki"},
    "Point England": {"Glen Innes", "Tamaki", "Saint Johns"},
    "Tamaki": {"Point England", "Saint Johns", "Panmure"},
    "Saint Johns": {"Tamaki", "Meadowbank", "Glen Innes"},
    "Meadowbank": {"Saint Johns", "Orakei", "Mission Bay", "Remuera"},              # +Remuera
    "Orakei": {"Meadowbank", "Mission Bay", "Kohimarama", "Remuera"},               # +Remuera
    "Mission Bay": {"Orakei", "Kohimarama", "Saint Heliers"},
    "Kohimarama": {"Mission Bay", "Saint Heliers", "Glendowie"},
    "Saint Heliers": {"Kohimarama", "Glendowie", "Mission Bay"},
    "Glendowie": {"Saint Heliers", "Kohimarama"},

    # --- South Auckland cluster (Karaka/Hingaia/Papakura/Drury/Paerata etc.) ---
    "Karaka": {"Hingaia", "Papakura", "Takanini", "Drury", "Paerata", "Rosehill", "Pahurehure"},
    "Hingaia": {"Karaka", "Papakura", "Takanini", "Rosehill", "Pahurehure", "Conifer Grove"},
    "Papakura": {"Takanini", "Karaka", "Hingaia", "Drury", "Rosehill", "Pahurehure", "Red Hill", "Opaheke"},
    "Takanini": {"Papakura", "Hingaia", "Karaka", "Wattle Downs", "Manurewa", "Conifer Grove"},
    "Drury": {"Papakura", "Karaka", "Paerata", "Opaheke"},
    "Paerata": {"Drury", "Karaka"},
    "Rosehill": {"Papakura", "Pahurehure", "Hingaia"},
    "Pahurehure": {"Papakura", "Rosehill", "Hingaia", "Conifer Grove"},
    "Red Hill": {"Papakura", "Opaheke"},
    "Opaheke": {"Papakura", "Red Hill", "Drury"},

    # --- New small nodes added for completeness ---
    "Conifer Grove": {"Takanini", "Hingaia", "Pahurehure", "Wattle Downs", "Manurewa"},
    "Remuera": {"Greenlane", "Orakei", "Meadowbank", "Epsom"},
}


SUFFIXES = [
    "Road","Street","Drive","Place","Crescent","Point","Boulevard","Lane",
    "Terrace","Court","Grove","Parade", "Point", "Heights","Close","Way","Trail","Walk",
    "Rise","Circuit","Quay","Loop","Green","Avenue"
]
SUFFIX_REGEX = re.compile(r"\b(" + "|".join(SUFFIXES) + r")\b", re.IGNORECASE)

def strip_suburb_after_street_suffix(street, suburb):
    pattern = r"\b(" + "|".join(SUFFIXES) + r")\b\s+(" + re.escape(suburb) + r")\b"
    m = re.search(pattern, street, flags=re.IGNORECASE)
    return street[:m.end(1)].strip() if m else street


def _ensure_globals():
    required = [
        "geocode_sources_used",
        "_log_lock",
        "_db_lock",
        "cancel_flag",
        "AUCKLAND_LAT_MIN", "AUCKLAND_LAT_MAX", "AUCKLAND_LON_MIN", "AUCKLAND_LON_MAX",
    ]
    missing = [name for name in required if name not in globals()]
    if missing:
        raise RuntimeError(f"Missing required globals: {missing}")


def is_nearby_suburb(old_suburb, new_suburb):
    if not old_suburb or not new_suburb:
        return False
    return new_suburb in NEARBY_SUBURBS.get(old_suburb, set())

# ---- Verbose helpers (put near top-level imports) ----
VERBOSE_PRE = False  # keep the tqdm bar, hide probe/address prints


def _vprint(msg: str):
    if VERBOSE_PRE:
        print(msg, flush=True)

from contextlib import contextmanager
import time as _time

@contextmanager
def step_timer(label: str):
    t0 = _time.perf_counter()
    _vprint(f"▶ {label} ...")
    try:
        yield
    finally:
        _vprint(f"✓ {label} done in {_time.perf_counter() - t0:.2f}s")


# Replace your existing function with this
def group_corrections_log_by_street(src="corrections_log.csv", dst="corrections_log_grouped.csv"):
    """
    Read the live corrections log and write a grouped summary to `dst`.
    Does NOT overwrite the live log.
    Output schema: Street, Occurrences, Details
    """
    import csv
    from collections import defaultdict

    grouped = defaultdict(list)

    if not os.path.exists(src):
        log_correction("Corrections Grouping", f"Log file '{src}' not found; skipping grouping.")
        return

    try:
        with open(src, "r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Live schema: Timestamp, Street, Event, Details
                street = (row.get("Street") or "").strip().title()
                event  = (row.get("Event") or "").strip()
                details= (row.get("Details") or "").strip()
                if street or event or details:
                    grouped[street].append(f"{event} — {details}" if event or details else "")
    except Exception as e:
        log_correction("Corrections Grouping Error", f"read failed: {e}")
        return

    try:
        with open(dst, "w", newline="", encoding="utf-8") as out:
            writer = csv.DictWriter(out, fieldnames=["Street", "Occurrences", "Details"])
            writer.writeheader()
            for street, entries in grouped.items():
                writer.writerow({
                    "Street": street,
                    "Occurrences": len(entries),
                    # Keep it readable; clip very long detail blobs
                    "Details": "; ".join(entries[:20]) + ("; ..." if len(entries) > 20 else "")
                })
        log_correction("Corrections Grouping", f"Grouped log written to {dst}")
    except Exception as e:
        log_correction("Corrections Grouping Error", f"write failed: {e}")


def _is_protected_full(st: str) -> bool:
    return (st or "").strip().title() in PROTECTED_FULL_STREETS

def _protected_base(st: str) -> str:
    base_disp, _ = _norm_base_key((st or "").strip())
    return base_disp if base_disp in PROTECTED_BASES else ""



def clean_street_suffix_and_suburb(street: str) -> str:
    """
    1) Removes any text appearing *after the last valid street suffix*
       (works with or without comma, handles multi-word suburbs, tolerates 'Auckland' tail).
       • Safety: keeps legit directional tails like "Road West".
       • If a suburb lexicon (valid_suburbs_data) exists, only strips when the tail is a known suburb.
    2) Expands a trailing suffix abbreviation to the full form (once).
    3) Collapses multiple spaces and trims.

    Uses a small internal cache so suffix/tail regexes are compiled only once per
    street_suffix_map content, and folds the suburb lexicon lazily.
    """
    if not street:
        return street

    import re, unicodedata

    s = street.strip()

    # --- Build & cache regexes based on current street_suffix_map ---
    def _build_patterns():
        mac = "āĀēĒīĪōŌūŪ"
        tokens = sorted({*(street_suffix_map.keys()), *(street_suffix_map.values())}, key=len, reverse=True)

        def _regexify(t: str) -> str:
            esc = re.escape(t)
            # allow optional dot for short abbreviations (St, Rd, Pl, etc.)
            if esc.endswith(r"\."):
                return esc[:-2] + r"\.?"
            if t.isalpha() and len(t) <= 4 and "." not in t:
                return esc + r"\.?"
            return esc

        suffix_pat = re.compile(rf"\b(?:{'|'.join(_regexify(t) for t in tokens)})\b", re.IGNORECASE)
        tail_pat   = re.compile(rf"(?:[,\s]+[A-Za-z{mac}\-'\s]+(?:,\s*Auckland)?\s*)$", re.IGNORECASE)
        return suffix_pat, tail_pat, tokens

    _tokens_key = tuple(sorted({*(street_suffix_map.keys()), *(street_suffix_map.values())}))
    if not hasattr(clean_street_suffix_and_suburb, "_cache_key") or clean_street_suffix_and_suburb._cache_key != _tokens_key:
        suffix_pat, tail_pat, tokens = _build_patterns()
        clean_street_suffix_and_suburb._cache = (suffix_pat, tail_pat, tokens)
        clean_street_suffix_and_suburb._cache_key = _tokens_key
    else:
        suffix_pat, tail_pat, tokens = clean_street_suffix_and_suburb._cache

    # --- Find the *last* suffix, then conditionally drop a suburb-like tail ---
    last_m = None
    for m in suffix_pat.finditer(s):
        last_m = m  # keep last
    if last_m:
        cut  = last_m.end()
        head = s[:cut]
        tail = s[cut:]

        if tail_pat.fullmatch(tail):
            # Safety: keep legit directional tails like "Road West"
            tail_clean = re.sub(r",\s*Auckland\s*$", "", tail, flags=re.IGNORECASE).strip(" ,")
            _dirs = {"north", "south", "east", "west", "upper", "lower", "central"}

            if tail_clean and tail_clean.lower() in _dirs:
                pass  # keep as-is
            else:
                # If we have a suburb lexicon, only strip when the tail is a known suburb
                vs = globals().get("valid_suburbs_data")
                if isinstance(vs, (list, set)) and vs:
                    def _fold(x: str) -> str:
                        x = unicodedata.normalize("NFKD", x or "")
                        x = "".join(ch for ch in x if not unicodedata.combining(ch))
                        x = re.sub(r"[^A-Za-z0-9\s]", " ", x)
                        return re.sub(r"\s+", " ", x).strip().lower()

                    cached_vs_id = getattr(clean_street_suffix_and_suburb, "_subs_id", None)
                    subs_folded  = getattr(clean_street_suffix_and_suburb, "_subs_folded", None)
                    if subs_folded is None or cached_vs_id != id(vs):
                        subs_folded = {_fold(x) for x in vs if x}
                        clean_street_suffix_and_suburb._subs_folded = subs_folded
                        clean_street_suffix_and_suburb._subs_id = id(vs)

                    if not tail_clean or _fold(tail_clean) in subs_folded:
                        s = head.strip()
                else:
                    # No lexicon available → fall back to original behavior
                    s = head.strip()

    # --- Expand a single trailing suffix abbreviation (once) ---
    for abbr, full in street_suffix_map.items():
        if re.search(rf"\b{re.escape(abbr)}\.?\s*$", s, flags=re.IGNORECASE):
            s = re.sub(rf"\b{re.escape(abbr)}\.?\s*$", full, s, flags=re.IGNORECASE)
            break

    # --- Collapse multiple spaces & trim ---
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s

# --- Missing utilities (added) ---

# Safe fallback for 'Other_Functions.remove_files' if module not present
try:
    import Other_Functions as oth
except Exception:
    class _FallbackRemove:
        @staticmethod
        def remove_files(paths):
            import os, shutil
            for p in paths:
                try:
                    if os.path.isdir(p):
                        shutil.rmtree(p)
                    elif os.path.exists(p):
                        os.remove(p)
                except Exception:
                    pass
    oth = _FallbackRemove()

def _list_existing_outputs():
    """
    Return a list of output files/folders that we consider 'generated',
    so the user can approve deleting them before a fresh run.
    """
    from pathlib import Path
    candidates = [
        "output_clean.csv",
        "output_fail.csv",
        "corrections_log.csv",
        "corrections_log_grouped.csv",

    ]
    out = [str(Path(c)) for c in candidates if Path(c).exists()]

    # Include suburb-split folder contents if present
    suburb_dir = Path("New_Addresses_By_Suburb")
    if suburb_dir.exists():
        for p in suburb_dir.glob("*"):
            out.append(str(p))
        out.append(str(suburb_dir))

    return out


def addr_key(number, street, suburb):
    number = normalize_number(number or "")
    street = correct_suffix_typos((street or "").strip()).title()
    suburb = (suburb or "").strip().title() or "Auckland"
    return f"{number} {street}, {suburb}, Auckland"

# --- NEW: Session flags to avoid repeat printing ---
_printed_linz_load = False
_printed_memory_load = False

_printed_linz_load = False
_printed_memory_load = False

def print_once_linz_loaded():
    global _printed_linz_load
    if not _printed_linz_load:
        print("✅ Loaded linz_auckland_addresses.csv into LINZ SQLite DB")
        _printed_linz_load = True

def print_once_memory_loaded(rows, files):
    global _printed_memory_load
    if not _printed_memory_load:
        print(f"✅ Loaded {rows} rows into in-memory DB from {files} file(s).")
        _printed_memory_load = True



def is_auckland_result(result):
    """Returns True if the result appears to be located in Auckland."""
    if not result or len(result) < 1 or not result[0]:
        return False
    address = result[0].lower()
    return "auckland" in address


def _linz_accept_and_normalize(label, lat, lon, postal):
    """
    Accept only Auckland points and return (label, lat, lon, postal) with lat/lon in the right order.
    Rejects None/bad numbers and out-of-Auckland coords.
    """
    try:
        la = float(lat); lo = float(lon)
    except Exception:
        return None
    la, lo = _maybe_swap_latlon(la, lo)
    if not is_in_auckland(la, lo):
        return None
    return (label, la, lo, postal or "")

def enforce_postcode_by_suburb_inplace(rows):
    """
    For any row with a known suburb, replace PostalCode with the canonical
    nz_postal_lookup[suburb]. Logs a quiet correction when it changes.
    Returns the number of rows updated.
    """
    changed = 0
    for r in rows or []:
        sb = (r.get("Suburb") or "").strip().title()
        if not sb:
            continue
        sb = macron_suburb_map.get(sb, sb)  # keep macron-canon
        expected = nz_postal_lookup.get(sb, "")
        if not expected:
            continue
        cur = (r.get("PostalCode") or "").strip()
        if cur != expected:
            r["PostalCode"] = expected
            try:
                _log_quiet("PostalCode Enforce",
                           f"{cur or '<blank>'} → {expected}",
                           street=(r.get("Street") or ""))
            except Exception:
                pass
            changed += 1
    return changed


def fix_lat_lon_if_swapped(row):
    lat = safe_float(row.get("Latitude"), None)
    lon = safe_float(row.get("Longitude"), None)
    if lat is None or lon is None:
        return row
    # swap only if NZ hemisphere looks wrong and swap lands in AKL
    if lat > 0 and lon < 0:
        if is_in_auckland(lon, lat):  # swapped lands in Auckland
            row["Latitude"], row["Longitude"] = lon, lat
            log_correction("Lat/Lon Swapped", f"Swapped → lat: {lat}, lon: {lon}")
    return row




# --- RD helpers (place once, near other small helpers) ---
_RD_RE = re.compile(r"^\s*(rd\s*[\- ]?\s*\d+|rural\s*delivery\s*\d+)\b", re.IGNORECASE)

def _is_rd_token_only(s: str) -> bool:
    """True if string is ONLY an RD token like 'RD1', 'RD 1', 'Rural Delivery 2'."""
    if not s: return False
    s = s.strip()
    return bool(_RD_RE.fullmatch(s))

def _strip_leading_rd_token(s: str) -> str:
    """Remove a leading RD token; e.g. 'RD1 Whitford' -> 'Whitford'."""
    if not s: return s
    return _RD_RE.sub("", s).strip()


def process_single_row(row,
                       geocode_results,
                       all_rows,
                       all_streets,
                       seen_addresses,
                       fieldnames,
                       verify_geocode,
                       dominant_suburb_map=None,
                       known_geocodes_by_street=None,
                       # NEW (all optional; Option 2 only):
                       nearby_policy_enabled=False,
                       majority_suburb=""):
    """
    Process a single CSV row: clean fields, apply geocode policy, write pass/fail result.

    RD & skip-suburb lookup integration:
      • RD-only suburb → blank display; never used in search.
      • 'RD1 Something' → strip 'RD1' for display; never pass RD token to search.
      • Honors row['_skip_suburb_lookup'] to force suburb-less geocoding.
    """

    # --- helpers ---
    def _auckland_tuple(addr, lat, lon, postal):
        try:
            if is_auckland_result((addr, lat, lon, postal)):
                return True
        except Exception:
            pass
        try:
            if lat is not None and lon is not None and is_in_auckland(float(lat), float(lon)):
                return True
        except Exception:
            pass
        return False

    def _nearby_disallows(majority, fresh_full_addr):
        try:
            parts = fresh_full_addr.split(",")
            gs_raw = parts[1].strip() if len(parts) > 1 else ""
        except Exception:
            gs_raw = ""
        return False, canon_geocoded_suburb(gs_raw)

    def _adopt_label_suburb_and_postcode(r, fresh_addr, fresh_postal):
        if not fresh_addr:
            return
        try:
            parts = (fresh_addr or "").split(",")
            geo_suburb = parts[1].strip().title() if len(parts) > 1 else ""
        except Exception:
            geo_suburb = ""

        cur_suburb = (r.get("Suburb", "") or "").strip().title()

        if geo_suburb:
            if not cur_suburb:
                log_correction("Suburb Replaced", f"(blank) → {geo_suburb} for {fresh_addr}")
                r["Suburb"] = geo_suburb
            elif geo_suburb != cur_suburb:
                if is_nearby_suburb(cur_suburb, geo_suburb):
                    log_correction("Suburb Replaced", f"{cur_suburb} → {geo_suburb} for {fresh_addr}")
                    r["Suburb"] = geo_suburb

        pc_cur = (r.get("PostalCode") or "").strip()
        pc_geo = (fresh_postal or "").strip()
        pc_from_suburb = nz_postal_lookup.get((r.get("Suburb") or "").strip().title(), "")
        if not pc_cur:
            r["PostalCode"] = pc_geo or pc_from_suburb or pc_cur
        elif pc_from_suburb and pc_cur != pc_from_suburb:
            r["PostalCode"] = pc_from_suburb

    # --- early cancel guard ---
    if cancel_flag.is_set():
        return {"status": "fail", "row": row}

    row_result = {"status": "fail", "row": row}
    row = ensure_row_text_types(row)

    # --- BASIC fields/flags ---
    type_field = (row.get("Type", "") or "").strip().lower()
    is_business = (type_field == "business")

    # ✅ "Other" rows always pass
    if "other" in type_field:
        row["Suburb"] = (row.get("Suburb", "") or "").strip().title()
        if is_blank_or_zero(row.get("PostalCode")) and row["Suburb"]:
            row["PostalCode"] = nz_postal_lookup.get(row["Suburb"], "")
        row["State"] = "Auckland"
        row["Status"] = row.get("Status") or "Available"
        row["Final Status"] = "Pass"
        return {"status": "clean", "row": row}

    latitude  = (row.get("Latitude", "")  or "").strip()
    longitude = (row.get("Longitude", "") or "").strip()
    has_original_coords = not is_blank_or_zero(latitude) and not is_blank_or_zero(longitude)

    # Must have number + street
    if not (row.get('Number', '').strip() and row.get('Street', '').strip()):
        row["Final Status"] = "Fail"
        log_street_fail(row, "Missing number and/or street")
        return row_result

    # --- CLEANING (number + street) ---
    row['Number'] = normalize_number(row['Number'])
    row['Number'], row['Street'] = merge_number_with_street(row['Number'], row['Street'])

    # --- RD handling BEFORE suburb normalization / resolve ---
    raw_suburb = (row.get("Suburb", "") or "").strip()
    rd_note = None
    skip_suburb_lookup = bool(row.get("_skip_suburb_lookup"))  # honor pre-existing flag

    if _is_rd_token_only(raw_suburb):
        # Display: blank; Search: none
        row["Suburb"] = ""
        skip_suburb_lookup = True
        rd_note = f"Removed RD-only suburb '{raw_suburb}' (not a valid suburb)."
    elif _RD_RE.match(raw_suburb):
        # Strip the RD token; search must not include RD
        stripped = _strip_leading_rd_token(raw_suburb)
        row["Suburb"] = stripped  # may be blank
        if not stripped:
            skip_suburb_lookup = True
        rd_note = f"Stripped RD prefix from suburb '{raw_suburb}' → '{row['Suburb']}'."

    if rd_note:
        prev = (row.get("Notes") or "").strip()
        row["Notes"] = (prev + (" | " if prev else "") + rd_note)

    # Continue normal suburb cleaning/capitalization (macrons etc.)
    row = clean_and_capitalize_fields(row, valid_suburbs_data)

    # Dominant suburb enforcement (preliminary)
    if dominant_suburb_map and row.get("Street") in dominant_suburb_map:
        dominant = dominant_suburb_map[row["Street"]]
        current = (row.get("Suburb", "") or "").strip()
        if not current or not is_nearby_suburb(current, dominant):
            row["Suburb"] = dominant

    if not row.get('Suburb', '').strip():
        row['Suburb'] = resolve_suburb(row['Street'], row['Suburb'], all_rows, all_streets, row.get('Number',''))

    # ✅ Canonicalize/repair missing street suffix using safe sources
    fixed = ensure_suffix_via_sources(row['Number'], row['Street'], row['Suburb'], all_rows)
    if fixed and fixed != row['Street']:
        log_correction("Canonical Suffix Applied", f"{row['Street']} → {fixed}")
        row['Street'] = fixed

    if not row.get('PostalCode', '').strip() and row['Suburb']:
        row['PostalCode'] = nz_postal_lookup.get(row['Suburb'].strip(), "")

    # If no suburb AND no valid street suffix → last-chance suffix resolve
    if not row.get('Suburb', '').strip() and not SUFFIX_REGEX.search(row.get('Street', '')):
        retry_suffix = ensure_suffix_via_sources(row['Number'], row['Street'], row['Suburb'], all_rows)
        if retry_suffix and SUFFIX_REGEX.search(retry_suffix):
            log_correction("Canonical Suffix Applied (late)", f"{row['Street']} → {retry_suffix}")
            row['Street'] = retry_suffix
        else:
            row["Final Status"] = "Fail"
            log_street_fail(row, "Invalid street/suburb (missing suffix)")
            return row_result

    # --- Build suburb_for_search (the ONLY suburb value that goes to geocoders) ---
    if skip_suburb_lookup:
        suburb_for_search = ""
    else:
        # Use the (post-RD-stripped) display suburb for searching, never raw RD tokens
        suburb_for_search = (row.get("Suburb") or "").strip()

    # Build a clean address key/query that never carries RD tokens
    # Note: when suburb_for_search is blank, we use 'Auckland' as the bounding/city in queries.
    addr_query = addr_key(row['Number'], row['Street'], suburb_for_search or 'Auckland')

    # --- GET fresh geocode candidates ---
    fresh_addr = fresh_lat = fresh_lon = fresh_postal = None

    if is_business:
        if not verify_geocode:
            # Option 2 & 4: only geocode if blank
            if not has_original_coords:
                fresh_addr, fresh_lat, fresh_lon, fresh_postal = geocode_results.get(addr_query, (None, None, None, None))
                if not fresh_addr:
                    q = fmt_addr_parts(row['Number'], row['Street'], suburb_for_search or "Auckland")
                    fresh_addr, fresh_lat, fresh_lon, fresh_postal = get_lat_long(q)
        else:
            # Option 3: always check a fresh geocode for comparison
            fresh_addr, fresh_lat, fresh_lon, fresh_postal = geocode_results.get(addr_query, (None, None, None, None))
            if not fresh_addr:
                q = fmt_addr_parts(row['Number'], row['Street'], suburb_for_search or "Auckland")
                fresh_addr, fresh_lat, fresh_lon, fresh_postal = get_lat_long(q)
    else:
        # Non-business: try batch result; if missing, do fresh geocode
        fresh_addr, fresh_lat, fresh_lon, fresh_postal = geocode_results.get(addr_query, (None, None, None, None))
        if not fresh_addr:
            q = fmt_addr_parts(row['Number'], row['Street'], suburb_for_search or "Auckland")
            fresh_addr, fresh_lat, fresh_lon, fresh_postal = get_lat_long(q)

    # --- APPLY geocode results (with business rules) ---
    if is_business:
        if not verify_geocode:
            if not has_original_coords and fresh_addr:
                row["Latitude"] = fresh_lat
                row["Longitude"] = fresh_lon
                if is_blank_or_zero(row.get("PostalCode")):
                    row["PostalCode"] = fresh_postal or nz_postal_lookup.get(row['Suburb'].strip(), "")
                _adopt_label_suburb_and_postcode(row, fresh_addr, fresh_postal)
        else:
            if fresh_addr and has_original_coords:
                try:
                    lat_old = float(latitude or "0")
                    lon_old = float(longitude or "0")
                    lat_new = float(fresh_lat or 0.0)
                    lon_new = float(fresh_lon or 0.0)
                except Exception:
                    lat_old = lon_old = lat_new = lon_new = 0.0

                old_in_akl = is_in_auckland(lat_old, lon_old)
                new_in_akl = is_in_auckland(lat_new, lon_new)

                if (not old_in_akl) and new_in_akl:
                    row["Latitude"] = lat_new
                    row["Longitude"] = lon_new
                    if is_blank_or_zero(row.get("PostalCode")):
                        row["PostalCode"] = fresh_postal or nz_postal_lookup.get(row['Suburb'].strip(), "")
                    log_correction("Geocode Correction Override",
                                   f"Business: replaced outside-AKL coords with AKL coords for {addr_query}")
                _adopt_label_suburb_and_postcode(row, fresh_addr, fresh_postal)
            elif fresh_addr and not has_original_coords:
                row["Latitude"] = fresh_lat
                row["Longitude"] = fresh_lon
                if is_blank_or_zero(row.get("PostalCode")):
                    row["PostalCode"] = fresh_postal or nz_postal_lookup.get(row['Suburb'].strip(), "")
                _adopt_label_suburb_and_postcode(row, fresh_addr, fresh_postal)
    else:
        # ---------- Non-business ----------
        if not fresh_addr:
            retry = targeted_geocode_retry(
                row=row,
                all_rows=all_rows,
                known_geocodes_by_street=known_geocodes_by_street
            )
            if retry:
                fresh_addr, fresh_lat, fresh_lon, fresh_postal = retry
                row["Latitude"] = fresh_lat
                row["Longitude"] = fresh_lon
                _adopt_label_suburb_and_postcode(row, fresh_addr, fresh_postal)
            else:
                row["Final Status"] = "Fail"
                log_street_fail(row, "Geocode not found after CSV-aware retry", addr_query)
                return row_result
        else:
            if is_blank_or_zero(row.get("Latitude")) or is_blank_or_zero(row.get("Longitude")):
                lat_new = float(fresh_lat or 0.0)
                lon_new = float(fresh_lon or 0.0)
                lat_new, lon_new = maybe_swap_into_auckland(lat_new, lon_new)
                if is_blank_or_zero(row.get("Latitude")):
                    row["Latitude"] = lat_new
                if is_blank_or_zero(row.get("Longitude")):
                    row["Longitude"] = lon_new
            _adopt_label_suburb_and_postcode(row, fresh_addr, fresh_postal)

        if verify_geocode:
            try:
                lat_old = float(latitude or "0")
                lon_old = float(longitude or "0")
                lat_new = float(fresh_lat or 0.0)
                lon_new = float(fresh_lon or 0.0)
                lat_new, lon_new = maybe_swap_into_auckland(lat_new, lon_new)

                lat_ok = not is_blank_or_zero(lat_old) and abs(lat_old - lat_new) < 0.0001
                lon_ok = not is_blank_or_zero(lon_old) and abs(lon_old - lon_new) < 0.0001
                should_replace = not (lat_ok and lon_ok)
                if should_replace:
                    street_key = (row["Street"].strip().title(), row["Suburb"].strip().title())
                    existing_coords = known_geocodes_by_street.get(street_key, []) if known_geocodes_by_street else []
                    if existing_coords:
                        distances = [haversine_distance(lat_new, lon_new, a, b) for (a, b) in existing_coords]
                        if all(d > MAX_ALLOWED_DISTANCE for d in distances):
                            should_replace = False
                if should_replace:
                    row["Latitude"] = lat_new
                    row["Longitude"] = lon_new
            except Exception as e:
                log_correction("Geocode Verification Error", f"{addr_query} → {str(e)}")
        else:
            if is_blank_or_zero(row.get("PostalCode")):
                row["PostalCode"] = fresh_postal or nz_postal_lookup.get(row['Suburb'].strip(), "")

    # --- Status filtering/duplicates ---
    status = (row.get("Status", "") or "").strip().lower()
    if status in {"custom1", "donotcall"}:
        if status == "custom1":
            row["Final Status"] = "Not Chinese"
        elif status == "donotcall":
            row["Final Status"] = "Do Not Call"
        return row_result

    full_key = (
        row.get("ApartmentNumber", "").strip(),
        row['Number'].strip(),
        row['Street'],
        row['Suburb']
    )
    # NEW: do NOT mark Duplicate here
    if seen_addresses is not None:
        # keep tracking if you still want a set, but don’t fail the row
        seen_addresses.add(addr_key)
    # continue normal processing...

    row['State'] = "Auckland"
    row = fix_lat_lon_if_swapped(row)
    row['PostalCode'] = row.get("PostalCode") or nz_postal_lookup.get(row['Suburb'].strip(), "")
    row['Status'] = "Available"
    row["Final Status"] = "Pass"
    row["Suburb"] = row["Suburb"].strip().title()

    if dominant_suburb_map and row.get("Street") in dominant_suburb_map:
        final = dominant_suburb_map[row["Street"]].strip().title()
        if row["Suburb"] != final:
            log_correction("Suburb Replaced", f"Enforced dominant suburb → {row['Suburb']} → {final} for {row['Street']}")
            row["Suburb"] = final

    row_result["status"] = "clean"
    return row_result

# ---------- PATCH: Lift embedded suburb from Street (all variants) ----------

# Aliases & neutral tails we should strip from the end of a Street field.
SUBURB_ALIASES = {
    # shortforms → canonical
    "gi": "Glen Innes",
    "st heliers": "St Heliers",
    "saint heliers": "St Heliers",
    "st johns": "St Johns",
    "saint johns": "St Johns",
    "mt wellington": "Mount Wellington",
    "mt  wellington": "Mount Wellington",
    "mtwellington": "Mount Wellington",
    "tamaki": "Tāmaki",
    "tāmaki": "Tāmaki",
}
NEUTRAL_TAILS = {"Auckland", "Auckland City", "New Zealand", "NZ"}

def _ascii_fold_patch(s: str) -> str:
    """ASCII-fold and lightly clean a string (keeps only letters/digits/spaces)."""
    import unicodedata, re
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^A-Za-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def _canon_suburb_name_patch(s: str, valid_suburbs_set):
    """
    Map 's' to a canonical suburb found in valid_suburbs_set.
    Handles aliases, case/space differences, ASCII/macron variants, and light fuzzy.
    Returns '' if no confident match.
    """
    import re
    if not s: return ""
    base = s.strip()

    # alias first (case/space-insensitive via folded key)
    key = re.sub(r"\s+", " ", _ascii_fold_patch(base)).lower()
    alias = SUBURB_ALIASES.get(key)
    if alias:
        base = alias

    # exact hit preserves macrons
    if base in valid_suburbs_set:
        return base

    # case-insensitive
    lowmap = {vs.lower(): vs for vs in valid_suburbs_set}
    hit = lowmap.get(base.lower())
    if hit:
        return hit

    # ascii-folded hit
    foldmap = {_ascii_fold_patch(vs).lower(): vs for vs in valid_suburbs_set}
    hit = foldmap.get(_ascii_fold_patch(base).lower())
    if hit:
        return hit

    # optional fuzzy (prefers your helper if present)
    try:
        if "safe_fuzzy_match" in globals() and callable(safe_fuzzy_match):
            cand = safe_fuzzy_match(base, list(valid_suburbs_set), threshold=88)
            if cand:
                return cand
        else:
            import difflib
            cand = difflib.get_close_matches(base, list(valid_suburbs_set), n=1, cutoff=0.88)
            if cand:
                return cand[0]
    except Exception:
        pass
    return ""

def lift_embedded_suburb_all(row: dict, valid_suburbs_iterable):
    """
    Pull ANY suburb that’s embedded in Street into Suburb.
    Handles: commas, dashes, slashes, parentheses, spaces-only tails,
    'Auckland/NZ' tails, RD/postcode tails, Mt↔Mount, Saint↔St, GI→Glen Innes,
    macron glitches. Leaves row unchanged if no safe match.

    Expected row keys: "Street", "Suburb".
    """
    import re

    # Prepare inputs
    street_in = fix_macron_corruption((row.get("Street") or "").strip())
    suburb_in = (row.get("Suburb") or "").strip()
    if not street_in or suburb_in:
        return row  # nothing to do

    valid_set = set(valid_suburbs_iterable or [])

    # 1) strip trailing RD/postcode/neutral country tails
    s = street_in
    s = re.sub(r"\bR\.?D\.?\s*\d+\b\s*$", "", s, flags=re.IGNORECASE)  # RD 1, RD1, R.D. 1
    s = re.sub(r"\b\d{4}\b\s*$", "", s)  # NZ 4-digit postcode (trailing)
    s = re.sub(
        r"(?:[,\s/\-–—()]*)(?:%s)\s*$" % "|".join(re.escape(t) for t in sorted(NEUTRAL_TAILS, key=len, reverse=True)),
        "",
        s,
        flags=re.IGNORECASE,
    ).strip()

    # 2) build candidates from delimiters and no-delimiter endings
    parts = re.split(r"[,/()\-–—]+", s)
    parts = [p.strip() for p in parts if p.strip()]
    candidates = []

    if len(parts) >= 2:
        # prefer the rightmost chunk, and also the last two chunks joined
        candidates.append(parts[-1])
        candidates.append(" ".join(parts[-2:]))

    words = s.split()
    # last 3/2/1 words (only if at least one word remains for the street)
    for k in (3, 2, 1):
        if len(words) >= k + 1:
            candidates.append(" ".join(words[-k:]))

    # 3) normalise candidates and try to find a suburb
    hit_suburb = ""
    for c in candidates:
        c_norm = c.strip(" ,")
        # Skip neutral tails
        if _ascii_fold_patch(c_norm).lower() in {t.lower() for t in NEUTRAL_TAILS}:
            continue
        # Normalise Saint/Mount variants commonly seen in tails
        c_norm = re.sub(r"(?i)^saint\s+", "St ", c_norm)
        c_norm = re.sub(r"(?i)^mt\s+", "Mount ", c_norm)

        cand = _canon_suburb_name_patch(c_norm, valid_set)
        if cand:
            hit_suburb = cand
            break

    if not hit_suburb:
        return row  # no confident suburb found; leave untouched

    # 4) remove the matched suburb token from the END of the street safely;
    #    allow optional delimiter and optional Auckland/NZ after it.
    pattern = r"""
        [\s,/()\-–—]*                 # optional delimiters
        %s                            # matched suburb name
        (?:[\s,/()\-–—]+(?:%s))?      # optional neutral tail (Auckland/NZ) after suburb
        \s*$                          # end of string
    """ % (re.escape(hit_suburb), "|".join(re.escape(t) for t in NEUTRAL_TAILS))
    new_street = re.sub(pattern, "", s, flags=re.IGNORECASE | re.VERBOSE).strip()

    # cleanup & guard
    new_street = re.sub(r"\s+", " ", new_street).strip()
    if not new_street:
        return row  # never blank the street

    # 5) write back with canon suburb (respect macrons)
    row["Street"] = new_street.title()
    row["Suburb"] = macron_suburb_map.get(hit_suburb, hit_suburb)
    return row
# ---------- END PATCH ----------




def _canonical_by_proximity_for_street(street_title, rows, radius_m=800, k_nearest=5):
    """
    Pick a single suburb for a street using proximity across BOTH buffers.
    Uses coords from any rows that already have them (clean > fail). Falls back to CSV counts.
    """
    from collections import Counter
    pts = []
    for r in rows:
        st = (r.get("Street") or "").strip().title()
        if st != street_title:
            continue
        sb = (r.get("Suburb") or "").strip().title() or "Auckland"
        la = safe_float(r.get("Latitude"), None)
        lo = safe_float(r.get("Longitude"), None)
        if la is None or lo is None or not is_in_auckland(la, lo):
            continue
        pts.append((la, lo, sb))

    # proximity vote if we have coordinates
    if pts:
        # centroid
        lat_c = sum(p[0] for p in pts)/len(pts)
        lon_c = sum(p[1] for p in pts)/len(pts)
        # k-nearest
        scored = []
        for la, lo, sb in pts:
            d = haversine_distance(la, lo, lat_c, lon_c)
            scored.append((d, sb))
        scored.sort(key=lambda x: x[0])
        topk = scored[:max(1, k_nearest)]
        # winner = most common suburb among nearest; tie → smallest avg distance
        from collections import Counter
        top_counts = Counter(sb for _, sb in topk)
        best, _ = top_counts.most_common(1)[0]
        return best

    # fallback: frequency in CSV if no coords
    subs = [ (r.get("Suburb") or "").strip().title()
             for r in rows if (r.get("Street") or "").strip().title() == street_title and (r.get("Suburb") or "").strip() ]
    if subs:
        return Counter(subs).most_common(1)[0][0]

    return ""


def unify_street_suburb_across_outputs(clean_rows, fail_rows, radius_m=800, k_nearest=5):
    """
    Enforce one-suburb-per-street across BOTH buffers before writing files.
    Returns (clean_rows, fail_rows, affected_streets_set).
    - Canonicalizes suburb strings before compare/lookup (handles macrons/variants).
    - Avoids preferring 'Auckland' unless it's the only viable label.
    """
    # Safe helpers present elsewhere in your codebase
    def _norm_street(s): return (s or "").strip().title()
    def _norm_suburb(s):  # canon + title for compare
        s0 = (s or "").strip().title()
        try:
            return macron_suburb_map.get(s0, s0)  # if you have it
        except Exception:
            return s0



    # Build a light index with normalized fields to cut repeated .strip().title() calls
    def _prep(rows):
        out = []
        for r in rows:
            st = _norm_street(r.get("Street"))
            sb_raw = (r.get("Suburb") or "").strip()
            sb = _norm_suburb(sb_raw) if sb_raw else ""   # keep truly blank as ""
            out.append((r, st, sb))
        return out

    clean_idx = _prep(clean_rows)
    fail_idx  = _prep(fail_rows)
    all_idx   = clean_idx + fail_idx

    streets = sorted({ st for (_r, st, _sb) in all_idx if st })

    affected = set()
    for st in streets:
        # Pull rows for this street
        rows_for_st = [(r, st2, sb2) for (r, st2, sb2) in all_idx if st2 == st]

        # Let proximity choose, but normalize and avoid defaulting to Auckland if others exist
        canonical_suburb = _canonical_by_proximity_for_street(
            st,
            [r for (r, _st2, _sb2) in rows_for_st],  # pass raw rows as your helper expects
            radius_m=radius_m,
            k_nearest=k_nearest
        ) or ""

        canonical_suburb = _norm_suburb(canonical_suburb)
        # If proximity returned 'Auckland' but we have non-empty, non-Auckland labels in this street,
        # prefer the most common non-Auckland suburb.
        if canonical_suburb == "Auckland":
            non_akls = [sb for (_r, _st2, sb) in rows_for_st if sb and sb != "Auckland"]
            if non_akls:
                from collections import Counter
                canonical_suburb = Counter(non_akls).most_common(1)[0][0]

        if not canonical_suburb:
            # Nothing to unify to
            continue

        # Is there any disagreement vs the canonical (treat blank suburb as blank, not 'Auckland')
        had_disagreement = any(
            sb != canonical_suburb
            for (_r, _st2, sb) in rows_for_st
        )

        if not had_disagreement:
            continue

        affected.add(st)

        # Postal: lookup using canonical (already canonized)
        pc = ""
        try:
            pc = nz_postal_lookup.get(canonical_suburb, "")  # safe if mapping exists
        except Exception:
            pc = ""

        def _apply(idx, rows):
            for (r, st2, sb2) in idx:
                if st2 != st:
                    continue
                if (sb2 or "Auckland") == canonical_suburb or sb2 == canonical_suburb:
                    continue  # already correct

                old_sb_raw = (r.get("Suburb") or "").strip()
                r["Suburb"] = canonical_suburb

                # Only set PostalCode if we actually have a canonical code and it's different
                if pc and (r.get("PostalCode", "") or "") != pc:
                    r["PostalCode"] = pc

                log_correction(
                    "Cross-Buffer Unify",
                    f"{old_sb_raw or '<blank>'} → {canonical_suburb}",
                    street=st
                )

        _apply(clean_idx, clean_rows)
        _apply(fail_idx,  fail_rows)

    return clean_rows, fail_rows, affected


async def collect_all_results(address, session, limiters):
    """Run LINZ, geocode.xyz, Nominatim, Photon, collect all results, then choose."""
    tasks = [
        fetch_linz(address, session, limiter=limiters['linz']),
        fetch_geocodexyz(address, session, limiter=limiters['geocodexyz']),
        fetch_nominatim(address, session, limiter=limiters['nominatim']),
        fetch_photon(address, session, limiter=limiters['photon'])
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    valid_results = [r for r in results if isinstance(r, tuple) and r[0] and r[1]]

    if not valid_results:
        return None

    # Compare all collected results → pick the best
    return choose_best_geocode(valid_results)



def reattempt_fail_geocodes_after_unify(
    fail_rows,
    affected_streets,
    all_rows,
    known_geocodes_by_street=None
):
    """
    Re-try ONLY rows whose Final Status is 'Fail' AND whose Status is retryable,
    and whose street is in affected_streets. Skip Duplicate/Not Chinese/Do Not Call/etc.
    """
    cleaned = []
    still_fail = []

    for r in fail_rows:
        st = (r.get("Street") or "").strip().title()
        if st not in affected_streets or not is_retryable_fail(r):
            still_fail.append(r)
            continue

        num = (r.get("Number") or "").strip()
        sb  = (r.get("Suburb") or "").strip().title()   # unified suburb already applied

        # Ensure suffix before retry
        r["Street"] = ensure_suffix_via_sources(num, r["Street"], sb, all_rows)

        # Targeted retry first
        hit = targeted_geocode_retry(r, all_rows, known_geocodes_by_street=known_geocodes_by_street)

        # Hard fallback: plain get_lat_long on unified address
        if not hit:
            hit = get_lat_long(fmt_addr_parts(num, r["Street"], sb),
                               known_geocodes_by_street=known_geocodes_by_street)

        if _is_valid_geocode_tuple(hit):
            addr, la, lo, pc = hit
            r["Latitude"] = la
            r["Longitude"] = lo
            if not (r.get("PostalCode") or "").strip() and pc:
                r["PostalCode"] = pc
            r["Final Status"] = "Pass"
            log_correction("Re-Geocode After Unify", f"Accepted '{addr}'", street=st)
            cleaned.append(r)
        else:
            still_fail.append(r)

    return cleaned, still_fail




def _norm_status(s: str) -> str:
    """Normalize status/final status for comparison."""
    import re
    return re.sub(r"\s+", "", (s or "").strip().lower())

# Skip list for both Status and Final Status checks
_NONRETRY_STATUSES = {
    "duplicate", "notchinese", "custom1", "donotcall",
    "cancelled", "moved", "deceased"
}

def is_retryable_fail(row) -> bool:
    """
    True if:
      - Final Status == 'Fail'
      - Status not in skip list
      - Final Status also not in skip list
    """
    fs = _norm_status(row.get("Final Status"))
    s  = _norm_status(row.get("Status"))

    # Skip if Status or Final Status matches non-retryable list
    if fs in _NONRETRY_STATUSES or s in _NONRETRY_STATUSES:
        return False

    return fs == "fail"




def load_cache():
    global _geocode_cache
    with _cache_lock:
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    _geocode_cache = json.load(f)   # ← no re-keying here
            except Exception:
                _geocode_cache = {}


def save_cache():
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with _cache_lock:
        # write normalized keys
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({k: v for k, v in _geocode_cache.items()}, f)



# ------------------- LINZ DB Setup -------------------
def ensure_linz_sqlite():
    """
    Import LINZ CSV into SQLite, normalizing columns and adding search-friendly folds:
    - Guarantees columns exist: Number, Postalcode, Latitude, Longitude, Street, Suburb
    - Splits LatLong if present
    - Adds StreetFold/SuburbFold (ASCII/diacritic-free, lowercase) for macron-insensitive search
    - Adds BaseFold (street base w/o suffix, folded) for fast suffix-agnostic queries
    - Creates indexes on the folded columns
    """
    import unicodedata, re

    def _fold(s: str) -> str:
        # diacritic-insensitive, ascii-ish, lowercase, single-spaced
        s = (s or "")
        s = unicodedata.normalize("NFKD", s)
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        s = s.encode("ascii", "ignore").decode("ascii")
        s = re.sub(r"\s+", " ", s).strip().lower()
        return s

    def _base_of(street: str) -> str:
        parts = (street or "").strip().split()
        return " ".join(parts[:-1]).strip() if len(parts) > 1 else (street or "").strip()

    needs_rebuild = False
    if os.path.exists(LINZ_DB):
        try:
            conn = sqlite3.connect(LINZ_DB)
            c = conn.cursor()
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='addresses';")
            has_table = bool(c.fetchone())
            if not has_table:
                needs_rebuild = True
            else:
                # If table exists but is empty OR missing new folded columns → rebuild
                c.execute("SELECT COUNT(*) FROM addresses;")
                if (c.fetchone() or [0])[0] == 0:
                    needs_rebuild = True
                else:
                    c.execute("PRAGMA table_info(addresses);")
                    cols = {row[1] for row in c.fetchall()}
                    required = {"StreetFold", "SuburbFold", "BaseFold"}
                    if not required.issubset(cols):
                        needs_rebuild = True
            conn.close()
        except Exception:
            needs_rebuild = True
    else:
        needs_rebuild = True

    if not needs_rebuild:
        return

    # Read CSV into DataFrame
    df = pd.read_csv(LINZ_FILE, dtype=str).fillna("")
    df = df.loc[:, ~df.columns.duplicated()]  # drop duplicate headings

    # Ensure mandatory columns exist
    for col in ["Number", "Postalcode", "Latitude", "Longitude", "Street", "Suburb"]:
        if col not in df.columns:
            df[col] = ""

    # Split "LatLong" if present
    if "LatLong" in df.columns:
        lat_lon_split = df["LatLong"].str.split(",", n=1, expand=True)
        df["Latitude"] = lat_lon_split[0].astype(str).str.strip()
        df["Longitude"] = lat_lon_split[1].astype(str).str.strip()

    # Build folded/search helper columns
    # Keep original Street/Suburb as-is for display; folds are for query joins
    df["StreetFold"] = df["Street"].apply(_fold)
    df["SuburbFold"] = df["Suburb"].apply(_fold)
    df["BaseFold"]   = df["Street"].apply(_base_of).apply(_fold)

    # Write to SQLite
    conn = sqlite3.connect(LINZ_DB)
    df.to_sql("addresses", conn, if_exists="replace", index=False)
    c = conn.cursor()

    # Helpful indexes (folds + Number for fast exact and base-prefix style lookups)
    c.execute("CREATE INDEX IF NOT EXISTS idx_number        ON addresses (Number)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_street_fold   ON addresses (StreetFold)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_suburb_fold   ON addresses (SuburbFold)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_base_fold     ON addresses (BaseFold)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_postalcode    ON addresses (Postalcode)")
    # Keep legacy indexes too (no harm, but folds will be used in new queries)
    c.execute("CREATE INDEX IF NOT EXISTS idx_street        ON addresses (Street)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_suburb        ON addresses (Suburb)")

    conn.commit()
    conn.close()

    log_correction("LINZ DB Rebuild",
                   f"Rebuilt from {os.path.basename(LINZ_FILE)} with {len(df)} rows (folded columns added)")




def get_linz_conn():
    ensure_linz_sqlite()
    with _db_lock:
        return sqlite3.connect(LINZ_DB)


def bulk_linz_lookup(addresses, linz_conn=None, memory_conn=None):
    if linz_conn is None:
        linz_conn = globals().get("linz_conn", None)
    if memory_conn is None:
        memory_conn = globals().get("memory_conn", None)

    results = {}

    # Parse and normalize wanted addresses
    parsed = []
    for addr in addresses:
        m = ADDRESS_PARSE_RX.match(addr)
        if not m:
            continue
        num, street, suburb = [x.strip() for x in m.groups()]
        try:
            num = normalize_number(num)
            num, street = merge_number_with_street(num, street)
            street = correct_suffix_typos(street).strip().title()
            suburb = suburb.strip().title()
        except Exception:
            pass
        parsed.append((addr, street.lower(), suburb.lower(), num))

    if not parsed:
        return results

    # What we want to match exactly
    wanted = {(s, sub, n) for _, s, sub, n in parsed}
    streets = list({p[1] for p in parsed})
    in_clause = ",".join(["?"] * len(streets))

    def run_query(conn, table_name="addresses"):
        if not conn:
            return []
        q = f"""
            SELECT Number, Street, Suburb, Latitude, Longitude, Postalcode
            FROM {table_name}
            WHERE LOWER(Street) IN ({in_clause})
        """
        try:
            return conn.execute(q, streets).fetchall()
        except Exception:
            return []

    linz_rows = run_query(linz_conn, "addresses")
    memory_rows = []
    if memory_conn:
        try:
            memory_rows = memory_conn.execute(f"""
                SELECT number, street, suburb, latitude, longitude, postalcode
                FROM other_addresses
                WHERE LOWER(street) IN ({in_clause})
            """, streets).fetchall()
        except Exception:
            memory_rows = []

    # Filter rows to only those we actually want, then emit results
    for number, street, suburb, lat, lon, postcode in (linz_rows + memory_rows):
        if lat in ("", None) or lon in ("", None):
            continue
        try:
            lat = float(lat); lon = float(lon)
        except Exception:
            continue

        street_l = (street or "").strip().lower()
        suburb_l = (suburb or "").strip().lower()
        number_n = normalize_number(str(number or ""))

        if (street_l, suburb_l, number_n) not in wanted:
            continue

        key = addr_key(number_n, street, suburb)
        results[key] = (
            f"{str(street).strip().title()}, {str(suburb).strip().title()}, Auckland",
            lat,
            lon,
            str(postcode or "")
        )

    return results


# --- External-friendly address helpers ---
UNIT_RX = re.compile(r'^Unit([A-Z0-9]+)/(\d+)$', re.IGNORECASE)

def to_external_query(addr: str) -> str:
    """Convert 'UnitB/246 Bucklands Beach Rd, Suburb' to '246B Bucklands Beach Road, Suburb'."""
    m = ADDRESS_PARSE_RX.match(addr.strip())
    if not m:
        return addr

    number, street, suburb = [x.strip() for x in m.groups()]
    street = correct_suffix_typos(street).title()
    suburb = suburb.title()

    um = UNIT_RX.match(number)
    if um:
        unit, base = um.groups()
        number_ext = f"{base}{unit.upper()}"
    else:
        number_ext = re.sub(r'\s+', '', number)

    # Expand suffix if in map
    parts = street.split()
    if parts and parts[-1] in street_suffix_map:
        parts[-1] = street_suffix_map[parts[-1]]
    street = " ".join(parts)

    return f"{number_ext} {street}, {suburb}, Auckland"


from collections import Counter, defaultdict
from fuzzywuzzy import fuzz
import re

def _letters_only(s: str) -> str:
    return re.sub(r"[^a-z]", "", (s or "").lower())

def _bases_similar_70(a: str, b: str) -> bool:
    a1, b1 = _letters_only(a), _letters_only(b)
    if not a1 or not b1:
        return False
    try:
        score = max(
            fuzz.token_set_ratio(a1, b1),
            fuzz.ratio(a1, b1),
            fuzz.partial_ratio(a1, b1),
        )
    except Exception:
        import difflib
        score = int(difflib.SequenceMatcher(None, a1, b1).ratio() * 100)
    return score >= 80

# >>> PATCH START: Unit/House number normaliser
import re


# Canonical patterns
_UNIT_PREFIX_RE = re.compile(
    r'^\s*Unit\s*([A-Za-z0-9]+)\s*/\s*([0-9]+[A-Za-z]?(?:\s*-\s*[0-9]+[A-Za-z]?)?)\s*$',
    re.IGNORECASE
)
_HOUSE_UNIT_SUFFIX_RE = re.compile(
    r'^\s*([0-9]+[A-Za-z]?(?:\s*-\s*[0-9]+[A-Za-z]?)?)\s*/\s*Unit\s*([A-Za-z0-9]+)\s*$',
    re.IGNORECASE
)

def normalize_unit_house_number(s: str) -> str:
    """
    Lossless normalizer for 'Number' that **never** swaps sides.
    - Keeps the semantics exactly as written: UnitX/HouseY ≠ UnitY/HouseX.
    - Cleans spacing and dash/slash formatting.
    - Uppercases the unit token.
    - If the *reverse* form 'House/UnitX' is supplied, it is converted
      to the canonical internal form 'UnitX/House' (no inference).
    - Does not try to "fix" ambiguous forms like '26/3' (no 'Unit' keyword).
    """
    s = (s or "").strip()
    if not s:
        return ""

    # strip any leading punctuation noise (e.g., ". Unit15/3")
    s = re.sub(r"^[^\w]+", "", s)

    # tidy spaces around slash and dash
    s = re.sub(r"\s*/\s*", "/", s)
    s = re.sub(r"\s*-\s*", "-", s)

    # 1) Unit-prefix form: keep sides, normalize token + house formatting
    m = _UNIT_PREFIX_RE.match(s)
    if m:
        unit_token = m.group(1).upper()
        house_part = m.group(2)
        return f"Unit{unit_token}/{house_part}"

    # 2) Reverse form 'House/UnitX' → canonical 'UnitX/House' (no guesswork)
    m = _HOUSE_UNIT_SUFFIX_RE.match(s)
    if m:
        house_part = m.group(1)
        unit_token = m.group(2).upper()
        return f"Unit{unit_token}/{house_part}"

    # 3) Plain house number or ambiguous patterns → return tidied input unchanged
    return s



def _unify_similar_bases(bases: list[str], base_counts: Counter) -> dict[str, str]:
    """
    Map variant_base -> canonical_base using 70% similarity.
    Canonical = most frequent, then longest.
    """
    def _len_letters(s): return len(_letters_only(s))
    uniques = sorted(set(bases), key=lambda x: (-base_counts.get(x, 0), -_len_letters(x), x))
    alias, visited = {}, set()

    for base in uniques:
        if base in visited:
            continue
        group = [base]
        for other in uniques:
            if other in visited or other == base:
                continue
            if _bases_similar_70(base, other):
                group.append(other)
                visited.add(other)
        visited.add(base)

        canonical = max(group, key=lambda x: (base_counts.get(x, 0), _len_letters(x)))
        for g in group:
            alias[g] = canonical

        if len(group) > 1:
            try:
                merged = [g for g in group if g != canonical]
                if merged:
                    log_correction("Street Base Merge",
                                   f"Canonical '{canonical}' ← {', '.join(sorted(merged))}")
            except Exception:
                pass

    return alias

# =========================
# 🔧 FAST PATCH: Stages 3.3–3.5
# - pre_correct_street_spellings (3.3)
# - standardize_similar_streets (3.4)
# - resolve_conflicting_suburbs_by_proximity (3.5)
# Uses RapidFuzz when available. Minimal logging to speed up I/O.
# =========================

# ---- RapidFuzz (fallback to difflib) ----
try:
    from rapidfuzz import fuzz as _rf_fuzz, process as rf_process
    def _rf_score(a: str, b: str) -> int:
        return max(int(_rf_fuzz.token_set_ratio(a, b)), int(_rf_fuzz.ratio(a, b)))
    _HAS_RF = True
except Exception:
    import difflib as _difflib
    def _rf_score(a: str, b: str) -> int:
        return int(_difflib.SequenceMatcher(None, a, b).ratio() * 100)
    _HAS_RF = False


def _append_note(msg_base, extra):
    msg_base = (msg_base or "").strip()
    extra = (extra or "").strip()
    if not msg_base:
        return extra
    if extra.lower() in msg_base.lower():
        return msg_base
    return f"{msg_base} / {extra}"

def _read_csv_rows(path):
    import csv, os
    if not os.path.exists(path):
        return [], []
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        rows = list(csv.DictReader(f))
        fieldnames = list((rows[0].keys() if rows else []))
    return rows, fieldnames

def _write_csv_rows(path, rows, fieldnames):
    import csv
    # sanitize headers and keep stable order
    fns = [c for c in (fieldnames or []) if isinstance(c, str) and c.strip()]
    # add required columns if missing
    for col in ["Status", "Number", "Notes", "Final Status"]:
        if col not in fns:
            fns.append(col)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fns, extrasaction="ignore", restval="")
        w.writeheader()
        w.writerows(rows)

def _transform_new_street(row, note_msg):
    row["Status"] = "Custom3"
    row["Number"] = ""
    row["Notes"] = _append_note(row.get("Notes", ""), note_msg)
    return row

def postprocess_new_streets(clean_file="output_clean.csv",
                            fail_file="output_fail.csv",
                            missing_file="missing_addresses.csv",
                            include_missing_into_clean=True):
    """
    Apply New Streets changes to clean + fail rows and (optionally) ingest
    missing_addresses.csv → into clean (Pass), then rewrite clean/fail files.
    """
    import os

    note_msg = 'Please refer to "New Streets" for more information'

    # --- Clean ---
    clean_rows, clean_fns = _read_csv_rows(clean_file)
    if clean_rows:
        for r in clean_rows:
            _transform_new_street(r, note_msg)
    _write_csv_rows(clean_file, clean_rows, clean_fns)
    ok_c = bool(clean_rows)

    # --- Fail ---
    fail_rows, fail_fns = _read_csv_rows(fail_file)
    if fail_rows:
        for r in fail_rows:
            _transform_new_street(r, note_msg)
    _write_csv_rows(fail_file, fail_rows, fail_fns)
    ok_f = bool(fail_rows)

    # --- Missing → Clean (Pass) ---
    ok_m = False
    if include_missing_into_clean and os.path.exists(missing_file):
        missing_rows, missing_fns = _read_csv_rows(missing_file)
        # If there are any missing rows, transform & promote to clean:
        if missing_rows:
            # Normalize schemas: union of clean + missing headers (preserve order by preferring clean first)
            union_fns = list(dict.fromkeys((clean_fns or []) + (missing_fns or [])))
            new_missing = []
            for r in missing_rows:
                r = _transform_new_street(r, note_msg)
                # "send to pass" → clear Final Status so they count as Clean
                r["Final Status"] = ""
                new_missing.append(r)

            # Append promoted missings to existing clean rows
            clean_rows = (clean_rows or []) + new_missing
            _write_csv_rows(clean_file, clean_rows, union_fns)
            ok_m = True

    print(f"✅ New Streets post-process → clean: {ok_c} | fail: {ok_f} | promoted_missing: {ok_m}")




# >>> PATCH: add write_missing_addresses_csv_and_check
def write_missing_addresses_csv_and_check(input_file, clean_file, fail_file, out_file):
    """
    Compare input_nws.csv against the union of output_clean.csv + output_fail.csv
    and write any addresses that disappeared to `out_file`.

    • Multiset-aware: if an address appears N times in input but only M times in outputs,
      it records (N-M) missing instances.
    • Canonicalizes address keys so minor formatting isn’t treated as different:
      - flips "UnitX/<house>" to "<house>/UnitX" for comparison
      - expands common street suffix abbreviations once (Rd -> Road, etc.)
      - fixes common suffix typos (Hts -> Heights, Cresent -> Crescent, etc.)
      - normalizes suburb with macrons when available; treats exact "Auckland" as blank
    • Skips rows where Type == "Other" (these are not geocoded by the pipeline).
    """
    import csv, re
    from collections import Counter

    # ---- Safe hooks to existing helpers (fallbacks if not defined) ----
    _expand_once = globals().get("expand_street_suffix_once", lambda s: s)
    _fix_typos   = globals().get("correct_suffix_typos",   lambda s: s)
    _flip_unit   = globals().get("flip_unit_prefix_in_number", lambda s: s)
    _norm_suburb_ascii = globals().get("normalize_suburb_ascii", lambda s: (s or "").strip().title())
    _macron_map = globals().get("macron_suburb_map", {})

    def _to_str(x):
        if x is None: return ""
        s = str(x).strip()
        return s

    def _canon_number(n):
        s = _to_str(n)
        s = re.sub(r"\s*-\s*", "-", s)  # tidy ranges
        # Normalize "UnitX/<house>" → "<house>/UnitX"
        s = _flip_unit(s)
        # Normalize "unit" case and any spaces around slash
        s = re.sub(r"(?i)^\s*(\d+[A-Za-z]?(?:-\d+[A-Za-z]?)?)\s*/\s*unit\s*([A-Za-z0-9]+)\s*$",
                   r"\1/Unit\2", s)
        return s

    def _canon_street(st):
        s = _to_str(st)
        # one-time suffix expand, then typo fix, then Title Case and space collapse
        s = _expand_once(s)
        s = _fix_typos(s)
        s = " ".join(s.split()).title()
        return s

    def _canon_suburb(sb):
        s = _to_str(sb)
        if s.lower() == "auckland":
            return ""  # treat as blank
        # Prefer your macron-aware normaliser if available
        s = _norm_suburb_ascii(s)
        # Ensure Title Case and macron mapping if provided
        s = _macron_map.get(s.title(), s.title())
        return s

    def _addr_key(number, street, suburb):
        n = _canon_number(number)
        st = _canon_street(street)
        sb = _canon_suburb(suburb)
        return f"{n}|{st}|{sb}"

    def _load_rows(path):
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                return list(csv.DictReader(f))
        except FileNotFoundError:
            return []
        except Exception:
            return []

    # ---- Load files ----
    input_rows = _load_rows(input_file)
    clean_rows = _load_rows(clean_file)
    fail_rows  = _load_rows(fail_file)

    # ---- Build multiset of OUTPUT address keys ----
    out_counts = Counter()
    for r in clean_rows + fail_rows:
        num = _to_str(r.get("Number"))
        st  = _to_str(r.get("Street"))
        sb  = _to_str(r.get("Suburb"))
        if num and st:
            out_counts[_addr_key(num, st, sb)] += 1

    # ---- Walk INPUT rows in-order and find missing instances ----
    missing_rows = []
    for r in input_rows:
        # Skip Type == "Other" — the pipeline never geocodes these
        type_norm = _to_str(r.get("Type")).lower()
        if type_norm == "other":
            continue

        num = _to_str(r.get("Number"))
        st  = _to_str(r.get("Street"))
        sb  = _to_str(r.get("Suburb"))
        if not (num and st):
            # no address — keep original behaviour of not counting these
            continue

        k = _addr_key(num, st, sb)
        if out_counts[k] > 0:
            out_counts[k] -= 1  # consume one instance
        else:
            # This instance is missing → keep the original row as-is in the report
            missing_rows.append(r)

    # ---- Write report ----
    # Use the input header order when possible
    fieldnames = list(input_rows[0].keys()) if input_rows else [
        "Number","Street","Suburb","PostalCode","Status","Latitude","Longitude"
    ]
    # Ensure consistent set
    fieldnames = [c for c in fieldnames if isinstance(c, str) and c.strip()]
    fieldnames = list(dict.fromkeys(fieldnames))  # de-dup while preserving order

    with open(out_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore", restval="")
        writer.writeheader()
        for r in missing_rows:
            writer.writerow(r)

    # Console + optional log message
    msg = f"Missing address check: {len(missing_rows)} row(s) not found in outputs → wrote '{out_file}'."
    print("🔎 " + msg)
    if "log_correction" in globals():
        try:
            log_correction("Missing Address Check", msg)
        except Exception:
            pass
# >>> PATCH END

import csv, re

# --- helpers for canonical comparison (ignore suburb) ---
_UNIT_PREFIX_RX = re.compile(
    r'^\s*Unit\s*([A-Za-z0-9]+)\s*/\s*([0-9]+[A-Za-z]?(?:-[0-9]+[A-Za-z]?)?)\s*$',
    re.IGNORECASE
)
_UNIT_SUFFIX_RX = re.compile(
    r'^\s*([0-9]+[A-Za-z]?(?:-[0-9]+[A-Za-z]?)?)\s*/\s*Unit\s*([A-Za-z0-9]+)\s*$',
    re.IGNORECASE
)


def _canon_number_for_compare(num: str) -> str:
    """
    Map UnitA/1 and 1/UnitA to the same token: '1|UA'.
    Keeps ranges (e.g. 12-14) and letter suffixes on the house number.
    """
    s = (num or "").strip()
    if not s:
        return ""
    m = _UNIT_PREFIX_RX.match(s)
    if m:
        unit = m.group(1).upper()
        house = re.sub(r'\s*-\s*', '-', m.group(2))
        return f"{house}|U{unit}"
    m = _UNIT_SUFFIX_RX.match(s)
    if m:
        house = re.sub(r'\s*-\s*', '-', m.group(1))
        unit = m.group(2).upper()
        return f"{house}|U{unit}"
    # plain house number (normalize dash spacing)
    house = re.sub(r'\s*-\s*', '-', s)
    return house.upper() if house.isalpha() else house


def _canon_street_for_compare(st: str) -> str:
    """
    Normalize street for comparison:
      - Title case
      - expand one trailing suffix (Rd→Road, etc.)
      - fix common typos (Hght→Heights, Cresent→Crescent, etc.)
      - collapse spaces
    """
    s = (st or "").strip().title()
    s = expand_street_suffix_once(s)
    s = correct_suffix_typos(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def write_missing_addresses_csv_and_check(input_file, clean_file, fail_file, out_file):
    """
    Write rows from input_file that are NOT present in (clean_file ∪ fail_file),
    comparing ONLY (Number, Street) after canonicalization.
    Suburb differences will NOT cause a row to be flagged as missing.
    """

    def _read_rows(path):
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                return list(csv.DictReader(f))
        except FileNotFoundError:
            return []

    inp_rows = _read_rows(input_file)
    clean_rows = _read_rows(clean_file)
    fail_rows = _read_rows(fail_file)

    # Build a set of present keys from outputs (clean + fail), ignoring suburb
    present_keys = set()
    for r in (clean_rows + fail_rows):
        num = _canon_number_for_compare((r.get("Number") or "").strip())
        st = _canon_street_for_compare((r.get("Street") or "").strip())
        if num and st:
            present_keys.add((num, st))

    # Collect input rows whose (Number, Street) pair does NOT exist in outputs
    missing = []
    for r in inp_rows:
        num = _canon_number_for_compare((r.get("Number") or "").strip())
        st = _canon_street_for_compare((r.get("Street") or "").strip())
        if num and st:
            if (num, st) not in present_keys:
                missing.append(r)
        else:
            # If Number or Street is blank, treat it as missing (unchanged behavior)
            missing.append(r)

    # Write missing rows to out_file (preserving input headers if possible)
    if inp_rows:
        headers = list(inp_rows[0].keys())
    elif clean_rows:
        headers = list(clean_rows[0].keys())
    elif fail_rows:
        headers = list(fail_rows[0].keys())
    else:
        headers = ["Number", "Street", "Suburb", "PostalCode", "Status", "Latitude", "Longitude"]

    with open(out_file, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore", restval="")
        w.writeheader()
        w.writerows(missing)


# ---- quiet logging switch (avoid disk I/O unless important) ----
RESULT_ONLY_LOGS = True  # set False to see detailed audit logs again

def _log_quiet(event, details="", street=None, important=False):
    # only write to file if it's marked important OR global switch is off
    if RESULT_ONLY_LOGS and not important:
        return
    try:
        log_correction(event, details, street=street)
    except Exception:
        pass

# ---- similarity helpers (keep thresholds consistent with your design) ----
def _letters_only_fast(s: str) -> str:
    # cheaper than regex per call
    s = (s or "").lower()
    return "".join(ch for ch in s if "a" <= ch <= "z")

def _bases_similar(a: str, b: str, threshold: int) -> bool:
    a1, b1 = _letters_only_fast(a), _letters_only_fast(b)
    if not a1 or not b1:
        return False
    return _rf_score(a1, b1) >= threshold

def _unify_similar_bases_fast(
    bases: list[str],
    base_counts,
    sim_threshold: int = 86,     # ↑ from 80 → 86 by default
    max_len_delta: int = 2       # block merges if len diff > 2
) -> dict[str, str]:
    """
    Map variant_base -> canonical_base using similarity.
    Guards to avoid false merges like Eaglen → Eaglemont:
      • higher default threshold (86)
      • max length delta (±2)
      • block long-tail prefixy merges (≥4-char common prefix then ≥3-char tail)
      • skip PROTECTED_STREETS bases
    Callers can lower/raise `sim_threshold` as needed (e.g., 70 for 3.3).
    """
    def _letters_only_fast(s: str) -> str:
        # use existing util if present
        try:
            return globals()['_letters_only_fast'](s)
        except Exception:
            import re
            return re.sub(r'[^A-Za-z]', '', s or '')

    def _common_prefix_len(a: str, b: str) -> int:
        n = min(len(a), len(b))
        i = 0
        while i < n and a[i] == b[i]:
            i += 1
        return i

    def _blocks_long_tail_extension(a: str, b: str) -> bool:
        sa = _letters_only_fast(a).lower()
        sb = _letters_only_fast(b).lower()
        cpl = _common_prefix_len(sa, sb)
        tail_a = len(sa) - cpl
        tail_b = len(sb) - cpl
        # If they share a solid prefix (≥4) and one side adds a ≥3-char tail, block.
        return cpl >= 4 and (tail_a >= 3 or tail_b >= 3)

    # Build protected base set from PROTECTED_STREETS (if defined)
    protected_bases = set()
    try:
        if 'PROTECTED_STREETS' in globals():
            for s in PROTECTED_STREETS:
                base_disp, _ = _norm_base_key(s)  # your helper: returns (display_base, key)
                protected_bases.add(base_disp)
    except Exception:
        pass

    # prefix buckets to avoid O(n^2) on unrelated names
    buckets: dict[str, list[str]] = {}
    for b in bases:
        k = _letters_only_fast(b)[:4]  # short key
        buckets.setdefault(k, []).append(b)

    alias: dict[str, str] = {}
    visited: set[str] = set()

    for _, group in buckets.items():
        # sort: most common, then longest, then alpha — improves canonical stability
        group_sorted = sorted(
            set(group),
            key=lambda x: (-base_counts.get(x, 0), -len(_letters_only_fast(x)), x)
        )
        for i, base in enumerate(group_sorted):
            if base in visited:
                continue
            visited.add(base)
            ba = _letters_only_fast(base)
            for other in group_sorted[i + 1:]:
                if other in visited:
                    continue
                if base in protected_bases or other in protected_bases:
                    continue

                ob = _letters_only_fast(other)
                # hard length guard
                if abs(len(ba) - len(ob)) > max_len_delta:
                    continue
                # long-tail prefixy guard
                if _blocks_long_tail_extension(base, other):
                    continue

                # similarity check (uses your existing _bases_similar if available)
                try:
                    similar = _bases_similar(base, other, sim_threshold)
                except Exception:
                    # difflib fallback if _bases_similar not available
                    import difflib
                    ratio = difflib.SequenceMatcher(None, base, other).ratio()
                    similar = ratio >= (sim_threshold / 100.0)

                if similar:
                    alias[other] = base
                    visited.add(other)
    return alias



def _parse_geocoded_label(full_addr: str) -> tuple[str, str]:
    """Return (Street, Suburb) parsed from geocoder label."""
    try:
        parts = (full_addr or "").split(",")
        street = (parts[0] or "").strip().title()
        suburb = (parts[1] or "").strip().title() if len(parts) > 1 else ""
        return street, suburb
    except Exception:
        return "", ""


def enforce_final_street_spelling(all_rows):
    """
    Final enforcement of street spelling:
    Ensures all variations of the same base match the dominant spelling in the dataset.
    Runs after Stage 3.5, so geocode failures can't leave bad spellings in output.
    """
    from collections import defaultdict, Counter

    clusters = defaultdict(list)

    # Group by base (suffixless)
    for idx, r in enumerate(all_rows):
        st = (r.get("Street") or "").strip()
        if not st:
            continue
        base_disp, base_key = _norm_base_key(st)
        clusters[base_key].append(idx)

    # Apply dominant spelling for each base cluster
    for base_key, idxs in clusters.items():
        street_counts = Counter(
            (all_rows[i].get("Street") or "").strip().title()
            for i in idxs if (all_rows[i].get("Street") or "").strip()
        )
        if not street_counts:
            continue

        dominant_street = street_counts.most_common(1)[0][0]

        for i in idxs:
            cur_st = (all_rows[i].get("Street") or "").strip().title()
            if cur_st != dominant_street:
                _log_quiet(
                    "Final-Enforce: Street",
                    f"{cur_st} → {dominant_street}",
                    street=dominant_street,
                    important=False
                )
                all_rows[i]["Street"] = dominant_street

    return all_rows



# ---- Stage 3.3: Pre-correct street spellings (faster & quieter) ----
def pre_correct_street_spellings(all_rows, verbose=False):
    from tqdm import tqdm as _tqdm
    from collections import Counter, defaultdict
    import re

    changed = 0

    # --- Pre-normalise / typo fixes BEFORE base key extraction ---
    for r in all_rows:
        st = (r.get("Street") or "").strip()
        if not st:
            continue
        fixed = st
        fixed = re.sub(r"ikd", "ickd", fixed, flags=re.IGNORECASE)  # Carrikdawson -> Carrickdawson
        fixed = re.sub(r"\s+", " ", fixed)  # collapse spaces
        fixed = fix_known_text_glitches(fixed)
        if fixed != st:
            _log_quiet("Pre-correct: Street OCR", f"{st} → {fixed}", street=fixed, important=False)
            r["Street"] = fixed
            changed += 1

    # Build raw bases with progress bar
    raw_bases, idx_to_base = [], {}
    for idx, r in _tqdm(enumerate(all_rows), total=len(all_rows),
                        desc="🔄 Stage 1: Checking/Correcting Streets...", unit="row"):
        st = (r.get("Street") or "").strip()
        if not st:
            continue
        base_disp, _ = _norm_base_key(st)
        raw_bases.append(base_disp)
        idx_to_base[idx] = base_disp

    base_counts = Counter(raw_bases)

    # --- Bucketed fuzzy match (≥70%) ---
    alias_70 = {}
    buckets = {}
    for b in set(raw_bases):
        k = _letters_only_fast(b)[:4]
        buckets.setdefault(k, []).append(b)
    for group in buckets.values():
        group_sorted = sorted(group, key=lambda x: (-base_counts.get(x,0), -len(_letters_only_fast(x)), x))
        for i, base in enumerate(group_sorted):
            for other in group_sorted[i+1:]:
                if _bases_similar(base, other, 80):
                    canonical = max((base, other), key=lambda x: (base_counts.get(x,0), len(_letters_only_fast(x))))
                    alias_70[(other if canonical == base else base)] = canonical

    # --- Global fallback fuzzy pass for rare bases ---
    rare_bases = [b for b, c in base_counts.items() if c < 3]
    for base in rare_bases:
        for other in set(raw_bases):
            if base != other and _bases_similar(base, other, 80):
                canonical = max((base, other), key=lambda x: (base_counts.get(x,0), len(_letters_only_fast(x))))
                alias_70[base] = canonical
                break

    # --- Apply canonical replacements ---
    clusters = defaultdict(list)
    for idx, r in enumerate(all_rows):
        if idx not in idx_to_base:
            continue
        base_disp, _ = _norm_base_key(r.get("Street") or "")
        can_base = alias_70.get(base_disp, base_disp)
        clusters[can_base].append(idx)

    for base, idxs in clusters.items():
        # Majority suburb in cluster
        sub_counts = Counter(
            canon_suburb((all_rows[i].get("Suburb") or "").strip())
            for i in idxs if (all_rows[i].get("Suburb") or "").strip()
        )
        majority_suburb = sub_counts.most_common(1)[0][0] if sub_counts else ""

        # Choose canonical spelling from majority suburb or most frequent overall
        street_counts = Counter(
            (all_rows[i].get("Street") or "").strip().title()
            for i in idxs if (all_rows[i].get("Street") or "").strip()
        )
        majority_street = street_counts.most_common(1)[0][0] if street_counts else base

        for i in idxs:
            cur_st = (all_rows[i].get("Street") or "").strip().title()
            new_st = majority_street
            if new_st and cur_st != new_st:
                _log_quiet("Pre-correct: Street", f"{cur_st} → {new_st}", street=new_st, important=False)
                all_rows[i]["Street"] = new_st
                changed += 1

    return all_rows, changed


def unit_word_variant(addr: str) -> str:
    """Convert 'UnitB/246 Bucklands Beach Rd, Suburb' to '246 Bucklands Beach Road, Unit B, Suburb'."""
    m = ADDRESS_PARSE_RX.match(addr.strip())
    if not m:
        return addr

    number, street, suburb = [x.strip() for x in m.groups()]
    um = UNIT_RX.match(number)
    if not um:
        return addr

    unit, base = um.groups()
    street = correct_suffix_typos(street).title()
    suburb = suburb.title()

    return f"{base} {street}, Unit {unit.upper()}, {suburb}, Auckland"


def _nearby_support_count(lat, lon, known_coords, radius_m=1000):
    if not known_coords:
        return 0
    try:
        return sum(1 for (a,b) in known_coords if haversine_distance(lat, lon, a, b) <= radius_m)
    except Exception:
        return 0

# --- House/Unit number normalizers (used by addr_key, LINZ lookups, etc.) ---
import re

# Use the global UNIT_RX if it exists; otherwise define a local fallback.
try:
    UNIT_RX
except NameError:
    UNIT_RX = re.compile(r'^Unit([A-Z0-9]+)/(\d+)$', re.IGNORECASE)

_RANGE_RX  = re.compile(r'^\s*(\d+[A-Za-z]?)[\s-]+(\d+[A-Za-z]?)\s*$')
_SIMPLE_RX = re.compile(r'^\s*(\d+)([A-Za-z]?)\s*$')
_SLASH_RX  = re.compile(r'^\s*(\d+[A-Za-z]?)\s*/\s*(\d+[A-Za-z]?)\s*$')

def normalize_number(number_val: str) -> str:
    """
    Normalizes NZ unit/house numbers consistently.
    - Converts month codes (Jan–Dec) to Unit1–Unit12 based on correct month index.
    - Handles letter suffixes (37B → UnitB/37).
    - Cleans separators (~, _, -, etc.) into '/'.
    - Ensures Unit prefix, uppercased.
    """
    number = number_val.strip()
    number = re.sub(r"\s+", "", number)  # collapse spaces

    # Month abbreviation mapping (Jan = 1 ... Dec = 12)
    month_map = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5,
        'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10,
        'nov': 11, 'dec': 12
    }

    # Match patterns like "1-Nov", "2-Oct", "Nov-41", or just "Nov"
    m = re.match(r'^(\d*)[-_/]*([A-Za-z]{3})(?:[-_/]*(\d+))?$', number, re.IGNORECASE)
    if m:
        unit_part, month_abbr, trailing_num = m.groups()
        month_num = month_map.get(month_abbr.lower(), 1)

        # If unit number exists (like "1-Nov"), that becomes the unit prefix
        if unit_part:
            return f"Unit{unit_part}/{month_num}"
        # If it's just "Nov-41", month becomes the unit, trailing is the number
        elif trailing_num:
            return f"Unit{month_num}/{trailing_num}"
        # If it's just "Nov"
        else:
            return f"Unit{month_num}"

    # Letter suffix (e.g., 37B → UnitB/37)
    m = re.match(r'^(\d+)([A-Za-z])$', number)
    if m:
        return f"Unit{m.group(2).upper()}/{m.group(1)}"

    # Replace odd separators with '/'
    number = re.sub(r'[~_\-,.\\:;!\=\+\"\'\(\)]', '/', number)

    # Prepend 'Unit' if there’s a slash but no Unit prefix
    if '/' in number and not number.lower().startswith('unit'):
        parts = number.split('/', 1)
        number = f"Unit{parts[0]}/{parts[1]}"

    # Normalize casing
    if number.lower().startswith("unit"):
        prefix = "Unit"
        remainder = ''.join(ch.upper() if ch.isalpha() else ch for ch in number[4:])
        number = prefix + remainder
    else:
        number = ''.join(ch.upper() if ch.isalpha() else ch for ch in number)

    return number


def merge_number_with_street(number_val, street_val):
    """
    Combines and normalizes NZ unit/house numbers with streets:
    - Converts 39A → UnitA/39
    - If both Number and Street begin with the same digit (e.g., "3" + "3 Macleans Rd"),
      strip the street's duplicate number.
    - Fixes street typos like "Bucklandsbeach" → "Bucklands Beach".
    """
    num_clean = re.sub(r"\s+", "", number_val.strip())

    # Lettered numbers: 39A → UnitA/39
    m = re.match(r'^(\d+)([A-Za-z])$', num_clean)
    if m:
        num_clean = f"Unit{m.group(2).upper()}/{m.group(1)}"

    # If street starts with the same number, strip it
    m2 = re.match(r"^\s*(\d+)\s+(.*)$", street_val.strip())
    if m2:
        street_num, street_name = m2.groups()
        if street_num == re.sub(r'\D', '', num_clean):  # compare digits only
            street_val = street_name

    # Normalize "Bucklandsbeach" type issues
    street_val = re.sub(r"bucklands\s*beach", "Bucklands Beach", street_val, flags=re.IGNORECASE)

    # Expand suffix abbreviations & title case
    parts = street_val.strip().title().split()
    if parts and parts[-1] in street_suffix_map:
        parts[-1] = street_suffix_map[parts[-1]]
    street_val = " ".join(parts)

    return num_clean, street_val


def _apply_status_override(rows, map_home_to_at_home: bool):
    """
    Preserve Status exactly as in the input.
    Only map 'Home' -> 'At Home' when requested.
    """
    if not map_home_to_at_home or not rows:
        return
    for r in rows:
        s = (r.get("Status") or "").strip()
        if s.lower() == "home":
            r["Status"] = "At Home"



def demote_streets_with_out_of_auckland_coords(clean_rows, fail_rows):
        """
        If ANY row on a street has coordinates outside Auckland,
        move ALL rows on that street to Fail (Final Status = 'Fail (Outside Auckland)').

        Returns: new_clean_rows, new_fail_rows, moved_count, affected_streets (set)
        """
        from collections import defaultdict

        # 1) Find streets that have at least one OOB coord
        streets_with_oob = set()
        by_street = defaultdict(list)

        for r in clean_rows:
            st = (r.get("Street") or "").strip().title()
            if not st:
                continue
            by_street[st].append(r)
            la = safe_float(r.get("Latitude"), None)
            lo = safe_float(r.get("Longitude"), None)
            if la is not None and lo is not None:
                if not is_in_auckland(la, lo):
                    streets_with_oob.add(st)

        if not streets_with_oob:
            return clean_rows, fail_rows, 0, set()

        # 2) Demote all rows that belong to any affected street
        new_clean, moved = [], 0
        for r in clean_rows:
            st = (r.get("Street") or "").strip().title()
            if st in streets_with_oob:
                old = (r.get("Final Status") or "").strip()
                r["Final Status"] = "Fail (Outside Auckland)"
                fail_rows.append(r)
                moved += 1
                try:
                    log_correction(
                        "Coverage Demote (Street-Wide)",
                        f"Street '{st}' → moved to fail (prev Final Status: {old or '<blank>'})",
                        street=st
                    )
                except Exception:
                    pass
            else:
                new_clean.append(r)

        return new_clean, fail_rows, moved, streets_with_oob



def clean_and_capitalize_fields(row, valid_suburbs_data=None):
    original_suburb = (row.get("Suburb") or "").strip()
    suburb_name = original_suburb
    suburb_name = fix_known_text_glitches(suburb_name)

    # --- Step 1: Remove RD + number patterns ---
    cleaned = re.sub(r'\bR\.?D\.?\s*\d+\b', '', suburb_name, flags=re.IGNORECASE)

    # --- Step 2: Remove any standalone numbers (postcodes or others) ---
    cleaned = re.sub(r'\b\d+\b', '', cleaned)

    # --- Step 3: Normalize spacing ---
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    # --- Step 4: If cleaned suburb is empty → skip suburb for geocode ---
    if not cleaned:
        if original_suburb:
            log_correction("Removed invalid suburb", f"{original_suburb} → (blank)")
        row["Suburb"] = ""
        row["_skip_suburb_lookup"] = True  # ✅ custom flag for process_single_row()
        return row

    # Hardcoded suburb corrections
    corrections = {
        "bucklands beach": "Bucklands Beach", "east t膩maki heights": "East Tāmaki Heights",
        "east tāmaki heights": "East Tāmaki Heights",
        "east tamaki heights": "East Tāmaki Heights",
        "bucklandsbeach": "Bucklands Beach",
        "bucklands  beach": "Bucklands Beach",
        "half moon bay": "Half Moon Bay",
        "flatbush": "Flat Bush",
        "manukau central": "Manukau Central",
        "mount wellington": "Mount Wellington",
        "onehunga": "Onehunga",
        "sunnyhills": "Sunnyhills"
    }

    lower_suburb = cleaned.lower()
    if lower_suburb in corrections:
        cleaned = corrections[lower_suburb]
    elif valid_suburbs_data:
        match = next((s for s in valid_suburbs_data if s.lower() == lower_suburb), None)
        if match:
            cleaned = match
        else:
            match = safe_fuzzy_match(cleaned, valid_suburbs_data, threshold=90)
            if match:
                cleaned = match

    # Final title-case
    cleaned = cleaned.title()

    # Log change if suburb was altered
    if cleaned != original_suburb:
        log_correction("Suburb corrected", f"{original_suburb} → {cleaned}")

    row["Suburb"] = cleaned
    return row

def _geocode_with_plus_minus_5(anchor_number, street, suburb, anchor_lat=None, anchor_lon=None, radius_m=300):
    """
    Try the given number first, then ±5 numbers (only positive house numbers).
    If anchor coords are provided, require proximity to anchor.
    Returns (addr, lat, lon, postal) or (None, None, None, None) if no acceptable hit.
    """
    def _try_one(n):
        cand = fmt_addr_parts(str(n), street, suburb or "Auckland")
        res = get_lat_long(cand)
        if _is_valid_geocode_tuple(res):
            if anchor_lat is not None and anchor_lon is not None:
                try:
                    d = haversine_distance(float(res[1]), float(res[2]), anchor_lat, anchor_lon)
                    if d <= radius_m:
                        return res
                    return (None, None, None, None)
                except Exception:
                    return (None, None, None, None)
            return res
        return (None, None, None, None)

    # exact first
    n0 = re.sub(r"[^\d]", "", str(anchor_number or ""))
    if n0.isdigit():
        hit = _try_one(int(n0))
        if hit[0]:
            return hit

        # ±5 sweep
        base = int(n0)
        for delta in range(1, 6):
            for cand_n in (base - delta, base + delta):
                if cand_n > 0:
                    hit = _try_one(cand_n)
                    if hit[0]:
                        return hit
    return (None, None, None, None)

from tqdm import tqdm
from collections import defaultdict
import math

# ---- Stage 3.5: Resolve conflicting suburbs by proximity (fast + full features) ----
def resolve_conflicting_suburbs_by_proximity(
    all_rows,
    known_geocodes_by_street,
    radius_m=300,
    k_nearest=3,
    max_samples_per_street=20,
    max_workers=8,
):
    """
    Resolve conflicting suburb labels for the same street using spatial proximity.

    Combines:
      • Early exits (single-label or strong plurality)
      • KD-tree nearest neighbor lookup (SciPy if available; fallback to fast distance)
      • Postal code updates when suburb changes
      • Minimal enrichment (one probe per street, global budget cap)
      • Coord filling via ±5 number probes
      • Caching for repeated (street, suburb) resolutions
      • Parallel execution with progress bar
    """
    from collections import defaultdict, Counter
    import math, re, heapq, random
    from tqdm import tqdm as _tqdm

    # --- Distance helpers ---
    RAD = math.pi / 180.0
    def _fast_dist_m(lat1, lon1, lat2, lon2):
        phi1 = lat1 * RAD; phi2 = lat2 * RAD
        x = (lon2 - lon1) * RAD * math.cos((phi1 + phi2) * 0.5)
        y = (lat2 - lat1) * RAD
        return 6371000.0 * math.sqrt(x*x + y*y)

    # --- Build per-street view ---
    def _get_street_items(rows):
        by_street = defaultdict(list)
        for i, r in enumerate(rows):
            st = (r.get("Street") or "").strip().title()
            if not st: continue
            sb = (r.get("Suburb") or "").strip().title()
            by_street[st].append((i, r, sb))
        return by_street

    # --- Coord extraction ---
    def _street_pts(items):
        pts = []
        for idx, r, sb in items:
            la = safe_float(r.get("Latitude"), None)
            lo = safe_float(r.get("Longitude"), None)
            if la is None or lo is None: continue
            if not is_in_auckland(la, lo): continue
            row_id = r.get("__RowID", idx + 2)
            addr = f"{(r.get('Number') or '').strip()} {(r.get('Street') or '').strip().title()}, {(sb or 'Auckland')}"
            pts.append((la, lo, (sb or "Auckland"), row_id, addr))
        return pts

    def _centroid(pts):
        n = float(len(pts))
        return (sum(p[0] for p in pts)/n, sum(p[1] for p in pts)/n)

    # --- Voting (top-k distances) ---
    def _k_nearest_vote(pts, center, k):
        scored = [(_fast_dist_m(p[0], p[1], center[0], center[1]), p[2]) for p in pts]
        topk = heapq.nsmallest(max(1, k), scored, key=lambda x: x[0])
        top_counts = Counter(lbl for _, lbl in topk)
        all_counts = Counter(lbl for _, lbl in scored)

        buckets = defaultdict(list)
        for d, lbl in scored:
            buckets[lbl].append(d)

        per_label = {
            lbl: {
                "n_all": all_counts[lbl],
                "n_topk": top_counts.get(lbl, 0),
                "min_d": min(arr),
                "avg_d": sum(arr)/len(arr),
            }
            for lbl, arr in buckets.items()
        }
        return top_counts, per_label

    def _pick_canonical(topk_counts, per_label, fallback_label):
        if topk_counts:
            ordered = topk_counts.most_common()
            if len(ordered) == 1 or (len(ordered) > 1 and ordered[0][1] > ordered[1][1]):
                return ordered[0][0]
        if per_label:
            return min(per_label.keys(), key=lambda lbl: per_label[lbl]["avg_d"])
        return fallback_label

    # --- Apply suburb + postal updates ---
    def _apply_suburb_postal(items, canonical_suburb):
        canonical_suburb = (canonical_suburb or "").strip().title()
        canonical_postal = nz_postal_lookup.get(canonical_suburb, "")
        for idx, row, old_sb in items:
            eff_street = (row.get("Street") or "").strip().title()
            if old_sb != canonical_suburb:
                _log_quiet("ConflictResolve: Suburb", f"{old_sb} → {canonical_suburb} (Street '{eff_street}')",
                           street=eff_street, important=False)
                row["Suburb"] = canonical_suburb
            cur_pc = (row.get("PostalCode") or "").strip()
            if canonical_postal and cur_pc != canonical_postal:
                _log_quiet("ConflictResolve: PostalCode", f"{cur_pc} → {canonical_postal} (Street '{eff_street}')",
                           street=eff_street, important=False)
                row["PostalCode"] = canonical_postal
        return canonical_suburb

    # --- One-probe enrichment (when zero coords) ---
    def _try_min_enrich(street, items, budget_left):
        if budget_left <= 0 or len(items) < 2:
            return [], budget_left
        nums = [re.sub(r"\D", "", (r.get("Number") or "")) for _, r, _ in items]
        sample_num = next((n for n in nums if n), "")
        probe_suburb = next((s for *_x, s in items if s), "")
        try:
            enriched = _probe_all_services_for_address(sample_num, street, probe_suburb or "Auckland")
        except Exception:
            enriched = []
        out = []
        for la, lo, lbl, pretty, _addr in enriched[:1]:
            out.append((la, lo, lbl, 0, pretty))
        return out, max(0, budget_left - (1 if out else 0))

    # --- KD-tree index (global) ---
    use_kdtree, tree, pts_global, labels_global = False, None, [], []
    for (st, sb), coords in known_geocodes_by_street.items():
        sample = coords if len(coords) <= max_samples_per_street else random.sample(coords, max_samples_per_street)
        for lat, lon in sample:
            pts_global.append((lat, lon))
            labels_global.append((st, sb))
    if pts_global:
        try:
            from scipy.spatial import cKDTree
            tree = cKDTree(pts_global)
            use_kdtree = True
        except ImportError:
            pass

    # --- Cache for suburb decisions ---
    cache = {}
    PROBE_BUDGET = int(getattr(globals(), "SUBURB_RESOLVE_PROBE_BUDGET", 200))

    # --- Per-street resolution ---
    def resolve_street(street, items):
        nonlocal PROBE_BUDGET

        pts = _street_pts(items)
        labels = [p[2] for p in pts]

        # EARLY EXIT A: single suburb
        if labels and len(set(labels)) == 1:
            _apply_suburb_postal(items, labels[0])
            return

        # EARLY EXIT B: strong plurality
        if labels:
            cnts = Counter(labels)
            total = sum(cnts.values())
            top, c = cnts.most_common(1)[0]
            if c >= max(3, int(0.7 * total)):
                _apply_suburb_postal(items, top)
                return

        # Try enrichment if no coords
        if not pts:
            add, PROBE_BUDGET = _try_min_enrich(street, items, PROBE_BUDGET)
            pts.extend(add)

        if not pts:
            return  # still nothing

        # Decide canonical suburb
        center = _centroid(pts)
        topk_counts, per_label = _k_nearest_vote(pts, center, k_nearest)
        fallback = labels[0] if labels else pts[0][2]
        chosen = _pick_canonical(topk_counts, per_label, fallback)
        canonical_suburb_now = _apply_suburb_postal(items, chosen)

        # Fill coords if missing
        c_lat, c_lon = center
        for idx, row, _old in items:
            la = safe_float(row.get("Latitude"), None)
            lo = safe_float(row.get("Longitude"), None)
            if la is not None and lo is not None:
                continue
            best = _geocode_with_plus_minus_5(
                row.get("Number", ""),
                street,
                canonical_suburb_now,
                anchor_lat=c_lat,
                anchor_lon=c_lon,
                radius_m=radius_m,
            )
            if _is_valid_geocode_tuple(best):
                row["Latitude"] = best[1]
                row["Longitude"] = best[2]
                if is_blank_or_zero(row.get("PostalCode")):
                    cp = nz_postal_lookup.get(canonical_suburb_now, "")
                    if cp:
                        row["PostalCode"] = cp

    # --- Run with parallel executor ---
    by_street = _get_street_items(all_rows)
    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(resolve_street, st, items): st for st, items in by_street.items()}
        for _ in _tqdm(as_completed(futures), total=len(futures),
                       desc="🔄 Resolving Suburb Conflicts....",
                       unit="street", dynamic_ncols=True):
            pass

    return all_rows





def geocode_linz(address, memory_conn=None):
    """
    LINZ local geocode with safer number matching + index-friendly predicates.
    Tries (in order):
      1) Exact number match (fast, index-friendly)
      2) Guarded LIKE fallback for common unit/house patterns
      3) Base street prefix with suffix swaps (Street/Drive/Road/etc.)
      4) NEW: If a suburb was supplied but nothing matched, retry base+number with ANY suburb
      5) Optional in-memory 'Other' DB with the same guards
    Returns: (formatted_address, lat, lon, postal)
    """
    def _base_and_suffix(st):
        st = (st or "").strip().title()
        parts = st.split()
        if not parts:
            return st, ""
        return " ".join(parts[:-1]).strip(), parts[-1].title()

    m = ADDRESS_PARSE_RX.match(address)
    if not m:
        return None, None, None, None

    num, street, suburb = [x.strip() for x in m.groups()]

    try:
        num = normalize_number(num)
        num, street = merge_number_with_street(num, street)
        street = correct_suffix_typos(street).strip().title()
        suburb = suburb.strip().title()
    except Exception:
        street = street.strip().title()
        suburb = suburb.strip().title()

    base, _suffix = _base_and_suffix(street)

    row = None
    try:
        with _db_lock:
            conn = sqlite3.connect(LINZ_DB, check_same_thread=False)
            c = conn.cursor()

            # 1) Exact match
            c.execute("""
                SELECT Street, Suburb, Latitude, Longitude, Postalcode
                  FROM addresses
                 WHERE Street = ? COLLATE NOCASE
                   AND Suburb = ? COLLATE NOCASE
                   AND Number = ?
                 LIMIT 1
            """, (street, suburb, num))
            row = c.fetchone()

            # 2) Guarded LIKE patterns for unit/house formats
            if not row:
                digits = re.sub(r'\D', '', num or "")
                like_patterns = []
                if digits:
                    like_patterns = [f'Unit%/{digits}', f'{digits}/%', f'%/{digits}/%']

                if like_patterns:
                    placeholders = " OR ".join(["Number LIKE ?"] * len(like_patterns))
                    c.execute(f"""
                        SELECT Street, Suburb, Latitude, Longitude, Postalcode
                          FROM addresses
                         WHERE Street = ? COLLATE NOCASE
                           AND Suburb = ? COLLATE NOCASE
                           AND ({placeholders})
                         LIMIT 1
                    """, (street, suburb, *like_patterns))
                    row = c.fetchone()

            # 3) Base-prefix search (suffix-agnostic)
            has_suburb = bool(suburb and suburb.lower() != "auckland")
            if not row and base:
                if has_suburb:
                    c.execute("""
                        SELECT Street, Suburb, Latitude, Longitude, Postalcode
                          FROM addresses
                         WHERE Street LIKE ? ESCAPE '\\' COLLATE NOCASE
                           AND Suburb = ? COLLATE NOCASE
                           AND Number = ?
                         LIMIT 1
                    """, (f"{base} %", suburb, num))
                else:
                    c.execute("""
                        SELECT Street, Suburb, Latitude, Longitude, Postalcode
                          FROM addresses
                         WHERE Street LIKE ? ESCAPE '\\' COLLATE NOCASE
                           AND Number = ?
                         LIMIT 1
                    """, (f"{base} %", num))
                row = c.fetchone()

            # 4) ✅ NEW: suburb-loosen fallback for same base+number
            #    If a suburb was provided but nothing matched, retry with ANY suburb.
            if (not row) and base and has_suburb:
                c.execute("""
                    SELECT Street, Suburb, Latitude, Longitude, Postalcode
                      FROM addresses
                     WHERE Street LIKE ? ESCAPE '\\' COLLATE NOCASE
                       AND Number = ?
                     LIMIT 1
                """, (f"{base} %", num))
                row = c.fetchone()

            conn.close()
    except Exception as e:
        print(f"❌ SQLite access error: {e}")

    if row:
        s, sub, lat, lon, postal = row
        try:
            lat = float(lat); lon = float(lon)
        except Exception:
            return None, None, None, None
        return f"{str(s).strip().title()}, {str(sub).strip().title()}, Auckland", lat, lon, (postal or "")

    # 5) In-memory 'Other' DB (unchanged logic; suburb-loosen already exists there)
    if memory_conn:
        try:
            with _db_lock:
                mc = memory_conn.cursor()

                digits = re.sub(r'\D', '', num or "")
                like_patterns = []
                if digits:
                    like_patterns = [f'Unit%/{digits}', f'{digits}/%', f'%/{digits}/%']

                has_suburb = bool(suburb and suburb.lower() != "auckland")

                # Prefer base-prefix first (suffix-agnostic)
                if base:
                    if has_suburb:
                        mc.execute("""
                            SELECT street, suburb, latitude, longitude, postalcode
                              FROM other_addresses
                             WHERE street LIKE ? ESCAPE '\\' COLLATE NOCASE
                               AND suburb = ? COLLATE NOCASE
                               AND number = ?
                             LIMIT 1
                        """, (f"{base} %", suburb, num))
                    else:
                        mc.execute("""
                            SELECT street, suburb, latitude, longitude, postalcode
                              FROM other_addresses
                             WHERE street LIKE ? ESCAPE '\\' COLLATE NOCASE
                               AND number = ?
                             LIMIT 1
                        """, (f"{base} %", num))
                    row = mc.fetchone()
                else:
                    row = None

                # Guarded LIKE on number
                if (not row) and like_patterns:
                    placeholders = " OR ".join(["number LIKE ?"] * len(like_patterns))
                    if has_suburb:
                        mc.execute(f"""
                            SELECT street, suburb, latitude, longitude, postalcode
                              FROM other_addresses
                             WHERE street LIKE ? ESCAPE '\\' COLLATE NOCASE
                               AND suburb LIKE ? ESCAPE '\\' COLLATE NOCASE
                               AND ({placeholders})
                             LIMIT 1
                        """, (f"%{street}%", f"%{suburb}%", *like_patterns))
                    else:
                        mc.execute(f"""
                            SELECT street, suburb, latitude, longitude, postalcode
                              FROM other_addresses
                             WHERE street LIKE ? ESCAPE '\\' COLLATE NOCASE
                               AND ({placeholders})
                             LIMIT 1
                        """, (f"%{street}%", *like_patterns))
                    row = mc.fetchone()

                # No-digit or exact-number fallback
                if (not row) and not like_patterns:
                    if base:
                        if has_suburb:
                            mc.execute("""
                                SELECT street, suburb, latitude, longitude, postalcode
                                  FROM other_addresses
                                 WHERE street LIKE ? ESCAPE '\\' COLLATE NOCASE
                                   AND suburb = ? COLLATE NOCASE
                                   AND number = ?
                                 LIMIT 1
                            """, (f"{base} %", suburb, num))
                        else:
                            mc.execute("""
                                SELECT street, suburb, latitude, longitude, postalcode
                                  FROM other_addresses
                                 WHERE street LIKE ? ESCAPE '\\' COLLATE NOCASE
                                   AND number = ?
                                 LIMIT 1
                            """, (f"{base} %", num))
                        row = mc.fetchone()

                    if not row:
                        if has_suburb:
                            mc.execute("""
                                SELECT street, suburb, latitude, longitude, postalcode
                                  FROM other_addresses
                                 WHERE street LIKE ? ESCAPE '\\' COLLATE NOCASE
                                   AND suburb LIKE ? ESCAPE '\\' COLLATE NOCASE
                                   AND number = ?
                                 LIMIT 1
                            """, (f"%{street}%", f"%{suburb}%", num))
                        else:
                            mc.execute("""
                                SELECT street, suburb, latitude, longitude, postalcode
                                  FROM other_addresses
                                 WHERE street LIKE ? ESCAPE '\\' COLLATE NOCASE
                                   AND number = ?
                                 LIMIT 1
                            """, (f"%{street}%", num))
                        row = mc.fetchone()

            if row:
                s, sub, lat, lon, postal = row
                lat = float(lat); lon = float(lon)
                return f"{str(s).strip().title()}, {str(sub).strip().title()}, Auckland", lat, lon, (postal or "")
        except Exception as e:
            print(f"⚠️ Memory DB lookup failed: {e}")

    return None, None, None, None




import os
import re
from typing import List, Tuple, Optional

_MARKERS = [
    ("Part 1.py", r"#\s*📌\s*Part\s*1/3\s*Start", r"#\s*📌\s*Part\s*1/3\s*End"),
    ("Part 2.py", r"#\s*📌\s*Part\s*2/3\s*Start", r"#\s*📌\s*Part\s*2/3\s*End"),
    ("Part 3.py", r"#\s*📌\s*Part\s*3/3\s*Start", r"#\s*📌\s*Part\s*3/3\s*End"),
]

def _find_block(lines: List[str], start_rx: re.Pattern, end_rx: re.Pattern) -> Optional[Tuple[int, int]]:
    start_idx = None
    for i, line in enumerate(lines):
        if start_idx is None and start_rx.search(line):
            start_idx = i
            continue
        if start_idx is not None and end_rx.search(line):
            return start_idx, i
    return None

# ADD near export_script_parts()
def _log_export_parts(event, details=""):
    # Route to the global logger with empty Street to keep schema stable
    log_correction(event, details, street="")


def export_script_parts(script_path=None, out_dir="Exported Files",
                        min_lines_per_part=30, min_nonblank_per_part=5):
    """
    Export the script into 4 files using 1/4..4/4 markers only.
    - Does NOT modify the source file.
    - Deletes prior Part*.py in out_dir, then writes Part 1.py..Part 4.py.
    - Skips a part if its marker block is missing/too small.
    """
    import os, re, glob

    PART_PATTERNS = [
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

    if script_path is None:
        try:
            script_path = __file__
        except NameError:
            script_path = "1.py"

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

    def _find_blocks(rx_start, rx_end):
        starts = [i for i, ln in enumerate(lines) if rx_start.match(ln)]
        ends   = [i for i, ln in enumerate(lines) if rx_end.match(ln)]
        pairs = []
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





def split_corrections_log(src_path="corrections_log.csv", out_prefix="Log", max_rows_per_file=1000):
    """
    Split corrections_log.csv into multiple CSV files with at most `max_rows_per_file`
    *data rows* per chunk (header is repeated in each chunk).
    Output files are named: Log1.csv, Log2.csv, ...
    Prints a summary of created files and their line counts.
    """
    import os, csv

    if not os.path.exists(src_path):
        print(f"⚠️ corrections_log.csv not found at '{src_path}'. Skipping log split.")
        return

    # Read header + all rows
    try:
        with open(src_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            rows = list(reader)
    except Exception as e:
        print(f"❌ Failed to read '{src_path}': {e}")
        return

    if not rows:
        print("ℹ️ corrections_log.csv is empty. Nothing to split.")
        return

    header = rows[0]
    data = rows[1:]  # only log records (exclude header)

    if not data:
        print("ℹ️ corrections_log.csv has a header but no data rows. Nothing to split.")
        return

    # Make chunks of data rows
    total = len(data)
    chunks = [data[i:i + max_rows_per_file] for i in range(0, total, max_rows_per_file)]

    created = []
    for idx, chunk in enumerate(chunks, start=1):
        out_name = f"{out_prefix}{idx}.csv"
        try:
            with open(out_name, "w", encoding="utf-8", newline="") as out:
                writer = csv.writer(out)
                writer.writerow(header)
                writer.writerows(chunk)
            # Count total lines written (header + data)
            created.append((out_name, 1 + len(chunk)))
        except Exception as e:
            print(f"❌ Failed to write '{out_name}': {e}")

    if not created:
        print("⚠️ No log files were created.")
        return

    print("\n✅ Correction_log Split Complete.")
    print(f"📄 Source: {src_path}")
    print(f"🔀 Chunk size (data rows): {max_rows_per_file}")
    print(f"🧾 Files created: {len(created)}")
    for name, line_count in created:
        # line_count includes header; show both counts for clarity
        data_count = line_count - 1
        print(f"   • {name} — {line_count} total lines ({data_count} data + 1 header)")

def export_bundle_after_parts(out_dir="Exported Files", max_lines_per_file=1000):
    """
    Prepares 'Exported Files' and puts ONLY logs (Log*.csv) inside.
    Parts are written separately by export_script_parts(out_dir=...).
    """
    import os, csv

    os.makedirs(out_dir, exist_ok=True)

    # Clean only logs (we let export_script_parts handle Part*.py itself)
    prior_logs = [f for f in os.listdir(out_dir) if f.lower().startswith("log") and f.lower().endswith(".csv")]
    for f in prior_logs:
        try:
            os.remove(os.path.join(out_dir, f))
        except Exception as e:
            print(f"⚠️ Could not delete {f}: {e}")

    created = []

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
        print("\n✅ Export complete. Files in 'Exported Files':")
        for name, line_count in created:
            print(f"   • {name} — {line_count} line(s)")
    else:
        print("\nℹ️ Nothing was exported (no logs found).")

# ---------- Post-run reporting & splitting ----------

def _addr_key_for_compare(row: dict) -> str:
    """Key to compare input vs outputs (aligns with dedupe logic)."""
    try:
        return canonical_addr_key_for_dedupe(row)
    except Exception:
        num = (row.get("Number") or "").strip()
        st  = (row.get("Street") or "").strip().title()
        sb  = (row.get("Suburb") or "").strip().title()
        apt = (row.get("ApartmentNumber") or "").strip()
        return f"{num}|{st}|{sb}|{apt}"

def write_missing_addresses_report(input_path, clean_path, fail_path, out_path="missing_addresses.csv"):
    """
    Mark a row as 'Missing' ONLY if its Street is not present in either
    output file at all (case/whitespace-insensitive). Suburb differences
    are ignored. If Street is blank in the input row, treat it as missing.

    Always writes the CSV (header only when none are missing).
    Returns the count of missing rows written.
    """
    import csv, os

    def _norm_street(s):
        return (s or "").strip().title()

    if not os.path.exists(input_path):
        print(f"ℹ️ Input file not found for missing-report: {input_path}")
        return 0

    def _read_rows(p):
        if not os.path.exists(p):
            return []
        with open(p, "r", encoding="utf-8-sig", errors="replace") as f:
            return list(csv.DictReader(f))

    input_rows = _read_rows(input_path)
    clean_rows = _read_rows(clean_path)
    fail_rows  = _read_rows(fail_path)

    # Build a set of streets present in outputs (ignore suburb differences)
    streets_in_outputs = {
        _norm_street(r.get("Street"))
        for r in (clean_rows + fail_rows)
        if (r.get("Street") or "").strip()
    }

    # A row is missing iff its Street is blank OR its Street not in outputs at all
    missing = []
    for r in input_rows:
        st = _norm_street(r.get("Street"))
        if not st or st not in streets_in_outputs:
            row = dict(r)
            # 🔁 Flip unit-prefixed numbers for consistency with other outputs
            try:
                num_before = (row.get("Number") or "").strip()
                num_after  = flip_unit_prefix_in_number(num_before)
                if num_after and num_after != num_before:
                    row["Number"] = num_after
            except Exception:
                # fail-safe: leave as-is if flip helper not available for any reason
                pass
            row["Final Status"] = "Missing Addresses"
            missing.append(row)

    # Build header from input and ensure 'Final Status'
    hdr = list(input_rows[0].keys()) if input_rows else []
    if "Final Status" not in hdr:
        hdr.append("Final Status")
    if "Number" not in hdr:
        hdr.insert(0, "Number")  # keep Number visible even if odd input headers

    # Always write the file (with header), even if 0 rows
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=hdr, extrasaction="ignore", restval="")
        w.writeheader()
        for row in missing:
            w.writerow(row)

    if missing:
        print(f"⚠️ Missing-address Check: Wrote {len(missing)} row(s) to {out_path}")
        return len(missing)
    else:
        print("✅ Missing-address check: no missing rows.")
        return 0


def split_output_clean_if_large(src="output_clean.csv", dst_prefix="output_clean", max_rows=300, header=None):
    """
    If output_clean.csv has > max_rows data rows, split into multiple parts
    using the same header order as the input file.
    """
    import csv, os
    if not os.path.exists(src):
        print(f"ℹ️ No {src} to split.")
        return

    with open(src, "r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    total = len(rows)
    if total <= max_rows:
        print(f"ℹ️ Split check: {src} has {total} row(s) (≤ {max_rows}); no split needed.")
        return

    # Use header passed in (from input CSV), fallback to detected
    hdr = header or reader.fieldnames

    # Chunk and write
    chunks = [rows[i:i+max_rows] for i in range(0, total, max_rows)]
    out_files = []
    written_total = 0

    for i, chunk in enumerate(chunks, start=1):
        out_name = f"{dst_prefix}{i}.csv"
        with open(out_name, "w", newline="", encoding="utf-8") as out:
            w = csv.DictWriter(out, fieldnames=hdr, extrasaction="ignore", restval="")
            w.writeheader()
            w.writerows(chunk)
        out_files.append((out_name, len(chunk)))
        written_total += len(chunk)

    print("\n📦 output_Clean Split Summary")
    for name, count in out_files:
        print(f"   • {name} — {count} row(s)")
    print(f"   Total Rows Across Files: {written_total} (original: {total})")
    if written_total == total:
        print("✅ File Split Success")
    else:
        print("❌ split mismatch — counts do not add up!")



# Cache Code

def _norm(s):  # tiny normalizer
    return (s or "").strip().title()

def delete_cache_by_street():
    global _geocode_cache
    load_cache()

    if not _geocode_cache and not os.path.exists(CACHE_FILE):
        print("ℹ️ No cache file found and in-memory cache is empty.")
        return

    street_in = input("Street name (e.g., 'Gills Road'): ").strip()
    if not street_in:
        print("❌ No street entered; aborting.")
        return
    suburb_in = input("Optional suburb filter (press Enter to skip): ").strip()

    street_norm = _norm(street_in)
    suburb_norm = _norm(suburb_in)

    matches = []
    for raw_key in list(_geocode_cache.keys()):
        k = raw_key
        # normalize comparison against canonical form
        m = _cache_key_rx.match(k)
        if not m:
            # last-ditch: substring match
            if street_norm.lower() in k.lower() and (not suburb_norm or suburb_norm.lower() in k.lower()):
                matches.append(raw_key)
            continue

        _num, _street, _suburb = m.groups()
        _suburb = _suburb.replace(", Auckland", "").strip().title()
        if _norm(_street) == street_norm and (not suburb_norm or _suburb == suburb_norm):
            matches.append(raw_key)

    if not matches:
        print("ℹ️ No matching cache entries found.")
        return

    print(f"⚠️ Found {len(matches)} cached address(es) to remove.")
    for ex in matches[:10]:
        print(f"   • {ex}")
    if len(matches) > 10:
        print(f"   … and {len(matches)-10} more")

    confirm = input("Type 'DELETE' to confirm removal: ").strip()
    if confirm != "DELETE":
        print("❌ Cancelled; nothing deleted.")
        return

    try:
        if os.path.exists(CACHE_FILE):
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy(CACHE_FILE, f"{CACHE_FILE}.bak_{ts}")
            print(f"🗂️  Backup saved → {CACHE_FILE}.bak_{ts}")
    except Exception as e:
        print(f"⚠️ Could not back up cache file: {e}")

    for k in matches:
        _geocode_cache.pop(k, None)

    try:
        save_cache()
        print(f"✅ Removed {len(matches)} cache entrie(s) and saved changes.")
    except Exception as e:
        print(f"❌ Failed to write updated cache: {e}")

def run_clean_verify_and_split_newstreets_after_purge():
    if not ensure_delete_option_outputs_interactive("4"):  # same deletion scope as opt 4
        return
    log_correction("Session Start", "Corrections log recreated after deletion or fresh start.")
    process_csv(
        "input_nws.csv",
        "output_clean.csv",
        "output_fail.csv",
        expected_headers=EXPECTED_HEADERS,
        verify_geocode=True
    )
    # Apply New Streets changes to clean+fail and promote any missings → clean
    postprocess_new_streets(
        clean_file="output_clean.csv",
        fail_file="output_fail.csv",
        missing_file="missing_addresses.csv",
        include_missing_into_clean=True
    )

    # Now split (same as option 4)
    split_cleaned_by_polygon_and_include_failed(
        "output_clean.csv",
        "output_fail.csv",
        kml_dir="KML Boundaries"
    )



def run_clean_live_after_purge(expected_headers):
    # Clean only the files relevant to this option
    if not ensure_delete_option_outputs_interactive("5"):
        return
    log_correction("Session Start", "Corrections log recreated after deletion or fresh start.")
    process_csv(
        "input_nws.csv",
        "output_clean.csv",
        "output_fail.csv",
        expected_headers=expected_headers,
        verify_geocode=False,
        preserve_input_status=True,     # ← keep original Status
        map_home_to_at_home=True,
        geocode_scope="missing")

def run_clean_verify_live_after_purge(expected_headers):
    if not ensure_delete_option_outputs_interactive("6"):
        return
    log_correction("Session Start", "Corrections log recreated after deletion or fresh start.")
    process_csv(
        "input_nws.csv",
        "output_clean.csv",
        "output_fail.csv",
        expected_headers=expected_headers,
        verify_geocode=True,
        preserve_input_status=True,     # ← keep original Status
        map_home_to_at_home=True        # ← map "Home" → "At Home"
    )



def run_clean_and_split_after_purge_verify():
    if not ensure_delete_suburb_dir_interactive():
        return
    log_correction("Session Start", "Corrections log recreated after deletion or fresh start.")
    # run the cleaning with verify=True
    process_csv(
        "input_nws.csv",
        "output_clean.csv",
        "output_fail.csv",
        expected_headers=["Number","Street","Suburb","PostalCode","Status","Latitude","Longitude"],
        verify_geocode=True
    )
    # then split
    split_cleaned_by_suburb_and_include_failed("output_clean.csv", "output_fail.csv")



# --- Canonical suffix resolver (no guessing) ---

CANON_SUFFIX_BY_BASE = {}           # base -> Counter({suffix: count})
_canon_lock = threading.Lock()

def _split_base_suffix(st: str):
    st = (st or "").strip().title()
    if not st:
        return "", ""
    parts = st.split()
    if len(parts) >= 2 and parts[-1].title() in SUFFIXES:
        return " ".join(parts[:-1]).strip(), parts[-1].title()
    return st, ""  # no suffix present

def build_canon_suffix_map_from_outputs(paths=("output_clean.csv",)):
    """Build base->suffix frequency from prior cleaned output(s)."""
    from collections import Counter, defaultdict
    by_base = defaultdict(Counter)
    for p in paths:
        if not os.path.exists(p):
            continue
        try:
            with open(p, "r", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    st = (r.get("Street","") or "").strip().title()
                    base, sfx = _split_base_suffix(st)
                    if base and sfx:
                        by_base[base][sfx] += 1
        except Exception as e:
            log_correction("CanonSuffixLoadError", f"{p}: {e}")
    with _canon_lock:
        global CANON_SUFFIX_BY_BASE
        CANON_SUFFIX_BY_BASE = dict(by_base)

# --- Cross-buffer unify after geocoding: top-level, always defined
def _unify_crossfiles_postgeocode(clean_rows, fail_rows):
    """
    Make the same street have the same suburb across clean + fail,
    chosen by proximity (using whatever coords we have).
    """
    from collections import defaultdict, Counter
    import math

    def hav(la1, lo1, la2, lo2):
        R = 6371000
        dphi = math.radians(la2 - la1)
        dl   = math.radians(lo2 - lo1)
        a = math.sin(dphi/2)**2 + math.cos(math.radians(la1))*math.cos(math.radians(la2))*math.sin(dl/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    groups = defaultdict(list)
    for src, arr in (("clean", clean_rows), ("fail", fail_rows)):
        for r in arr:
            st = (r.get("Street") or "").strip().title()
            sb = (r.get("Suburb") or "").strip().title()
            la = safe_float(r.get("Latitude"), None)
            lo = safe_float(r.get("Longitude"), None)
            if st:
                groups[st].append((r, sb, la, lo, src))

    for street, items in groups.items():
        pts = [(sb, la, lo) for (_r, sb, la, lo, _src) in items if la is not None and lo is not None]
        if not pts:
            continue

        c_la = sum(p[1] for p in pts) / len(pts)
        c_lo = sum(p[2] for p in pts) / len(pts)

        by_label = {}
        for sb, la, lo in pts:
            if sb:
                by_label.setdefault(sb, []).append(hav(la, lo, c_la, c_lo))
        if not by_label:
            continue

        avg_dist = {lbl: (sum(ds)/len(ds)) for lbl, ds in by_label.items()}
        min_avg = min(avg_dist.values())
        tied = [lbl for lbl, d in avg_dist.items() if abs(d - min_avg) < 1e-6]
        if len(tied) > 1:
            freq = Counter(sb for (_r, sb, _la, _lo, _src) in items if sb)
            best = max(tied, key=lambda s: (freq[s], s))
        else:
            best = tied[0]
        canonical_suburb = best.strip().title()

        for (row, _sb, _la, _lo, _src) in items:
            old = (row.get("Suburb") or "").strip().title()
            if old != canonical_suburb:
                row["Suburb"] = canonical_suburb
                _log_quiet("Post-Enforce Crossfiles: Suburb",
                           f"{old or '<blank>'} → {canonical_suburb} (Street '{street}')",
                           street=street, important=False)

    return clean_rows, fail_rows


def _choose_from_all_rows(base, all_rows):
    """Look inside current CSV for same base + a known suffix."""
    from collections import Counter
    cnt = Counter()
    for r in all_rows:
        st = (r.get("Street","") or "").strip().title()
        b, sfx = _split_base_suffix(st)
        if b == base and sfx:
            cnt[sfx] += 1
    return cnt.most_common(1)[0][0] if cnt else ""

def _choose_from_linz(base, suburb=""):
    """Ask LINZ. Prefer same-suburb; accept only if unambiguous."""
    try:
        # 1) same-suburb resolution
        conn = get_linz_conn()
        c = conn.cursor()
        if suburb:
            c.execute("""
              SELECT Street FROM addresses
               WHERE Suburb = ? COLLATE NOCASE AND Street LIKE ? ESCAPE '\\' COLLATE NOCASE
            """, (suburb.strip().title(), f"{base} %"))
            rows = [r[0] for r in c.fetchall()]
            if rows:
                sfxs = [s.split()[-1].title() for s in rows if s.split()[-1].title() in SUFFIXES]
                uniq = sorted(set(sfxs))
                if len(uniq) == 1:
                    conn.close()
                    return uniq[0]
        # 2) any-suburb, but only if single unique suffix
        suffixes = linz_suffixes_for_base(base)  # your existing helper
        if len(suffixes) == 1:
            conn.close()
            return next(iter(suffixes))
        conn.close()
    except Exception as e:
        log_correction("LINZSuffixLookupError", f"{base}: {e}")
    return ""

def _choose_from_external(number, base, suburb):
    """Geocode and parse street back (only accept if we see a known suffix)."""
    cand = fmt_addr_parts(number, base, suburb or "Auckland")
    addr, lat, lon, _ = get_lat_long(cand)
    if addr:
        first = (addr.split(",")[0] or "").strip().title()
        b, sfx = _split_base_suffix(first)
        if b == base and sfx:
            return sfx
    return ""

def ensure_suffix_via_sources(number, street, suburb, all_rows):
    """
    If street lacks a suffix, try: output_clean -> all_rows -> LINZ -> external.
    Never guess; return original if nothing is found.
    """
    st = (street or "").strip().title()
    if not st or st.split()[-1].title() in SUFFIXES or st in PROTECTED_STREETS:
        return st

    base, _ = _split_base_suffix(st)
    if not base:
        return st

    # 1) Prior cleaned outputs
    with _canon_lock:
        cnt = CANON_SUFFIX_BY_BASE.get(base)
    if cnt:
        sfx, _ = cnt.most_common(1)[0]
        return f"{base} {sfx}"

    # 2) Current CSV
    sfx = _choose_from_all_rows(base, all_rows)
    if sfx:
        return f"{base} {sfx}"

    # 3) LINZ
    sfx = _choose_from_linz(base, suburb)
    if sfx:
        return f"{base} {sfx}"

    # 4) External
    sfx = _choose_from_external(number, base, suburb)
    if sfx:
        return f"{base} {sfx}"

    # Give up—do not invent a suffix
    return st

# Cache key helpers
def cache_key_from_parts(num, street, suburb):
    num = (num or "").strip()
    street = correct_suffix_typos((street or "").strip()).title()
    suburb = (suburb or "").strip().title()
    return f"{num} {street}, {suburb}, Auckland"

# Use the same tolerant parser
_cache_key_rx = ADDRESS_PARSE_RX

def cache_key(address: str) -> str:
    a = (address or "").strip()
    m = ADDRESS_PARSE_RX.match(a)
    if not m:
        return a
    num, street, suburb = m.groups()
    return cache_key_from_parts(num, street, suburb)


def looks_like_expected(label: str, street: str, suburb: str) -> bool:
    L = (label or "").lower()
    return street.lower() in L and suburb.lower() in L



from collections import Counter

def compute_majority_suburb(rows):
    """
    Return the most frequent Suburb (title-cased) from the CSV.
    Ignores blanks. If none found, returns "".
    """
    counts = Counter((r.get("Suburb") or "").strip().title() for r in rows if (r.get("Suburb") or "").strip())
    return counts.most_common(1)[0][0] if counts else ""

def is_suburb_allowed_for_majority(majority_suburb, geocoded_suburb):
    ms = canon_suburb(majority_suburb)
    gs = canon_geocoded_suburb(geocoded_suburb)  # was canon_suburb(...)
    if not ms or not gs:
        return True
    nearby = NEARBY_SUBURBS.get(ms)
    if nearby is None:
        return True
    return gs == ms or gs in {canon_suburb(x) for x in nearby}




def safe_float(x, default=None):
    try:
        s = str(x).strip()
        if s == "":
            return default
        return float(s)
    except Exception:
        return default



# ------------------- External Geocoders -------------------
PHOTON_URL = "https://photon.komoot.io/api/"


def geocode_photon(address):
    try:
        resp = requests.get(
            PHOTON_URL,
            params={
                "q": address,
                "limit": 1,
                "lang": "en",
                # ✅ Auckland bbox (lon,lat,lon,lat)
                "bbox": f"{AUCKLAND_LON_MIN},{AUCKLAND_LAT_MIN},{AUCKLAND_LON_MAX},{AUCKLAND_LAT_MAX}",
            },
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("features"):
                feat = data["features"][0]
                props = feat.get("properties", {}) or {}
                coords = (feat.get("geometry") or {}).get("coordinates") or []
                if len(coords) >= 2:
                    lon, lat = coords[0], coords[1]
                    if ("auckland" in (props.get("city","")+props.get("county","")+props.get("state","")).lower()
                        or is_in_auckland(lat, lon)):
                        street = props.get("street") or props.get("name") or ""
                        suburb = props.get("suburb") or props.get("district") or ""
                        with geocode_lock:
                            geocode_sources_used["Photon"] += 1
                        return f"{street}, {suburb}, Auckland", float(lat), float(lon), ""
    except Exception:
        pass
    return None


# ------------------- NEW: Nominatim + geocode.xyz (sync) -------------------
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
GEOCODEXYZ_URL = "https://geocode.xyz"

def geocode_nominatim(address):
    try:
        # Respect Nominatim usage policy: identify your app
        headers = {"User-Agent": "NZAddressCleaner/1.0"}
        params = {
            "q": address,
            "format": "jsonv2",
            "addressdetails": 1,
            "limit": 1,
            "countrycodes": "nz",
            # Auckland viewbox (lon min, lat min, lon max, lat max)
            "viewbox": f"{AUCKLAND_LON_MIN},{AUCKLAND_LAT_MAX},{AUCKLAND_LON_MAX},{AUCKLAND_LAT_MIN}",
            "bounded": 1,
        }
        resp = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=8)
        if resp.status_code != 200:
            return None
        data = resp.json() or []
        if not data:
            return None
        item = data[0]
        lat = float(item.get("lat", 0) or 0)
        lon = float(item.get("lon", 0) or 0)
        addr = item.get("display_name", "") or ""
        # Try structured props for street/suburb
        props = item.get("address", {}) or {}
        street = props.get("road") or props.get("pedestrian") or props.get("residential") or props.get("name") or ""
        suburb = props.get("suburb") or props.get("neighbourhood") or props.get("city_district") or props.get("city") or ""
        full = f"{street}, {suburb}, Auckland".strip(", ")
        if not full or full == ", Auckland":
            full = addr
        if (("auckland" in addr.lower()) or is_in_auckland(lat, lon)):
            with geocode_lock:
                geocode_sources_used["Nominatim"] += 1
            return (full, lat, lon, props.get("postcode", "") or "")
    except Exception:
        pass
    return None

def geocode_geocodexyz(address):
    try:
        # Free tier ~1 req/sec; keep requests simple
        params = {"locate": address, "region": "NZ", "json": 1}
        resp = requests.get(GEOCODEXYZ_URL, params=params, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json() or {}
        if "error" in data:
            return None
        lat = data.get("latt"); lon = data.get("longt")
        if lat is None or lon is None:
            return None
        lat = float(lat); lon = float(lon)
        # geocode.xyz doesn't return rich address parts; keep our input street/suburb as label basis
        full = fmt_addr_str(address)
        if is_in_auckland(lat, lon):
            with geocode_lock:
                geocode_sources_used["geocode.xyz"] += 1
            return (full, lat, lon, data.get("postal", "") or "")
    except Exception:
        pass
    return None





import time  # Make sure this is imported at the top

def get_lat_long(address, memory_conn=None, known_geocodes_by_street=None):
    """
    Geocode using this exact sequence (stop on first accepted hit):
    0) Local LINZ (accept immediately if numeric lat/lon)
    1) Nearby-biased variants (one pass) → Photon → HERE
    2) Original (numbered) → Photon → HERE
    3) Externalized variants (to_external_query, unit_word_variant) → Photon → HERE
    4) Stripped (numbered) → Photon → HERE
    5) ±5 number variants → Photon → HERE
    6) Suburb swap using NEARBY_SUBURBS → Photon → HERE (if multiple, pick most common; then closest to known coords)
    7) Street suffix swap (current suburb) → Photon → HERE (if multiple, pick most common; then closest)
    8) Final HERE on original (hard fallback)

    Common rules:
      • Always include a house number in every candidate (via _force_number).
      • Acceptance gate: coords parse; AND (label says Auckland OR coords in Auckland OR label says New Zealand/NZ);
        AND if known_geocodes_by_street[(street, suburb)] exists → min distance ≤ MAX_ALLOWED_DISTANCE.
      • Log EVERY unsuccessful attempt (Photon/HERE) to 'different_geocode_variations.csv'
        with Number, Street, Suburb, PostalCode, Latitude, Longitude, Notes.
    """
    import re, csv, os
    from collections import Counter

    if memory_conn is None:
        memory_conn = globals().get("memory_conn", None)

    if GEOCODE_DEBUG:
        log_correction("Geocode Start", f"Original: {address}")

    # ---------- Step 0: local LINZ first ----------
    linz_result = geocode_linz_parallel(address, memory_conn)
    if linz_result and all(linz_result[1:3]):
        with geocode_lock:
            geocode_sources_used["LINZ"] += 1
        log_correction("Geocode Success", f"LINZ: {address} → {linz_result[1]}, {linz_result[2]}")
        return linz_result
    log_correction("Geocode Fallback", f"LINZ failed for {address}")

    # ---------- Parse components ----------
    base_number, street, suburb = "", "", ""
    try:
        m = ADDRESS_PARSE_RX.match(address)
        if m:
            base_number, street, suburb = [x.strip() for x in m.groups()]
            street = correct_suffix_typos(street).strip().title()
            suburb = (suburb.strip().title() or "Auckland")
            if "Unit" in base_number and "/" in base_number:
                base_number = base_number.split("/")[-1]
            base_number = re.sub(r"[^\d]", "", base_number)
        # tidy (idempotent)
        street = correct_suffix_typos(street).strip().title()
        suburb = suburb.strip().title()
        if "Unit" in base_number and "/" in base_number:
            base_number = base_number.split("/")[-1]
        base_number = re.sub(r"[^\d]", "", base_number)
    except Exception as e:
        log_correction("Geocode Parse Error", f"{address} → {e}")

    # ---------- helpers ----------
    SUFFIXES = [
        "Road","Street","Drive","Place","Crescent","Point","Boulevard","Lane",
        "Terrace","Court","Grove","Parade","Heights","Close","Way","Trail","Walk",
        "Rise","Circuit","Quay","Loop","Green","Avenue"
    ]

    def _fmt(num, st, sub):
        st = correct_suffix_typos((st or "").strip()).title()
        sub = (sub or "").strip().title() or "Auckland"
        num = (num or "").strip()
        return (f"{num} {st}, {sub}" if num else f"{st}, {sub}")

    numbered_original = _fmt(base_number, street, suburb) if (street and suburb) else address

    # ---- NEW sync rate limiters (very simple) ----
    _last_req = {"Photon": 0.0, "Nominatim": 0.0, "geocode.xyz": 0.0}
    _rl_lock = threading.Lock()
    # in get_lat_long(): _min_gap
    _min_gap = {"Photon": 0.30, "Nominatim": 1.10, "geocode.xyz": 1.20}

    def _throttle(label):
        with _rl_lock:
            now = time.monotonic()
            wait = _min_gap.get(label, 0) - (now - _last_req.get(label, 0))
            if wait > 0:
                time.sleep(wait)
            _last_req[label] = time.monotonic()

    def _race_geocoders(cand_addr, note=None):
        """
        Launch Photon + Nominatim + geocode.xyz concurrently and return the first ACCEPTED result.
        Logs rejected attempts to variations file (already handled by caller via _append_variation on failure).
        """
        def _call(label, fn):
            _throttle(label)
            res = fn(cand_addr)
            ok, why = _accept_tuple(res)
            return (label, res, ok, why)

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            futs = [
                ex.submit(_call, "Photon", geocode_photon),
                ex.submit(_call, "Nominatim", geocode_nominatim),
                ex.submit(_call, "geocode.xyz", geocode_geocodexyz),
            ]
            for fut in concurrent.futures.as_completed(futs):
                label, res, ok, why = fut.result()
                if ok:
                    if note:
                        log_correction("Geocode Variant Used", f"{label} used: {note}")
                    log_correction("Geocode Success", f"{label}: {cand_addr} → lat:{res[1]}, lon:{res[2]}")
                    log_correction("Geocode Source", f"{label} returned: {res} for input: {cand_addr}")
                    return res
                else:
                    _append_variation(cand_addr, label, why or "rejected", res)
                    log_correction("Geocode Failed", f"{label} → {cand_addr} ({why})")
        return None

    def purge_non_auckland_from_memory(memory_conn):
        """
        Deletes cached LINZ memory rows that aren't in Auckland.
        Adjust table/column names to your schema.
        """
        import math
        cur = memory_conn.cursor()
        # Example assumes table: geocode_cache(label TEXT, lat REAL, lon REAL, postal TEXT)
        rows = cur.execute("SELECT rowid, lat, lon FROM geocode_cache").fetchall()
        bad_ids = []
        for rowid, lat, lon in rows:
            try:
                la = float(lat);
                lo = float(lon)
            except Exception:
                bad_ids.append(rowid);
                continue
            la, lo = _maybe_swap_latlon(la, lo)
            if not is_in_auckland(la, lo):
                bad_ids.append(rowid)
        if bad_ids:
            qmarks = ",".join("?" for _ in bad_ids)
            cur.execute(f"DELETE FROM geocode_cache WHERE rowid IN ({qmarks})", bad_ids)
            memory_conn.commit()
            log_correction("LINZ Memory Purge", f"Removed {len(bad_ids)} non-Auckland cached entries")



    def _label_is_nz(result):
        try:
            L = (result[0] or "").lower()
        except Exception:
            return False
        return ("new zealand" in L) or bool(re.search(r"\bnz\b", L))

    def _accept_tuple(result):
        # validity
        if not _is_valid_geocode_tuple(result):
            return False, "invalid"
        # numeric
        try:
            lat, lon = float(result[1]), float(result[2])
        except Exception:
            return False, "non-numeric"
        # region gate: Auckland label OR within Auckland OR NZ label
        if not (is_auckland_result(result) or is_in_auckland(lat, lon) or _label_is_nz(result)):
            return False, "non-AKL/NZ"
        # distance screen vs known street coords
        coords = known_geocodes_by_street.get((street, suburb), []) if known_geocodes_by_street else []
        if coords:
            dists = [haversine_distance(lat, lon, a, b) for a, b in coords]
            if dists and all(d > MAX_ALLOWED_DISTANCE for d in dists):
                return False, "too-far"

        return True, ""

    def _append_variation(*args, **kwargs):
        return  # disabled

    def _try_geocoder(source_func, label, addr_to_try, variant_note=None):
        log_correction("Geocode Attempt", f"{label} → {addr_to_try}")
        result = source_func(addr_to_try)

        ok, why = _accept_tuple(result)
        if not ok:
            _append_variation(addr_to_try, label, why or "no result", result)
            log_correction("Geocode Failed", f"{label} → {addr_to_try} ({why})")
            return None

        if variant_note:
            log_correction("Geocode Variant Used", f"{label} used: {variant_note}")
        log_correction("Geocode Success", f"{label}: {addr_to_try} → lat:{result[1]}, lon:{result[2]}")
        log_correction("Geocode Source", f"{label} returned: {result} for input: {addr_to_try}")
        return result

    def _force_number(addr: str) -> str:
        """Ensure a leading house number for every candidate if base_number exists."""
        if not addr:
            return addr
        if re.match(r"^\s*\d+", addr):
            return addr
        m = ADDRESS_PARSE_RX.match(addr)
        if m:
            num2, st2, sub2 = [x.strip() for x in m.groups()]
            if not re.match(r"^\d+$", num2 or "") and base_number:
                return _fmt(base_number, st2, sub2)
            return addr
        if base_number and street and suburb:
            return _fmt(base_number, street, suburb)
        return addr

    def _try_sequence_once(addr_to_try, note=None):
        return _race_geocoders(addr_to_try, note)

    def _suffixes():
        return list(SUFFIXES)

    def _base_of(st):
        parts = (st or "").split()
        return " ".join(parts[:-1]).strip() if len(parts) > 1 else ""

    def _generate_close_numbers(n, st, sub):
        try:
            if not (n and n.isdigit()):
                return []
            nn = int(n)
            return [f"{nn + i} {st}, {sub}" for i in range(-5, 6) if i != 0 and nn + i > 0]
        except Exception as e:
            log_correction("Geocode Number Variant Error", f"{address} → {e}")
            return []

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _check_source(label, source_func, cand, note):
        # fire one geocoder, run acceptance, and self-log success/failure
        log_correction("Geocode Attempt", f"{label} → {cand}")
        res = source_func(cand)
        ok, why = _accept_tuple(res)

        if ok:
            if note:
                log_correction("Geocode Variant Used", f"{label} used: {note}")
            # counters are incremented inside geocode_* already
            log_correction("Geocode Success", f"{label}: {cand} → lat:{res[1]}, lon:{res[2]}")
            log_correction("Geocode Source", f"{label} returned: {res} for input: {cand}")
            return ("accepted", res)

        # log unsuccessful attempt to variations file
        _append_variation(cand, label, why or "no result", res)
        log_correction("Geocode Failed", f"{label} → {cand} ({why})")
        return ("rejected", why or "rejected")

    def _attempt_with_retries(source_func, label, cand, note=None, retries=3, delay=0.5):
        for i in range(retries):
            log_correction("Geocode Attempt", f"{label} → {cand} (try {i + 1}/{retries})")
            res = source_func(cand)
            ok, why = _accept_tuple(res)
            if ok:
                if note:
                    log_correction("Geocode Variant Used", f"{label} used: {note}")
                log_correction("Geocode Success", f"{label}: {cand} → lat:{res[1]}, lon:{res[2]}")
                log_correction("Geocode Source", f"{label} returned: {res} for input: {cand}")
                return res
            _append_variation(cand, label, why or "no result", res)
            time.sleep(delay)
        return None

    def _try_geocoders_sequential(addr_to_try, note=None):
        cand = _force_number(addr_to_try)
        # NEW: race Photon + Nominatim + geocode.xyz
        return _race_geocoders(cand, note)

    def _choose_best_hit(hits):
        """
        hits: list[(candidate_addr_str, result_tuple)]
        Rule:
          1) Pick most common (street, suburb) among collected hits.
          2) Tie-breaker: closest to any known coord for that (street, suburb).
        """
        if not hits:
            return None

        def _key(addr_str):
            parts = (addr_str or "").split(",")
            st = parts[0].strip().title() if parts else ""
            sb = parts[1].strip().title() if len(parts) > 1 else ""
            return (st, sb)

        counts = Counter(_key(a) for a, _ in hits)
        mode_key, _ = counts.most_common(1)[0]
        candidates = [(a, r) for a, r in hits if _key(a) == mode_key]
        if len(candidates) == 1:
            return candidates[0][1]

        if known_geocodes_by_street:
            pts = known_geocodes_by_street.get(mode_key, [])
            if pts:
                def _min_dist(res):
                    try:
                        lat, lon = float(res[1]), float(res[2])
                        return min(haversine_distance(lat, lon, a, b) for a, b in pts)
                    except Exception:
                        return float("inf")
                candidates.sort(key=lambda x: _min_dist(x[1]))
                return candidates[0][1]
        return candidates[0][1]

    base = _base_of(street)

    # ---------- Candidate blocks ----------
    def _block_nearby_biased():
        cands = []
        if not (base_number and street and suburb):
            return cands
        # a) same street, same suburb

        first = _fmt(base_number, street, suburb)
        try:
            first = to_external_query(first)  # 'UnitB/246' → '246B'
        except Exception:
            pass
        cands.append(first)

        # b) suffix swaps, same suburb
        if base:
            for sfx in _suffixes():
                cand_st = f"{base} {sfx}"
                if cand_st != street:
                    cands.append(_fmt(base_number, cand_st, suburb))
        # c) nearby suburbs
        for nb in NEARBY_SUBURBS.get(suburb, set()):
            cands.append(_fmt(base_number, street, nb))
            if base:
                for sfx in _suffixes():
                    cand_st = f"{base} {sfx}"
                    if cand_st != street:
                        cands.append(_fmt(base_number, cand_st, nb))
        return cands

    def _block_original():
        return [numbered_original]

    def _block_externalized():
        out = []
        try:
            ext1 = to_external_query(numbered_original)
            if ext1 and ext1 != numbered_original:
                out.append(ext1)
        except Exception as e:
            log_correction("Geocode Externalize Error", f"to_external_query({numbered_original}) → {e}")
        try:
            ext2 = unit_word_variant(numbered_original)
            if ext2 and ext2 != numbered_original:
                out.append(ext2)
        except Exception as e:
            log_correction("Geocode Externalize Error", f"unit_word_variant({numbered_original}) → {e}")
        return out

    def _block_stripped():
        return [_fmt(base_number, street, suburb)]

    def _block_plus_minus_5():
        return _generate_close_numbers(base_number, street, suburb)

    def _block_suburb_swap():
        return [_fmt(base_number, street, nb) for nb in NEARBY_SUBURBS.get(suburb, set())]

    def _block_suffix_swap_current_suburb():
        if not base:
            return []
        # ✅ Only try suffixes that exist for this base in LINZ (no exotic types)
        suffixes = linz_suffixes_for_base(base)
        return [_fmt(base_number, f"{base} {sfx}", suburb) for sfx in sorted(suffixes)]

    # ---------- Execution sequence ----------
    # 1) Nearby-biased
    for cand in _block_nearby_biased():
        res = _try_geocoders_sequential(cand, "Nearby-biased")

        if res:
            return res
    # 2) Original (numbered)
    for cand in _block_original():
        res = _try_sequence_once(cand, "Original")
        if res:
            return res
    # 3) Externalized variants
    for cand in _block_externalized():
        res = _try_sequence_once(cand, "Externalized")
        if res:
            return res
    # 4) Stripped (numbered)
    for cand in _block_stripped():
        res = _try_sequence_once(cand, "Stripped")
        if res:
            return res
    # 5) ±5 numbers
    for cand in _block_plus_minus_5():
        res = _try_sequence_once(cand, "±5")
        if res:
            return res
    # 6) Suburb swap (collect hits, then choose best)
    suburb_hits = []
    for cand in _block_suburb_swap():
        res = _try_sequence_once(cand, "Suburb Swap")
        if res:
            suburb_hits.append((cand, res))
    if suburb_hits:
        chosen = _choose_best_hit(suburb_hits)
        if chosen:
            return chosen
    # 7) Street suffix swap (collect hits, then choose best)
    suffix_hits = []
    for cand in _block_suffix_swap_current_suburb():
        res = _try_sequence_once(cand, "Suffix Swap")
        if res:
            suffix_hits.append((cand, res))
    if suffix_hits:
        chosen = _choose_best_hit(suffix_hits)
        if chosen:
            return chosen

    # 8) Final race on original (hard fallback)
    log_correction("Geocode Fallback", f"Final race on original: {numbered_original}")
    final_res = _race_geocoders(numbered_original, "Final Race Fallback")
    if final_res:
        return final_res

    log_correction("Geocode Failed", f"No valid geocode found for: {numbered_original}")
    return "", "", "", ""



# >>> PATCH START: multi-source probe helper
def _probe_all_services_for_address(number, street, suburb):
    """
    Query LINZ + Photon + Nominatim + geocode.xyz for one address.
    Returns [(lat, lon, suburb_label, pretty_label, addr_str)].
    """
    addr_str = fmt_addr_parts(number, street, suburb or "Auckland")
    hits = []

    # --- LINZ (memory) first: count only if inside Auckland
    try:
        if USE_LINZ_MEMORY:
            linz = geocode_linz_parallel(addr_str, globals().get("memory_conn"))
            if _is_valid_geocode_tuple(linz):
                _label, _lat, _lon, _postal = linz
                la, lo = float(_lat), float(_lon)
                if is_in_auckland(la, lo):
                    with geocode_lock:
                        geocode_sources_used.setdefault("LINZ_MEMORY", 0)
                        geocode_sources_used["LINZ_MEMORY"] += 1
                    hits.append(linz)
    except Exception:
        pass

    # --- External geocoders
    for fn in (geocode_photon, geocode_nominatim, geocode_geocodexyz):
        try:
            res = fn(addr_str)
            if _is_valid_geocode_tuple(res):
                hits.append(res)
        except Exception:
            pass

    # --- Deduplicate by (lat,lon,suburb) and format
    out, seen = [], set()
    for full, lat, lon, _pc in hits:
        st, sb = _parse_geocoded_label(full)
        sb = canon_geocoded_suburb(sb or suburb or "Auckland")
        try:
            key = (round(float(lat), 6), round(float(lon), 6), sb)
        except Exception:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append((float(lat), float(lon), sb,
                    f"{(st or '').strip().title()}, {sb}", addr_str))
    return out
# >>> PATCH END



# >>> PATCH: CSV-aware targeted geocode retry (for rows that fail first pass)
def _csv_suburbs_for_street(street, all_rows):
    """Suburb frequency for exact same street spelling in CSV."""
    from collections import Counter
    s = (street or "").strip().title()
    subs = [ (r.get("Suburb") or "").strip().title()
             for r in all_rows
             if (r.get("Street") or "").strip().title() == s and (r.get("Suburb") or "").strip() ]
    cnt = Counter(subs)
    return [sub for sub,_ in cnt.most_common()]

def _similar_street_in_csv(street, all_rows, threshold=80):
    """Find a similar street spelling in CSV (fast + prefix-bucketed)."""
    streets = sorted({(r.get("Street") or "").strip().title() for r in all_rows if r.get("Street")})
    idx = build_street_index(streets)
    hit = fast_find_similar_street((street or "").strip().title(), idx, threshold=threshold)
    return hit if hit and hit.strip().title() != (street or "").strip().title() else None

def _ordered_nearby_for(anchor):
    """Deterministic order for nearby suburbs; empty if anchor unknown."""
    a = canon_suburb(anchor or "")
    return sorted(NEARBY_SUBURBS.get(a, set()))

def _all_csv_suburbs(all_rows):
    return sorted({(r.get("Suburb") or "").strip().title() for r in all_rows if (r.get("Suburb") or "").strip()})

def _try_candidates(number, street, candidates, known_geocodes_by_street=None, reason="CSV-aware retry"):
    """Iterate address candidates; return first accepted get_lat_long() result."""
    for sub in candidates:
        cand = fmt_addr_parts(number, street, sub) if sub else f"{number} {street}, Auckland"
        res = get_lat_long(cand, known_geocodes_by_street=known_geocodes_by_street)
        ok = _is_valid_geocode_tuple(res)
        if ok:
            log_correction("CSV-aware Geocode", f"Accepted '{cand}'", street=street)
            return res
        else:
            log_correction("CSV-aware Geocode Miss", f"Tried '{cand}'", street=street)
    return None


def targeted_geocode_retry(row, all_rows, known_geocodes_by_street=None):
    """
    Implements your procedure:
      1) If same/similar street exists in CSV with a (different) suburb, try those suburbs first.
      2) Try 'number street' with no suburb (Auckland-level).
      3) Try NEARBY_SUBURBS anchored to the row's suburb (or Papakura if the row says Papakura).
      4) For blank-suburb cases, also try 'all suburbs present in CSV'.
    Returns a valid (addr, lat, lon, postal) or None.
    """
    num = (row.get("Number") or "").strip()
    st  = (row.get("Street") or "").strip().title()
    sb  = (row.get("Suburb") or "").strip().title()

    # 1a) exact same street → CSV suburbs (most common first, excluding current)
    csv_subs = [s for s in _csv_suburbs_for_street(st, all_rows) if s != sb]
    if csv_subs:
        hit = _try_candidates(num, st, csv_subs, known_geocodes_by_street, reason="CSV exact-street suburbs")
        if hit: return hit

    # 1b) similar street spelling (use that street + its CSV suburbs)
    sim_st = _similar_street_in_csv(st, all_rows, threshold=80)
    if sim_st:
        sim_subs = _csv_suburbs_for_street(sim_st, all_rows)
        # Prefer the row suburb first (if present), then the others
        ordered = ([sb] if sb else []) + [s for s in sim_subs if s != sb]
        hit = _try_candidates(num, sim_st, ordered, known_geocodes_by_street, reason="CSV similar-street suburbs")
    if sim_st and hit:
        return hit

    # 2) No-suburb attempt (Auckland-level)
    hit = _try_candidates(num, st, [None], known_geocodes_by_street, reason="No suburb")
    if hit: return hit

    # 3) Nearby list anchored to current suburb (or Papakura, per your note)
   # anchor = sb or "Papakura" if "papakura" in sb.lower() or sb == "" else sb
    anchor = "Papakura" if (not sb or "papakura" in sb.lower()) else sb
    nearby = _ordered_nearby_for(anchor)
    if nearby:
        hit = _try_candidates(num, st, nearby, known_geocodes_by_street, reason="Nearby suburbs")
        if hit: return hit

    # 4) If the suburb was blank, try ALL suburbs seen in the CSV (light brute force)
    if not sb:
        any_subs = _all_csv_suburbs(all_rows)
        hit = _try_candidates(num, st, any_subs, known_geocodes_by_street, reason="All CSV suburbs")
        if hit: return hit

    return None



# ------------------- NEW async fetchers + limiters -------------------
class AsyncRateLimiter:
    def __init__(self, min_interval_sec: float):
        self.min_interval = min_interval_sec
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def wait(self):
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            delta = self.min_interval - (now - self._last)
            if delta > 0:
                await asyncio.sleep(delta)
            self._last = loop.time()

async def fetch_photon(addr, session, limiter=None):
    if limiter: await limiter.wait()
    try:
        params = {
            "q": addr, "limit": 1, "lang": "en",
            "bbox": f"{AUCKLAND_LON_MIN},{AUCKLAND_LAT_MIN},{AUCKLAND_LON_MAX},{AUCKLAND_LAT_MAX}",
        }
        async with session.get(PHOTON_URL, params=params, timeout=8) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            feats = data.get("features") or []
            if not feats: return None
            feat = feats[0]
            coords = (feat.get("geometry") or {}).get("coordinates") or []
            if len(coords) < 2: return None
            lon, lat = coords[0], coords[1]
            props = feat.get("properties", {}) or {}
            if ("auckland" in (props.get("city","")+props.get("county","")+props.get("state","")).lower()
                or is_in_auckland(lat, lon)):
                street = props.get("street") or props.get("name") or ""
                suburb = props.get("suburb") or props.get("district") or ""
                with geocode_lock:
                    geocode_sources_used["Photon"] += 1
                return (f"{street}, {suburb}, Auckland", float(lat), float(lon), "")
    except Exception:
        return None
    return None

async def fetch_nominatim(addr, session, limiter=None):
    if limiter: await limiter.wait()
    try:
        headers = {"User-Agent": "NZAddressCleaner/1.0"}
        params = {
            "q": addr, "format": "jsonv2", "addressdetails": 1, "limit": 1, "countrycodes": "nz",
            "viewbox": f"{AUCKLAND_LON_MIN},{AUCKLAND_LAT_MIN},{AUCKLAND_LON_MAX},{AUCKLAND_LAT_MAX}",
            "bounded": 1,
        }
        async with session.get(NOMINATIM_URL, params=params, headers=headers, timeout=8) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            if not data: return None
            item = data[0]
            lat = float(item.get("lat", 0) or 0)
            lon = float(item.get("lon", 0) or 0)
            props = item.get("address", {}) or {}
            street = props.get("road") or props.get("pedestrian") or props.get("residential") or props.get("name") or ""
            suburb = props.get("suburb") or props.get("neighbourhood") or props.get("city_district") or props.get("city") or ""
            full = f"{street}, {suburb}, Auckland".strip(", ")
            if (("auckland" in (item.get('display_name','')).lower()) or is_in_auckland(lat, lon)):
                with geocode_lock:
                    geocode_sources_used["Nominatim"] += 1
                return (full, lat, lon, props.get("postcode", "") or "")
    except Exception:
        return None
    return None

async def fetch_geocodexyz(addr, session, limiter=None):
    if limiter: await limiter.wait()
    try:
        params = {"locate": addr, "region": "NZ", "json": 1}
        async with session.get(GEOCODEXYZ_URL, params=params, timeout=10) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            if not data or "error" in data:
                return None
            lat = data.get("latt"); lon = data.get("longt")
            if lat is None or lon is None:
                return None
            lat = float(lat); lon = float(lon)
            if is_in_auckland(lat, lon):
                with geocode_lock:
                    geocode_sources_used["geocode.xyz"] += 1
                return (fmt_addr_str(addr), lat, lon, data.get("postal","") or "")
    except Exception:
        return None
    return None



# --- Final batch_geocode with Photon + Nominatim + geocode.xyz hedged race ---
async def batch_geocode(addresses, max_workers=20, max_retries=3, verify=False):
    if not addresses:
        log_correction("Batch Geocoding Start", "Starting With 0 Addresses")
        return {}
    log_correction("Batch Geocoding Start", f"Starting With {len(addresses)} Addresses")

    # de-dupe
    targets = [a for a in set(addresses) if a]
    results = {}

    # 1) LINZ bulk first (kept)
    linz_hits = {}
    if USE_LINZ_MEMORY:
        linz_hits = bulk_linz_lookup(
            targets,
            linz_conn=get_linz_conn(),
            memory_conn=globals().get("memory_conn"),
        )

    # NEW: filter/normalize and drop anything outside Auckland
    filtered = {}
    for akey, tpl in (linz_hits or {}).items():
        if isinstance(tpl, tuple) and len(tpl) == 4:
            label, lat, lon, pc = tpl
            norm = _linz_accept_and_normalize(label, lat, lon, pc)
            if norm:
                filtered[akey] = norm
    linz_hits = filtered

    # ✅ keep LINZ hits in final results immediately
    results.update(linz_hits)

    remaining = [a for a in targets if a not in results]
    if not remaining:
        return results

    # --- simple acceptor
    def _accept_tuple(res):
        if not (isinstance(res, tuple) and len(res) == 4):
            return False
        _, lat, lon, _ = res
        try:
            lat = float(lat); lon = float(lon)
        except Exception:
            return False
        # 🔒 Only accept if actually inside Auckland
        return is_in_auckland(lat, lon)

    # per-service rate limiters (approx global rate)
    limiter_photon     = AsyncRateLimiter(0.20)  # ~5 rps
    limiter_nominatim  = AsyncRateLimiter(1.50)  # ~1 rps (safer for public policy)
    limiter_geocodexyz = AsyncRateLimiter(1.20)  # ~1 rps (free tier)

    sem = asyncio.Semaphore(max_workers)

    async def race_one(session, addr):
        if cancel_flag.is_set():
            return addr, (None, None, None, None)

        async with sem:
            runners = [
                asyncio.create_task(fetch_photon(addr, session, limiter_photon)),
                asyncio.create_task(fetch_nominatim(addr, session, limiter_nominatim)),
                asyncio.create_task(fetch_geocodexyz(addr, session, limiter_geocodexyz)),
            ]
            winner = None
            try:
                for fut in asyncio.as_completed(runners):
                    try:
                        res = await fut
                    except asyncio.CancelledError:
                        continue
                    except Exception:
                        res = None
                    if res and _accept_tuple(res):
                        winner = res
                        break
            finally:
                for t in runners:
                    if not t.done():
                        t.cancel()
                await asyncio.gather(*runners, return_exceptions=True)

            return addr, (winner if winner else (None, None, None, None))

    from tqdm import tqdm as _tqdm

    merged = {}
    try:
        # Bounded connector to avoid socket exhaustion on large batches
        connector = aiohttp.TCPConnector(
            limit=80,          # total concurrent connections
            limit_per_host=10, # per-host cap
            ttl_dns_cache=300  # cache DNS lookups
        )
        timeout = aiohttp.ClientTimeout(total=None)  # rely on per-request timeouts in fetch_* functions

        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            tasks = [asyncio.create_task(race_one(session, a)) for a in remaining]
            with _tqdm(total=len(tasks),
                       desc="🌐 Stage 3: Geocoding....",
                       unit="addr",
                       dynamic_ncols=True) as pbar:
                for fut in asyncio.as_completed(tasks):
                    try:
                        akey, tpl = await fut
                        if isinstance(tpl, tuple) and len(tpl) == 4:
                            merged[akey] = tpl
                    except Exception as e:
                        log_correction("BATCH_TASK_ERROR", f"{e}")
                    finally:
                        pbar.update(1)
    except Exception as e:
        log_correction("BATCH_SESSION_ERROR", f"{e}")

    results.update(merged)
    return results




CACHE_STREETS = "auckland_streets.json"

street_suffix_map = {
    # --- Terrace / Crescent / Court ---
    "Tce": "Terrace", "Tce.": "Terrace", "Terr": "Terrace",
    "Cr": "Crescent", "Cres": "Crescent", "Cresc": "Crescent",
    "Crt": "Court", "Crt.": "Court", "Ct": "Court",

    # --- Road / Street / Avenue / Drive / Place ---
    "Rd": "Road", "Rd.": "Road",
    "St": "Street", "St.": "Street", "Str": "Street",
    "Ave": "Avenue", "Ave.": "Avenue", "Av": "Avenue",
    "Dr": "Drive", "Dr.": "Drive",
    "Pl": "Place", "Pl.": "Place",

    # --- Grove / Green / Gully ---
    "Grv": "Grove", "Grv.": "Grove", "Gr": "Grove",
    "Gl": "Gully", "Gly": "Gully",


    # --- Heights ---
    "Hts": "Heights", "Hts.": "Heights",
    "Hgts": "Heights", "Hghts": "Heights",
    "Ht": "Heights",

    # --- Boulevard / Parade / Lane / Manor ---
    "Blvd": "Boulevard", "Bvld": "Boulevard",
    "Bvd": "Boulevard", "Blv": "Boulevard",
    "Pde": "Parade", "Pde.": "Parade",
    "Lne": "Lane", "Ln": "Lane", "Ln.": "Lane",
    "Mnr": "Manor", "Mnr.": "Manor",

    # --- Square / Circuit / Close ---
    "Sq": "Square", "Sq.": "Square",
    "Cct": "Circuit", "Circ": "Circuit",
    "Cl": "Close",

    # --- Highway / Parkway / Trail / Walk / Point / Way ---
    "Hwy": "Highway", "Hwy.": "Highway",
    "Pkwy": "Parkway", "Pky": "Parkway",
    "Trl": "Trail", "Tr": "Trail",
    "Wlk": "Walk", "Wk": "Walk",
    "Pt": "Point", "Pt.": "Point",
    "Way": "Way",

    # --- Extras (NZ/AU common) ---
    "Espl": "Esplanade", "Esp": "Esplanade",
    "Br": "Bridge",
    "Mt": "Mount", "Mtn": "Mountain",
    "Pk": "Park",
    "Hl": "Hill", "Hls": "Hills",
    "Vw": "View", "Vws": "Views",
    "Ch": "Chase",
    "Cds": "Crossing", "Xing": "Crossing",
    "Rte": "Route", "Byp": "Bypass",
    "Prom": "Promenade", "Ret": "Retreat",
    "Rdg": "Ridge", "Rise": "Rise",
    "Row": "Row", "Loop": "Loop",
    "Outlk": "Outlook", "Otlk": "Outlook",
    "Cmn": "Common", "Vale": "Vale",
    "Gardens": "Gardens", "Gdns": "Gardens",
    "Fairway": "Fairway",
}

# --- Protected Streets & Helpers --- Good
PROTECTED_STREETS = {'Treeway', 'The Crest'}



def fix_macron_corruption(text):
    import unicodedata, re
    # Preserve macron characters explicitly
    macrons = "āĀēĒīĪōŌūŪ"
    text = unicodedata.normalize('NFKC', text)
    cleaned = ''.join(ch for ch in text if ch.isascii() or ch in macrons)
    # If result is too short, fallback to removing all special chars
    if len(cleaned.strip()) < 3:
        cleaned = re.sub(r"[^a-zA-Z0-9\s," + macrons + r"'\-]", "", text).strip().title()
    return cleaned



def strip_punctuation(value):
    import re
    # Preserve macrons explicitly (ā, ē, ī, ō, ū)
    macrons = "āĀēĒīĪōŌūŪ"
    # Remove everything except letters, digits, spaces, and macrons
    value = re.sub(rf"[^A-Za-z0-9\s{macrons}]", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value.title()



def normalize_suburb_ascii(suburb: str) -> str:
    """
    Canonicalise suburb names with macron awareness:
      1) Keep 'Howick' as-is.
      2) Try exact / case-insensitive / ASCII-folded lookups in macron_suburb_map.
      3) If still unknown, return a clean ASCII, title-cased fallback.
    """
    import re, unicodedata

    def _ascii_fold(s: str) -> str:
        s = unicodedata.normalize("NFKD", s or "")
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        s = s.encode("ascii", "ignore").decode("ascii")
        s = re.sub(r"[^A-Za-z0-9\s]", "", s)
        return re.sub(r"\s+", " ", s).strip()

    s = (suburb or "").strip()
    if not s:
        return ""

    # 1) Always prioritise Howick
    if "howick" in s.lower():
        return "Howick"

    # 2) Try macron_suburb_map in multiple ways
    #    (expects you’ve populated it with both macron and non-macron keys)
    #    e.g., {"East Tamaki": "East Tāmaki", "East Tāmaki": "East Tāmaki"}
    if "macron_suburb_map" in globals() and isinstance(macron_suburb_map, dict):
        # exact
        hit = macron_suburb_map.get(s)
        if not hit:
            # case-insensitive
            hit = next((v for k, v in macron_suburb_map.items() if k.lower() == s.lower()), None)
        if not hit:
            # ASCII-folded key lookup (handles corrupt variants like "T膩maki")
            folded = _ascii_fold(s)
            hit = macron_suburb_map.get(folded) or next(
                (v for k, v in macron_suburb_map.items() if _ascii_fold(k).lower() == folded.lower()),
                None
            )
        if hit:
            return hit  # return canonical (with macrons if that’s your canonical)

    # 3) Fallback: clean ASCII title-case (keeps old function’s contract)
    fallback = _ascii_fold(s).title()

    # Pin common Tāmaki variants to a single ASCII fallback if still unknown
    tamaki_variants = {
        "East Tamaki", "East Tmaki", "East Tamki", "Tamki", "Tmaki",
        "East Tamaki Heights", "East Tamaki South", "Tamaki"
    }
    if fallback in tamaki_variants:
        return "East Tamaki"

    return fallback

# ---- Pre-3.4 standardisation helpers ----
import re
from collections import Counter, defaultdict

def _norm_base_key(street: str):
    """
    Turn any street string into a clustering key:
      - fix suffix typos, Title Case
      - drop suffix -> base
      - collapse spaces in base, lower-case for key
    Returns: (display_base, cluster_key)
    """
    st = correct_suffix_typos((street or "").strip()).title()
    base, _ = _split_base_suffix(st)
    base_disp = re.sub(r"\s+", " ", base).strip()
    key = re.sub(r"\s+", "", base_disp).lower()
    return base_disp, key

def _pick_canonical_suburb(suburb_counts: Counter, majority_suburb: str) -> str:
    """
    Choose one suburb for the cluster:
      1) highest frequency
      2) if tie, prefer exact majority_suburb
      3) else prefer any that's 'nearby' to majority
      4) else alphabetical
    """
    if not suburb_counts:
        return ""
    items = suburb_counts.most_common()
    top_count = items[0][1]
    tops = [s for s, c in items if c == top_count]
    ms = canon_suburb(majority_suburb)

    # exact majority?
    for s in tops:
        if canon_suburb(s) == ms:
            return s
    # nearby majority?
    nearby = NEARBY_SUBURBS.get(ms, set())
    for s in tops:
        if canon_suburb(s) in {canon_suburb(x) for x in nearby}:
            return s
    # deterministic fallback
    return sorted(tops)[0]

def _pick_canonical_suffix_for_base(base: str, candidate_suburb: str, sample_rows, probe_row):
    """
    Decide one suffix for a base using safe sources (no guessing):
      1) prior outputs (CANON_SUFFIX_BY_BASE)
      2) sample_rows in current CSV (same base)
      3) LINZ (prefer same-suburb if unambiguous; else unique overall)
      4) external echo via get_lat_long parsing (single probe)
    Returns "" if none can be established.
    """
    # 1) prior cleans
    with _canon_lock:
        cnt = CANON_SUFFIX_BY_BASE.get(base)
    if cnt:
        return cnt.most_common(1)[0][0]

    # 2) current CSV sample (we pass only rows in this cluster)
    sfx = _choose_from_all_rows(base, sample_rows) if sample_rows else ""
    if sfx:
        return sfx

    # 3) LINZ
    sfx = _choose_from_linz(base, candidate_suburb)
    if sfx:
        return sfx

    # 4) external echo (use one row as probe)
    if probe_row:
        sfx = _choose_from_external(
            number=probe_row.get("Number", ""),
            base=base,
            suburb=candidate_suburb or (probe_row.get("Suburb") or "")
        )
        if sfx:
            return sfx

    return ""

# --- NEW: Full-name/base protections and anti-alias pairs ---
# Keep near your existing "Protected Streets & Helpers" section.
PROTECTED_FULL_STREETS = {
    'Treeway', 'The Crest',         # from earlier
    'Eaglen Place', 'Eaglemont Drive',
    'Castlebane Drive', 'Castlemaine Close',
}

PROTECTED_BASES = {
    'Eaglen', 'Eaglemont',
    'Castlebane', 'Castlemaine',
}

DO_NOT_ALIAS_BASES = {
    tuple(sorted(['Eaglen', 'Eaglemont'])),
    tuple(sorted(['Castlebane', 'Castlemaine'])),
}




def _harden_alias_map(alias_map, base_counts):
    """
    Tighten the base-alias map produced by _unify_similar_bases_fast:
      • Never alias if either side is protected (PROTECTED_BASES).
      • Never alias if the (base, canonical) pair is in DO_NOT_ALIAS_BASES.
      • If both names appear 2+ times, require >0.92 similarity AND length delta < 2.
    """
    import difflib

    def _pair(a, b):
        return tuple(sorted([(a or '').strip().title(), (b or '').strip().title()]))

    blocked = 0
    hardened = {}
    anti_pairs = {tuple(sorted(p)) for p in DO_NOT_ALIAS_BASES}

    for base, canonical in (alias_map or {}).items():
        b = (base or '').strip().title()
        c = (canonical or '').strip().title()

        # 1) respect protection lists
        if b in PROTECTED_BASES or c in PROTECTED_BASES:
            hardened[b] = b
            blocked += 1
            try:
                log_correction("Street Alias Blocked", f"{b} → {c} (protected base)")
            except Exception:
                pass
            continue

        # 2) explicit anti-alias pairs
        if _pair(b, c) in anti_pairs:
            hardened[b] = b
            blocked += 1
            try:
                log_correction("Street Alias Blocked", f"{b} → {c} (explicit anti-pair)")
            except Exception:
                pass
            continue

        # 3) when both are present with some support, be very strict
        if base_counts.get(b, 0) >= 2 and base_counts.get(c, 0) >= 2:
            ratio = difflib.SequenceMatcher(None, b, c).ratio()
            if ratio <= 0.92 or abs(len(b) - len(c)) >= 2:
                hardened[b] = b
                blocked += 1
                try:
                    log_correction("Street Alias Blocked", f"{b} → {c} (low similarity/length delta)")
                except Exception:
                    pass
                continue

        hardened[b] = c

    if blocked:
        try:
            log_correction("Alias Guard", f"Blocked {blocked} risky base merge(s)")
        except Exception:
            pass
    return hardened

# ---- Stage 3.4: Standardize similar streets (faster) ----
def standardize_similar_streets(all_rows, majority_suburb, verbose=False):
    """
    Standardise similar streets BEFORE batch geocoding:
      • one street spelling/suffix per base
      • one suburb per base (chosen via frequency / tie)
      • one postcode per base (majority non-blank else lookup)
    Hardened to avoid merging distinct streets like 'Eaglen' vs 'Eaglemont'.
    """
    from collections import Counter, defaultdict
    from tqdm import tqdm as _tqdm

    # Collect bases with progress bar
    bases = []
    for r in _tqdm(all_rows, total=len(all_rows),
                   desc="🔄 Stage 2: Standardizing Streets...", unit="row"):
        st = (r.get("Street") or "").strip()
        if not st:
            continue
        base_disp, _ = _norm_base_key(st)
        bases.append(base_disp)

    base_counts = Counter(bases)

    # unify at ~80% (existing fast routine), then harden
    alias_map = _unify_similar_bases_fast(bases, base_counts)
    alias_map = _harden_alias_map(alias_map, base_counts)  # << NEW guard layer

    # build clusters (respect protections)
    clusters = defaultdict(list)
    for idx, r in enumerate(all_rows):
        st = (r.get("Street") or "").strip()
        if not st:
            continue
        base_disp, _ = _norm_base_key(st)
        full_street_title = st.title()

        if (full_street_title in PROTECTED_FULL_STREETS) or (base_disp in PROTECTED_BASES):
            can_base = base_disp
        else:
            can_base = alias_map.get(base_disp, base_disp)

        clusters[can_base].append(idx)

    changed = 0

    for canonical_base, idxs in clusters.items():
        # compute counts within cluster
        suburb_counts = Counter(
            (all_rows[i].get("Suburb") or "").strip().title() for i in idxs if (all_rows[i].get("Suburb") or "").strip()
        )
        postcode_counts = Counter(
            (all_rows[i].get("PostalCode") or "").strip() for i in idxs if (all_rows[i].get("PostalCode") or "").strip()
        )
        canonical_suburb = _pick_canonical_suburb(suburb_counts, majority_suburb) if suburb_counts else ""

        # decide suffix using prior -> csv -> LINZ -> external (single probe)
        sample_rows = [all_rows[i] for i in idxs]
        probe_row = sample_rows[0] if sample_rows else None
        sfx = _pick_canonical_suffix_for_base(canonical_base, canonical_suburb, sample_rows, probe_row)

        canonical_street = f"{canonical_base} {sfx}".strip() if sfx else canonical_base
        canonical_postal = ""
        if canonical_suburb:
            canonical_postal = nz_postal_lookup.get(canonical_suburb, "") or ""
        if not canonical_postal and postcode_counts:
            canonical_postal = postcode_counts.most_common(1)[0][0]  # fallback only

        # apply
        for i in idxs:
            row = all_rows[i]
            row_id = row.get("__RowID", i + 2)

            cur_st = (row.get("Street") or "").strip().title()
            cur_sb = (row.get("Suburb") or "").strip().title()
            cur_pc = (row.get("PostalCode") or "").strip()

            # Do not overwrite a protected full name
            if cur_st in PROTECTED_FULL_STREETS:
                new_st = cur_st
            else:
                new_st = (canonical_street or cur_st).strip()

            new_sb = (canonical_suburb or cur_sb).strip()
            new_pc = cur_pc or canonical_postal or (nz_postal_lookup.get(new_sb, "") if new_sb else "")

            if new_st and cur_st != new_st:
                _log_quiet("Standardise: Street", f"{cur_st} → {new_st}", street=new_st, important=False)
                row["Street"] = new_st
                changed += 1

            eff_st = (row.get("Street") or new_st or cur_st).strip().title()

            if new_sb and cur_sb != new_sb:
                _log_quiet("Standardise: Suburb", f"{cur_sb} → {new_sb}", street=eff_st, important=False)
                row["Suburb"] = new_sb
                changed += 1

            final_pc = canonical_postal or new_pc or cur_pc
            if final_pc and final_pc != cur_pc:
                _log_quiet("Standardise: PostalCode", f"{cur_pc} → {final_pc}", street=eff_st, important=False)
                row["PostalCode"] = final_pc
                changed += 1

    return all_rows, changed

def correct_suffix_typos(street_name: str) -> str:
    # Unified typo map – this is the only definition used
    typo_map = {
        "Hght": "Heights", "Hghts": "Heights", "Hts": "Heights",
        "Cresent": "Crescent", "Cresent.": "Crescent",
        "Rd.": "Road", "St.": "Street"
    }
    parts = street_name.split()
    if parts:
        last = parts[-1].title()
        if last in typo_map:
            parts[-1] = typo_map[last]
    return " ".join(parts)


DEBUG_LOG = "debug_log.txt"
valid_suburbs_data = sorted(list(set(nz_postal_lookup.keys()) | {"Howick"}))






# ---------- FINAL NORMALISATION HELPERS ----------
def _to_str_safe(v):
    """Return a safe string for any incoming value (int/float/None/etc.)."""
    import math
    if v is None:
        return ""
    if isinstance(v, float):
        if math.isnan(v):
            return ""
        if v.is_integer():
            return str(int(v))
        return str(v)
    return str(v)

def ensure_row_text_types(row: dict) -> dict:
    """Coerce all fields (except free-form text) to strings (idempotent)."""
    for k, v in list(row.items()):
        if k in PRESERVE_FREEFORM_FIELDS:
            continue  # keep Notes/NotesFromPublisher verbatim
        row[k] = _to_str_safe(v)
    return row


def expand_street_suffix_once(street: str) -> str:
    """Expand a trailing suffix abbreviation (Dr, Rd, Ave...) once, if present."""
    if not street:
        return street
    parts = (street or "").strip().split()
    if not parts:
        return street
    last = parts[-1].title()
    if last in street_suffix_map:
        parts[-1] = street_suffix_map[last]
    return " ".join(parts)

def remove_embedded_suburb_from_street(street: str, suburb: str, valid_suburbs_iterable) -> str:
    """
    If the street accidentally contains a suburb token (e.g., 'Kaimanawa Road Karaka'),
    remove it. Works for any known suburb name (case-insensitive).
    """
    s = (street or "").strip()
    if not s:
        return s
    # Build a set of candidate suburb tokens (lower-cased, incl. current suburb)
    cand = { (suburb or "").strip().lower() }
    cand |= { (x or "").strip().lower() for x in valid_suburbs_iterable or [] }
    # Remove any trailing suburb token
    parts = s.split(",")[-1].strip().split()
    # Pop tokens off the end while they exactly match a known suburb word or the full suburb
    while parts:
        tail = " ".join(parts[-1:]).lower()
        full = " ".join(parts).lower()
        if full in cand:
            parts = []  # whole thing was a suburb; drop entirely (unlikely)
            break
        if tail in cand:
            parts = parts[:-1]
        else:
            break
    cleaned = " ".join(parts).strip()
    # If we removed everything by accident, fall back to original
    cleaned = cleaned or s
    return cleaned

def final_normalize_rows(all_rows, valid_suburbs_list, enforce_title=True):
    changed = 0
    for r in all_rows:
        ensure_row_text_types(r)

        # --- NEW: normalise Number like Unit364/2 → Unit2/364
        num_orig = (r.get("Number") or "").strip()
        num_fix  = normalize_unit_house_number(num_orig)
        if num_fix != num_orig:
            r["Number"] = num_fix
            _log_quiet("Final normalise: Number", f"{num_orig} → {num_fix}",
                       street=(r.get("Street") or ""), important=False)
            changed += 1

        st_orig = (r.get("Street") or "").strip()
        sb = (r.get("Suburb") or "").strip()


        # 1) Remove suburb tokens the old way (exact match)
        st1 = remove_embedded_suburb_from_street(st_orig, sb, valid_suburbs_list)

        # 1b) NEW: extra catch-all to strip suburb after any valid suffix
        st1b = clean_street_suffix_and_suburb(st1)

        # 2) Expand suffix once
        st2 = expand_street_suffix_once(st1b)

        # 3) Basic typo fixers
        st3 = correct_suffix_typos(st2)

        # 4) Title-case
        if enforce_title:
            st3 = " ".join(st3.split()).title()

        if st3 and st3 != st_orig:
            r["Street"] = st3
            _log_quiet(
                "Final normalise: Street",
                f"{st_orig} → {st3}",
                street=st3,
                important=False
            )
            changed += 1

        # Make sure Suburb is normalised (macrons + title)
        if sb:
            sb_new = macron_suburb_map.get(sb.title(), sb.title())
            if sb_new != sb:
                r["Suburb"] = sb_new
                _log_quiet(
                    "Final normalise: Suburb",
                    f"{sb} → {sb_new}",
                    street=st3 or st_orig,
                    important=False
                )
                changed += 1

    return all_rows, changed

def canonical_addr_key_for_dedupe(row):
    # number → normalize and canonicalize “Unit” formats
    num = normalize_unit_house_number((row.get("Number") or "").strip())
    num = flip_unit_prefix_in_number(num).strip()

    # street → Title Case final form
    st = (row.get("Street") or "").strip().title()

    # suburb → canonicalize (macrons); treat literal "Auckland" as blank
    sb_raw = (row.get("Suburb") or "").strip().title()
    sb = macron_suburb_map.get(sb_raw, sb_raw)
    if sb.lower() == "auckland":
        sb = ""

    # NEW: apartment number in the key
    apt = _norm_apartment_number(row.get("ApartmentNumber") or "")

    # Now duplicates require SAME Number, Street, Suburb AND ApartmentNumber
    return f"{num}|{st}|{sb}|{apt}"


def assign_duplicates_globally(clean_rows, fail_rows):
    """
    Decide 'Duplicate' at the very end:
      • Keep the first Clean occurrence for each canonical address.
      • Move later duplicates to Fail with Final Status='Duplicate'.
      • Prefer keeping the row that has coords (if one has coords and the other doesn't).
    """
    new_clean = []
    new_fail = list(fail_rows)
    pos_by_key = {}  # key -> index in new_clean

    def _has_coords(r):
        la = safe_float(r.get("Latitude"), None)
        lo = safe_float(r.get("Longitude"), None)
        return (la is not None and lo is not None)

    for r in clean_rows:
        key = canonical_addr_key_for_dedupe(r)

        # Empty key? Just keep it in Clean; not dedupable.
        if key == "||":
            new_clean.append(r)
            continue

        if key not in pos_by_key:
            pos_by_key[key] = len(new_clean)
            new_clean.append(r)
        else:
            keep_idx = pos_by_key[key]
            keep_row = new_clean[keep_idx]
            cur_has = _has_coords(r)
            keep_has = _has_coords(keep_row)

            if cur_has and not keep_has:
                # Swap: keep the one with coords in Clean; demote previous to Fail/Duplicate
                keep_row["Final Status"] = "Duplicate"
                new_fail.append(keep_row)
                new_clean[keep_idx] = r  # current becomes the kept one
                log_correction("Global Dedupe", f"Chose row with coords for key '{key}'", street=r.get("Street"))
            else:
                # Current is the duplicate → demote to Fail/Duplicate
                r["Final Status"] = "Duplicate"
                new_fail.append(r)

    if len(new_clean) != len(clean_rows):
        moved = len(clean_rows) - len(new_clean)
        log_correction("Global Dedupe Summary", f"Moved {moved} duplicate row(s) to Fail")

    return new_clean, new_fail

def enforce_real_duplicates(clean_rows, fail_rows):
    """
    Keep 'Duplicate' status in FAIL only if the exact canonical address
    also exists in CLEAN. Otherwise, promote it to Clean.
    """
    clean_keys = {canonical_addr_key_for_dedupe(r) for r in clean_rows}

    new_fail = []
    promoted = 0
    for r in fail_rows:
        fs = (r.get("Final Status") or "").strip().lower()
        if fs == "duplicate":
            key = canonical_addr_key_for_dedupe(r)
            if key not in clean_keys:
                # Not a real duplicate → should be clean
                r["Final Status"] = ""
                clean_rows.append(r)
                promoted += 1
            else:
                new_fail.append(r)
        else:
            new_fail.append(r)

    if promoted:
        log_correction("Real Duplicate Enforcer",
                       f"Promoted {promoted} 'Duplicate' row(s) to Clean (no Clean counterpart).")
    return clean_rows, new_fail

# ---------- MANUAL OVERRIDES ----------
# Address key is (Number, Street, Suburb) AFTER normalisation
MANUAL_FINAL_STATUS_OVERRIDES = {
    ("2", "Pahekeheke Road", "Karaka"): {"Final Status": "Not Chinese"}
}

def apply_manual_overrides(rows):
    """
    Apply explicit per-address corrections (e.g., mark Not Chinese).
    Run this AFTER your core cleaning & geocoding, but BEFORE writing files.
    """
    applied = 0
    for r in rows:
        ensure_row_text_types(r)
        key = (
            (r.get("Number") or "").strip(),
            (r.get("Street") or "").strip().title(),
            (r.get("Suburb") or "").strip().title(),
        )
        if key in MANUAL_FINAL_STATUS_OVERRIDES:
            for k, v in MANUAL_FINAL_STATUS_OVERRIDES[key].items():
                old = (r.get(k) or "").strip()
                r[k] = v
                if k.lower() == "final status":
                    _log_quiet("Manual Override", f"{old or '<blank>'} → {v}", street=key[1], important=True)
            applied += 1
    if applied:
        log_correction("Manual Overrides", f"Applied {applied} manual override(s)")
    return rows




# --- Keep validation unchanged ---

def is_valid_nz_number(number: str) -> bool:
    # Explicit Unit format: UnitX/Number (with optional -range)
    unit_pattern = re.compile(r'^Unit[A-Z0-9]+/[0-9]+(?:-[0-9]+)?$', re.IGNORECASE)
    house_pattern = re.compile(r'^[0-9]+[A-Za-z]?(-[0-9]+[A-Za-z]?)?$')
    num = number.strip().replace(' ', '')
    return bool(unit_pattern.fullmatch(num) or house_pattern.fullmatch(num))





def contains_invalid_chars(value):
    """
    Return True if `value` contains any character outside the allowed set.

    Allowed:
      • ASCII letters/digits
      • Whitespace (\\s)
      • Comma, apostrophe, hyphen, forward slash
      • Māori macron letters: ā Ā ē Ē ī Ī ō Ō ū Ū
      • (Also permits the combining macron U+0304 when present)

    Notes:
      • Treats other non-ASCII characters (emoji, smart quotes, NBSP, etc.) as invalid.
      • Normalizes to NFC and inspects NFD to allow the combining macron specifically.
    """
    import re
    import unicodedata

    macron_chars = "āĀēĒīĪōŌūŪ"
    s = "" if value is None else str(value)

    # Fast path for ASCII-only strings: just regex-check the allowed ASCII set.
    if s.isascii():
        pattern = rf"[^A-Za-z0-9\s,'\-\/{macron_chars}]"
        return bool(re.search(pattern, s))

    # Normalize to NFC for stable composed characters.
    s_nfc = unicodedata.normalize("NFC", s)
    # Also examine NFD to allow the *combining macron* explicitly.
    s_nfd = unicodedata.normalize("NFD", s_nfc)

    # Reject any non-ASCII char that is neither a macron letter nor the combining macron.
    COMBINING_MACRON = "\u0304"
    for ch in s_nfd:
        if ch.isascii():
            continue
        # Allow precomposed macron letters (present in NFC)
        if ch in macron_chars:
            continue
        # Allow the combining macron mark in NFD
        if ch == COMBINING_MACRON:
            continue
        # Any other non-ASCII character is invalid
        return True

    # Finally, ensure no disallowed ASCII punctuation is present.
    pattern = rf"[^A-Za-z0-9\s,'\-\/{macron_chars}]"
    return bool(re.search(pattern, s_nfc))


# ---------- Flip "UnitX/<house>" → "<house>/UnitX" for outputs ----------

_UNIT_PREFIX_RE = re.compile(
    r'^\s*Unit\s*([A-Za-z0-9]+)\s*/\s*([0-9]+[A-Za-z]?(?:\s*-\s*[0-9]+[A-Za-z]?)?)\s*$',
    re.IGNORECASE
)

def flip_unit_prefix_in_number(number: str) -> str:
    """
    If number looks like 'Unit<token>/<house>' (e.g. 'Unit3/219', 'UnitA/2', 'Unit5A/12-14'),
    return '<house>/Unit<token>' (e.g. '219/Unit3'). Otherwise return the original.
    """
    s = (number or "").strip()
    m = _UNIT_PREFIX_RE.match(s)
    if not m:
        return number
    unit_token = m.group(1).upper()          # normalize token letters to uppercase (A, 5A, etc.)
    house = re.sub(r'\s*-\s*', '-', m.group(2))  # tidy any spaces around range dashes
    return f"{house}/Unit{unit_token}"

def flip_units_for_rows(rows) -> int:
    """
    In-place pass over rows to flip Unit-prefixed numbers for output.
    Returns the count of flips applied.
    """
    flips = 0
    for r in rows or []:
        old = (r.get("Number") or "").strip()
        new = flip_unit_prefix_in_number(old)
        if new != old and new:
            r["Number"] = new
            try:
                _log_quiet("Flip Unit", f"{old} → {new}", street=(r.get("Street") or ""), important=False)
            except Exception:
                pass
            flips += 1
    return flips




# --- Fast Street Fuzzy Matching (prefix-indexed) ---
def build_street_index(street_list):
    idx = defaultdict(list)
    for s in street_list:
        idx[s[:3].lower()].append(s)
    return idx

def fast_find_similar_street(street, index, threshold=60):
    if not street:
        return None
    key = street[:3].lower()
    candidates = index.get(key, [])
    if not candidates:
        return None
    if _HAS_RF:
        hit = rf_process.extractOne(street, candidates, score_cutoff=threshold)
        return hit[0] if hit else None
    else:
        # difflib fallback
        import difflib
        match = max(candidates, key=lambda c: difflib.SequenceMatcher(None, street, c).ratio(), default=None)
        score = int(difflib.SequenceMatcher(None, street, match).ratio() * 100) if match else 0
        return match if score >= threshold else None




from collections import Counter



# Replace fuzzywuzzy calls with fast_find_similar_street

def resolve_bad_address(number, street_val, suburb_val, all_rows, all_streets, street_index=None, geocode_result=None):
    """
    Fixes broken addresses. Always returns a street if possible.
    Deduplicates geocoding by accepting pre-fetched `geocode_result`.

    Hardened rules:
      • Fuzzy: threshold=88 and first 5 chars must match.
      • NEVER remap when the input street is protected:
          - Full-name in PROTECTED_FULL_STREETS → keep exact.
          - Base in PROTECTED_BASES → don't switch to a different base.
    """
    from collections import Counter

    number     = (number or "").strip()
    street_val = (street_val or "").strip().title()
    suburb_val = (suburb_val or "").strip().title()
    if "auckland" in suburb_val.lower():
        suburb_val = ""

    # Protection flags for the *input* street
    obase_disp, _ = _norm_base_key(street_val)
    prot_full = street_val in PROTECTED_FULL_STREETS
    prot_base = obase_disp in PROTECTED_BASES

    # Use pre-fetched geocode result (from process_csv), but do NOT cross protected boundaries
    if geocode_result:
        addr, lat, lon, postal = geocode_result
        if addr:
            parts    = [p.strip() for p in addr.split(",")]
            g_street = parts[0].title() if parts else ""
            g_suburb = parts[1].title() if len(parts) > 1 else suburb_val

            # Do not adopt a different street if protected
            if prot_full and g_street and g_street != street_val:
                return street_val, g_suburb
            if prot_base and g_street:
                gbase_disp, _ = _norm_base_key(g_street)
                if gbase_disp != obase_disp:
                    return street_val, g_suburb

            return (g_street or street_val), g_suburb

    # Guess suburb if invalid
    all_suburbs = [ (r.get('Suburb') or '').strip().title() for r in all_rows if r.get('Suburb') ]
    guessed_suburb = None
    if not suburb_val or suburb_val.lower() not in [s.lower() for s in all_suburbs]:
        guessed_suburb = Counter(all_suburbs).most_common(1)[0][0] if all_suburbs else ""

    # Fast fuzzy street matching (STRICT) — skip entirely if street is protected
    if street_index and not (prot_full or prot_base):
        fast_match = fast_find_similar_street(street_val, street_index, threshold=88)
        if fast_match and street_val[:5].lower() == fast_match[:5].lower():
            street_val = fast_match

    # Final fallback geocode (only if no pre-fetched result) — respect protections when adopting label
    if not geocode_result or not geocode_result[0]:
        query_suburb = guessed_suburb or suburb_val or "Auckland"
        addr, lat, lon, postal = get_lat_long(f"{number} {street_val}, {query_suburb}")
        if addr:
            parts    = [p.strip() for p in addr.split(",")]
            g_street = parts[0].title() if parts else ""
            g_suburb = parts[1].title() if len(parts) > 1 else query_suburb

            if prot_full and g_street and g_street != street_val:
                return street_val, g_suburb
            if prot_base and g_street:
                gbase_disp, _ = _norm_base_key(g_street)
                if gbase_disp != obase_disp:
                    return street_val, g_suburb

            return (g_street or street_val), g_suburb

    # Always return a street even if suburb can't be resolved
    if street_val:
        return street_val, guessed_suburb or suburb_val or ""

    return "Fail", "Fail"

# ---- Auckland coord guards (drop-in) ----
def _in_akl_bbox(lat: float, lon: float) -> bool:
    """
    Simple rectangular gate for Auckland region.
    Good for cleaning; keep tight to avoid false positives.
    """
    return (-37.30 <= lat <= -36.20) and (174.30 <= lon <= 175.60)

def _maybe_swap_latlon(lat, lon):
    try:
        la = float(lat); lo = float(lon)
    except Exception:
        return lat, lon

    # existing quick rules
    if abs(la) > 90 and abs(lo) <= 90:
        return lo, la
    if 170.0 <= abs(la) <= 180.0 and (-47.0 <= lo <= -34.0):
        return lo, la

    # ✅ new: if swapping places the point inside Auckland, do it
    if is_in_auckland(lo, la) and not is_in_auckland(la, lo):
        return lo, la

    return la, lo


from concurrent.futures import ThreadPoolExecutor, as_completed

def prune_auckland_coords_inplace(row, row_id_fallback=None):
    """
    Remove invalid or out-of-Auckland coordinates from a row.
    Unlike before, this version no longer marks __NeedsRegeo.
    """
    lat = row.get("Latitude")
    lon = row.get("Longitude")

    if not lat or not lon:
        return  # Already blank, nothing to prune

    try:
        lat = float(lat)
        lon = float(lon)
    except Exception:
        # Bad numeric format → clear only
        row["Latitude"] = ""
        row["Longitude"] = ""
        log_correction(
            "Coord Prune",
            f"Non-numeric coords cleared (row {row_id_fallback})",
            street=row.get("Street"),
        )
        return

    if not is_in_auckland(lat, lon):
        row["Latitude"] = ""
        row["Longitude"] = ""
        log_correction(
            "Coord Prune",
            f"Outside Auckland — cleared (row {row_id_fallback})",
            street=row.get("Street"),
        )



def _retry_geocode(row, all_rows=None):
    """Worker function to retry geocoding a single row (tuple/dict-safe result handling)."""
    if all_rows is None:
        all_rows = []

    number = row.get("Number") or row.get("HouseNumber") or ""
    street = row.get("Street") or ""
    suburb = row.get("Suburb") or ""
    addr = f"{number} {street}, {suburb}, Auckland".strip(", ")

    try:
        result = targeted_geocode_retry(row, all_rows, known_geocodes_by_street=None)

        # Support tuple (addr, lat, lon, postal) or dict {'lat':..., 'lon':...}
        lat = lon = None
        if isinstance(result, tuple) and len(result) == 4:
            _addr_lbl, lat, lon, _pc = result
        elif isinstance(result, dict):
            lat, lon = result.get("lat"), result.get("lon")

        if lat is not None and lon is not None:
            if is_in_auckland(float(lat), float(lon)):
                row["Latitude"] = str(lat)
                row["Longitude"] = str(lon)
                row["__NeedsRegeo"] = False
                return ("recovered", f"{addr} → {lat},{lon}")
            else:
                return ("skip", f"{addr} → outside Auckland {lat},{lon}")
        else:
            return ("fail", f"{addr} → no result")
    except Exception as e:
        return ("error", f"{addr} → {e}")



def try_geocoders_with_variants(number, street, suburb):
    """
    Backward compatibility shim for _retry_geocode.
    Just calls targeted_geocode_retry() with a fake row.
    """
    row = {"Number": number, "Street": street, "Suburb": suburb}
    return targeted_geocode_retry(row, all_rows=[], known_geocodes_by_street=None)





def _street_stats(rows):
    """
    Return stats for a list of rows:
      - Number of streets with all coords blank
      - Number of streets with any coords outside Auckland
      - Total number of unique streets
    """
    from collections import defaultdict

    # Group rows by street
    street_buckets = defaultdict(list)
    for r in rows:
        st = (r.get("Street") or "").strip().title()
        if not st:
            continue
        street_buckets[st].append(r)

    blank_count = 0
    oob_count = 0

    for st, bucket in street_buckets.items():
        coords = []
        for r in bucket:
            la = safe_float(r.get("Latitude"), None)
            lo = safe_float(r.get("Longitude"), None)
            if la is not None and lo is not None:
                coords.append((la, lo))

        if not coords:
            blank_count += 1
        else:
            if any(not is_in_auckland(la, lo) for la, lo in coords):
                oob_count += 1

    return blank_count, oob_count, len(street_buckets)



# --- Suburb validation & auto-fill ---


def resolve_suburb(street_val, suburb_val, all_rows, all_streets, number_val: str = ""):
    """
    Resolve a correct suburb for a given street/suburb combo.

    Improvements:
      • Uses a house number when geocoding (falls back to most-common number for that street in CSV).
      • Adopts the suburb returned by geocoders when available (canonized), not just in CSV-retry paths.
      • Keeps 'Howick' whitelisted.
      • Treats 'Auckland' as blank/unknown and normalizes macrons/variants via macron_suburb_map.
    """
    from collections import Counter
    import re

    def _norm(s): return (s or "").strip()
    def _low(s):  return _norm(s).lower()

    # Quick allow-list
    cand = _low(suburb_val)
    if "howick" in cand:
        return "Howick"

    valid_set_low = {s.lower() for s in valid_suburbs_data}
    is_valid = (cand and cand != "auckland" and cand in valid_set_low)
    if is_valid:
        # Normalize macrons/title-case
        sv = _norm(suburb_val).title()
        if "howick" in sv.lower():
            return "Howick"
        return macron_suburb_map.get(sv, sv)

    # ------ CSV heuristics first ------
    street_l = _low(street_val)

    # (1) Exact same street → most-common suburb
    exact_matches = [ _norm(r.get('Suburb','')) for r in all_rows
                      if _low(r.get('Street','')) == street_l and _norm(r.get('Suburb','')) ]
    if exact_matches:
        top = Counter(exact_matches).most_common(1)[0][0]
        if "howick" in _low(top): return "Howick"
        return macron_suburb_map.get(_norm(top).title(), _norm(top).title())

    # (1.5) Partial street match → most-common suburb
    partial_matches = [ _norm(r.get('Suburb','')) for r in all_rows
                        if street_l in _low(r.get('Street','')) and _norm(r.get('Suburb','')) ]
    if partial_matches:
        top = Counter(partial_matches).most_common(1)[0][0]
        if "howick" in _low(top): return "Howick"
        return macron_suburb_map.get(_norm(top).title(), _norm(top).title())

    # ------ Geocode with a HOUSE NUMBER ------
    # Prefer provided number; else borrow most-common number used with this street in CSV.
    digits = re.sub(r"\D", "", _norm(number_val))
    if not digits:
        nums = [ re.sub(r"\D","", _norm(r.get('Number',''))) for r in all_rows
                 if _low(r.get('Street','')) == street_l and _norm(r.get('Number','')) ]
        nums = [n for n in nums if n]
        if nums:
            digits = Counter(nums).most_common(1)[0][0]

    # Build a numbered candidate; fall back to Auckland when suburb is blank/invalid.
    suburb_for_query = _norm(suburb_val) if _norm(suburb_val) else "Auckland"
    addr_query = fmt_addr_parts(digits, _norm(street_val).title(), suburb_for_query)

    try:
        addr, lat, lon, _pc = get_lat_long(addr_query)
    except Exception:
        addr = None

    if addr:
        # Prefer the suburb from the geocoder label
        parts = [p.strip() for p in addr.split(",")]
        g_suburb = parts[1] if len(parts) > 1 else suburb_val
        if g_suburb:
            if "howick" in g_suburb.lower():
                return "Howick"
            # Canonize geocoded suburb (handles macrons/variants)
            g_final = macron_suburb_map.get(_norm(g_suburb).title(), _norm(g_suburb).title())
            return g_final

    # ------ Fuzzy street-based guess (as last hints before global mode) ------
    if all_streets:
        match = safe_fuzzy_match(_norm(street_val), list(all_streets), threshold=20)
        if match:
            guess_suburbs = [ _norm(r.get('Suburb','')) for r in all_rows
                              if _low(r.get('Street','')) == _low(match) and _norm(r.get('Suburb','')) ]
            if guess_suburbs:
                best = Counter(guess_suburbs).most_common(1)[0][0]
                if "howick" in _low(best): return "Howick"
                return macron_suburb_map.get(_norm(best).title(), _norm(best).title())

    # ------ Global most-common suburb in the CSV ------
    all_suburbs = [ _norm(r.get('Suburb','')) for r in all_rows if _norm(r.get('Suburb','')) ]
    if all_suburbs:
        top = Counter(all_suburbs).most_common(1)[0][0]
        if "howick" in _low(top): return "Howick"
        return macron_suburb_map.get(_norm(top).title(), _norm(top).title())

    # Nothing better
    return ""



def is_blank_or_zero(val):
    s = str(val).strip()
    if not s or s in {"0", "O", "None"}:
        return True
    try:
        return float(s) == 0.0
    except ValueError:
        return False


def build_dominant_suburb_map_from_verified(rows, threshold=0.7):
    from collections import defaultdict, Counter
    street_suburb_counter = defaultdict(Counter)
    for row in rows:
        street = row.get("Street","").strip()
        suburb = row.get("Suburb","").strip()
        status = row.get("Final Status","").strip()
        if street and suburb and status == "Pass":
            street_suburb_counter[street][suburb] += 1
    dominant_map = {}
    for street, counter in street_suburb_counter.items():
        total = sum(counter.values())
        if total:
            top_suburb, top_count = counter.most_common(1)[0]
            if (top_count / total) >= threshold:
                dominant_map[street] = top_suburb
    return dominant_map



def build_global_dominant_suburb_map(rows, threshold=0.6):
    from collections import defaultdict, Counter

    street_suburb_counts = defaultdict(Counter)
    for row in rows:
        street = row.get("Street", "").strip()
        suburb = row.get("Suburb", "").strip()
        if street and suburb:
            street_suburb_counts[street][suburb] += 1

    dominant_map = {}
    for street, counter in street_suburb_counts.items():
        total = sum(counter.values())
        top_suburb, count = counter.most_common(1)[0]
        if total > 0 and (count / total) >= threshold:
            dominant_map[street] = top_suburb.strip().title()
    return dominant_map

# ---------- Known text glitch fixes ----------
import re, unicodedata

_EAST_TAMAKI_RX = re.compile(r'(?i)\bEast\s+T(?:膩|ā)maki\s+Heights\b')

def fix_known_text_glitches(s: str) -> str:
    if not s:
        return s
    # Exactly: East T膩maki Heights / East Tāmaki Heights → East Tamaki Heights
    s2 = _EAST_TAMAKI_RX.sub("East Tamaki Heights", s)
    return s2

# ---------- Notes sanitization Patch ----------

import re, unicodedata

_MONTHS_RX = r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*'
_DATE_RX = re.compile(
    rf'\b(?:\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}}|\d{{4}}-\d{{1,2}}-\d{{1,2}}|{_MONTHS_RX}\s+\d{{1,2}}(?:,\s*\d{{2,4}})?)\b',
    re.IGNORECASE
)

# phrases to delete (case-insensitive, keeps other text)
_NOTE_DROP_PATTERNS = [
    # check/confirm boilerplate
    r'pl[sz]\.?\s*check', r'pl[sz]\.?\s*confirm(?:\s*again)?', r'please\s*check', r'please\s*confirm(?:\s*again)?',
    r'check\s*if\s*chinese', r'pl[sz]\s*check\s*if\s*chinese', r'please\s*check\s*if\s*chinese', r'\bif\s*chinese\b(?:\s*[?.!])?',

    # sources / provenance
    r'found\s+in\s+white[\s\-]*pages?', r'white[\s\-]*pages?',  # "white-pages", "whitepages"
    r'passed\s+on\s+from\s+english', r'\bfrom\s+english\b',

    # letter/tract boilerplate
    r'will\s+need\s+to\s+post\s+a?\s+letter\s+(?:to\s+address)?',
    r'posted\s+a?\s+letter', r'left\s+a?\s+letter',
    r'left\s*tract',

    # door/bell boilerplate
    r'no\s*intercom\s*or\s*bell', r'no\s*(?:door)?\s*bell',

    # misc boilerplate
    r'\binitial\s*call\b', r'\bdone\b', r'\bavailable\b', r'\bnew\b',
    r'\bno\s+access\s+to\s+house\.?\b',   # drop completely
    r'\bPLO\b',                           # drop completely
    r'\benglish\b',                       # per spec: delete 'English'
    r'\bbring\s+letter(?:\s+for\s+second\s+call)?\b', r'\bsecond\s+call\b',
]
_NOTE_DROP_RES = [re.compile(p, re.IGNORECASE) for p in _NOTE_DROP_PATTERNS]

# --- extra phrases to drop (case-insensitive, matches even with punctuation/spaces in between)
_EXTRA_NOTE_DROPS = [
    r'wbl',                               # "WBL"
    r'top\s*garden',                      # "Top Garden"
    r'a\s*man\s*with\s*a\s*chinese',      # "A man with a Chinese"
    r'\b\d+[a-z]?\s*also\s*chinese\b',    # "70a also Chinese", etc.
    r'\bthe\s+house\b',                   # "the house"
    r'intercom',                          # "Intercom" (any mention)
    r'\b\d+\s*houses?\b',                 # "4 houses"
    r'\b[d]\s*is\s*chinese\b',            # "D is Chinese"
    r'under\s*decoration(?:\s*no\s*people\s*live\s*there)?',  # "Under decoration no people live there"
    r'\bno\s*people\s*live\s*there\b',    # standalone variant
    r'\bbig\b\s*(?:[.,])?\s*\bwrite\s*letter\b',              # "Big . Write letter for ..."
    r'\bif\s*still\s*chinese\b',          # "If still Chinese"
]

# Extend both the pattern list and the compiled regexes so they’re removed anywhere in the text
try:
    _NOTE_DROP_PATTERNS += _EXTRA_NOTE_DROPS
    _NOTE_DROP_RES.extend(re.compile(p, re.IGNORECASE) for p in _EXTRA_NOTE_DROPS)
except NameError:
    # If this block appears before _NOTE_DROP_RES is created, just append to patterns;
    # the later compile step will include them.
    _NOTE_DROP_PATTERNS += _EXTRA_NOTE_DROPS

# --- token-level hard drops (delete the whole segment if these appear anywhere)
# keep this conservative to avoid collateral damage; you asked to delete even when found separately
_EXTRA_TOKEN_WORDS = [
    r'\bwbl\b',
    r'\bintercom\b',
    r'\bthe\s+house\b',
    r'\bwrite\s*letter\b',
]

_EXTRA_TOKEN_RES = [re.compile(p, re.IGNORECASE) for p in _EXTRA_TOKEN_WORDS]

def _segment_contains_forced_drop(seg: str) -> bool:
    """Return True if a segment still contains any forced-drop tokens/phrases (delete the segment)."""
    if not seg:
        return False
    for rx in _EXTRA_TOKEN_RES:
        if rx.search(seg):
            return True
    # Also treat the big extra list as hard drops at segment level
    for ptn in _EXTRA_NOTE_DROPS:
        if re.search(ptn, seg, re.IGNORECASE):
            return True
    return False


def _normalize_separators(s: str) -> str:
    # unify commas/semicolons/pipes/slashes as " / ", collapse spaces
    s = re.sub(r'\s*[,;|]\s*', ' / ', s)
    s = re.sub(r'\s*/\s*', ' / ', s)
    s = re.sub(r'\s{2,}', ' ', s)
    return s.strip(' ,;/')

def _dedupe_segments_keep_njm(segments):
    seen = {}
    out = []
    for seg in segments:
        key = re.sub(r'(?i)\s*\(NJM\)\s*', '', seg).strip().lower()
        has_njm = '(njm' in seg.lower() or seg.strip().upper() == 'NJM'
        if key in seen:
            idx, prev_has_njm = seen[key]
            if has_njm and not prev_has_njm:
                out[idx] = seg
                seen[key] = (idx, True)
        else:
            seen[key] = (len(out), has_njm)
            out.append(seg)
    # collapse multiple raw 'NJM' segments
    njm_seen = False
    final = []
    for seg in out:
        if seg.strip().upper() == 'NJM':
            if njm_seen:
                continue
            njm_seen = True
        final.append(seg)
    return final

def _pull_njm_from_parentheses(t: str) -> str:
    # Turn "(NJM)" or "[NJM]" into " / NJM " so we preserve it before stripping parens
    return re.sub(r'[\(\[]\s*NJM\s*[\)\]]', ' / NJM ', t, flags=re.IGNORECASE)

def _strip_all_parentheses_content(t: str) -> str:
    # Remove any remaining (...) or [...] completely (including empty "()")
    t = re.sub(r'\([^()]*\)', ' ', t)
    t = re.sub(r'\[[^\[\]]*\]', ' ', t)
    return t

def _remove_non_ascii(t: str) -> str:
    # Drop any non-ASCII characters (keeps pure English only)
    return re.sub(r'[^\x00-\x7F]+', '', t)

def _strip_short_tail_after_proper_nouns(t: str) -> str:
    """
    Remove short (<=4 letters) lowercase 'tail' immediately after 1–3 Proper Nouns.
    Example: 'Hong Kong ren' -> 'Hong Kong'
    Whitelist keeps meaningful short words like 'dog'/'cat'.
    """
    keep = {'dog', 'cat'}
    def repl(m):
        tail = m.group(2)
        return m.group(0) if tail.lower() in keep else m.group(1)
    return re.sub(r'((?:[A-Z][a-z]+\s+){1,3})([a-z]{1,4})\b', repl, t)

# Grammar/wording fixes applied per segment
_GRAMMAR_FIXES = [
    (re.compile(r'(?i)\bReligion\s+Property\b'), 'Religious Property'),
]

# NEW: strip outer punctuation (full stops, commas, colons, etc.)
def _clean_segment_punct(seg: str) -> str:
    seg = re.sub(r'^[\s,.;:!?\-/_\\|]+', '', seg or '')
    seg = re.sub(r'[\s,.;:!?\-/_\\|]+$', '', seg)
    return re.sub(r'\s{2,}', ' ', seg).strip()

def _apply_grammar_fixes(seg: str) -> str:
    # Expand bare "Locked" (with optional punctuation) → "Locked Gate"
    if re.fullmatch(r'(?i)\s*Locked[ \t]*[.,;:!?\-]*\s*', seg or ''):
        return 'Locked Gate'
    for rx, rep in _GRAMMAR_FIXES:
        seg = rx.sub(rep, seg)
    return seg


def _sentence_case(seg: str) -> str:
    seg = (seg or '').strip()
    if not seg:
        return seg
    if seg.upper() == 'NJM':
        return 'NJM'
    return seg[0].upper() + seg[1:]

def _drop_punct_only(seg: str) -> bool:
    # true if the segment is only punctuation like "," ".", "..." or slashes/dashes
    return bool(re.fullmatch(r'[\s,.\-/_\\|]+', seg or ''))

def sanitize_notes_text(s: str) -> str:
    if not s:
        return ""

    t = unicodedata.normalize("NFC", str(s))

    # Replace "no junk mail"/"no circulars" with NJM
    t = re.sub(r'(?i)\bno\s+junk\s*mail(s)?\b', 'NJM', t)
    t = re.sub(r'(?i)\bno\s+circulars?\b', 'NJM', t)

    # dog inside → dog
    t = re.sub(r'(?i)\bdog\s+inside\b', 'dog', t)

    # Pull NJM out of parentheses first, then drop every other (...) / [...]
    t = _pull_njm_from_parentheses(t)
    t = _strip_all_parentheses_content(t)

    # Remove common date forms
    t = _DATE_RX.sub('', t)

    # Map "Locked . NJM" / "Locked, NJM" (any punct/space) → "Locked Gate / NJM"
    t = re.sub(r'(?i)\blocked[\s,.\-;:]*NJM\b', 'Locked Gate / NJM', t)

    # Remove lone question marks and stray backslashes
    t = t.replace('?', ' ').replace('\\', ' ')

    # Delete boilerplate phrases (with lots of “similar” variants)
    for rx in _NOTE_DROP_RES:
        t = rx.sub(' ', t)

    # Remove non-ASCII (keep only English)
    t = _remove_non_ascii(t)

    # Remove short non-English-ish tails after proper nouns (e.g., "Hong Kong ren")
    t = _strip_short_tail_after_proper_nouns(t)

    # Normalize repeated dots/commas and odd sequences
    t = re.sub(r'(?:\s*\.\s*){2,}', ' ', t)   # collapse " . . . " / "..." → space
    t = re.sub(r'\s*,\s*,\s*', ' / ', t)      # ", , " → separator
    t = re.sub(r'(?<!\d)\s*,\s*(?!\d)', ' / ', t)

    # Language-specific trims
    t = re.sub(r'(?i)\bNJM\s+English\s+and\s+(Cantonese)\b', r'NJM \1', t)
    t = re.sub(r'(?i)\b(Cantonese)\s*(?:and|/)\s*English\b', r'\1', t)
    t = re.sub(r'(?i)\bEnglish\s*(?:and|/)\s*(Cantonese)\b', r'\1', t)
    # From Vietnam, can speak Cantonese and English → From Vietnam / Cantonese
    t = re.sub(r'(?i)^From\s+([A-Za-z ]+),?\s*can\s*speak\s*(Cantonese|Mandarin)(?:\s*(?:and|/)\s*English)?\b',
               r'From \1 / \2', t)

    # Normalize separators and split
    t = _normalize_separators(t)
    parts = [p.strip(' /,;') for p in t.split(' / ') if p.strip(' /,;')]

    # Hard delete any segment that still mentions banned phrases/tokens,
    # even if they appear separately or with odd spacing/punctuation.
    parts = [p for p in parts if not _segment_contains_forced_drop(p)]

    # Drop punctuation-only fragments like "," "." "…" "/"
    parts = [p for p in parts if not _drop_punct_only(p)]
    parts = [_clean_segment_punct(p) for p in parts if p.strip()]
    # Dedupe, preferring the NJM variant
    parts = _dedupe_segments_keep_njm(parts)

    # Grammar fixes + sentence case each segment
    cleaned = []
    for p in parts:
        p2 = _apply_grammar_fixes(p)
        p2 = _sentence_case(p2)
        cleaned.append(p2)

    # Final tidy
    out = ' / '.join([p for p in cleaned if p])
    out = _normalize_separators(out)
    return out

def sanitize_notes_in_rows(rows) -> int:
    """In-place cleanup for NotesFromPublisher and Notes. Returns count of changed fields."""
    changed = 0
    for r in rows or []:
        for fld in ("NotesFromPublisher", "Notes"):
            if fld in r and (r[fld] or "").strip():
                before = r[fld]
                after = sanitize_notes_text(before)
                if after != before:
                    r[fld] = after
                    changed += 1
    return changed  # similar phrasings/variants are handled via regexes above


# ---------- Notes sanitization Patch End----------


# --- Main CSV processor (patched) ---


from collections import defaultdict
from tqdm import tqdm


# --- process_csv

def process_csv(input_file, output_clean, output_fail, expected_headers,
                verify_geocode=False,
                preserve_input_status=False,
                map_home_to_at_home=False,
                geocode_scope: str = "all"):   # ← NEW: "all" or "missing"
    """
    Verbose/instrumented version with STAGE markers:

    STAGE 0: Globals / Setup
    STAGE 1: Load CSV + Header Validation
      1.1 Sanitize Row Types
      1.2 Lift Suburb From Street (embedded tails)
      1.3 Early street clean: remove suburb after suffix + expand suffix
    STAGE 2: Load Canon Suffix Map (previous outputs)
    STAGE 3: Attach Row IDs
    STAGE 4: Build Quick Lookups
    STAGE 5: Detect Majority Suburb
    STAGE 6: 3.3 Pre-correct street spellings
    STAGE 7: 3.4 Standardise similar streets
    STAGE 8: 3.5 Resolve conflicting suburbs by proximity (pre-geocode)
    STAGE 9: 3.6 Final street spelling enforcement (+ final normalise sweep)
    STAGE 10: Build Address Query Set
    STAGE 11: Batch Geocode (LINZ → Photon/Nominatim/geocode.xyz)
    STAGE 12: Build Known Coords (for row processing)
    STAGE 13: Post-Geocode Row Processing
    STAGE 14: Post-Geocode Suburb Resolve + Cleanup
    STAGE 15: Cross-buffer Unify (clean + fail)
    STAGE 16: Retry Fail Candidates (re-geocode)
    STAGE 17: Reclassify Eligible Fails → Clean
    STAGE 18: Final Cross-buffer Unify (post-retry/reclassify)
    STAGE 19: Write Outputs + Summary
    """

    import traceback
    from collections import Counter, defaultdict as _dd
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from tqdm import tqdm as _tqdm

    # ---------- Helpers for logging stage progress ----------
    def _dbg(msg): print(f"[DEBUG] {msg}")
    def _stage_ok(name): print(f"✅ Stage OK: {name}")
    def _stage_start(name):
        print(f"\n=== ▶ {name} ===")
        if 'cancel_flag' in globals():
            print(f"   cancel_flag = {cancel_flag.is_set()}")
    def _cancelled(name):
        print(f"⚠️  Cancelled right after: {name}")
        return
    def _counts_snapshot(rows, label="rows"):
        try:
            n = len(rows)
            streets = len({(r.get('Street') or '').strip().title() for r in rows if r.get('Street')})
            subs = len({(r.get('Suburb') or '').strip().title() for r in rows if r.get('Suburb')})
            print(f"   {label}: {n} | unique streets: {streets} | unique suburbs: {subs}")
        except Exception:
            pass

    # =======================================================
    # STAGE 0: Globals / Setup
    # USES: _ensure_globals(), build_other_linz_memory_db()
    # =======================================================
    _stage_start("Globals/Setup")
    try:
        _ensure_globals()
        enable_hotpath_caches()
        global memory_conn
        memory_conn = build_other_linz_memory_db()
        _stage_ok("Globals/Setup")
    except Exception as e:
        print("❌ Setup error:", e)
        print(traceback.format_exc())
        return

    # =======================================================
    # STAGE 1: Load CSV + Header Validation
    # USES: csv.DictReader
    # -------------------------------------------------------
    # 1.1 Sanitize Row Types
    # 1.2 Lift Suburb From Street (embedded tails)
    # 1.3 Early street clean (strip suburb after suffix; expand)
    # =======================================================
    _stage_start("Load CSV + Header Validation")
    try:
        with open(input_file, "r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.DictReader(f)
            # --- sanitize headers up front ---
            headers = [h for h in (reader.fieldnames or []) if isinstance(h, str) and h.strip()]
            reader.fieldnames = headers  # ✅ remove None/blank headers before row dicts are built
            if not headers:
                print("❌ CSV appears to have no valid headers.")
                return
            if expected_headers:
                missing = [h for h in expected_headers if h not in headers]
                if missing:
                    print(f"⚠️ Missing expected column(s): {missing}")
            all_rows = list(reader)
        _counts_snapshot(all_rows, "loaded rows")
        _stage_ok("Load CSV + Header Validation")
    except FileNotFoundError:
        print(f"❌ Input file not found: {input_file}")
        return
    except Exception as e:
        print("❌ CSV load error:", e)
        print(traceback.format_exc())
        return

    _stage_start("Sanitize Row Types")
    try:
        import math
        def _to_str(v):
            if v is None:
                return ""
            if isinstance(v, float):
                if math.isnan(v):
                    return ""
                if v.is_integer():
                    return str(int(v))  # 2113.0 → "2113"
                return str(v)
            return str(v)

        for r in all_rows:
            for k, v in list(r.items()):
                # 🚫 Never touch free-form text columns
                if k in PRESERVE_FREEFORM_FIELDS:
                    continue
                r[k] = _to_str(v)
        _stage_ok("Sanitize Row Types")
    except Exception as e:
        print("❌ Sanitize error:", e)

    _stage_start("Lift Suburb From Street (embedded tails)")
    try:
        # Build case-insensitive suburb set + canonical map
        canon_map = {}
        cand_set = set()
        source_suburbs = (valid_suburbs_data if 'valid_suburbs_data' in globals() else [])
        for s in source_suburbs:
            if not s:
                continue
            canon = macron_suburb_map.get(s, s) if 'macron_suburb_map' in globals() else s
            canon_map[s.lower()] = canon
            cand_set.add(s.lower())

        # Keep the original Status around if we need to preserve it later
        for r in all_rows:
            r.setdefault("__OrigStatus", (r.get("Status") or ""))

        # Also add ASCII-folded variants
        def _ascii_fold(s: str) -> str:
            import unicodedata, re
            s = unicodedata.normalize("NFKD", s or "")
            s = "".join(ch for ch in s if not unicodedata.combining(ch))
            s = re.sub(r"[^A-Za-z0-9\s]", " ", s)
            return re.sub(r"\s+", " ", s).strip().lower()

        for s in list(cand_set):
            canon = canon_map.get(s, s.title())
            folded = _ascii_fold(s)
            if folded and folded not in cand_set:
                cand_set.add(folded)
                canon_map[folded] = canon

        ordered_cands = sorted(cand_set, key=len, reverse=True)  # longest first

        import re
        def _maybe_lift(row):
            """
            If street ends with a known suburb token (with/without comma, optional 'Auckland' tail),
            move that token into Suburb. Only lifts when Suburb is blank/invalid.
            """
            st = (row.get("Street") or "").strip()
            sb = (row.get("Suburb") or "").strip()
            if not st:
                return

            sb_low = sb.lower()
            has_valid_suburb = (sb_low in canon_map) or (
                sb and macron_suburb_map.get(sb.title(), sb.title())
                in (canon_map.get(sb_low, sb.title()) if 'macron_suburb_map' in globals() else sb)
            )
            if has_valid_suburb and sb_low != "auckland":
                return

            st_norm = re.sub(r"\s+", " ", st.replace(",", " ")).strip().lower()
            st_norm = re.sub(r"(,\s*)?auckland\s*$", "", st_norm).strip()

            hit = None
            for cand in ordered_cands:
                if not cand:
                    continue
                if re.search(rf"(?:\s|^){re.escape(cand)}$", st_norm, flags=re.IGNORECASE):
                    hit = cand
                    break

            if not hit:
                return

            new_suburb = canon_map.get(hit, hit.title())
            if "howick" in new_suburb.lower():
                new_suburb = "Howick"  # policy

            pattern = rf"(?i)[,\s]*{re.escape(hit)}(?:[,\s]+auckland)?\s*$"
            new_street = re.sub(pattern, "", st).rstrip(", ").rstrip()

            if new_street != st or (not sb or sb_low == "auckland"):
                try:
                    _log_quiet("Lift Suburb",
                               f"Street: '{st}' → '{new_street}' | Suburb: '{sb}' → '{new_suburb}'",
                               street=new_street or st, important=False)
                except Exception:
                    pass
                row["Street"] = new_street or st
                row["Suburb"] = new_suburb

        # Run the lift + early suffix/suburb clean together, row by row
        for r in all_rows:
            r = ensure_row_text_types(r)  # safe strings
            _maybe_lift(r)               # 1.2 lift
            # 1.3 early street clean (remove trailing suburb after a suffix, expand suffix, fix spaces)
            st = (r.get("Street") or "").strip()
            if st:
                st_clean = clean_street_suffix_and_suburb(st)
                if st_clean != st:
                    r["Street"] = st_clean
                    _log_quiet("Suffix-tail strip (early)", f"{st} → {st_clean}", street=st_clean, important=False)

        _stage_ok("Lift Suburb From Street (embedded tails)")
    except Exception as e:
        print("ℹ️ Lift-suburb step skipped:", e)

    # =======================================================
    # STAGE 2: Load Canon Suffix Map (from previous outputs)
    # USES: build_canon_suffix_map_from_outputs()
    # =======================================================
    _stage_start("Load Canon Suffix Map (from previous output)")
    try:
        build_canon_suffix_map_from_outputs(paths=("output_clean.csv",))
        _stage_ok("Load Canon Suffix Map (from previous output)")
    except Exception as e:
        print("ℹ️ Canon suffix load skipped:", e)

    # =======================================================
    # STAGE 3: Attach Row IDs (no coord pruning)
    # =======================================================
    _stage_start("Attach Row IDs")
    try:
        bad_rows = [i for i, r in enumerate(all_rows) if not isinstance(r, dict)]
        if bad_rows:
            print(f"❌ Found {len(bad_rows)} invalid row(s): {bad_rows[:3]}")
            return

        for i, r in enumerate(all_rows, start=2):
            r["__RowID"] = i
            # NEW: remember original street to compare later
            r.setdefault("__OrigStreet", (r.get("Street") or "").strip().title())

        _stage_ok("Attach Row IDs")
    except Exception as e:
        print("❌ Row ID step error:", e)
        print(traceback.format_exc())
        return

    # =======================================================
    # STAGE 4: Build Quick Lookups
    # =======================================================
    _stage_start("Build Quick Lookups")
    try:
        all_streets = set()
        input_street_lookup = {}
        for idx, row in enumerate(all_rows):
            street = (row.get("Street", "") or "").strip().title()
            suburb = (row.get("Suburb", "") or "").strip().title()
            type_  = (row.get("Type",   "") or "").strip().title()
            if street:
                all_streets.add(street)
                input_street_lookup[street] = {"row": idx + 2, "suburb": suburb, "type": type_}
        print(f"   unique streets in input: {len(all_streets)}")
        _stage_ok("Build Quick Lookups")
    except Exception as e:
        print("❌ Quick lookup error:", e)
        print(traceback.format_exc())
        return

    # =======================================================
    # STAGE 5: Detect Majority Suburb
    # USES: canon_suburb(), NEARBY_SUBURBS, log_correction()
    # =======================================================
    _stage_start("Detect Majority Suburb")
    majority_suburb = ""
    try:
        counts = Counter(
            (r.get("Suburb") or "").strip().title()
            for r in all_rows if (r.get("Suburb") or "").strip()
        )
        majority_suburb = counts.most_common(1)[0][0] if counts else ""
        majority_suburb = canon_suburb(majority_suburb)
        if majority_suburb not in NEARBY_SUBURBS:
            log_correction("Nearby Policy Disabled", f"Unrecognized majority '{majority_suburb or '<none>'}'")
            majority_suburb = ""
        log_correction("Majority Suburb", f"Detected: {majority_suburb or '<none>'}")
        print(f"   majority_suburb = {majority_suburb or '<none>'}")
        _stage_ok("Detect Majority Suburb")
    except Exception as e:
        print("❌ Majority suburb error:", e)
        print(traceback.format_exc())
        majority_suburb = ""

    if cancel_flag.is_set():
        return _cancelled("Detect Majority Suburb")

    # =======================================================
    # STAGE 6: 3.3 Pre-correct street spellings
    # USES: pre_correct_street_spellings()
    # =======================================================
    _stage_start("3.3 Pre-correct street spellings")
    try:
        with step_timer("Pre-correct street spellings"):
            all_rows, _fixed = pre_correct_street_spellings(
                all_rows, verbose=bool(globals().get("VERBOSE_PRE", False))
            )
        print(f"   changed fields: {_fixed}")
        _counts_snapshot(all_rows, "after 3.3")
        _stage_ok("3.3 Pre-correct street spellings")
    except Exception as e:
        print("❌ 3.3 error:", e)
        print(traceback.format_exc())
    if cancel_flag.is_set():
        return _cancelled("3.3 Pre-correct street spellings")

    # =======================================================
    # STAGE 7: 3.4 Standardise similar streets
    # USES: standardize_similar_streets(), build_global_dominant_suburb_map()
    # =======================================================
    _stage_start("3.4 Standardise similar streets")
    try:
        with step_timer("Standardise similar streets"):
            all_rows, _changed = standardize_similar_streets(
                all_rows, majority_suburb, verbose=bool(globals().get("VERBOSE_PRE", False))
            )
        all_streets = set((r.get('Street') or '').strip().title() for r in all_rows if r.get('Street'))
        _ = build_global_dominant_suburb_map(all_rows)  # recompute map
        print(f"   field changes: {_changed}")
        _counts_snapshot(all_rows, "after 3.4")
        _stage_ok("3.4 Standardise similar streets")
    except Exception as e:
        print("❌ 3.4 error:", e)
        print(traceback.format_exc())
    if cancel_flag.is_set():
        return _cancelled("3.4 Standardise similar streets")

    # =======================================================
    # STAGE 8: 3.5 Resolve conflicting suburbs by proximity (pre-geocode)
    # USES: resolve_conflicting_suburbs_by_proximity(), safe_float()
    # =======================================================
    _stage_start("3.5 Resolve conflicting suburbs by proximity (pre-geocode)")
    try:
        known_coords_early = _dd(list)
        for r in all_rows:
            st = (r.get("Street", "") or "").strip().title()
            sb = (r.get("Suburb", "") or "").strip().title()
            la = safe_float(r.get("Latitude"), None)
            lo = safe_float(r.get("Longitude"), None)
            if st and sb and la is not None and lo is not None:
                known_coords_early[(st, sb)].append((la, lo))

        print(f"   streets with coords before 3.5: {len(known_coords_early)}")
        with step_timer("Resolve conflicting suburbs by proximity"):
            resolve_conflicting_suburbs_by_proximity(
                all_rows,
                known_geocodes_by_street=known_coords_early,
                radius_m=300
            )
        print("   ✔ finished resolve_conflicting_suburbs_by_proximity()")
        _counts_snapshot(all_rows, "after 3.5")
        _stage_ok("3.5 Resolve conflicting suburbs by proximity (pre-geocode)")
    except Exception as e:
        print("❌ 3.5 error:", e)
        print(traceback.format_exc())

    print(f"🔎 Post-3.5 cancel_flag = {cancel_flag.is_set()}")
    if cancel_flag.is_set():
        return _cancelled("3.5 Resolve conflicting suburbs by proximity (pre-geocode)")

    # =======================================================
    # STAGE 9: 3.6 Final street spelling enforcement
    #   9.a Final street/suburb normalisation sweep first
    # USES: final_normalize_rows(), enforce_final_street_spelling()
    # =======================================================
    _stage_start("3.6 Final street spelling enforcement")
    try:
        with step_timer("Final street/suburb normalisation"):
            all_rows, n_changed = final_normalize_rows(all_rows, valid_suburbs_data, enforce_title=True)
            print(f"   normalised (street/suburb): {n_changed} change(s)")

        with step_timer("Final street spelling enforcement"):
            all_rows = enforce_final_street_spelling(all_rows)

        _counts_snapshot(all_rows, "after 3.6")
        _stage_ok("3.6 Final street spelling enforcement")
    except Exception as e:
        print("❌ 3.6 error:", e)
        print(traceback.format_exc())
    if cancel_flag.is_set():
        return _cancelled("3.6 Final street spelling enforcement")

    # =======================================================
    # INITIALIZATION: Build LINZ memory cache
    # =======================================================
    memory_conn = build_other_linz_memory_db()

    # One-time cleanup: drop polluted coords from cache
    try:
        purge_non_auckland_from_memory(memory_conn)
    except Exception:
        log_correction("LINZ Memory Purge", "Cleanup failed (ignored)")

    # =======================================================
    # STAGE 10: Build Address Query Set
    # =======================================================
    _stage_start("Build Address Query Set")
    try:
        address_queries = {}
        missing_only = (str(geocode_scope).lower() == "missing")

        def _is_missing_coords(row):
            la = (row.get("Latitude") or "").strip()
            lo = (row.get("Longitude") or "").strip()
            if la == "" or lo == "":
                return True
            try:
                return float(la) == 0.0 or float(lo) == 0.0
            except Exception:
                return True  # treat non-numeric as missing

        for r in all_rows:
            if not isinstance(r, dict):
                continue
            if (r.get('Type', '') or '').strip().lower() == 'other':
                continue

            number = (r.get('Number') or '').strip()
            street = (r.get('Street') or '').strip()
            suburb = ((r.get('Suburb') or '').strip() or 'Auckland')
            if not (number and street):
                continue

            # Scope gate: only enqueue if coords are missing/empty when geocode_scope == "missing"
            if missing_only and not _is_missing_coords(r):
                continue

            k = addr_key(number, street, suburb)
            address_queries[k] = True

        print(f"   to geocode ({'missing only' if missing_only else 'all'}): {len(address_queries)}")
        if not address_queries:
            print("ℹ️ No addresses need batch geocoding in this scope.")
        _stage_ok("Build Address Query Set")
    except Exception as e:
        print("❌ Address list build error:", e)
        print(traceback.format_exc())
        return

    if cancel_flag.is_set():
        return _cancelled("Build Address Query Set")

    # =======================================================
    # STAGE 11: Batch Geocode  (+ prune/replace patch)
    # =======================================================
    _stage_start("Batch Geocode")
    try:
        address_list = list(address_queries.keys())
        if not address_list:
            print("   (scope produced 0 addresses) — skipping batch geocoding.")
            geocode_results = {}  # make sure downstream has a dict
            _stage_ok("Batch Geocode (skipped)")
        else:
            log_correction("Preparing Addresses", f"Preparing {len(address_list)} Addresses For Geocoding")

        # 11.0 Fetch initial results
        # scale concurrency to the batch size
        addr_n = len(address_list)
        max_workers = 12 if addr_n < 200 else 30 if addr_n < 2000 else 60

        geocode_results = run_async_coro(
            batch_geocode,
            addresses=address_list,
            verify=verify_geocode,
            max_workers=max_workers
        )

        print(f"   geocode results (raw): {len(geocode_results)}")
        log_correction("Batch Geocoding Completed", f"{len(geocode_results)} address results retrieved")

        # 11.1 Sanity pass: swap-if-needed, prune out-of-Auckland, then targeted replacement
        #     We keep all dict keys, but replace bad tuples with a fixed one or a blank tuple.
        cleaned_results = {}
        swapped_fix = 0
        pruned = 0
        replaced = 0
        still_bad = 0

        for akey in address_list:
            tpl = geocode_results.get(akey)

            # Normalize to a 4-tuple
            if not (isinstance(tpl, tuple) and len(tpl) == 4):
                cleaned_results[akey] = ("", "", "", "")
                pruned += 1
                continue

            label, lat, lon, postal = tpl

            # Try to coerce to floats; if not, mark for replacement
            lat_ok = lon_ok = True
            try:
                la = float(lat) if lat not in (None, "") else None
                lo = float(lon) if lon not in (None, "") else None
                if la is None or lo is None:
                    lat_ok = lon_ok = False
            except Exception:
                lat_ok = lon_ok = False

            # If both numeric, check for obvious swap and fix
            if lat_ok and lon_ok:
                la2, lo2 = _maybe_swap_latlon(la, lo)
                if (la2, lo2) != (la, lo):
                    swapped_fix += 1
                    la, lo = la2, lo2

            # Accept if we now have numeric and inside Auckland
            if (lat_ok and lon_ok) and is_in_auckland(la, lo):
                cleaned_results[akey] = (label, la, lo, postal or "")
                continue

            # 11.2 Replacement attempt: re-geocode this exact address string
            #     akey is already the canonical "Number Street, Suburb, Auckland"
            try:
                repl = get_lat_long(akey)
            except Exception:
                repl = None

            if isinstance(repl, tuple) and len(repl) == 4:
                r_label, r_lat, r_lon, r_postal = repl
                try:
                    r_la = float(r_lat);
                    r_lo = float(r_lon)
                except Exception:
                    r_la = r_lo = None

                if (r_la is not None and r_lo is not None) and is_in_auckland(r_la, r_lo):
                    cleaned_results[akey] = (r_label, r_la, r_lo, r_postal or "")
                    replaced += 1
                    continue

            # Couldn’t fix → blank it so downstream won’t trust it
            cleaned_results[akey] = ("", "", "", "")
            pruned += 1
            still_bad += 1

        geocode_results = cleaned_results

        # 11.3 Summary + OK
        print(f"   swapped fixed: {swapped_fix}")
        print(f"   pruned outside/invalid: {pruned} (replaced: {replaced}, still bad: {still_bad})")
        _stage_ok("Batch Geocode")

        # Optional detailed log lines
        if swapped_fix:
            log_correction("Geocode Swap Fix", f"Auto-corrected {swapped_fix} swapped lat/lon pair(s)")
        if pruned:
            log_correction("Geocode Prune",
                           f"Pruned {pruned} outside/invalid result(s) — {replaced} replaced immediately")

    except Exception as e:
        print("❌ Batch geocode error:", e)
        print(traceback.format_exc())
        return

    if cancel_flag.is_set():
        return _cancelled("Batch Geocode")


    # =======================================================
    # STAGE 12: Build Known Coords (for row processing)
    # =======================================================
    _stage_start("Build Known Coords (for row processing)")
    try:
        known_coords = _dd(list)
        for r in all_rows:
            street = (r.get("Street") or "").strip().title()
            suburb = (r.get("Suburb") or "").strip().title()
            lat = r.get("Latitude", "")
            lon = r.get("Longitude", "")
            if street and suburb and not is_blank_or_zero(lat) and not is_blank_or_zero(lon):
                try:
                    known_coords[(street, suburb)].append((float(lat), float(lon)))
                except Exception:
                    continue
        print(f"   known street/suburb coord buckets: {len(known_coords)}")
        _stage_ok("Build Known Coords (for row processing)")
    except Exception as e:
        print("❌ Known coords build error:", e)
        print(traceback.format_exc())
        return
    if cancel_flag.is_set():
        return _cancelled("Build Known Coords (for row processing)")

    # =======================================================
    # STAGE 13: Post-Geocode Row Processing
    # =======================================================
    _stage_start("Post-Geocode Row Processing")
    clean_rows, fail_rows = [], []
    try:
        # Compute once (instead of per-row)
        dom_verified_map = build_dominant_suburb_map_from_verified(all_rows, threshold=0.7)
        header_keys = list(all_rows[0].keys())

        def _call_row(row):
            if cancel_flag.is_set():
                return {"status": "cancelled", "row": row}
            try:
                row = ensure_row_text_types(row)
                return process_single_row(
                    row,
                    geocode_results,
                    all_rows,
                    all_streets,
                    seen_addresses,
                    header_keys,
                    verify_geocode,
                    dom_verified_map,  # ← precomputed once
                    known_geocodes_by_street=known_coords,
                    nearby_policy_enabled=False,
                    majority_suburb=majority_suburb,
                )
            except TypeError:
                # existing fallback
                return process_single_row(
                    row,
                    geocode_results,
                    all_rows,
                    all_streets,
                    seen_addresses,
                    header_keys,
                    verify_geocode,
                    dom_verified_map,  # ← precomputed once
                    known_geocodes_by_street=known_coords
                )

        seen_addresses = set()
        processed_input_streets = set()
        processed_street_lock = threading.Lock()

        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=40) as executor:
            future_map = {executor.submit(_call_row, row): row for row in all_rows}
            for fut in _tqdm(as_completed(future_map), total=len(future_map),
                             desc="🔄 Stage 4: Post-Geocode Processing....", unit="row"):
                if cancel_flag.is_set():
                    return _cancelled("Post-Geocode Row Processing (during futures)")
                orig_row = future_map[fut]
                try:
                    result = fut.result()
                    row = fix_lat_lon_if_swapped(result["row"])
                    street_t = (row.get("Street") or "").strip().title()
                    if street_t:
                        with processed_street_lock:
                            processed_input_streets.add(street_t)
                    if result["status"] == "clean":
                        clean_rows.append(row)
                    else:
                        if not (row.get("Final Status") or "").strip():
                            row["Final Status"] = "Fail"
                        fail_rows.append(row)
                except Exception as e:
                    log_correction("Row Processing Error", f"{e}", street=(orig_row.get("Street", "") or ""))
                    orig_row = dict(orig_row)
                    if not (orig_row.get("Final Status") or "").strip():
                        orig_row["Final Status"] = "Fail"
                    fail_rows.append(orig_row)
        print(f"   clean buffer: {len(clean_rows)} | fail buffer: {len(fail_rows)}")
        _stage_ok("Post-Geocode Row Processing")
    except Exception as e:
        print("❌ Post-geocode processing error:", e)
        print(traceback.format_exc())
        return

    # =======================================================
    # STAGE 14: Post-Geocode Suburb Resolve + Cleanup
    # USES: resolve_conflicting_suburbs_by_proximity(), log_field_change()
    # =======================================================
    _stage_start("Post-Geocode Suburb Resolve + Cleanup")
    try:
        known_coords_after = _dd(list)
        for r in clean_rows:
            st = (r.get("Street", "") or "").strip().title()
            sb = (r.get("Suburb", "") or "").strip().title()
            la = safe_float(r.get("Latitude"), None)
            lo = safe_float(r.get("Longitude"), None)
            if st and sb and la is not None and lo is not None:
                known_coords_after[(st, sb)].append((la, lo))

        with step_timer("Resolve conflicting suburbs by proximity (post-geocode)"):
            resolve_conflicting_suburbs_by_proximity(
                clean_rows,
                known_geocodes_by_street=known_coords_after,
                radius_m=300,
                k_nearest=3
            )

            removed_count = 0
            for r in clean_rows:
                old_sb = (r.get("Suburb") or "").strip()
                if old_sb.lower() == "auckland":
                    street_for_log = (r.get("Street") or "").strip().title()
                    row_id = r.get("__RowID")
                    log_field_change(
                        "Final Cleanup", row_id, "Suburb",
                        old_sb, "", "Removed exact 'Auckland' in Suburb",
                        street=street_for_log
                    )
                    r["Suburb"] = ""
                    removed_count += 1
            if removed_count:
                log_correction("Final Cleanup Summary", f"Removed exact 'Auckland' from {removed_count} row(s)")
        print("   post-geocode resolve done")
        _stage_ok("Post-Geocode Suburb Resolve + Cleanup")
    except Exception as e:
        print("❌ Post-geocode suburb resolve error:", e)
        print(traceback.format_exc())
    if cancel_flag.is_set():
        return _cancelled("Post-Geocode Suburb Resolve + Cleanup")




    # =======================================================
    # STAGE 15: Cross-buffer Unify (clean + fail)
    # USES: _unify_crossfiles_postgeocode()
    # =======================================================
    _stage_start("Cross-buffer Unify (clean + fail)")
    try:
        clean_rows, fail_rows = _unify_crossfiles_postgeocode(clean_rows, fail_rows)
        print(f"   after cross-buffer unify → clean: {len(clean_rows)} | fail: {len(fail_rows)}")
        _stage_ok("Cross-buffer Unify (clean + fail)")
    except Exception as e:
        print("❌ Cross-buffer unify error:", e)
        print(traceback.format_exc())
    if cancel_flag.is_set():
        return _cancelled("Cross-buffer Unify (clean + fail)")

    # =======================================================
    # STAGE 16: Retry Fail Candidates
    # USES: run_async_coro(batch_geocode), is_in_auckland(), macron_suburb_map
    # =======================================================
    _stage_start("Retry Fail Candidates")
    try:
        retry_candidates = []
        for r in fail_rows:
            fs = (r.get("Final Status") or "").strip().lower()
            st = (r.get("Status") or "").strip().lower()
            if fs != "fail": continue
            if st in {"duplicate", "donotcall"}: continue
            if st == "custom1" and fs == "fail": continue
            number = (r.get("Number") or "").strip()
            street = (r.get("Street") or "").strip()
            suburb = (r.get("Suburb") or "").strip()
            if number and street and suburb:
                retry_candidates.append(fmt_addr_parts(number, street, suburb))
        print(f"   retry candidates: {len(retry_candidates)}")

        if retry_candidates:
            retry_results = run_async_coro(
                batch_geocode,
                addresses=list(set(retry_candidates)),
                verify=False,
                max_workers=20
            )
            promoted = 0
            new_fail_rows = []
            for r in fail_rows:
                k = fmt_addr_parts((r.get("Number") or "").strip(),
                                   (r.get("Street") or "").strip(),
                                   (r.get("Suburb") or "").strip())
                hit = retry_results.get(k)
                if hit and isinstance(hit, tuple) and len(hit) == 4:
                    full, lat, lon, postal = hit
                    if lat and lon and is_in_auckland(float(lat), float(lon)):
                        parts = [p.strip() for p in (full or "").split(",")]
                        g_suburb = parts[1].title() if len(parts) > 1 else (r.get("Suburb") or "").strip().title()
                        r["Latitude"] = f"{float(lat):.8f}"
                        r["Longitude"] = f"{float(lon):.8f}"

                        # ✅ Guard postal using nz_postal_lookup
                        if postal:
                            expected = nz_postal_lookup.get(g_suburb, "")
                            if expected and postal != expected:
                                postal = expected

                        if postal and not (r.get("PostalCode") or "").strip():
                            r["PostalCode"] = postal

                        if g_suburb:
                            r["Suburb"] = macron_suburb_map.get(g_suburb, g_suburb)
                        r["Final Status"] = ""
                        clean_rows.append(r)
                        promoted += 1
                        continue

                new_fail_rows.append(r)
            fail_rows = new_fail_rows
            print(f"   promoted from retry: {promoted}")
        _stage_ok("Retry Fail Candidates")
    except Exception as e:
        print("❌ Retry block error:", e)
        print(traceback.format_exc())
    if cancel_flag.is_set():
        return _cancelled("Retry Fail Candidates")

    # =======================================================
    # STAGE 17: Reclassify Eligible Fails → Clean
    # =======================================================
    _stage_start("Reclassify Eligible Fails To Clean")
    try:
        def _bare(s):
            return (s or "").strip().lower().replace(" ", "")

        # Treat these Status values as eligible for Clean (Pass), including DoNotCall
        eligible_statuses = {"home", "nothome", "available", "newfrompublisher", "donotcall"}

        # Only these Final Statuses must remain in Fail
        protected_final = {"duplicate", "notchinese"}  # ← removed "donotcall"

        moved = 0
        keep_fail = []
        for r in fail_rows:
            s_norm = _bare(r.get("Status"))
            fs_norm = _bare(r.get("Final Status"))
            if (s_norm in eligible_statuses) and (fs_norm not in protected_final):
                # Do NOT change Status; just clear Final Status to mark as Clean
                if r.get("Final Status"):
                    log_correction("Reclassify To Clean",
                                   f"Status='{r.get('Status')}', Final Status='{r.get('Final Status')}' → clean",
                                   street=(r.get("Street") or ""))
                r["Final Status"] = ""  # Clean (Pass)
                clean_rows.append(r)
                moved += 1
            else:
                keep_fail.append(r)
        fail_rows = keep_fail
        print(f"   reclassified from fail → clean: {moved}")
        _stage_ok("Reclassify Eligible Fails To Clean")
    except Exception as e:
        print("❌ Reclassify step error:", e)

    # =======================================================
    # STAGE 18: Final Cross-buffer Unify (post-retry/reclassify)
    # USES: unify_street_suburb_across_outputs()
    # =======================================================
    _stage_start("Final Cross-buffer Unify (post-retry/reclassify)")
    try:
        clean_rows, fail_rows, _ = unify_street_suburb_across_outputs(
            clean_rows, fail_rows, radius_m=800, k_nearest=5
        )
        print(f"   final unify → clean: {len(clean_rows)} | fail: {len(fail_rows)}")
        _stage_ok("Final Cross-buffer Unify (post-retry/reclassify)")
    except Exception as e:
        print("❌ Final cross-buffer unify error:", e)
        print(traceback.format_exc())
    if cancel_flag.is_set():
        return _cancelled("Final Cross-buffer Unify (post-retry/reclassify)")

    # =======================================================
    # STAGE 19: Write Outputs + Summary
    # =======================================================
    _stage_start("Write Outputs")
    try:
        def _num_key(n: str) -> int:
            # Sort by the *house* number even if value is "Unit3/219" or "219/Unit3" or "12-14"
            s = (n or "").strip()
            m = re.match(r"\s*(?:Unit[A-Za-z0-9]+\s*/\s*)?(\d+)", s, re.IGNORECASE)
            try:
                return int(m.group(1)) if m else 0
            except Exception:
                return 0

        # --- Enforce protected streets just before logging/writing ---
        def _enforce_protected_streets(rows):
            fixed = 0
            for r in rows or []:
                orig = (r.get("__OrigStreet") or "").strip().title()
                final = (r.get("Street") or "").strip().title()
                if not orig or not final:
                    continue

                # Full-name protection
                if _is_protected_full(orig) and final != orig:
                    r["Street"] = orig
                    fixed += 1
                    log_correction("Protected Street Undo", f"Reverted '{final}' → '{orig}'", street=orig)
                    continue

                # Base-level protection (e.g., Eaglen vs Eaglemont)
                obase = _protected_base(orig)
                if obase:
                    fbase, _ = _norm_base_key(final)
                    if fbase != obase:
                        r["Street"] = orig
                        fixed += 1
                        log_correction("Protected Base Undo", f"Reverted '{final}' → '{orig}'", street=orig)
            return fixed

        # Apply to both buffers before we log any changes
        _ = _enforce_protected_streets(clean_rows)
        _ = _enforce_protected_streets(fail_rows)

        # --- NEW: log any street-name changes from original → final
        try:
            changes = 0
            for r in (clean_rows + fail_rows):
                orig = (r.get("__OrigStreet") or "").strip().title()
                final = (r.get("Street") or "").strip().title()
                if orig and final and orig != final:
                    # Example: "Eaglen Place - Eaglemont Drive"
                    log_correction("Street Name Changed", f"{orig} - {final}", street=final)
                    changes += 1
            if changes:
                log_correction("Street Name Changed Summary", f"Logged {changes} street rename(s)")
        except Exception as e:
            log_correction("Street Change Logging Error", f"{e}")

        def _strip_internal_fields(rows, keep_keys=("__OrigStatus",)):
            if not rows:
                return
            keep = set(keep_keys or ())
            for r in rows:
                if not isinstance(r, dict):
                    continue
                to_remove = []
                for k in list(r.keys()):
                    if not isinstance(k, str):
                        to_remove.append(k)
                        continue
                    if k.startswith("_") and k not in keep:
                        to_remove.append(k)
                for k in to_remove:
                    r.pop(k, None)

        # Ensure we have the full schema
        fieldnames = list(all_rows[0].keys())
        for col in [
            "TerritoryID", "TerritoryNumber", "CategoryCode", "Category",
            "TerritoryAddressID", "ApartmentNumber", "Number", "Street",
            "Suburb", "PostalCode", "State", "Name", "Phone", "Type", "Status",
            "NotHomeAttempt", "Date1", "Date2", "Date3", "Date4", "Date5",
            "Language", "Latitude", "Longitude", "Notes", "NotesFromPublisher",
            "Final Status"
        ]:
            if col not in fieldnames:
                fieldnames.append(col)

        # Fail rows must carry an explicit Final Status
        for r in fail_rows:
            if not (r.get("Final Status") or "").strip():
                r["Final Status"] = "Fail"

        # --- Apply manual overrides BEFORE sorting ---
        _stage_start("Apply Manual Overrides")
        try:
            clean_rows = apply_manual_overrides(clean_rows)
            fail_rows = apply_manual_overrides(fail_rows)
            _stage_ok("Apply Manual Overrides")
        except Exception as e:
            print("❌ Manual overrides error:", e)
            print(traceback.format_exc())
        if cancel_flag.is_set():
            return _cancelled("Apply Manual Overrides")

        # --- Build sorted_* AFTER overrides ---
        def _status_bucket(s: str) -> int:
            s = (s or "").strip().lower()
            if s in {"duplicate"}: return 0
            if s in {"not chinese", "notchinese", "custom1"}: return 1
            if s in {"do not call", "donotcall"}: return 2
            if s in {"fail"}: return 3
            return 4

        sorted_clean = sorted(
            clean_rows,
            key=lambda r: (
                (r.get("Street") or "").strip().lower(),
                (r.get("Suburb") or "").strip().lower(),
                _num_key(r.get("Number", ""))
            )
        )

        sorted_fail = sorted(
            fail_rows,
            key=lambda r: (
                _status_bucket(r.get("Final Status")),
                (r.get("Street") or "").strip().lower(),
                (r.get("Suburb") or "").strip().lower(),
                _num_key(r.get("Number", ""))
            )
        )

        # ---------- Coverage checks ----------
        blank_count = 0
        oob_count = 0
        blank_rows = []
        oob_rows = []

        for r in (sorted_clean + sorted_fail):
            la = safe_float(r.get("Latitude"), None)
            lo = safe_float(r.get("Longitude"), None)
            num = (r.get("Number") or "").strip()
            st = (r.get("Street") or "").strip().title()
            sb = (r.get("Suburb") or "").strip().title()
            addr_label = f"{num} {st}, {sb}".strip(", ")

            if la is None or lo is None or str(la).strip() == "" or str(lo).strip() == "":
                blank_count += 1
                blank_rows.append(addr_label)
            else:
                if not is_in_auckland(la, lo):
                    oob_count += 1
                    oob_rows.append(f"{addr_label} → {la},{lo}")

        if blank_count > 0 or oob_count > 0:
            print("\n📍 Coordinate Coverage Check")
            if blank_count > 0:
                print(f"   • Rows with blank coords: {blank_count}")
                for b in blank_rows:
                    print(f"      - {b}")
                    log_correction("Coverage Blank Coord", f"{b}", street=b)
            if oob_count > 0:
                print(f"   • Rows Outside Auckland:  {oob_count}")
                for o in oob_rows:
                    print(f"      - {o}")
                    log_correction("Coverage OOB Coord", f"{o}", street=o.split("→")[0].strip())

        # Per-row OOB demotion
        moved_rows = 0
        keep_clean = []
        for r in sorted_clean:
            la = safe_float(r.get("Latitude"), None)
            lo = safe_float(r.get("Longitude"), None)
            if la is not None and lo is not None and not is_in_auckland(la, lo):
                r["Final Status"] = "Geocode Outside Auckland/NZ"
                sorted_fail.append(r)
                moved_rows += 1
            else:
                keep_clean.append(r)
        sorted_clean = keep_clean
        if moved_rows:
            log_correction("Coverage Demote (per-row)", f"Moved {moved_rows} OOB row(s) to fail")

        # Street-wide demotion for any OOB coords (always run)
        sorted_clean, sorted_fail, moved, affected = demote_streets_with_out_of_auckland_coords(
            sorted_clean, sorted_fail
        )
        if moved:
            log_correction(
                "Coverage Demote Summary",
                f"Moved {moved} row(s) to fail across {len(affected)} street(s)"
            )

        # --- Final counts after demotions ---
        clean_count = len(sorted_clean)
        fail_count = len(sorted_fail)

        # >>> INSERT HERE, *before* building sorted_clean/sorted_fail <<<
        clean_rows, fail_rows = enforce_real_duplicates(clean_rows, fail_rows)

        # now build the sorted buffers as you already do:
        sorted_clean = sorted(
            clean_rows,
            key=lambda r: (
                (r.get("Street") or "").strip().lower(),
                (r.get("Suburb") or "").strip().lower(),
                _num_key(r.get("Number", ""))
            )
        )
        sorted_fail = sorted(
            fail_rows,
            key=lambda r: (
                _status_bucket(r.get("Final Status")),
                (r.get("Street") or "").strip().lower(),
                (r.get("Suburb") or "").strip().lower(),
                _num_key(r.get("Number", ""))
            )
        )



        # Optional geocode source summary
        if 'geocode_sources_used' in globals() and geocode_sources_used:
            print("📊 Geocode Source Summary:")
            for source, count in geocode_sources_used.items():
                print(f"   - {source}: {count}")

        # Group corrections without touching the live log
        try:
            group_corrections_log_by_street(
                src="corrections_log.csv",
                dst="corrections_log_grouped.csv"
            )
        except Exception as e:
            log_correction("Corrections Grouping Error", f"Could not write grouped corrections log: {e}")

        # Sanitize fieldnames: strings only, non-empty, de-dupe
        fieldnames = [c for c in fieldnames if isinstance(c, str) and c.strip()]
        fieldnames = list(dict.fromkeys(fieldnames))


        # If the caller asked to preserve input Status (options 5/6), DO NOT override it.
        # Only map `Home` → `At Home` when requested.
        # >>> GLOBAL DEDUPE (decide 'Duplicate' at the end, using FINAL names)
        clean_rows, fail_rows = assign_duplicates_globally(clean_rows, fail_rows)

        # … keep everything up to/including dedupe …

        # >>> NEW: append any input rows that never made it into either buffer as Missing
        present_ids = set()
        for r in (clean_rows + fail_rows):
            rid = r.get("__RowID")
            if rid:
                present_ids.add(rid)

        missing_added = 0
        for r in all_rows:
            rid = r.get("__RowID")
            if rid and rid not in present_ids:
                m = dict(r)  # shallow copy so we don't mutate all_rows
                m["Final Status"] = "Missing"
                fail_rows.append(m)
                missing_added += 1

        if missing_added:
            log_correction("Missing Rows → Fail",
                           f"Appended {missing_added} missing row(s) to output_fail.csv with Final Status='Missing'")

        # ✅ Restore original Status FIRST
        if preserve_input_status:
            def _restore_status(rows):
                for r in rows or []:
                    orig = (r.get("__OrigStatus") or r.get("Status") or "").strip()
                    if map_home_to_at_home and orig.lower() == "home":
                        r["Status"] = "At Home"
                    else:
                        r["Status"] = orig

            _restore_status(clean_rows)
            _restore_status(fail_rows)

        # ✅ Now it’s safe to drop internal fields
        _strip_internal_fields(clean_rows)
        _strip_internal_fields(fail_rows)

        # ⚠️ IMPORTANT: rebuild the sorted buffers AFTER the dedupe + status restore
        def _num_key(n: str) -> int:
            s = (n or "").strip()
            m = re.match(r"\s*(?:Unit[A-Za-z0-9]+\s*/\s*)?(\d+)", s, re.IGNORECASE)
            try:
                return int(m.group(1)) if m else 0
            except Exception:
                return 0

        def _status_bucket(s: str) -> int:
            s = (s or "").strip().lower()
            if s in {"duplicate"}: return 0
            if s in {"not chinese", "notchinese", "custom1"}: return 1
            if s in {"do not call", "donotcall"}: return 2
            if s in {"fail"}: return 3
            return 4

        sorted_clean = sorted(
            clean_rows,
            key=lambda r: (
                (r.get("Street") or "").strip().lower(),
                (r.get("Suburb") or "").strip().lower(),
                _num_key(r.get("Number", ""))
            )
        )
        sorted_fail = sorted(
            fail_rows,
            key=lambda r: (
                _status_bucket(r.get("Final Status")),
                (r.get("Street") or "").strip().lower(),
                (r.get("Suburb") or "").strip().lower(),
                _num_key(r.get("Number", ""))
            )
        )

        # --- Quick postcode sanity cleanup (remove obviously foreign or invalid) ---
        for r in (sorted_clean + sorted_fail):
            pc = (r.get("PostalCode") or "").strip()
            if pc:
                try:
                    # NZ postcodes are 4 digits, typically 0xxx–9xxx
                    if not pc.isdigit() or int(pc) > 9999 or len(pc) != 4:
                        r["PostalCode"] = ""
                except Exception:
                    r["PostalCode"] = ""

        # --- ENFORCE ONE POSTCODE PER SUBURB (final guard) ---
        _stage_start("Enforce Postcodes By Suburb (final)")
        try:
            ch_c = enforce_postcode_by_suburb_inplace(sorted_clean)
            ch_f = enforce_postcode_by_suburb_inplace(sorted_fail)
            print(f"   postcode fixes → clean: {ch_c} | fail: {ch_f}")
            _stage_ok("Enforce Postcodes By Suburb (final)")
        except Exception as e:
            print("ℹ️ Postcode enforce step skipped:", e)

        # --- FLIP UNITS LAST (right before writing) & ensure coords unchanged ---
        _stage_start("Flip Unit Prefixes for Output (final)")
        try:
            def _snap_coords(rows):
                return [(r.get("Latitude", ""), r.get("Longitude", "")) for r in rows]

            clean_coords_before = _snap_coords(sorted_clean)
            fail_coords_before = _snap_coords(sorted_fail)

            flips_clean = flip_units_for_rows(sorted_clean)  # only mutates Number
            flips_fail = flip_units_for_rows(sorted_fail)

            # Guard: make sure flipping didn't alter coords
            def _assert_coords_same(before, rows, label):
                after = [(r.get("Latitude", ""), r.get("Longitude", "")) for r in rows]
                if after != before:
                    # Hard stop so bad side effects can never slip into outputs
                    raise RuntimeError(f"{label}: coordinates changed after unit flip")

            _assert_coords_same(clean_coords_before, sorted_clean, "Clean")
            _assert_coords_same(fail_coords_before, sorted_fail, "Fail")

            print(f"   flipped unit prefixes → clean: {flips_clean} | fail: {flips_fail}")
            _stage_ok("Flip Unit Prefixes for Output (final)")
        except Exception as e:
            print("ℹ️ Flip-unit step skipped:", e)

        # --- Merge NotesFromPublisher -> Notes for outputs ---
        _stage_start("Move NotesFromPublisher → Notes")
        try:
            merged_c = merge_publisher_notes_into_notes(sorted_clean)
            merged_f = merge_publisher_notes_into_notes(sorted_fail)
            print(f"   merged rows → clean: {merged_c} | fail: {merged_f}")
            _stage_ok("Move NotesFromPublisher → Notes")
        except Exception as e:
            print("ℹ️ Notes merge step skipped:", e)

        _stage_start("Sanitize Notes (per spec)")
        try:
            changed_c = sanitize_notes_in_rows(sorted_clean)
            changed_f = sanitize_notes_in_rows(sorted_fail)
            print(f"   sanitized notes → clean: {changed_c} field(s) | fail: {changed_f} field(s)")
            _stage_ok("Sanitize Notes (per spec)")
        except Exception as e:
            print("ℹ️ Notes sanitize step skipped:", e)


        # --- FINAL WRITE (nothing after this mutates rows) ---
        with open(output_clean, 'w', newline='', encoding='utf-8') as cleanfile, \
                open(output_fail, 'w', newline='', encoding='utf-8') as failfile:
            wc = csv.DictWriter(cleanfile, fieldnames=fieldnames, extrasaction="ignore", restval="")
            wf = csv.DictWriter(failfile, fieldnames=fieldnames, extrasaction="ignore", restval="")
            wc.writeheader();
            wf.writeheader()
            wc.writerows(sorted_clean)
            wf.writerows(sorted_fail)

        # --- FINAL POST-RUN CHECKS ---

        # 1) Generate missing_addresses.csv and capture its count for the summary
        missing_count = 0
        try:
            missing_count = write_missing_addresses_report(
                input_path=input_file,  # original Input CSV
                clean_path=output_clean,
                fail_path=output_fail,
                out_path="missing_addresses.csv"
            )
        except Exception as e:
            print(f"⚠️ Missing-address check failed: {e}")

        # (keep your split logic here if you like)

        # --- Extended summary (now uses missing_count) ---
        total_imported = len(all_rows)
        total_processed = clean_count + fail_count
        skipped_rows = total_imported - total_processed
        duplicates = sum(1 for r in all_rows if (r.get("Final Status") or "").strip().lower() == "duplicate")
        custom1 = sum(1 for r in all_rows if (r.get("Status") or "").strip().lower() == "custom1")
        donotcall = sum(1 for r in all_rows if (r.get("Status") or "").strip().lower() == "donotcall")

        def _fs(row):
            return (row.get("Final Status") or "").strip().lower()

        geocode_fail_cnt = sum(
            1 for r in sorted_fail
            if _fs(r) in {"geocode fail", "geocode outside auckland/nz"}
        )
        fail_status_cnt = sum(1 for r in sorted_fail if _fs(r) == "fail")
        # removed: missing_cnt from sorted_fail

        print("\n CSV Cleaning Summary")
        print("========================\n")
        print(f"✅ Total Imported Rows:  {total_imported}")
        print(f"✅ Total Processed:      {total_processed}")
        print(f"❌ Skipped Rows:         {skipped_rows}\n")
        print(f"✅ Cleaned Successfully: {clean_count}\n")
        print(f"❌ Total Failed:         {fail_count}")
        print(f" - Duplicate:            {duplicates}")
        print(f" - Not Chinese:          {custom1}")
        print(f" - Do Not Call:          {donotcall}")
        print(f" - Geocode Fail:         {geocode_fail_cnt}")
        print(f" - Fail:                 {fail_status_cnt}")
        print(f" - Missing:              {missing_count}\n")
        print("========================\n")

        _stage_ok("Write Outputs (final)")



    except Exception as e:

        print("❌ Write outputs error:", e)

        print(traceback.format_exc())

        return

    # If the user cancelled, stop here (no post-run checks)

    if cancel_flag.is_set():
        return _cancelled("Write Outputs")

    # --- FINAL POST-RUN CHECKS ---

    try:

        write_missing_addresses_report(

            input_path=input_file,  # original Input.nws.csv

            clean_path=output_clean,

            fail_path=output_fail,

            out_path="missing_addresses.csv"

        )

    except Exception as e:

        print(f"⚠️ Missing-address check failed: {e}")

    try:

        # Use the same headers as the input CSV for splitting

        with open(input_file, "r", encoding="utf-8-sig", errors="replace") as f:

            input_headers = list(csv.DictReader(f).fieldnames or [])

        split_output_clean_if_large(

            src=output_clean,

            dst_prefix="output_clean",

            max_rows=300,

            header=input_headers

        )

    except Exception as e:

        print(f"⚠️ Split check failed: {e}")


def split_cleaned_by_suburb_and_include_failed(clean_file, fail_file):
    out_dir = "New_Addresses_By_Suburb"

    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)

    # Split by suburb

    if os.path.exists(clean_file):
        with open(clean_file, 'r', encoding='utf-8') as infile:
            reader = csv.DictReader(infile)
            fieldnames = reader.fieldnames  # <-- cache once

            for row in tqdm(reader, desc="📂 Splitting By Suburb", unit="row"):
                suburb = row.get("Suburb", "").strip()
                suburb = "Other" if not suburb else suburb.replace(" ", "_")
                suburb_file = os.path.join(out_dir, f"{suburb}.csv")
                write_header = not os.path.exists(suburb_file)
                with open(suburb_file, 'a', newline='', encoding='utf-8') as sf:
                    writer = csv.DictWriter(sf, fieldnames=fieldnames)
                    if write_header:
                        writer.writeheader()
                    writer.writerow(row)


    # Include failed output
    if os.path.exists(fail_file):
        shutil.copy(fail_file, os.path.join(out_dir, "Failed_Output.csv"))

    if cancel_flag.is_set():
        print("⚠️ 'q' Pressed — Cancelling Process...")
        print("⚠️ Cancelled During File Splitting.")
        return None

    # Sort and display output files
    all_files = [f for f in os.listdir(out_dir) if f.strip()]
    normal_files = sorted(f for f in all_files if f not in {"Other.csv", "Failed_Output.csv"})
    special_files = [f for f in ["Other.csv", "Failed_Output.csv"] if f in all_files]
    final_files = normal_files + special_files

    print("\n✅ Cleaned Addresses Split Into Suburbs Inside 'New_Addresses_By_Suburb' Folder")
    print(f"📁 {len(final_files)} file(s) created:\n")
    for f in final_files:
        print(f"    📑 {f}")



# --- Output housekeeping helpers (fix for ensure_delete_outputs_interactive) ---
import os, shutil

def _list_existing_outputs():
    """
    Return a list of output files/folders that this tool creates,
    so we can show & delete them before a new run.
    """
    items = []

    # top-level CSVs written by the pipeline
    for name in [
        "output_clean.csv",
        "output_fail.csv",
        "corrections_log.csv",
        "corrections_log_grouped.csv",
    ]:
        if os.path.exists(name):
            items.append(name)

    # export/split folders (delete whole trees)
    for folder in ["Exported Files", "New_Addresses_By_Suburb"]:
        if os.path.isdir(folder):
            # include files in the folder (nice for preview) and the folder itself (for deletion)
            for root, _dirs, files in os.walk(folder):
                for f in files:
                    items.append(os.path.join(root, f))
            items.append(folder)

    return items

class oth:
    @staticmethod
    def remove_files(paths):
        """Best-effort removal of files or folders listed in `paths`."""
        for p in paths:
            try:
                if os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
                elif os.path.exists(p):
                    os.remove(p)
            except Exception as e:
                print(f"⚠️ Could not remove {p}: {e}")




def ensure_delete_outputs_interactive() -> bool:
    existing = _list_existing_outputs()
    if not existing:
        return True
    print("⚠️ Existing Output Files Detected:")
    for p in existing:
        print(f"   • {p}")
    print("Proceeding Will DELETE These Files.")
    confirm = input("Type 'y' to remove them and continue (anything else to cancel): ").strip().lower()
    if confirm != "y":
        print("❌ Cancelled — Outputs Were Not Deleted.")
        return False
    # call module helper
    oth.remove_files(existing)
    still = _list_existing_outputs()
    if still:
        print("❌ Could Not Remove The Following Files:")
        for p in still:
            print(f"   • {p}")
        return False
    print("✅ Files Removed Successfully...")
    return True

# --- NEW: per-option file collector (files only; never folders)
def _files_created_by_option(option_str: str):
    import os
    files = []

    core = [
        "output_clean.csv",
        "output_fail.csv",
        "corrections_log.csv",
        "corrections_log_grouped.csv",
    ]
    files += [p for p in core if os.path.isfile(p)]

    # Options that create split artifacts
    if option_str in {"3", "4", "7"}:  # ← added "7"
        for d in ["New_Addresses_By_Suburb", "Exported Files"]:
            if os.path.isdir(d):
                for root, _dirs, fns in os.walk(d):
                    for fn in fns:
                        files.append(os.path.join(root, fn))
    return files



# --- NEW: confirm & delete only the related files for a given option
def ensure_delete_option_outputs_interactive(option_str: str) -> bool:
    """
    Show and delete only the files created by a specific menu option.
    Folders are *never* removed; we only list & delete files.
    """
    targets = _files_created_by_option(option_str)
    if not targets:
        print("No existing output files to remove.")
        return True

    print("Existing output files for this option will be DELETED (folders will be kept):")
    for p in targets:
        print(f"   • {p}")

    confirm = input("Type 'y' to delete these files and continue (anything else to cancel): ").strip().lower()
    if confirm != "y":
        print("❌ Cancelled — no files were deleted.")
        return False

    removed = 0
    for p in targets:
        try:
            os.remove(p)   # files only
            removed += 1
        except Exception as e:
            print(f"⚠️ Could not remove {p}: {e}")

    print(f"✅ Removed {removed} file(s).")
    return True


# --- Option 7: New Streets (called by Clean_GoogleSheets option 3) -----------
import os
import sys

def option7_clean_split_new_streets(clean_path: str, fail_path: str, kml_dir: str = "KML Boundaries"):
    """
    New World Scheduler — Option 7
    Accepts output_clean/output_fail produced by the Google Sheets 'New Streets' flow
    and runs the usual split/export pipeline. (Rows were already filtered upstream.)
    """
    print("\n====================================================================")
    print("  Option 7 — Clean & Split Into Different Suburbs (New Streets)")
    print("--------------------------------------------------------------------")
    print(f"  Clean CSV : {os.path.abspath(clean_path)}")
    print(f"  Fail  CSV : {os.path.abspath(fail_path)}")
    print(f"  KML Dir   : {os.path.abspath(kml_dir)}")
    print("====================================================================\n")

    try:
        # 0) Validate inputs
        if not os.path.exists(clean_path):
            print(f"❌ Clean file not found: {clean_path}")
            return None
        if not os.path.exists(fail_path):
            print(f"⚠️  Fail file not found (continuing): {fail_path}")

        # 1) Resolve splitter function from this module (or elsewhere if you moved it)
        split_fn = None
        # try current module first
        split_fn = globals().get("split_cleaned_by_polygon_and_include_failed")
        if split_fn is None:
            # optional: if you moved the splitter to another module, import it here:
            # from GeoPackage_Borders import split_cleaned_by_polygon_and_include_failed as split_fn
            pass

        if split_fn is None or not callable(split_fn):
            print("❌ Could not find 'split_cleaned_by_polygon_and_include_failed'. "
                  "Ensure it is defined/imported in Clean_NewWorldScheduler.py.")
            return None

        # 2) Prefer a 'new_streets_only' flag if supported, else fall back
        try:
            result = split_fn(clean_path, fail_path, kml_dir=kml_dir, new_streets_only=True)
            print("✅ Split complete (new_streets_only=True).")
            return result
        except TypeError:
            # older signature without the flag
            result = split_fn(clean_path, fail_path, kml_dir=kml_dir)
            print("ℹ️  Splitter does not support 'new_streets_only'; ran standard split.")
            return result

    except KeyboardInterrupt:
        print("⛔ Interrupted.")
        return None
    except Exception as e:
        print(f"❌ Option 7 failed: {e}")
        return None




# --- Update menu actions to use the new file-only cleaner
def run_clean_normal_after_purge(expected_headers):
    if not ensure_delete_option_outputs_interactive("1"):
        return
    log_correction("Session Start", "Corrections log recreated after deletion or fresh start.")
    process_csv("input_nws.csv", "output_clean.csv", "output_fail.csv", expected_headers, verify_geocode=False,
                geocode_scope="missing")

def run_clean_verify_after_purge(expected_headers):
    if not ensure_delete_option_outputs_interactive("2"):
        return
    log_correction("Session Start", "Corrections log recreated after deletion or fresh start.")
    process_csv("input_nws.csv", "output_clean.csv", "output_fail.csv", expected_headers, verify_geocode=True)

def run_clean_and_split_after_purge():
    if not ensure_delete_option_outputs_interactive("3"):
        return
    log_correction("Session Start", "Corrections log recreated after deletion or fresh start.")
    process_csv(
        "input_nws.csv",
        "output_clean.csv",
        "output_fail.csv",
        expected_headers=["Number","Street","Suburb","PostalCode","Status","Latitude","Longitude"],
        verify_geocode=False,
        geocode_scope="missing")
    split_cleaned_by_polygon_and_include_failed("output_clean.csv", "output_fail.csv", kml_dir="KML Boundaries")

def run_clean_verify_and_split_after_purge():
    if not ensure_delete_option_outputs_interactive("4"):
        return
    log_correction("Session Start", "Corrections log recreated after deletion or fresh start.")
    process_csv(
        "input_nws.csv",
        "output_clean.csv",
        "output_fail.csv",
        expected_headers=EXPECTED_HEADERS,
        verify_geocode=True
    )
    split_cleaned_by_polygon_and_include_failed("output_clean.csv", "output_fail.csv", kml_dir="KML Boundaries")


import shutil, os

def ensure_delete_suburb_dir_interactive() -> bool:
    out_dir = "New_Addresses_By_Suburb"
    if not os.path.exists(out_dir):
        return True
    print(f"⚠️ Folder '{out_dir}' already exists. It will be DELETED.")
    confirm = input("Type 'y' to remove it and continue (anything else to cancel): ").strip().lower()
    if confirm != "y":
        print("❌ Cancelled — Folder was not deleted.")
        return False
    try:
        shutil.rmtree(out_dir)
        print("✅ Folder removed.")
        return True
    except Exception as e:
        print(f"❌ Could not remove '{out_dir}': {e}")
        return False


EXPECTED_HEADERS = ["Number","Street","Suburb","PostalCode","Status","Latitude","Longitude"]

def run_clean_verify_and_split_after_purge():
    """Option 4: verify + polygon split, but abort if the user declines deletion."""
    if not ensure_delete_suburb_dir_interactive():
        return
    if 'log_correction' in globals():
        log_correction("Session Start", "Corrections log recreated after deletion or fresh start.")
    process_csv(
        "input_nws.csv",
        "output_clean.csv",
        "output_fail.csv",
        expected_headers=EXPECTED_HEADERS,
        verify_geocode=True
    )
    split_cleaned_by_polygon_and_include_failed("output_clean.csv", "output_fail.csv", kml_dir="KML Boundaries")


def open_menu():
    actions = {
        "1": lambda: run_clean_normal_after_purge(EXPECTED_HEADERS),
        "2": lambda: run_clean_verify_after_purge(EXPECTED_HEADERS),
        "3": run_clean_and_split_after_purge,
        "4": run_clean_verify_and_split_after_purge,
        "5": lambda: run_clean_live_after_purge(EXPECTED_HEADERS),
        "6": lambda: run_clean_verify_live_after_purge(EXPECTED_HEADERS),
        "7": run_clean_verify_and_split_newstreets_after_purge,  # ← NEW
        "0": lambda: None,
    }

    while True:
        print("\n\033[4mNew World Scheduler (input_nws)\033[0m")
        print("1 - ✨ Run CSV File Cleaning")
        print("2 - ✨ Run CSV File Cleaning (Full Geocode Check)")
        print("3 - ✨ Clean & Split Into Different Suburbs")
        print("4 - ✨ Clean & Split Into Different Suburbs (Full Geocode Check)")
        print("5 - ✨ Run CSV File Cleaning (Live Updating)")
        print("6 - ✨ Run CSV File Cleaning (Live Updating + Full Geocode Check)")
        print("7 - ✨ Clean & Split Into Different Suburbs (New Streets - Full Geocode Check)")

        print("\n0 - Back/Exit")

        pick = input("\nChoose (0/1/2/3/4/5/6): ").strip()

        if pick not in actions:
            print("❌ Invalid choice.\n")
            continue

        if pick == "0":
            break
        actions[pick]()  # run the selected action



if __name__ == "__main__":
    try:
        open_menu()
    except KeyboardInterrupt:
        print("\n👋 Exiting...")



