#!/usr/bin/env python3
"""
GoogleSheets_CoreLite_Polygons.py

Purpose
-------
Polygon/KML split logic + geometry helpers.

Exports (as requested)
----------------------
- split_cleaned_by_polygon_and_include_failed
- split_cleaned_by_suburb_and_include_failed
- _safe_float
- _digits_int
- _point_in_poly
- _point_on_segment
- _dist_point_to_segment
- _min_dist_to_polygon
- _load_kml_polygons
- _assign_point_to_polygons
- _pick_nearest_number_target
- canon_suburb

Key globals/constants (copy-safe)
---------------------------------
- NEARBY_SUBURBS
- NEARBY_ALIAS
- any polygon/KML config constants used by the above functions

Assumptions / compatibility
---------------------------
- Input rows are dict-like with at least: 'Latitude','Longitude','Suburb'
  and optionally 'Number','Street' for naming outputs.
- KML polygons are expected as files with <Placemark><name>Suburb</name> and
  <coordinates>lon,lat[,alt] ...</coordinates>.
- This module is standalone (no import from GoogleSheets_CoreLite to avoid circulars).
"""

from __future__ import annotations

import os
import re
import math
import glob
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Optional, Iterable

from GoogleSheets_Log import module_loaded  # noqa: E402
module_loaded(__name__)

# -----------------------------------------------------------------------------
# Constants / aliasing
# -----------------------------------------------------------------------------

# Used to normalize suburbs. Keep these minimal; your Utils layer can also apply its own rules.
NEARBY_ALIAS: dict[str, str] = {
    # examples / safe defaults — extend as needed
    "Mt Eden": "Mount Eden",
    "Mt Wellington": "Mount Wellington",
    "St Heliers": "Saint Heliers",
    "St Johns": "Saint Johns",
    "Pts Chev": "Point Chevalier",
    "Pt Chev": "Point Chevalier",
}

# Suburbs that are allowed to “borrow” polygons when a point is close to borders.
# (This is best-effort, not critical; extend as needed.)
NEARBY_SUBURBS: dict[str, set[str]] = {
    "Remuera": {"Newmarket", "Parnell", "Epsom", "Saint Johns"},
    "Epsom": {"Mount Eden", "Greenlane", "Royal Oak", "Remuera"},
    "Mount Eden": {"Epsom", "Kingsland", "Balmoral"},
}

# Default folder(s) to search for polygons
POLYGON_DIR_CANDIDATES = [
    "Territory_Maps",          # common in your project
    "Territory Maps",
    "Polygons",
    "KML",
]

# -----------------------------------------------------------------------------
# Small helpers
# -----------------------------------------------------------------------------

def _safe_float(x) -> Optional[float]:
    try:
        if x is None:
            return None
        s = str(x).strip()
        if s == "":
            return None
        return float(s)
    except Exception:
        return None


def _digits_int(x) -> int:
    try:
        s = re.sub(r"\D+", "", str(x or ""))
        return int(s) if s else 0
    except Exception:
        return 0


def canon_suburb(suburb: str) -> str:
    s = (suburb or "").strip()
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s)
    # normalize case
    s = " ".join(p.capitalize() if p.lower() not in {"of", "the"} else p.lower() for p in s.split())
    return NEARBY_ALIAS.get(s, s)


# -----------------------------------------------------------------------------
# Geometry
# -----------------------------------------------------------------------------

def _point_on_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float, eps: float = 1e-10) -> bool:
    # colinear + within bbox
    cross = (px - ax) * (by - ay) - (py - ay) * (bx - ax)
    if abs(cross) > eps:
        return False
    dot = (px - ax) * (px - bx) + (py - ay) * (py - by)
    return dot <= eps


def _point_in_poly(px: float, py: float, poly: list[tuple[float, float]]) -> bool:
    """
    Ray casting algorithm. poly is list of (lon, lat) pairs.
    """
    inside = False
    n = len(poly)
    if n < 3:
        return False

    x, y = px, py
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]

        # Point exactly on edge counts as inside
        if _point_on_segment(x, y, x1, y1, x2, y2):
            return True

        # Ray cast
        intersects = ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-30) + x1)
        if intersects:
            inside = not inside

    return inside


