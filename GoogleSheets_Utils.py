#!/usr/bin/env python3
"""
GoogleSheets_Utils.py

Purpose
-------
Utilities for the Google Sheets cleaner/splitter:
- Portable bootstrap + APP_ROOT
- Canon/text helpers + parsing helpers
- Geocode decision helpers (choose best coordinate, accept updates)
- Cached geocode wrappers
- Filesystem helpers (merge CSVs, clear dirs, count rows)
- Suburb whitelist + postcode helpers

Design / Imports
----------------
- Imports GoogleSheets_CoreLite as core (drop-in replacement for the NWS core helpers).
- Does NOT import Flows or Menu (prevents circular imports).

Notes
-----
Function bodies below are copied verbatim from Clean_GoogleSheets.py so behavior matches
the legacy script. Keep edits minimal unless you are intentionally changing behavior.
"""

from __future__ import annotations

import os
import sys
import re
import csv
import shutil
import unicodedata
from pathlib import Path
from functools import lru_cache
from typing import Any, Optional
import difflib

# --- Logging: record module import as early as possible ---
from GoogleSheets_Log import module_loaded  # noqa: E402
module_loaded(__name__)

# ---------------------------------------------------------------------
# Polygon suburb name cleanup (shapefile label suffix)
# ---------------------------------------------------------------------
POLY_OFFICIALSHP_TAIL_RX = re.compile(r"\s*polygon\s*officialshp[\s\.\-_]*$", re.IGNORECASE)
POLY_POLYGON_TAIL_RX     = re.compile(r"\s*polygon[\s\.\-_]*$", re.IGNORECASE)
POLY_OFFICIALSHP_ONLY_RX = re.compile(r"\s*officialshp[\s\.\-_]*$", re.IGNORECASE)


# Known polygon suburb typos seen in shapefile names
_POLYGON_SUBURB_FIXES = {
    "East Tmaki Heights": "East Tamaki Heights",
}

# =============================================================================
# Portable app root bootstrap ...
# =============================================================================
def _normalize_polygon_suburb_name(name: str) -> str:
    """
    Normalize suburb names coming from polygon/shapefile sources so they match
    nz_postal_lookup keys (CoreLite_Geocode).

    Examples:
      "Flat Bush Polygon Officialshp" -> "Flat Bush"
      "East Tmaki Heights Polygon Officialshp" -> "East Tamaki Heights"
    """
    s = (name or "").strip()
    if not s:
        return ""

    # Strip shapefile tail labels (tolerant + case-insensitive)
    s = POLY_OFFICIALSHP_TAIL_RX.sub("", s)
    s = POLY_POLYGON_TAIL_RX.sub("", s)
    s = POLY_OFFICIALSHP_ONLY_RX.sub("", s)

    s = re.sub(r"\s{2,}", " ", s).strip()

    # Apply known fixups (after stripping suffixes)
    s = _POLYGON_SUBURB_FIXES.get(s, s)

    return s


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


_portable_bootstrap_here()

# =============================================================================
# CoreLite dependency (drop-in "core")
# =============================================================================

import GoogleSheets_CoreLite as core

# =============================================================================
# Module-level constants / regexes (copied from legacy)
# =============================================================================

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

# ✅ New: robust "New Street(s)" detector (kept here for compatibility even if flows own it)
NEW_STREET_DETECT_RX = re.compile(r"\bnew\s*street(s)?\b", re.IGNORECASE)

# --- add near the other module-level constants ---
_SUPPRESS_TEMP_DIR_WARNINGS = True

# Unit flip patterns (also used by Master/other modules)
HOUSE_FLIP_A = re.compile(r'^\s*unit\s*([A-Za-z0-9]+)\s*/\s*(\d+[A-Za-z]?)\s*$', flags=re.IGNORECASE)
HOUSE_FLIP_B = re.compile(r'^\s*(\d+[A-Za-z]?)\s*/\s*unit\s*([A-Za-z0-9]+)\s*$', flags=re.IGNORECASE)

COMMON_SUFFIX_LOWER = _COMMON_SUFFIX  # already lowercased entries

# Optional: seed with trusted suburb names if you have them
_SUBURB_WHITELIST = set()


# =============================================================================
# Canon/text helpers, parsing, geocode decision helpers, caches, filesystem helpers
# (Copied verbatim from Clean_GoogleSheets.py)
# =============================================================================

def _canon_street_suburb(street: str, suburb: str) -> tuple[str, str]:
    return (_canon_text_cached(street), _canon_text_cached(suburb))

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

def _canon_text(s: str) -> str:
    return _canon_text_cached(s)

def _looks_like_just_suburb(geo_street: str, geo_suburb: str) -> bool:
    """True when geocoded street is effectively the same as the suburb name."""
    return _canon_text_cached(geo_street) == _canon_text_cached(geo_suburb)

def _tokens_core(s: str) -> list[str]:
    return TOKEN_RX.findall((s or "").lower())

def _has_digits(s: str) -> bool:
    return any(ch.isdigit() for ch in (s or ""))

def _coords_in_auckland(lat: float, lon: float) -> bool:
    """
    Robust Auckland gate:
    - Coerces to float
    - Accepts swapped (lon,lat) mistakes using CoreLite helper if available
    """
    try:
        la = float(lat)
        lo = float(lon)
    except Exception:
        return False

    # If CoreLite exposes a swap helper, use it
    try:
        swap = getattr(core, "_maybe_swap_latlon", None)
        if callable(swap):
            la, lo = swap(la, lo)
    except Exception:
        pass

    try:
        return core.is_in_auckland(la, lo)
    except Exception:
        return False


def _merge_notes(*parts: str) -> str:
    out = []
    for p in parts:
        p = (p or "").strip()
        if not p:
            continue
        out.append(p)
    # remove duplicates while keeping order
    seen = set()
    uniq = []
    for p in out:
        key = p.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return " | ".join(uniq)

def _strip_trailing_postcode(s: str) -> str:
    return TRAILING_NZ_POSTCODE_RX.sub("", (s or "").strip())

def _strip_common_suffix_word(s: str) -> str:
    """
    Remove a trailing street-type suffix word (road/rd/street/st/etc.) from a string.
    This is ONLY used for fuzzy comparisons, not for writing output.
    """
    tokens = _tokens_core(s)
    if not tokens:
        return s or ""
    if tokens[-1] in COMMON_SUFFIX_LOWER:
        tokens = tokens[:-1]
    return " ".join(tokens)

