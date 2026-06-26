#Python Expert - Here's my script in different parts, please read as one file. Give suggestions after you recieved all the parts
# This script is split into 4 parts in total
# Part 1/4 Start
# Clean_NewWorldScheduler.py

import json
import logging
# --- OPTIONAL dependency: nest_asyncio ---------------------------------
# For portability, do NOT hard-fail if it's missing.
try:
    import nest_asyncio  # type: ignore
    try:
        nest_asyncio.apply()
    except Exception:
        pass
except ModuleNotFoundError:
    nest_asyncio = None  # type: ignore
# -----------------------------------------------------------------------

from datetime import datetime
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from random import uniform
from typing import Optional
try:
    from tqdm import tqdm  # type: ignore
except Exception:
    def tqdm(iterable=None, **kwargs):
        return iterable if iterable is not None else range(0)

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

# ---------------------------------------------------------------------
# Portable app root bootstrap (MUST be near the top, before paths are used)
# ---------------------------------------------------------------------
from pathlib import Path

def _app_root() -> Path:
    """
    If frozen (PyInstaller), use the EXE's folder; else use this file's folder.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

APP_ROOT = _app_root()

def _portable_bootstrap_here() -> None:
    """
    Make this module runnable from anywhere:
      - force working directory to APP_ROOT
      - ensure APP_ROOT is on sys.path for sibling imports
    Safe to call multiple times.
    """
    try:
        os.chdir(APP_ROOT)
    except Exception:
        pass

    try:
        sp = str(APP_ROOT)
        if sp not in sys.path:
            sys.path.insert(0, sp)
    except Exception:
        pass

def resource_path(rel: str) -> str:
    """
    Resolve a resource path for:
      - loose .py runs (next to script)
      - PyInstaller onefile (inside _MEIPASS)
      - PyInstaller onefolder (next to EXE)
    """
    # 1) Next to EXE / script (preferred)
    p1 = APP_ROOT / rel
    if p1.exists():
        return str(p1)

    # 2) Inside PyInstaller onefile bundle extraction
    base = getattr(sys, "_MEIPASS", None)
    if base:
        p2 = Path(base) / rel
        if p2.exists():
            return str(p2)

    # 3) Fallback to APP_ROOT/rel even if it doesn't exist (callers may create it)
    return str(p1)

_portable_bootstrap_here()

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

    PORTABLE:
    - If kml_dir is relative, treat it as relative to APP_ROOT.
    - Works for normal runs and for PyInstaller bundles (if you ship the folder).
    """
    polys = {}

    # Resolve folder robustly
    try:
        base = Path(kml_dir)
        if not base.is_absolute():
            # Prefer APP_ROOT if available
            try:
                base = Path(APP_ROOT) / base
            except Exception:
                base = Path(os.getcwd()) / base
        kml_dir_path = base
    except Exception:
        kml_dir_path = Path(kml_dir)

    if not kml_dir_path.is_dir():
        print(f"⚠️ KML folder not found: {kml_dir_path}")
        return polys

    for fname in os.listdir(str(kml_dir_path)):
        if not fname.lower().endswith(".kml"):
            continue
        path = kml_dir_path / fname
        name = path.stem  # suburb name
        try:
            tree = ET.parse(str(path))
            root = tree.getroot()

            # KML can have namespaces; find them loosely
            ns = {}
            if root.tag.startswith("{"):
                uri = root.tag.split("}")[0][1:]
                ns["k"] = uri

            coords_texts = []

            # Polygons & MultiGeometry
            for elem in root.findall(".//k:Polygon", ns) + root.findall(".//Polygon", ns):
                for ring in (
                    elem.findall(".//k:outerBoundaryIs/k:LinearRing/k:coordinates", ns)
                    + elem.findall(".//outerBoundaryIs/LinearRing/coordinates", ns)
                ):
                    if ring.text:
                        coords_texts.append(ring.text)

            if not coords_texts:
                # try simple coordinates under <coordinates> directly
                for ring in root.findall(".//k:coordinates", ns) + root.findall(".//coordinates", ns):
                    if ring.text:
                        coords_texts.append(ring.text)

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
    """
    Locate and load the Option 9 plugin once.

    Portable rules:
    - Prefer APP_ROOT (set by the portable bootstrap).
    - Also check PyInstaller _MEIPASS if present.
    - Still accept base_dir param for compatibility, but we don't trust it.
    """
    # Prefer the portable root if available
    try:
        root = APP_ROOT  # defined by the portable bootstrap near top of file
    except Exception:
        root = base_dir

    roots = []
    try:
        if root:
            roots.append(Path(root))
    except Exception:
        pass

    # PyInstaller onefile extraction dir
    try:
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            roots.append(Path(meipass))
    except Exception:
        pass

    # Also include the passed base_dir last (legacy)
    try:
        if base_dir:
            roots.append(Path(base_dir))
    except Exception:
        pass

    # De-dupe roots
    seen = set()
    uniq_roots = []
    for r in roots:
        rp = str(r.resolve()) if r.exists() else str(r)
        if rp not in seen:
            seen.add(rp)
            uniq_roots.append(r)

    # Candidate plugin locations (relative to each root)
    rel_candidates = [
        Path("GeoPackage Borders.py"),
        Path("GeoPackage Borders") / "GeoPackage Borders.py",
        Path("GeoPackage Borders") / "__init__.py",
        Path("GeoPackage Borders") / "option9.py",
    ]

    for r in uniq_roots:
        for rel in rel_candidates:
            p = (r / rel)
            mod = _load_module_from_path("geo_pkg_borders_option9", p)
            if isinstance(mod, types.ModuleType) and hasattr(mod, "extract_suburb_from_gpkg"):
                print(f"🔌 Option 9 plugin loaded from: {p}")
                return mod

    print("🔎 Option 9 plugin not found — option 9 will show a help message.")
    return None



_BASE_DIR = APP_ROOT
_OPTION9_MOD = _load_option9_plugin(_BASE_DIR)
BASE_DIR = APP_ROOT




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
# --- OPTIONAL dependency: nest_asyncio ---------------------------------
# This is only needed in certain environments (e.g., embedded event loops).
# For portability, do NOT hard-fail if it's missing.
try:
    import nest_asyncio  # type: ignore
    try:
        nest_asyncio.apply()
    except Exception:
        # If apply fails, continue normally (portable behavior)
        pass
except ModuleNotFoundError:
    nest_asyncio = None  # type: ignore
# -----------------------------------------------------------------------

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
# Part 1/4 End