def _dist_point_to_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    """
    Distance in degrees-space (approx). Used only for "nearest polygon" tie-breaking.
    """
    vx, vy = bx - ax, by - ay
    wx, wy = px - ax, py - ay
    c1 = vx * wx + vy * wy
    if c1 <= 0:
        return math.hypot(px - ax, py - ay)
    c2 = vx * vx + vy * vy
    if c2 <= 0:
        return math.hypot(px - ax, py - ay)
    t = c1 / c2
    if t >= 1:
        return math.hypot(px - bx, py - by)
    projx, projy = ax + t * vx, ay + t * vy
    return math.hypot(px - projx, py - projy)


def _min_dist_to_polygon(px: float, py: float, poly: list[tuple[float, float]]) -> float:
    """
    Minimum distance from point to any polygon edge.
    """
    if len(poly) < 2:
        return float("inf")
    best = float("inf")
    for i in range(len(poly)):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % len(poly)]
        d = _dist_point_to_segment(px, py, ax, ay, bx, by)
        if d < best:
            best = d
    return best


# -----------------------------------------------------------------------------
# KML/KMZ loading
# -----------------------------------------------------------------------------

def _iter_kml_paths(base_dir: Path) -> Iterable[Path]:
    """
    Yield .kml and .kmz files under base_dir.

    PATCHED:
    - Uses rglob so nested territory-map folders are supported.
    - Includes both lowercase and uppercase extensions.
    """
    # include both .kml and .kmz (case-insensitive)
    patterns = ("*.kml", "*.kmz", "*.KML", "*.KMZ")
    for pat in patterns:
        try:
            for p in base_dir.rglob(pat):
                yield p
        except Exception:
            continue


def _find_polygon_dirs() -> list[Path]:
    """
    Find candidate folders that may contain .kml/.kmz files.

    Portability goals:
    - Search relative to this module folder (dev runs)
    - Search relative to module parent (when modules are in a subfolder)
    - Search relative to current working directory (when launched from elsewhere)
    - Search relative to EXE folder when frozen (PyInstaller)
    """
    import sys

    here = Path(__file__).resolve().parent
    candidates: list[Path] = []

    # 1) Module folder + parent folder (common layout: /src/GoogleSheets_*.py, KML in parent)
    bases: list[Path] = [here]
    try:
        bases.append(here.parent)
    except Exception:
        pass

    # 2) Current working directory
    try:
        bases.append(Path.cwd())
    except Exception:
        pass

    # 3) PyInstaller EXE folder
    try:
        if getattr(sys, "frozen", False):
            bases.append(Path(sys.executable).resolve().parent)
    except Exception:
        pass

    # For each base, add common subfolders + base itself
    for base in bases:
        try:
            if base.exists() and base.is_dir():
                candidates.append(base)
        except Exception:
            pass

        for d in POLYGON_DIR_CANDIDATES:
            try:
                p = base / d
                if p.exists() and p.is_dir():
                    candidates.append(p)
            except Exception:
                continue

    # Dedupe while preserving order
    uniq: list[Path] = []
    seen = set()
    for p in candidates:
        try:
            key = str(p.resolve())
        except Exception:
            key = str(p)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)

    return uniq



def _read_kml_text(path: Path) -> str:
    if path.suffix.lower() == ".kmz":
        with zipfile.ZipFile(path, "r") as z:
            # usually "doc.kml", but pick first kml
            names = [n for n in z.namelist() if n.lower().endswith(".kml")]
            if not names:
                return ""
            return z.read(names[0]).decode("utf-8", errors="replace")
    return path.read_text(encoding="utf-8", errors="replace")