def normalize_number(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    s = re.sub(r"\s+", "", s)
    s = s.replace("UNIT", "Unit").replace("unit", "Unit")
    s = s.replace("FLAT", "Flat").replace("flat", "Flat")
    return s

def _numbers_match(a: str, b: str) -> bool:
    return normalize_number(a) == normalize_number(b)

def _clean_notes_and_language(notes: str, language: str) -> tuple[str, str]:
    """
    Legacy-compatible Notes/Language cleanup.

    Notes:
      - Remove phrases like:
          "Check If Chinese", "Please Check If Chinese",
          "Should be Chinese", "Speaks Mandarin"
        (case-insensitive)
      - Clean up dangling separators ('/', '|') left behind.
    Language:
      - If Language is Mandarin/Chinese variants (case/whitespace/punct tolerant),
        clear it.
    """
    notes = (notes or "")
    language = (language or "")

    # ---- Notes: strip known phrases (case-insensitive) ----
    if notes:
        strip_patterns = [
            r"\bplease\s*check\s*if\s*chinese\b",
            r"\bcheck\s*if\s*chinese\b",
            r"\bshould\s*be\s*chinese\b",
            r"\bspeaks\s*mandarin\b",
        ]
        for pat in strip_patterns:
            notes = re.sub(pat, "", notes, flags=re.IGNORECASE)

        # Normalize whitespace and separators after removals
        notes = re.sub(r"\s+", " ", notes).strip()
        notes = SEP_SQUASH_RX_1.sub(r"\1", notes)
        notes = SEP_SQUASH_RX_2.sub("", notes)
        notes = SEP_SQUASH_RX_3.sub("", notes)

    # ---- Language cleanup ----
    language = re.sub(r"\s+", " ", language).strip()
    lang_norm = LANG_LETTERS_ONLY_RX.sub("", language.strip().lower())
    clear_set = {"mandarin", "chinese", "chinesemandarin", "mandarinchinese"}
    if lang_norm in clear_set:
        language = ""

    return notes, language


def _append_other_notes(row: dict, msg: str) -> None:
    """
    Legacy-compatible "Other Notes" appender:
      - merges with " | "
      - dedupes while preserving order
      - ignores empty messages
    """
    msg = (msg or "").strip()
    if not msg:
        return

    other = (row.get("Other Notes") or "").strip()
    if not other:
        row["Other Notes"] = msg
        return

    row["Other Notes"] = _merge_notes(other, msg)


def _split_unit_house(number: str) -> tuple[str, str]:
    """
    Legacy-compatible split:

      UnitA/12  -> ("UnitA", "12")
      12/UnitA  -> ("UnitA", "12")

    If NOT a unit/house form, returns ("", "").

    Notes:
      - Normalizes unit prefix to "Unit" (title case) but avoids "UnitUnitX".
      - Returning ("", "") for non-split is CRITICAL because many callers use:
            if unit_guess and house_guess:
        or incorrectly:
            if house_guess:
        Returning ("", original) causes false positives where every value looks "split".
    """
    s = (number or "").strip()
    if not s:
        return "", ""

    m = HOUSE_FLIP_A.match(s)
    if m:
        raw_unit = (m.group(1) or "").strip()
        house = (m.group(2) or "").strip()
        unit = raw_unit
        if not unit.lower().startswith("unit"):
            unit = f"Unit{unit}"
        else:
            unit = "Unit" + unit[4:]
        return unit, house

    m = HOUSE_FLIP_B.match(s)
    if m:
        house = (m.group(1) or "").strip()
        raw_unit = (m.group(2) or "").strip()
        unit = raw_unit
        if not unit.lower().startswith("unit"):
            unit = f"Unit{unit}"
        else:
            unit = "Unit" + unit[4:]
        return unit, house

    return "", ""



def _house_digits_from_number(number: str) -> str:
    """
    Extracts digits from a Number field for comparison, preferring the house part
    if the value is a unit/house form.
    """
    unit, house = _split_unit_house(number)
    base = house if house else (number or "")
    m = re.search(r"\d+", base)
    return m.group(0) if m else ""

def gs_strip_leading_duplicate_number_from_street(number: str, street: str) -> str:
    """
    If Street begins with the same house number as Number, strip it off.
    Example:
        Number="12", Street="12 Queen Street" -> "Queen Street"
    """
    number = (number or "").strip()
    street = (street or "").strip()
    if not number or not street:
        return street

    # number might be "UnitA/12"; prefer house digits for match
    house_digits = _house_digits_from_number(number)
    if not house_digits:
        return street

    # Compare start of street with same digits (optionally followed by letter)
    rx = re.compile(rf"^\s*{re.escape(house_digits)}[A-Za-z]?\s+", flags=re.IGNORECASE)
    if rx.search(street):
        return rx.sub("", street).strip()
    return street

def _combine_unit_and_number(apartment: str, number: str) -> str:
    """
    Combine apartment/unit + house number into a single "Number" string.
    If apartment is blank, returns number unchanged.
    """
    apartment = (apartment or "").strip()
    number = (number or "").strip()
    if apartment and number:
        # normalize unit prefix
        if not apartment.lower().startswith(("unit", "flat")):
            apartment = f"Unit{apartment}"
        return f"{apartment}/{number}"
    return number or apartment

def _count_data_rows(csv_path: str | Path) -> int:
    csv_path = str(csv_path)
    if not os.path.exists(csv_path):
        return 0

    f = None
    try:
        f = _open_csv_text_best_effort(csv_path)
        r = csv.reader(f)
        try:
            next(r)  # header
        except StopIteration:
            return 0
        return sum(1 for _ in r)
    except Exception:
        # Legacy-safe: row count is non-critical; return 0 on any failure
        return 0
    finally:
        try:
            if f is not None:
                f.close()
        except Exception:
            pass


def _distance_meters(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, sqrt, atan2
    R = 6371000.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    c = 2 * atan2(sqrt(1-a), sqrt(a))
    return R * c

NEW_STREET_MSG = 'Please refer to "New Streets" for more information'

def _safe_forward_both(query: str):
    """
    Try Photon + Nominatim in parallel and return the first acceptable result.

    Returns:
      (best_tuple, source_str) or (None, None)

    Notes:
      - "Race" means whichever returns first with an acceptable tuple wins.
      - If one errors, we still allow the other to win.
      - Uses existing cached wrappers (_photon_cached/_nominatim_cached), so repeated
        queries remain fast and do not spam external services.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _ok(res) -> bool:
        try:
            return bool(res and isinstance(res, (list, tuple)) and len(res) >= 2)
        except Exception:
            return False

    def _call_photon():
        return _photon_cached(query), "photon"

    def _call_nominatim():
        return _nominatim_cached(query), "nominatim"

    # If query is blank, bail early
    q = (query or "").strip()
    if not q:
        return None, None

    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(fn) for fn in (_call_photon, _call_nominatim)]
        for fut in as_completed(futs):
            try:
                res, src = fut.result()
            except Exception:
                continue
            if _ok(res):
                return res, src

    return None, None


def _choose_best_coordinate(
    row: dict,
    *,
    allow_outside_auckland: bool = False
) -> tuple[Optional[float], Optional[float], Optional[str]]:
    """
    Chooses the best coordinate for a row.
    Returns: (lat, lon, source)

    Fixes:
      1) Robustly parses provider return shapes, especially 3-tuples like:
           (lat, lon, extra)  OR  (src, lat, lon)
      2) Adds a retry path when Street contains ", Suburb" (Scenario B),
         which is common in your data: "Mander Place, Bucklands Beach"
      3) Keeps legacy return behavior: (None, None, None) on failure

    USER PATCH:
      - If the row already has Latitude/Longitude, ALWAYS use them and skip refinding.
      - Attempt a swap-heuristic if core provides _maybe_swap_latlon.
      - Do NOT reject existing coords based on Auckland gating (as requested).
    """
    from GoogleSheets_Log import log_debug, log_info, log_warn

    attempts: list[dict] = []

    def _attempt(**kw) -> None:
        try:
            attempts.append({k: v for k, v in kw.items() if v is not None})
        except Exception:
            pass

    def _as_s(v) -> str:
        try:
            return "" if v is None else str(v).strip()
        except Exception:
            return ""

    def _set_meta(**kw) -> None:
        try:
            m = row.get("_geocode_meta")
            if not isinstance(m, dict):
                m = {}
            m.update({k: v for k, v in kw.items() if v is not None})
            m["attempts"] = attempts
            row["_geocode_meta"] = m
        except Exception:
            pass

    def _is_num(x) -> bool:
        try:
            float(x)
            return True
        except Exception:
            return False

    def _extract_latlon_postal(res) -> tuple[Optional[float], Optional[float], str]:
        """
        Accepts multiple legacy/provider shapes:
          - (src, lat, lon, postal)
          - (src, lat, lon)
          - (lat, lon, postal_or_extra)
          - (lat, lon)
        Returns (lat, lon, postal_str)
        """
        if not res:
            return None, None, ""
        if not isinstance(res, (list, tuple)):
            return None, None, ""

        # (src, lat, lon, postal)
        if len(res) >= 4 and not _is_num(res[0]):
            try:
                return float(res[1]), float(res[2]), _as_s(res[3])
            except Exception:
                return None, None, ""

        # (src, lat, lon)
        if len(res) == 3 and not _is_num(res[0]):
            try:
                return float(res[1]), float(res[2]), ""
            except Exception:
                return None, None, ""

        # (lat, lon, extra/postal)
        if len(res) == 3 and _is_num(res[0]) and _is_num(res[1]):
            try:
                return float(res[0]), float(res[1]), _as_s(res[2])
            except Exception:
                return None, None, ""

        # (lat, lon)
        if len(res) == 2 and _is_num(res[0]) and _is_num(res[1]):
            try:
                return float(res[0]), float(res[1]), ""
            except Exception:
                return None, None, ""

        return None, None, ""

    def _maybe_apply_postal_to_row(postal: str) -> None:
        try:
            postal = (postal or "").strip()
            if not postal:
                return
            existing = (row.get("PostalCode") or row.get("Postcode") or "").strip()
            if existing:
                return
            if "PostalCode" in row:
                row["PostalCode"] = postal
            if "Postcode" in row:
                row["Postcode"] = postal
        except Exception:
            pass

    def _coords_in_auckland_local(lat: float, lon: float) -> bool:
        try:
            return core.is_in_auckland(lat, lon)
        except Exception:
            return False

    def _in_scope(lat: float, lon: float) -> bool:
        return bool(allow_outside_auckland or _coords_in_auckland_local(lat, lon))

    def _build_query(ap: str, num: str, street: str, suburb: str) -> str:
        fmt = getattr(core, "fmt_addr_parts", None)
        if callable(fmt):
            qx = fmt(ap, num, street, suburb)
        else:
            qx = ", ".join([x for x in [ap, num, street, suburb, "Auckland"] if (x or "").strip()]).strip(", ")
        return (qx or "").strip()

    # ---------- 1) existing coords (ALWAYS USE, per your request) ----------
    try:
        lat0 = float((row.get("Latitude") or "").strip())
        lon0 = float((row.get("Longitude") or "").strip())

        # Try swap heuristic if available (prevents losing good coords when swapped)
        try:
            ms = getattr(core, "_maybe_swap_latlon", None)
            if callable(ms):
                lat0, lon0 = ms(lat0, lon0)
        except Exception:
            pass

        log_info(
            "GEOCODE_USE_EXISTING",
            module=__name__,
            fn="_choose_best_coordinate",
            extra={"lat": lat0, "lon": lon0},
        )
        _set_meta(
            query="",
            provider="existing",
            result="OK",
            fail_reason="",
            fail_detail="",
        )
        return lat0, lon0, "existing"

    except Exception:
        _attempt(step="existing", ok=False, reason="missing_or_invalid")

    # ---------- 2) build query ----------
    ap = (row.get("ApartmentNumber") or "").strip()
    num = (row.get("Number") or "").strip()
    street = (row.get("Street") or "").strip()
    suburb = (row.get("Suburb") or "").strip()

    # Try to split unit/house if ApartmentNumber is blank
    if not ap and num:
        try:
            ap_guess, num_guess = _split_unit_house(num)
            if ap_guess:
                ap = ap_guess
            if num_guess:
                num = num_guess
        except Exception:
            pass

    q = _build_query(ap, num, street, suburb)
    q = (q or "").strip()

    _set_meta(query=q)

    # Guard: avoid Auckland-only geocodes (no digits + just "auckland")
    q_canon = _canon_text_cached(q)
    q_digits = _has_digits(q)
    if (not q_digits) and (q_canon == "auckland"):
        log_debug(
            "GEOCODE_QUERY_EMPTY",
            module=__name__,
            fn="_choose_best_coordinate",
            extra={
                "query": q,
                "ApartmentNumber": ap,
                "Number": num,
                "Street": street,
                "Suburb": suburb,
                "allow_outside_auckland": bool(allow_outside_auckland),
                "attempts": attempts,
            },
        )
        _set_meta(
            provider="",
            result="QUERY_EMPTY",
            fail_reason="MISSING_REQUIRED_FIELDS",
            fail_detail="Address insufficient: would geocode to Auckland-only.",
        )
        return None, None, None

    _attempt(step="query", ok=True, query=q, ApartmentNumber=ap, Number=num, Street=street, Suburb=suburb)

    # ---------- 3) LINZ / internal lookup ----------
    try:
        gl = _gl_cached(q)
        lat1, lon1, postal1 = _extract_latlon_postal(gl)

        try:
            src1 = str(gl[0]) if isinstance(gl, (list, tuple)) and gl and (not _is_num(gl[0])) else "linz"
        except Exception:
            src1 = "linz"

        if lat1 is None or lon1 is None:
            _attempt(step="linz", ok=False, reason="no_latlon", source=src1)
        else:
            if _in_scope(lat1, lon1):
                _maybe_apply_postal_to_row(postal1)
                log_info(
                    "GEOCODE_SUCCESS",
                    module=__name__,
                    fn="_choose_best_coordinate",
                    extra={"source": src1, "query": q, "lat": lat1, "lon": lon1},
                )
                _set_meta(provider=src1, result="OK", fail_reason="", fail_detail="")
                return lat1, lon1, src1
            _attempt(step="linz", ok=False, reason="outside_auckland", source=src1, lat=lat1, lon=lon1)
    except Exception as e:
        _attempt(step="linz", ok=False, reason="exception", error=_as_s(e))
        _set_meta(
            provider="linz",
            result="EXCEPTION",
            fail_reason="GEOCODE_EXCEPTION",
            fail_detail=_as_s(e),
        )

    # ---------- 4) fallback providers (photon + nominatim) ----------
    best, src2 = _safe_forward_both(q)

    # ---------- 4b) retry when Street contains ", Suburb" ----------
    if not best:
        try:
            street2, suburb_guess = _try_parse_suburb_from_street(street)
        except Exception:
            street2, suburb_guess = street, ""

        if suburb_guess:
            suburb_col = (suburb or "").strip()
            use_suburb = suburb_col if (suburb_col and suburb_col.lower() != "auckland") else suburb_guess

            q2 = _build_query(ap, num, street2, use_suburb)
            if q2 and "new zealand" not in q2.lower():
                q2 = f"{q2}, New Zealand"

            q2 = (q2 or "").strip().strip(",")
            if q2 and q2 != q:
                _attempt(step="retry_split_street", ok=True, query=q2, suburb_guess=suburb_guess, use_suburb=use_suburb)

                best2, src2b = _safe_forward_both(q2)
                lat2b, lon2b, postal2b = _extract_latlon_postal(best2)

                if lat2b is not None and lon2b is not None:
                    if _in_scope(lat2b, lon2b):
                        _maybe_apply_postal_to_row(postal2b)
                        log_info(
                            "GEOCODE_SUCCESS",
                            module=__name__,
                            fn="_choose_best_coordinate",
                            extra={"source": _as_s(src2b), "query": q2, "lat": lat2b, "lon": lon2b},
                        )
                        _set_meta(provider=_as_s(src2b), result="OK", fail_reason="", fail_detail="")
                        return lat2b, lon2b, _as_s(src2b)
                    _attempt(step="retry_split_street", ok=False, reason="outside_auckland", provider=_as_s(src2b), lat=lat2b, lon=lon2b)
                else:
                    _attempt(step="retry_split_street", ok=False, reason="no_latlon", provider=_as_s(src2b))

        _attempt(step="fallback", ok=False, reason="no_results")
        log_debug(
            "GEOCODE_FAIL",
            module=__name__,
            fn="_choose_best_coordinate",
            extra={"query": q, "allow_outside_auckland": bool(allow_outside_auckland), "attempts": attempts},
        )
        _set_meta(
            provider=_as_s(src2),
            result="NO_RESULTS",
            fail_reason="GEOCODE_NO_RESULTS",
            fail_detail="No provider returned an accepted coordinate.",
        )
        return None, None, None

    lat2, lon2, postal2 = _extract_latlon_postal(best)
    if lat2 is None or lon2 is None:
        _attempt(step="fallback", ok=False, reason="bad_provider_response", provider=_as_s(src2))
        log_warn(
            "GEOCODE_FAIL",
            module=__name__,
            fn="_choose_best_coordinate",
            extra={"query": q, "provider": _as_s(src2), "allow_outside_auckland": bool(allow_outside_auckland), "attempts": attempts},
        )
        _set_meta(
            provider=_as_s(src2),
            result="BAD_PROVIDER_RESPONSE",
            fail_reason="GEOCODE_BAD_RESPONSE",
            fail_detail="Provider response had no usable lat/lon.",
        )
        return None, None, None

    if _in_scope(lat2, lon2):
        _maybe_apply_postal_to_row(postal2)
        log_info(
            "GEOCODE_SUCCESS",
            module=__name__,
            fn="_choose_best_coordinate",
            extra={"source": _as_s(src2), "query": q, "lat": lat2, "lon": lon2},
        )
        _set_meta(provider=_as_s(src2), result="OK", fail_reason="", fail_detail="")
        return lat2, lon2, _as_s(src2)

    _attempt(step="fallback", ok=False, reason="outside_auckland", provider=_as_s(src2), lat=lat2, lon=lon2)

    log_warn(
        "GEOCODE_FAIL",
        module=__name__,
        fn="_choose_best_coordinate",
        extra={"query": q, "provider": _as_s(src2), "allow_outside_auckland": bool(allow_outside_auckland), "attempts": attempts},
    )
    _set_meta(
        provider=_as_s(src2),
        result="OUT_OF_SCOPE",
        fail_reason="OUTSIDE_AUCKLAND",
        fail_detail="Provider returned coordinates outside Auckland scope.",
    )
    return None, None, None




def _open_csv_text_best_effort(p: str | Path):
    """
    Open a CSV text file with encoding fallbacks.
    Returns an open file handle (caller must close).

    Encodings:
      - utf-8-sig: handles BOM
      - utf-8: normal
      - cp1252/latin-1: common Windows exports

    This is purely robustness; does not change row parsing logic.
    """
    path = str(p)
    encodings = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
    last_err: Exception | None = None

    for enc in encodings:
        try:
            return open(path, newline="", encoding=enc)
        except Exception as e:
            last_err = e

    if last_err is not None:
        raise last_err
    raise OSError(f"Failed to open CSV: {path}")


def _accept_geocode_update(row: dict, lat: float, lon: float, source: str, postal: str = "") -> None:
    """
    Apply a chosen coordinate back onto the row.

    LEGACY PARITY PATCH:
    - Write Latitude/Longitude at 8 decimal places (legacy output format).
    - Do NOT inject 'Geocode: ...' into 'Other Notes' (legacy outputs did not add this).
      (Geocode provenance should be logged via GoogleSheets_Log instead.)

    Postal behavior (unchanged):
    - If provider gave a postcode AND the row's postcode is blank, set it.
    - Then enforce suburb->postcode whitelist (wins last).
    """
    # Legacy formatting (fixed width)
    row["Latitude"] = f"{float(lat):.8f}"
    row["Longitude"] = f"{float(lon):.8f}"

    # Do NOT write geocode debug/provenance into CSV fields (legacy parity)
    # (Keep logging for this elsewhere via GoogleSheets_Log.)

    # 1) Use provider postcode only if row is blank (so we don't overwrite existing)
    postal = (postal or "").strip()
    existing = (row.get("PostalCode") or row.get("Postcode") or "").strip()
    if postal and not existing:
        if "PostalCode" in row:
            row["PostalCode"] = postal
        if "Postcode" in row:
            row["Postcode"] = postal

    # 2) Always enforce suburb->postcode if known (wins last)
    try:
        _enforce_postcode_whitelist(row)
    except Exception:
        pass



def _clear_dir_contents(dir_path: str | Path) -> None:
    dir_path = Path(dir_path)
    if not dir_path.exists():
        return
    for child in dir_path.iterdir():
        try:
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
        except Exception:
            pass

def _clear_files_only(dir_path: str | Path) -> None:
    dir_path = Path(dir_path)
    if not dir_path.exists():
        return
    for child in dir_path.iterdir():
        try:
            if child.is_file():
                child.unlink(missing_ok=True)
        except Exception:
            pass

def _merge_csvs(*args) -> None:
    """
    Legacy-compatible CSV merge.

    Supports both call styles:
      A) _merge_csvs([in1, in2], "out.csv")
      B) _merge_csvs("in1.csv", "in2.csv", "out.csv")

    Behavior:
      - Skips missing inputs
      - Header begins from first existing input, then union-add columns from later inputs
      - Never writes private/internal keys (starting with "_")
      - Never propagates audit/log-only keys (e.g. geocode debug columns)
      - Never writes internal meta blobs (e.g. _geocode_meta)
      - Writes output only if at least one input had a header
    """
    from GoogleSheets_Log import log_warn, log_exception, log_info

    if not args:
        return

    # Parse args
    if len(args) == 2 and isinstance(args[0], (list, tuple)) and isinstance(args[1], (str, Path)):
        inputs_raw = list(args[0])
        out_path = str(args[1])
    else:
        if len(args) < 2:
            return
        out_path = str(args[-1])
        inputs_raw = list(args[:-1])

    # Normalize + filter inputs (accept str/Path/pathlike)
    inputs: list[str] = []
    for p in inputs_raw:
        if not p:
            continue
        try:
            sp = str(p)
        except Exception:
            continue
        if sp and os.path.exists(sp):
            inputs.append(sp)

    if not inputs:
        log_warn("MERGE_CSVS_NO_INPUTS", module=__name__, fn="_merge_csvs", extra={"out_path": out_path})
        return

    # Denylist (audit/log-only + internal meta)
    deny = set()
    try:
        # preferred
        deny |= set(audit_log_only_keys())
    except Exception:
        try:
            deny |= set(_AUDIT_LOG_ONLY_KEYS)
        except Exception:
            pass
    deny |= {"_geocode_meta"}

    def _is_allowed(col: str) -> bool:
        if not col:
            return False
        if str(col).startswith("_"):
            return False
        if col in deny:
            return False
        return True

    # Reader with encoding fallbacks (reuse helper)
    def _open_in(p: str):
        try:
            return _open_csv_text_best_effort(p)
        except Exception:
            return open(p, newline="", encoding="utf-8")

    rows: list[dict] = []
    fieldnames: list[str] = []
    raw_fieldnames_first: list[str] = []

    # First file decides initial schema (legacy)
    f0 = None
    try:
        f0 = _open_in(inputs[0])
        r0 = csv.DictReader(f0)
        raw_fieldnames_first = list(r0.fieldnames or [])
        fieldnames = [c for c in raw_fieldnames_first if _is_allowed(c)]
        rows.extend(list(r0))
    except Exception as e:
        log_exception(
            "MERGE_CSVS_FIRST_READ_FAIL",
            module=__name__,
            fn="_merge_csvs",
            extra={"input": inputs[0], "error": str(e), "out_path": out_path},
        )
        raise
    finally:
        try:
            if f0 is not None:
                f0.close()
        except Exception:
            pass

    if not raw_fieldnames_first:
        log_warn(
            "MERGE_CSVS_MISSING_HEADER",
            module=__name__,
            fn="_merge_csvs",
            extra={"first_input": inputs[0], "out_path": out_path},
        )
        return

    if not fieldnames:
        log_warn(
            "MERGE_CSVS_HEADER_FILTERED_EMPTY",
            module=__name__,
            fn="_merge_csvs",
            extra={"first_input": inputs[0], "out_path": out_path, "raw_fieldnames": raw_fieldnames_first},
        )
        return

    # Union-add additional columns from later files
    for p in inputs[1:]:
        fp = None
        try:
            fp = _open_in(p)
            r = csv.DictReader(fp)
            in_fields = list(r.fieldnames or [])
            for col in in_fields:
                if _is_allowed(col) and col not in fieldnames:
                    fieldnames.append(col)
            for row in r:
                rows.append(row)
        except Exception as e:
            log_warn(
                "MERGE_CSVS_READ_FAIL",
                module=__name__,
                fn="_merge_csvs",
                extra={"input": p, "error": str(e), "out_path": out_path},
            )
        finally:
            try:
                if fp is not None:
                    fp.close()
            except Exception:
                pass

    # Write output
    try:
        with open(out_path, "w", newline="", encoding="utf-8", buffering=1024 * 1024) as fout:
            w = csv.DictWriter(fout, fieldnames=fieldnames)
            w.writeheader()
            for row in rows:
                # Belt+Suspenders: strip log-only/meta keys before writing
                try:
                    strip_audit_columns_from_row(row)
                except Exception:
                    pass

                w.writerow({k: row.get(k, "") for k in fieldnames})

        log_info(
            "MERGE_CSVS_DONE",
            module=__name__,
            fn="_merge_csvs",
            extra={"out_path": out_path, "inputs": len(inputs), "rows": len(rows), "fieldnames": len(fieldnames)},
        )
    except Exception as e:
        log_exception(
            "MERGE_CSVS_WRITE_FAIL",
            module=__name__,
            fn="_merge_csvs",
            extra={"out_path": out_path, "error": str(e)},
        )
        raise


def audit_log_only_keys() -> set[str]:
    """
    Expose denylist for writers in other modules.
    """
    try:
        return set(_AUDIT_LOG_ONLY_KEYS)
    except Exception:
        return set()



def _strip_unit_prefix_for_match(s: str) -> str:
    """
    For matching only: normalize apartment/unit tokens so:
      "UnitA" -> "A"
      "unit a" -> "a"
      "Flat2" -> "2"
      "A" -> "A"
    """
    s = (s or "").strip()
    if not s:
        return ""
    s2 = re.sub(r"^\s*(unit|flat)\s*[:#\-]?\s*", "", s, flags=re.IGNORECASE)

    s2 = re.sub(r"\s+", "", s2)
    return s2


@lru_cache(maxsize=4096)
def _gl_cached(query: str):
    # LINZ / internal lookup via core.get_lat_long
    try:
        return core.get_lat_long(query)
    except Exception:
        return None

@lru_cache(maxsize=4096)
def _nominatim_cached(query: str):
    try:
        return core.forward_geocode_nominatim(query)
    except Exception:
        return None

@lru_cache(maxsize=4096)
def _photon_cached(query: str):
    try:
        return core.forward_geocode_photon(query)
    except Exception:
        return None

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
    s = getattr(core_ref, "suburb_list", None)
    if isinstance(s, (list, set, tuple)):
        vals.update(s)
    # A few always-safe known suburbs (optional)
    vals.update({"Botany Downs", "Dannemora", "Flat Bush", "Howick", "Pakuranga", "Golflands", "Highland Park", "Bucklands Beach"})
    _SUBURB_WHITELIST.update({_strip_macrons(v).title().strip() for v in vals if v})

_SUBURB_CORRUPTION_MAP = {
    # Add any known 1:1 suburb fixes you encounter
    # "Botanydown": "Botany Downs",
}

_BAD_CHARS_RX = re.compile(r"[^A-Za-z0-9'\-\s]")

def _repair_corrupted_suburb(s: str) -> str:
    """
    Repair suburb text using:
      1) explicit corruption map
      2) character cleanup + macron stripping
      3) close-match against a whitelist built from core suburb sources

    Legacy-safe behavior:
      - Lazily initializes the suburb whitelist on first use.
    """
    if not s:
        return ""
    s = s.strip()
    if s in _SUBURB_CORRUPTION_MAP:
        return _SUBURB_CORRUPTION_MAP[s]

    if not _SUBURB_WHITELIST:
        try:
            _init_suburb_whitelist(core)
        except Exception:
            pass

    cleaned = _BAD_CHARS_RX.sub("", s)
    cleaned = _strip_macrons(cleaned).strip()
    if not cleaned:
        return ""

    if _SUBURB_WHITELIST:
        cand = difflib.get_close_matches(cleaned.title(), _SUBURB_WHITELIST, n=1, cutoff=0.92)
        if cand:
            return cand[0]

    return cleaned.title()


def _canon_suburb_local(s: str) -> str:
    """
    Local suburb canonicalization for GoogleSheets:
      - strip polygon/shapefile suffixes
      - repair known corruptions
      - title-case
    """
    s = (s or "").strip()
    if not s:
        return ""

    # ✅ NEW: always normalize polygon/shapefile suburb labels
    s = _normalize_polygon_suburb_name(s)

    return _repair_corrupted_suburb(s)


def _canon_suburb_sheets(s: str) -> str:
    """
    Canon suburb used across the Sheets workflow.
    """
    return _canon_suburb_local(s)

from functools import lru_cache

@lru_cache(maxsize=1)
def _get_postal_lookup_map() -> dict[str, str]:
    """
    Robustly find the postcode lookup dict.

    Priority:
      1) CoreLite re-exports (core.nz_postal_lookup, etc)
      2) Direct import fallback from GoogleSheets_CoreLite_Geocode.nz_postal_lookup

    We normalize values to strings and ignore empties.
    """
    def _normalize_dict(m: dict) -> dict[str, str]:
        out: dict[str, str] = {}
        try:
            items = m.items()
        except Exception:
            return out
        for k, v in items:
            ks = (str(k).strip() if k is not None else "")
            vs = (str(v).strip() if v is not None else "")
            if ks and vs:
                out[ks] = vs
        return out

    # 1) Try CoreLite exposed attributes (preferred)
    candidate_attrs = (
        "nz_postal_lookup",
        "nz_postcode_lookup",
        "nz_postcodes",
        "postcode_lookup",
        "postal_lookup",
        "nz_postcode_map",
        "nz_postal_map",
    )

    for attr in candidate_attrs:
        m = getattr(core, attr, None)
        if isinstance(m, dict) and m:
            out = _normalize_dict(m)
            if out:
                return out

    # 2) Fallback: import directly from CoreLite_Geocode (covers cases where CoreLite doesn't re-export)
    try:
        from GoogleSheets_CoreLite_Geocode import nz_postal_lookup as _nz_map  # type: ignore
        if isinstance(_nz_map, dict) and _nz_map:
            out = _normalize_dict(_nz_map)
            if out:
                return out
    except Exception:
        pass

    return {}




def _postal_for_suburb_sheets(suburb: str) -> str:
    """
    Lookup postcode after canonicalization with multiple fallback strategies.

    Returns "" if not found.
    """
    suburb = (suburb or "").strip()
    if not suburb:
        return ""

    suburb_canon = _canon_suburb_sheets(suburb)
    m = _get_postal_lookup_map()
    if not m:
        return ""

    def _as_str(v) -> str:
        try:
            return str(v).strip()
        except Exception:
            return ""

    # 1) Direct attempts with common variants
    for key in (
        suburb_canon,
        suburb_canon.title(),
        suburb_canon.upper(),
        suburb_canon.lower(),
        _strip_macrons(suburb_canon),
        _strip_macrons(suburb_canon).title(),
        _strip_macrons(suburb_canon).lower(),
    ):
        if not key:
            continue
        v = m.get(key)
        if v is not None and _as_str(v):
            return _as_str(v)

    # 2) Canon-text keyed fallback (stable)
    @lru_cache(maxsize=1)
    def _canon_postal_map() -> dict[str, str]:
        out: dict[str, str] = {}
        for k, v in m.items():
            ks = (k or "")
            vs = _as_str(v)
            if not ks or not vs:
                continue
            out[_canon_text_cached(ks)] = vs
        return out

    try:
        cm = _canon_postal_map()
        v2 = cm.get(_canon_text_cached(suburb_canon))
        if v2:
            return v2
    except Exception:
        pass

    return ""

def _is_blank_any(v) -> bool:
    if v is None:
        return True
    s = str(v).strip()
    return s == "" or s.lower() == "nan"

_AUDIT_WATCH_FIELDS = ["Street","Suburb","PostalCode","State","Status","Final Status","Latitude","Longitude","Type","Number"]

# --- Audit fields that must NEVER be written to CSV ---
_AUDIT_LOG_ONLY_KEYS = {
    "Address Used",
    "Geocode Query",
    "Geocode Provider",
    "Geocode Result",
    "Geocode Attempts",
    "Fail Reason",
    "Fail Detail",
}

def strip_audit_columns_from_row(row: dict) -> None:
    """
    Hard safety-net: remove log-only audit keys + internal meta so they can’t reach CSV.

    Rules:
      - Remove explicit audit/log-only keys listed in _AUDIT_LOG_ONLY_KEYS
      - Remove internal meta blobs like _geocode_meta
      - Remove ANY private/internal keys starting with "_" (belt+braces)
        because these are never part of a stable CSV contract.
    """
    if not isinstance(row, dict):
        return

    # 1) Explicit log-only keys
    for k in list(_AUDIT_LOG_ONLY_KEYS):
        try:
            row.pop(k, None)
        except Exception:
            pass

    # 2) Known internal meta / diagnostics keys
    for k in ("_geocode_meta",):
        try:
            row.pop(k, None)
        except Exception:
            pass

    # 3) Belt+braces: remove any stray private keys
    try:
        for k in list(row.keys()):
            if k and str(k).startswith("_"):
                row.pop(k, None)
    except Exception:
        pass



def add_row_audit_fields(row: dict) -> None:
    """
    LOG-ONLY audit (legacy-safe change requested):
    - Do NOT add Address Used / Geocode* / Fail* columns to the row.
    - Instead, log them.
    - Keep 'Missing Fields' if you still want it in CSV; if not, I show how below.
    """
    from GoogleSheets_Log import log_debug

    # (A) If you STILL want "Missing Fields" in CSV, keep this:
    missing = [k for k in _AUDIT_WATCH_FIELDS if k in row and _is_blank_any(row.get(k))]
    row["Missing Fields"] = ";".join(missing)

    # (B) Build log payload (do NOT write to row)
    num = "" if _is_blank_any(row.get("Number")) else str(row.get("Number")).strip()
    street = "" if _is_blank_any(row.get("Street")) else str(row.get("Street")).strip()
    suburb = "" if _is_blank_any(row.get("Suburb")) else str(row.get("Suburb")).strip()
    address_used = " ".join([p for p in [num, street, suburb] if p])

    meta = row.get("_geocode_meta") if isinstance(row.get("_geocode_meta"), dict) else {}
    attempts = meta.get("attempts") or []

    log_debug(
        "ROW_AUDIT",
        module=__name__,
        fn="add_row_audit_fields",
        extra={
            "address_used": address_used,
            "missing_fields": missing,
            "geocode_query": str(meta.get("query", "") or ""),
            "geocode_provider": str(meta.get("provider", "") or ""),
            "geocode_result": str(meta.get("result", "") or ""),
            "geocode_attempts": attempts,
            "fail_reason": str(meta.get("fail_reason", "") or ""),
            "fail_detail": str(meta.get("fail_detail", "") or ""),
        },
    )

    # (C) Safety: ensure no stray keys remain (in case older code added them earlier)
    strip_audit_columns_from_row(row)

def final_status_is_pass_ok(row: dict) -> bool:
    """
    Canonical clean definition:
      - ONLY explicit Pass/OK belongs in output_clean.csv
      - EVERYTHING else (Fail, Duplicate, Bad Geocode, blanks, etc) is fail-side
    """
    try:
        v = (
            row.get("Final Status")
            or row.get("final_status")
            or row.get("FinalStatus")
            or ""
        )
        s = str(v).strip().lower()
        return s in ("pass", "ok")
    except Exception:
        return False

def final_status_is_fail(row: dict) -> bool:
    """
    Single source of truth:

    Rule (as requested):
      - Only treat as FAIL when final status text is exactly "Fail"
        (case-insensitive, whitespace-tolerant).

    Accepts common column variants:
      - "Final Status" (your CSV)
      - "final_status"
      - "FinalStatus"
    """
    try:
        v = (
            row.get("Final Status")
            or row.get("final_status")
            or row.get("FinalStatus")
            or ""
        )
        s = str(v).strip().lower()
        return s == "fail"
    except Exception:
        return False




def route_row_writers_by_final_status(
    row: dict,
    *,
    clean_writer,
    fail_writer,
    make_safe_row_fn,
) -> str:
    """
    Central routing helper (CANONICAL):

      - Pass/OK => clean
      - Anything else (Fail/Duplicate/Bad Geocode/blank/etc) => fail

    This prevents "Duplicate" and similar statuses from leaking into output_clean.csv.
    """
    safe = make_safe_row_fn(row)

    dest = "clean" if final_status_is_pass_ok(safe) else "fail"

    if dest == "clean":
        clean_writer.writerow(safe)
        return "clean"

    fail_writer.writerow(safe)
    return "fail"




def _enforce_postcode_whitelist(row: dict) -> None:
    suburb_raw = (row.get("Suburb") or "").strip()
    if not suburb_raw:
        return

    # ✅ Hard guarantee: normalize suburb in the row itself
    suburb_clean = _canon_suburb_sheets(suburb_raw)
    if suburb_clean and suburb_clean != suburb_raw:
        row["Suburb"] = suburb_clean

    pc = _postal_for_suburb_sheets(suburb_clean or suburb_raw)
    if not pc:
        return

    if "PostalCode" in row:
        row["PostalCode"] = pc
    if "Postcode" in row:
        row["Postcode"] = pc
    if "PostalCode" not in row and "Postcode" in row:
        row["Postcode"] = pc

def enforce_outputs_routing(
    clean_csv: str = "output_clean.csv",
    fail_csv: str = "output_fail.csv",
) -> dict:
    """
    Hard guarantee (CANONICAL):

      - output_clean.csv contains ONLY Final Status Pass/OK
      - output_fail.csv contains EVERYTHING else (Fail/Duplicate/Bad Geocode/blanks/etc)

    CRITICAL FIX:
      - Filters out audit/log-only keys and private/internal keys from the OUTPUT HEADER,
        even if an older run "infected" the CSV headers.
      - Strips audit/meta keys from every row before writing.

    Returns:
      {"moved": int, "clean_kept": int, "fail_total": int}
    """
    import os
    import csv
    from pathlib import Path

    clean_csv = str(clean_csv)
    fail_csv = str(fail_csv)

    if not os.path.exists(clean_csv) and not os.path.exists(fail_csv):
        return {"moved": 0, "clean_kept": 0, "fail_total": 0}

    # Denylist: audit/log-only + internal
    deny = set()
    try:
        deny |= set(audit_log_only_keys())
    except Exception:
        try:
            deny |= set(_AUDIT_LOG_ONLY_KEYS)
        except Exception:
            pass
    deny |= {"_geocode_meta"}

    def _allowed_field(k: str) -> bool:
        if not k:
            return False
        ks = str(k)
        if ks.startswith("_"):
            return False
        if ks in deny:
            return False
        return True

    def _read(path: str) -> tuple[list[str], list[dict]]:
        if not os.path.exists(path):
            return [], []
        f = None
        try:
            f = _open_csv_text_best_effort(path)
            r = csv.DictReader(f)
            return list(r.fieldnames or []), list(r)
        finally:
            try:
                if f is not None:
                    f.close()
            except Exception:
                pass

    clean_fields_raw, clean_rows = _read(clean_csv)
    fail_fields_raw, fail_rows = _read(fail_csv)

    # Build SAFE union schema (clean header order wins)
    fields: list[str] = []
    for k in (clean_fields_raw or []):
        if _allowed_field(k) and k not in fields:
            fields.append(k)
    for k in (fail_fields_raw or []):
        if _allowed_field(k) and k not in fields:
            fields.append(k)

    # If no header available, infer from first row keys, but still filter
    if not fields:
        probe = (clean_rows[:1] + fail_rows[:1])
        if probe:
            for k in list(probe[0].keys()):
                if _allowed_field(k) and k not in fields:
                    fields.append(k)

    # Ensure Final Status exists (contract)
    if "Final Status" not in fields:
        fields.append("Final Status")

    # Re-route BOTH sides to guarantee correctness
    new_clean: list[dict] = []
    new_fail: list[dict] = []

    def _push(row: dict) -> None:
        if not isinstance(row, dict):
            return
        if final_status_is_pass_ok(row):
            new_clean.append(row)
        else:
            new_fail.append(row)

    for row in clean_rows:
        _push(row)
    for row in fail_rows:
        _push(row)

    # How many rows were moved out of clean into fail?
    moved = 0
    try:
        moved = sum(1 for r in clean_rows if isinstance(r, dict) and not final_status_is_pass_ok(r))
    except Exception:
        moved = 0

    tmp_clean = str(Path(clean_csv).with_suffix(".tmp.csv"))
    tmp_fail  = str(Path(fail_csv).with_suffix(".tmp.csv"))

    def _write(path: str, rows: list[dict]) -> None:
        with open(path, "w", newline="", encoding="utf-8", buffering=1024 * 1024) as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for r in rows:
                if not isinstance(r, dict):
                    continue
                # safety net: remove audit/meta/private keys
                try:
                    strip_audit_columns_from_row(r)
                except Exception:
                    pass
                w.writerow({k: r.get(k, "") for k in fields})

    _write(tmp_clean, new_clean)
    _write(tmp_fail, new_fail)

    # Replace atomically
    os.replace(tmp_clean, clean_csv)
    os.replace(tmp_fail, fail_csv)

    return {"moved": int(moved), "clean_kept": len(new_clean), "fail_total": len(new_fail)}

# =============================================================================
# Backfill missing Suburb/PostalCode (A/B/C)
# =============================================================================

from typing import Tuple

@lru_cache(maxsize=2)
def _polygons_cached(kml_dir: str = ""):
    """
    Cache polygons so we don't reload KML for every row.
    kml_dir can be blank to rely on CoreLite_Polygons auto-discovery.
    """
    try:
        if kml_dir:
            return core._load_kml_polygons(kml_dir=kml_dir)  # re-exported by CoreLite
    except TypeError:
        pass
    except Exception:
        pass

    try:
        return core._load_kml_polygons()  # type: ignore[attr-defined]
    except Exception:
        return {}


def _try_parse_suburb_from_street(street: str) -> Tuple[str, str]:
    """
    Scenario B: Street may look like:
      "Mander Place, Bucklands Beach"

    Returns: (street_without_suburb, suburb_guess) or (original, "")
    """
    s = (street or "").strip()
    if not s or "," not in s:
        return s, ""

    parts = [p.strip() for p in s.split(",") if p.strip()]
    if len(parts) < 2:
        return s, ""

    suburb_guess = parts[-1]
    street_out = ", ".join(parts[:-1]).strip()

    # Guard: avoid "Auckland 1010" or other digit-containing tails
    if any(ch.isdigit() for ch in suburb_guess):
        return s, ""

    return street_out, suburb_guess


def backfill_suburb_postcode_for_row(
    row: dict,
    *,
    kml_dir: str = "",
    prefer_coords: bool = True,
    log_changes: bool = False,
) -> Tuple[bool, str]:
    """
    Fill missing Suburb and (via whitelist) PostalCode/Postcode under these scenarios:

      A) coords exist -> assign suburb via polygons
      B) Street has ", Suburb" -> split and use suburb
      C) otherwise unresolved

    Returns: (changed_any, reason_code)
      reason_code in {"A_COORDS_POLYGON", "B_STREET_COMMA_SUBURB", "C_UNRESOLVED", "NOOP"}
    """
    changed = False

    suburb = (row.get("Suburb") or "").strip()
    street = (row.get("Street") or "").strip()

    suburb_blank = _is_blank_any(suburb)

    # ---------- B) parse ", Suburb" from Street ----------
    if suburb_blank and street:
        street2, suburb_guess = _try_parse_suburb_from_street(street)
        if suburb_guess:
            row["Street"] = street2
            row["Suburb"] = _canon_suburb_sheets(suburb_guess)
            changed = True
            try:
                _enforce_postcode_whitelist(row)
            except Exception:
                pass

            if log_changes:
                try:
                    from GoogleSheets_Log import log_correction as _lc
                    _lc(
                        "BACKFILL_SUBURB_B",
                        details=f"Street contained suburb: '{street}' -> '{street2}', suburb='{row.get('Suburb','')}'",
                    )
                except Exception:
                    pass

            return changed, "B_STREET_COMMA_SUBURB"

    # ---------- A) coords -> polygon suburb ----------
    suburb = (row.get("Suburb") or "").strip()
    suburb_blank = _is_blank_any(suburb)

    if prefer_coords and suburb_blank:
        sf = globals().get("_safe_float") or getattr(core, "_safe_float", None)
        try:
            lat = sf(row.get("Latitude")) if callable(sf) else None
            lon = sf(row.get("Longitude")) if callable(sf) else None
        except Exception:
            lat = None
            lon = None

        if lat is not None and lon is not None:
            polys = _polygons_cached(kml_dir or "")
            try:
                name = core._assign_point_to_polygons(float(lon), float(lat), polys)
            except Exception:
                name = None

            if name:
                row["Suburb"] = _canon_suburb_sheets(_normalize_polygon_suburb_name(str(name)))
                changed = True
                try:
                    _enforce_postcode_whitelist(row)
                except Exception:
                    pass

                if log_changes:
                    try:
                        from GoogleSheets_Log import log_correction as _lc
                        _lc(
                            "BACKFILL_SUBURB_A",
                            details=f"Coords -> polygon suburb='{row.get('Suburb','')}' lat={lat} lon={lon}",
                        )
                    except Exception:
                        pass

                return changed, "A_COORDS_POLYGON"

    # ---------- C) unresolved ----------
    if suburb_blank:
        return False, "C_UNRESOLVED"

    # suburb already present -> ensure postcode consistency if possible
    try:
        _enforce_postcode_whitelist(row)
    except Exception:
        pass

    return False, "NOOP"



def backfill_suburb_postcode_for_rows(
    rows: list[dict],
    *,
    kml_dir: str = "",
    prefer_coords: bool = True,
    log_changes: bool = False,
) -> dict[str, int]:
    """
    Batch helper. Returns counts by reason code.
    """
    counts: dict[str, int] = {}
    for r in rows or []:
        _, code = backfill_suburb_postcode_for_row(
            r,
            kml_dir=kml_dir,
            prefer_coords=prefer_coords,
            log_changes=log_changes,
        )
        counts[code] = counts.get(code, 0) + 1
    return counts


def restore_missing_coords_from_input_csv(
    clean_rows: list[dict],
    input_csv_path: str,
    *,
    prefer_existing_clean_coords: bool = True,
) -> int:
    """
    For any row in clean_rows with blank Latitude/Longitude, try to restore coordinates
    from the ORIGINAL input CSV (input_googlesheets.csv) if that input row has coords.

    Matching strategy:
      - Build a canonical key: (Number, Street, Suburb)
      - Input CSV usually has Street like "Mander Place, Bucklands Beach"
        so we split trailing suburb off by comma.
      - Clean output typically has Street without suburb and Suburb in its own column.

    Returns:
      Number of rows restored.
    """
    import csv
    import re

    def _canon(s: str) -> str:
        s = (s or "").strip().lower()
        s = re.sub(r"\s+", " ", s)
        s = re.sub(r"[^a-z0-9 ]+", "", s)
        return s.strip()

    def _is_blank(s: str) -> bool:
        return (s or "").strip() == ""

    def _parse_input_street_and_suburb(street_field: str) -> tuple[str, str]:
        """
        Input 'Street' sometimes includes suburb: "X Road, Bucklands Beach"
        We'll split on comma; last chunk becomes suburb; rest becomes street.
        """
        s = (street_field or "").strip()
        if not s:
            return "", ""
        parts = [p.strip() for p in s.split(",") if p.strip()]
        if len(parts) >= 2:
            suburb = parts[-1]
            street = ", ".join(parts[:-1]).strip()
            return street, suburb
        return s, ""

    # --- build lookup from input csv ---
    lookup: dict[tuple[str, str, str], tuple[str, str]] = {}

    f = None
    try:
        f = _open_csv_text_best_effort(input_csv_path)
        r = csv.DictReader(f)
        for row in r:
            in_num = (row.get("Number") or "").strip()
            in_street_raw = (row.get("Street") or "").strip()
            in_lat = (row.get("Latitude") or "").strip()
            in_lon = (row.get("Longitude") or "").strip()

            if _is_blank(in_lat) or _is_blank(in_lon):
                continue

            street_name, suburb_guess = _parse_input_street_and_suburb(in_street_raw)

            key = (_canon(in_num), _canon(street_name), _canon(suburb_guess))
            if key == ("", "", ""):
                continue

            lookup[key] = (in_lat, in_lon)
    finally:
        try:
            if f is not None:
                f.close()
        except Exception:
            pass

    if not lookup:
        return 0

    # --- restore into clean rows ---
    restored = 0

    for row in clean_rows:
        lat0 = (row.get("Latitude") or "").strip()
        lon0 = (row.get("Longitude") or "").strip()

        if prefer_existing_clean_coords and (not _is_blank(lat0) and not _is_blank(lon0)):
            continue

        if _is_blank(lat0) or _is_blank(lon0):
            num = (row.get("Number") or "").strip()
            street = (row.get("Street") or "").strip()
            suburb = (row.get("Suburb") or "").strip()

            key = (_canon(num), _canon(street), _canon(suburb))
            hit = lookup.get(key)

            # If suburb mismatch, try without suburb as a fallback key
            if not hit:
                key2 = (_canon(num), _canon(street), _canon(""))
                hit = lookup.get(key2)

            if hit:
                in_lat, in_lon = hit
                row["Latitude"] = str(in_lat).strip()
                row["Longitude"] = str(in_lon).strip()
                restored += 1

                # Optional: centralized log if available
                try:
                    from GoogleSheets_Log import log_correction as _lc  # type: ignore
                    _lc("Coord Restore", details=f"Restored from input CSV: {num} {street}, {suburb}".strip())
                except Exception:
                    pass

    return restored

def audit_blank_auckland_rows(
    csv_path: str,
    *,
    max_print: int = 200,
    label: str = "",
    require_suburb_auckland_or_blank: bool = True,
    verbose: bool = False,
) -> list[dict]:
    """
    Audit rows that would produce an Auckland-only geocode query (effectively ", Auckland").

    DEFAULT BEHAVIOR:
      - NO console output (verbose=False)
      - Returns structured results only

    Set verbose=True to print detailed diagnostics (up to max_print).
    """
    import csv

    def _g(row: dict, key: str) -> str:
        v = row.get(key, "")
        return "" if v is None else str(v).strip()

    def _is_blank(v: str) -> bool:
        return (v or "").strip() == ""

    watched = [
        "Type",
        "ApartmentNumber", "Apartment/Business",
        "Unit",
        "Old Number", "Number",
        "Old Street", "Street",
        "Suburb",
        "Longitude", "Latitude",
        "Notes", "Other Notes",
        "Language",
        "Status", "Final Status",
    ]

    results: list[dict] = []

    f = None
    try:
        f = _open_csv_text_best_effort(csv_path)
        r = csv.DictReader(f)
        if not r.fieldnames:
            return results

        printed = 0
        total_hits = 0

        for i, row in enumerate(r, start=1):
            num = _g(row, "Number")
            street = _g(row, "Street")
            suburb = _g(row, "Suburb")

            suburb_effectively_blank = _is_blank(suburb) or suburb.lower() == "auckland"
            suburb_ok = suburb_effectively_blank if require_suburb_auckland_or_blank else True

            if suburb_ok and _is_blank(num) and _is_blank(street):
                total_hits += 1

                empty_fields: list[str] = []
                snap: dict[str, str] = {}
                for k in watched:
                    v = _g(row, k)
                    snap[k] = v
                    if _is_blank(v):
                        empty_fields.append(k)

                results.append({
                    "row_index": i,
                    "empty_fields": empty_fields,
                    "snapshot": snap,
                })

                if verbose and printed < max_print:
                    printed += 1
                    print(f"\n--- HIT #{total_hits} | Data Row {i} ---")
                    print("Empty fields:", ", ".join(empty_fields) if empty_fields else "(none)")
                    print("Number :", snap.get("Number", ""))
                    print("Street :", snap.get("Street", ""))
                    print("Suburb :", snap.get("Suburb", ""))
                    print("Lat/Lon:", f"{snap.get('Latitude','')}, {snap.get('Longitude','')}")

        if verbose:
            print(f"\nAUDIT SUMMARY ({label or 'audit'}): {total_hits} rows would geocode to Auckland-only")

        return results

    finally:
        try:
            if f is not None:
                f.close()
        except Exception:
            pass



# --- Logging: wrap functions defined in THIS module (CALL/RETURN/EXCEPTION) ---
from GoogleSheets_Log import autowrap_module  # noqa: E402

try:
    autowrap_module(__name__, include_private=True, only_defined_here=True)
except TypeError:
    # Backward compatible with older GoogleSheets_Log.autowrap_module signatures
    autowrap_module(__name__, include_private=True)