def _load_kml_polygons(kml_dir: str | Path | None = None) -> dict[str, list[list[tuple[float, float]]]]:
    """
    Returns:
      { suburb_name: [ polygon1_points, polygon2_points, ... ] }
    where each polygon points is list[(lon,lat)].

    If kml_dir is provided and exists, it is searched FIRST.
    Then we fall back to this module’s auto-discovery dirs.
    """
    polygons: dict[str, list[list[tuple[float, float]]]] = {}

    # Build search dirs (kml_dir first if valid)
    search_dirs: list[Path] = []
    try:
        if kml_dir is not None:
            kd = Path(kml_dir)
            if kd.exists() and kd.is_dir():
                search_dirs.append(kd)
    except Exception:
        pass

    # Auto-discovery dirs (module-local)
    try:
        search_dirs.extend(_find_polygon_dirs())
    except Exception:
        # last-resort fallback
        search_dirs.append(Path(__file__).resolve().parent)

    # Dedupe dirs
    seen_dirs = set()
    uniq_dirs: list[Path] = []
    for d in search_dirs:
        try:
            rp = str(d.resolve())
        except Exception:
            rp = str(d)
        if rp not in seen_dirs:
            seen_dirs.add(rp)
            uniq_dirs.append(d)

    # Parse KML/KMZ files
    for d in uniq_dirs:
        for kml_path in _iter_kml_paths(d):
            try:
                text = _read_kml_text(kml_path)
                if not text.strip():
                    continue
                root = ET.fromstring(text)

                # namespaces are common in KML
                ns = {}
                if "}" in root.tag:
                    ns_uri = root.tag.split("}")[0].strip("{")
                    ns = {"kml": ns_uri}

                placemarks = root.findall(".//kml:Placemark", ns) if ns else root.findall(".//Placemark")
                if not placemarks:
                    placemarks = root.findall(".//Placemark")

                for pm in placemarks:
                    name_el = pm.find("kml:name", ns) if ns else pm.find("name")
                    if name_el is None:
                        name_el = pm.find(".//name")
                    name = canon_suburb((name_el.text or "").strip() if name_el is not None else "")
                    if not name:
                        continue

                    coords_els = pm.findall(".//kml:coordinates", ns) if ns else pm.findall(".//coordinates")
                    if not coords_els:
                        coords_els = pm.findall(".//coordinates")
                    if not coords_els:
                        continue

                    for ce in coords_els:
                        raw = (ce.text or "").strip()
                        if not raw:
                            continue
                        pts: list[tuple[float, float]] = []
                        for token in raw.replace("\n", " ").split():
                            parts = token.split(",")
                            if len(parts) < 2:
                                continue
                            lon = _safe_float(parts[0])
                            lat = _safe_float(parts[1])
                            if lon is None or lat is None:
                                continue
                            pts.append((lon, lat))
                        if len(pts) >= 3:
                            polygons.setdefault(name, []).append(pts)
            except Exception:
                continue

    return polygons



# -----------------------------------------------------------------------------
# Assignment helpers
# -----------------------------------------------------------------------------

def _assign_point_to_polygons(
    lon: float,
    lat: float,
    polygons_by_name: dict[str, list[list[tuple[float, float]]]]
) -> Optional[str]:
    """
    Returns suburb/polygon name that contains the point.

    If multiple polygons contain it, choose the one with the LARGEST
    min distance to edge (i.e. the point is more "central" inside that polygon).

    NOTE:
    - _min_dist_to_polygon returns the minimum distance to any edge.
      Larger => deeper inside. Smaller => nearer boundary.
    """
    best_name: Optional[str] = None
    best_score = -1.0  # maximize distance-to-edge

    for name, polys in (polygons_by_name or {}).items():
        for poly in polys or []:
            if _point_in_poly(lon, lat, poly):
                score = _min_dist_to_polygon(lon, lat, poly)
                if score > best_score:
                    best_score = score
                    best_name = name

    return best_name



def _pick_nearest_number_target(row: dict[str, Any], assigned_name: str, fallback_name: str) -> str:
    """
    If the row seems to have a numeric target that aligns with a neighbor suburb better, choose that.
    Kept simple: currently returns assigned_name when present else fallback_name.
    """
    return assigned_name or fallback_name


# -----------------------------------------------------------------------------
# Main splitters
# -----------------------------------------------------------------------------
def split_cleaned_by_polygon_and_include_failed(
    clean_csv: str,
    fail_csv: str,
    *,
    kml_dir: str = "KML Boundaries",
    out_dir: str | Path = "New_Addresses_By_Suburb",
    failed_bucket_name: str = "__FAILED__",
    new_streets_only: bool = False,
    **_ignored_kwargs,
) -> Path:
    """
    File-based splitter (legacy-compatible with Clean_GoogleSheets expectations).

    PATCHED (legacy output parity):
    - Ensures both 'PostalCode' and legacy 'Postcode' columns exist in output headers.
    - Mirrors values between them so downstream sheets/legacy tooling sees 'Postcode'.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---- Local helpers ----
    def _read_rows(path: str) -> tuple[list[str], list[dict[str, Any]]]:
        import csv
        if not path or not os.path.exists(path):
            return ([], [])
        with open(path, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            fieldnames = r.fieldnames or []
            return (fieldnames, list(r))

    def _write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
        import csv
        with open(path, "w", newline="", encoding="utf-8", buffering=1024 * 1024) as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for row in rows:
                w.writerow({k: row.get(k, "") for k in fieldnames})

    def _safe_file_stem(name: str) -> str:
        """
        Make a Windows-safe filename stem (no path separators / reserved characters).
        Also collapses whitespace and trims trailing dots/spaces (Windows restriction).
        """
        s = str(name or "").strip()
        if not s:
            return failed_bucket_name

        # Replace path separators and reserved filename chars
        s = re.sub(r'[\\/:*?"<>|]+', "_", s)

        # Collapse whitespace
        s = re.sub(r"\s+", " ", s).strip()

        # Windows forbids trailing dot/space
        s = s.rstrip(". ").strip()

        return s or failed_bucket_name

    # More robust "new street(s)" detector (parity with Utils behavior)
    _NEW_STREET_DETECT_RX_LOCAL = re.compile(r"\bnew\s*street(s)?\b", re.IGNORECASE)

    def _bucket_name(display_name: str) -> str:
        n = canon_suburb(display_name)
        return n or failed_bucket_name

    def _looks_like_new_street(row: dict[str, Any]) -> bool:
        # Standalone heuristic (no Utils import):
        notes = str(row.get("Notes") or "")
        return bool(_NEW_STREET_DETECT_RX_LOCAL.search(notes))

    def _ensure_postcode_alias(fieldnames: list[str], rows: list[dict[str, Any]]) -> list[str]:
        """
        Ensure BOTH columns exist:
          - PostalCode  (new)
          - Postcode    (legacy)
        And mirror values across.
        """
        if not fieldnames:
            return fieldnames

        # Quick membership checks (case-sensitive because DictWriter uses exact keys)
        has_postal = "PostalCode" in fieldnames
        has_post = "Postcode" in fieldnames

        # Decide insertion position: right after Suburb if possible, else append.
        def _insert_after(col_name: str, new_col: str) -> None:
            if new_col in fieldnames:
                return
            try:
                i = fieldnames.index(col_name)
                fieldnames.insert(i + 1, new_col)
            except ValueError:
                fieldnames.append(new_col)

        if has_postal and not has_post:
            _insert_after("PostalCode", "Postcode")  # keep near the canonical column
        elif has_post and not has_postal:
            _insert_after("Postcode", "PostalCode")

        # Mirror values
        for r in rows or []:
            pc = (r.get("PostalCode") or "").strip()
            p  = (r.get("Postcode") or "").strip()

            if pc and not p:
                r["Postcode"] = pc
            elif p and not pc:
                r["PostalCode"] = p

        return fieldnames

    def _assign_rows(
        rows: list[dict[str, Any]],
        polygons_by_name: dict[str, list[list[tuple[float, float]]]],
    ) -> dict[str, list[dict[str, Any]]]:
        buckets: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            if new_streets_only and not _looks_like_new_street(row):
                continue

            lat = _safe_float(row.get("Latitude"))
            lon = _safe_float(row.get("Longitude"))
            if lat is None or lon is None:
                buckets.setdefault(failed_bucket_name, []).append(row)
                continue

            name = _assign_point_to_polygons(float(lon), float(lat), polygons_by_name)
            if not name:
                buckets.setdefault(failed_bucket_name, []).append(row)
                continue

            buckets.setdefault(_bucket_name(name), []).append(row)
        return buckets

    # ---- Load polygons (kml_dir first, then auto-discovery) ----
    try:
        polygons = _load_kml_polygons(kml_dir=kml_dir)
    except TypeError:
        polygons = _load_kml_polygons()

    # ---- Read clean + fail CSVs ----
    clean_fields, clean_rows = _read_rows(clean_csv)
    fail_fields, fail_rows = _read_rows(fail_csv)

    fieldnames = clean_fields or fail_fields
    if not fieldnames:
        return out_dir

    # PATCH: ensure Postcode/PostalCode alias exists in headers + rows
    fieldnames = _ensure_postcode_alias(list(fieldnames), clean_rows + fail_rows)

    # ---- Assign rows to buckets ----
    clean_buckets = _assign_rows(clean_rows, polygons) if clean_rows else {}
    fail_buckets  = _assign_rows(fail_rows, polygons) if fail_rows else {}

    # ---- Write out suburb CSVs (WINDOWS-SAFE FILENAMES) ----
    for suburb, rows in clean_buckets.items():
        stem = _safe_file_stem(suburb)
        _write_rows(out_dir / f"{stem}.csv", fieldnames, rows)

    for suburb, rows in fail_buckets.items():
        stem = _safe_file_stem(suburb)
        _write_rows(out_dir / f"{stem} failed.csv", fieldnames, rows)

    return out_dir





def split_cleaned_by_suburb_and_include_failed(
    clean_csv: str,
    fail_csv: str,
    *,
    out_dir: str | Path = "New_Addresses_By_Suburb",
    failed_bucket_name: str = "__FAILED__",
) -> Path:
    """
    File-based splitter by row['Suburb'] (legacy-compatible signature used by some flows).

    PATCHED (legacy output parity):
    - Ensures both 'PostalCode' and legacy 'Postcode' columns exist in output headers.
    - Mirrors values between them so downstream sheets/legacy tooling sees 'Postcode'.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    import csv

    def _safe_file_stem(name: str) -> str:
        s = str(name or "").strip()
        if not s:
            return failed_bucket_name
        s = re.sub(r'[\\/:*?"<>|]+', "_", s)
        s = re.sub(r"\s+", " ", s).strip()
        s = s.rstrip(". ").strip()
        return s or failed_bucket_name

    def _read_rows(path: str) -> tuple[list[str], list[dict[str, Any]]]:
        if not path or not os.path.exists(path):
            return ([], [])
        with open(path, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            fieldnames = r.fieldnames or []
            return (fieldnames, list(r))

    def _write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
        with open(path, "w", newline="", encoding="utf-8", buffering=1024 * 1024) as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for row in rows:
                w.writerow({k: row.get(k, "") for k in fieldnames})

    def _bucket(sub: str) -> str:
        s = canon_suburb(str(sub or "").strip())
        return s or failed_bucket_name

    def _ensure_postcode_alias(fieldnames: list[str], rows: list[dict[str, Any]]) -> list[str]:
        if not fieldnames:
            return fieldnames

        has_postal = "PostalCode" in fieldnames
        has_post = "Postcode" in fieldnames

        def _insert_after(col_name: str, new_col: str) -> None:
            if new_col in fieldnames:
                return
            try:
                i = fieldnames.index(col_name)
                fieldnames.insert(i + 1, new_col)
            except ValueError:
                fieldnames.append(new_col)

        if has_postal and not has_post:
            _insert_after("PostalCode", "Postcode")
        elif has_post and not has_postal:
            _insert_after("Postcode", "PostalCode")

        for r in rows or []:
            pc = (r.get("PostalCode") or "").strip()
            p  = (r.get("Postcode") or "").strip()
            if pc and not p:
                r["Postcode"] = pc
            elif p and not pc:
                r["PostalCode"] = p

        return fieldnames

    clean_fields, clean_rows = _read_rows(clean_csv)
    fail_fields, fail_rows = _read_rows(fail_csv)
    fieldnames = clean_fields or fail_fields
    if not fieldnames:
        return out_dir

    # PATCH: ensure Postcode/PostalCode alias exists in headers + rows
    fieldnames = _ensure_postcode_alias(list(fieldnames), clean_rows + fail_rows)

    clean_buckets: dict[str, list[dict[str, Any]]] = {}
    for row in clean_rows:
        clean_buckets.setdefault(_bucket(row.get("Suburb", "")), []).append(row)

    fail_buckets: dict[str, list[dict[str, Any]]] = {}
    for row in fail_rows:
        fail_buckets.setdefault(_bucket(row.get("Suburb", "")), []).append(row)

    for suburb, rows in clean_buckets.items():
        stem = _safe_file_stem(suburb)
        _write_rows(out_dir / f"{stem}.csv", fieldnames, rows)

    for suburb, rows in fail_buckets.items():
        stem = _safe_file_stem(suburb)
        _write_rows(out_dir / f"{stem} failed.csv", fieldnames, rows)

    return out_dir

