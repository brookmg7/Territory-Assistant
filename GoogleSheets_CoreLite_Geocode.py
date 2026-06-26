#!/usr/bin/env python3
"""
GoogleSheets_CoreLite_Geocode.py

Purpose
-------
Geocoding + address formatting + distance/acceptance logic.

Exports (as requested)
----------------------
- get_lat_long
- geocode_linz_parallel
- geocode_linz
- geocode_photon
- geocode_nominatim
- geocode_geocodexyz
- fmt_addr_parts
- _to_parts
- fmt_addr_str
- to_external_query
- unit_word_variant
- merge_number_with_street
- normalize_number
- correct_suffix_typos
- linz_suffixes_for_base
- is_in_auckland
- is_auckland_result
- haversine_distance
- _maybe_swap_latlon
- _is_valid_geocode_tuple

Key globals/constants (copy-safe)
---------------------------------
- ADDRESS_PARSE_RX
- UNIT_RX
- _UNIT_PREFIX_RE
- PHOTON_URL / NOMINATIM_URL / GEOCODEXYZ_URL
- LINZ_DB (env override supported)
- street_suffix_map
- MAX_ALLOWED_DISTANCE

Notes
-----
- This module is standalone (no import from GoogleSheets_CoreLite to avoid circulars).
- LINZ_DB can be overridden with env var: LINZ_DB_PATH
"""

from __future__ import annotations

import csv
import math
import os
import re
import sqlite3
import threading
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Any

import requests

from GoogleSheets_Log import module_loaded  # noqa: E402
module_loaded(__name__)



# =============================================================================
# Logging (minimal, thread-safe, compatible)
# =============================================================================

_log_lock = getattr(__import__("GoogleSheets_Log", fromlist=["_log_lock"]), "_log_lock", threading.Lock())


def log_correction(event: str, details: str = "", street: str = "") -> None:
    """
    Log a correction/event.

    Policy:
      - Prefer GoogleSheets_Log.log_correction (centralized logging).
      - If not available, do NOTHING (no console, no side files).
    """
    # Cache the logger function after first successful import
    global _GS_LOG_CORRECTION  # type: ignore[name-defined]
    try:
        _GS_LOG_CORRECTION  # type: ignore[name-defined]
    except Exception:
        _GS_LOG_CORRECTION = None  # type: ignore[name-defined]

    # 1) Preferred: centralized logging
    if _GS_LOG_CORRECTION is None:  # type: ignore[name-defined]
        try:
            from GoogleSheets_Log import log_correction as _fn  # type: ignore
            _GS_LOG_CORRECTION = _fn  # type: ignore[name-defined]
        except Exception:
            _GS_LOG_CORRECTION = False  # type: ignore[name-defined]

    if _GS_LOG_CORRECTION not in (None, False):  # type: ignore[name-defined]
        try:
            _GS_LOG_CORRECTION(event, details=details, street=street)  # type: ignore[misc]
        except Exception:
            # If central logger exists but fails, stay silent.
            pass

    # 2) Fallback: silent (no console, no corrections_log.csv)
    return

def flip_unit_prefix_in_number(number: str) -> str:
    """
    GoogleSheets normal form wants:  UnitX/12   (unit first)
    Accept common flips like:        12/UnitX, 12/FlatX, 12 / unit X
    and return:                      UnitX/12

    Leaves already-correct UnitX/12 unchanged.
    """
    s = (number or "").strip()
    if "/" not in s:
        return s

    left, right = [x.strip() for x in s.split("/", 1)]
    if not left or not right:
        return s

    # Already in preferred form
    if left.lower().startswith(("unit", "flat")):
        return s

    # If right is Unit/Flat-like, flip it to the front
    r = right.replace(" ", "")
    if r.lower().startswith(("unit", "flat")):
        return f"{r}/{left.replace(' ', '')}"

    return s


def _log_quiet(event: str, details: str = "", *, important: bool = False, street: str = "") -> None:
    """
    Quiet logger used by copied code.

    Preferred:
      - delegate to GoogleSheets_Log._log_quiet (centralized)

    Fallback:
      - if important=True, write via log_correction()
    """
    global _GS_LOG_QUIET  # type: ignore[name-defined]
    try:
        _GS_LOG_QUIET  # type: ignore[name-defined]
    except Exception:
        _GS_LOG_QUIET = None  # type: ignore[name-defined]

    if _GS_LOG_QUIET is None:  # type: ignore[name-defined]
        try:
            from GoogleSheets_Log import _log_quiet as _fn  # type: ignore
            _GS_LOG_QUIET = _fn  # type: ignore[name-defined]
        except Exception:
            _GS_LOG_QUIET = False  # type: ignore[name-defined]

    if _GS_LOG_QUIET not in (None, False):  # type: ignore[name-defined]
        try:
            _GS_LOG_QUIET(event, details=details, important=important, street=street)  # type: ignore[misc]
            return
        except Exception:
            pass

    if important:
        try:
            log_correction(event, details, street=street)
        except Exception:
            pass



# =============================================================================
# Shared counters/locks used by geocode_linz_parallel (re-exported by core)
# =============================================================================

geocode_sources_used: dict[str, int] = defaultdict(int)
geocode_lock = threading.Lock()
_db_lock = threading.Lock()

GEOCODE_DEBUG = False
RESULT_ONLY_LOGS = True

# =============================================================================
# Geocode miss reasons (debuggable without changing API)
# =============================================================================

LAST_GEOCODE_REASON: dict[str, str] = {}
_LAST_REASON_LOCK = threading.Lock()

def _set_geocode_reason(addr: str, reason: str) -> None:
    """
    Record the last known reason why geocoding failed for a given address key.

    Note:
    - We intentionally key by the canonical string passed to LINZ/external providers.
    - Keeps memory small and avoids changing the core (label,lat,lon,postal) API.
    """
    a = (addr or "").strip()
    if not a or not reason:
        return
    try:
        with _LAST_REASON_LOCK:
            LAST_GEOCODE_REASON[a] = str(reason).strip()
    except Exception:
        pass

def get_last_geocode_reason(addr: str) -> str:
    """
    Retrieve the last recorded miss reason for this canonical address string.
    Returns "" if none recorded.
    """
    a = (addr or "").strip()
    if not a:
        return ""
    try:
        with _LAST_REASON_LOCK:
            return LAST_GEOCODE_REASON.get(a, "")
    except Exception:
        return ""

# =============================================================================
# Auckland gating
# =============================================================================

# Rough Auckland bounding box (NZ)
AUCKLAND_LAT_MIN, AUCKLAND_LAT_MAX = -37.30, -36.60
AUCKLAND_LON_MIN, AUCKLAND_LON_MAX = 174.40, 175.50

def is_in_auckland(lat, lon) -> bool:
    try:
        lat = float(lat); lon = float(lon)
    except Exception:
        return False
    return (AUCKLAND_LAT_MIN <= lat <= AUCKLAND_LAT_MAX) and (AUCKLAND_LON_MIN <= lon <= AUCKLAND_LON_MAX)


def is_auckland_result(result) -> bool:
    """Returns True if the result appears to be located in Auckland (label contains 'Auckland')."""
    if not result or len(result) < 1 or not result[0]:
        return False
    return "auckland" in str(result[0]).lower()


MAX_ALLOWED_DISTANCE = 2000


# =============================================================================
# Regex + formatting helpers
# =============================================================================

# Accepts: "12 Smith St, Remuera" OR "12 Smith St, Remuera, Auckland"
ADDRESS_PARSE_RX = re.compile(r"^(\S+)\s+(.+?),\s*([^,]+)(?:,\s*Auckland)?$", re.IGNORECASE)

def _to_parts(address: str) -> tuple[str, str, str]:
    m = ADDRESS_PARSE_RX.match((address or "").strip())
    if not m:
        a = (address or "").strip()
        if a.lower().endswith(", auckland"):
            a = a[:-10].strip()
            m = ADDRESS_PARSE_RX.match(a)
    if not m:
        return "", "", ""
    num, street, suburb = [x.strip() for x in m.groups()]
    return num, street, suburb

# =============================================================================
# NZ suburb → postcode lookup (LEGACY PARITY)
# =============================================================================

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
    "Eastern Beach": "2012", "East Tāmaki": "2013", "East Tāmaki Heights": "2016", "East Tamaki": "2013", "East Tamaki Heights": "2016",
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

# Expanded suffix map (copied from your scheduler)
street_suffix_map = {
    "Tce": "Terrace", "Tce.": "Terrace", "Terr": "Terrace",
    "Cr": "Crescent", "Cres": "Crescent", "Cresc": "Crescent",
    "Crt": "Court", "Crt.": "Court", "Ct": "Court",
    "Rd": "Road", "Rd.": "Road",
    "St": "Street", "St.": "Street", "Str": "Street",
    "Ave": "Avenue", "Ave.": "Avenue", "Av": "Avenue",
    "Dr": "Drive", "Dr.": "Drive",
    "Pl": "Place", "Pl.": "Place",
    "Grv": "Grove", "Grv.": "Grove", "Gr": "Grove",
    "Gl": "Gully", "Gly": "Gully",
    "Hts": "Heights", "Hts.": "Heights",
    "Hgts": "Heights", "Hghts": "Heights", "Ht": "Heights",
    "Blvd": "Boulevard", "Bvld": "Boulevard", "Bvd": "Boulevard", "Blv": "Boulevard",
    "Pde": "Parade", "Pde.": "Parade",
    "Lne": "Lane", "Ln": "Lane", "Ln.": "Lane",
    "Mnr": "Manor", "Mnr.": "Manor",
    "Sq": "Square", "Sq.": "Square",
    "Cct": "Circuit", "Circ": "Circuit",
    "Cl": "Close",
    "Hwy": "Highway", "Hwy.": "Highway",
    "Pkwy": "Parkway", "Pky": "Parkway",
    "Trl": "Trail", "Tr": "Trail",
    "Wlk": "Walk", "Wk": "Walk",
    "Pt": "Point", "Pt.": "Point",
    "Way": "Way",
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

def correct_suffix_typos(street_name: str) -> str:
    typo_map = {
        "Hght": "Heights", "Hghts": "Heights", "Hts": "Heights",
        "Cresent": "Crescent", "Cresent.": "Crescent",
        "Rd.": "Road", "St.": "Street"
    }
    parts = (street_name or "").split()
    if parts:
        last = parts[-1].title()
        if last in typo_map:
            parts[-1] = typo_map[last]
    return " ".join(parts)


def fmt_addr_parts(*args) -> str:
    """
    Build a canonical query string.

    Supports BOTH call styles (legacy-safe):
      A) fmt_addr_parts(num, street, suburb)
      B) fmt_addr_parts(apartment, num, street, suburb)

    Output:
      - If suburb is present (and not Auckland): "<num> <street>, <suburb>, Auckland"
      - If suburb is blank OR suburb == Auckland: "<num> <street>, Auckland" (single Auckland only)
    """
    # -------------------------
    # Parse arguments
    # -------------------------
    ap = ""
    num = ""
    street = ""
    suburb = ""

    if len(args) == 3:
        num, street, suburb = args
    elif len(args) == 4:
        ap, num, street, suburb = args
    else:
        # Defensive: best-effort join
        args = [a for a in args if a is not None]
        return " ".join(str(a).strip() for a in args if str(a).strip())

    ap = (ap or "").strip()
    num = (num or "").strip()
    street = (street or "").strip()
    suburb = (suburb or "").strip()

    # Treat Auckland as "no suburb" to avoid "Auckland, Auckland"
    if suburb.lower() == "auckland":
        suburb = ""

    # If Number already contains a unit/flat, ignore ApartmentNumber
    if ap and num and "/" not in num:
        ap_clean = ap.replace(" ", "")
        if not ap_clean.lower().startswith(("unit", "flat")):
            ap_clean = f"Unit{ap_clean}"
        num = f"{ap_clean}/{num}"
    elif ap and not num:
        num = ap  # rare: only apartment provided

    # Street cleanup
    street = correct_suffix_typos(street).title()
    parts = street.split()
    if parts and parts[-1] in street_suffix_map:
        parts[-1] = street_suffix_map[parts[-1]]
    street = " ".join(parts).strip()

    # Suburb cleanup
    suburb = suburb.title()

    # Always include "Auckland" once
    if suburb:
        if num:
            return f"{num} {street}, {suburb}, Auckland".strip()
        return f"{street}, {suburb}, Auckland".strip()

    # suburb blank -> single Auckland only
    if num:
        return f"{num} {street}, Auckland".strip()
    return f"{street}, Auckland".strip()




def fmt_addr_str(address: str) -> str:
    n, s, sub = _to_parts(address)
    return fmt_addr_parts(n, s, sub)


# =============================================================================
# Unit helpers + external query helpers
# =============================================================================

UNIT_RX = re.compile(r"^Unit([A-Z0-9]+)/(\d+)$", re.IGNORECASE)

def to_external_query(addr: str) -> str:
    """
    Convert:
      'UnitB/246 Bucklands Beach Rd, Suburb' -> '246B Bucklands Beach Road, Suburb, Auckland'

    PATCHED:
    - Handles Unit/Flat + alnum units (Unit5A/12)
    - Handles ranges (UnitB/12-14)
    - Handles house-first flips (12/UnitB)
    - Does NOT depend on UNIT_RX (which is too strict)
    """
    m = ADDRESS_PARSE_RX.match((addr or "").strip())
    if not m:
        return addr

    number, street, suburb = [x.strip() for x in m.groups()]
    street = correct_suffix_typos(street).title()
    suburb = suburb.title()

    # Normalize any house-first forms into unit-first for parsing stability
    number_nf = flip_unit_prefix_in_number(number)

    # Parse Unit/Flat + house/range
    # Accept: UnitB/246, Unit5A/12-14, Flat2/7A
    rx = re.compile(
        r"^\s*(unit|flat)\s*([A-Za-z0-9]+)\s*/\s*([0-9]+[A-Za-z]?(?:\s*-\s*[0-9]+[A-Za-z]?)?)\s*$",
        re.IGNORECASE,
    )
    um = rx.match((number_nf or "").strip())
    if um:
        _kind, unit_token, house = um.groups()
        unit_token = (unit_token or "").strip().upper()
        house = re.sub(r"\s*-\s*", "-", (house or "").strip())
        # External style: append unit token to the house/range (e.g., 246B, 12-14B)
        number_ext = f"{house}{unit_token}"
    else:
        number_ext = re.sub(r"\s+", "", number)

    parts = street.split()
    if parts and parts[-1] in street_suffix_map:
        parts[-1] = street_suffix_map[parts[-1]]
    street = " ".join(parts)

    # Keep Auckland once; suburb from regex is guaranteed present here
    return f"{number_ext} {street}, {suburb}, Auckland"



# Matches "UnitB/246" and converts to "246 Street, Unit B, Suburb"
def unit_word_variant(addr: str) -> str:
    """
    Variant formatter for external geocoders:

    Convert:
      'UnitB/246 Bucklands Beach Rd, Suburb'
    to:
      '246 Bucklands Beach Road, Unit B, Suburb, Auckland'

    PATCHED:
    - Handles Unit/Flat + alnum units (Unit5A/12)
    - Handles ranges (UnitB/12-14)
    - Handles house-first flips (12/UnitB)
    - Does NOT depend on UNIT_RX (which is too strict)
    """
    m = ADDRESS_PARSE_RX.match((addr or "").strip())
    if not m:
        return addr

    number, street, suburb = [x.strip() for x in m.groups()]

    # Normalize into unit-first for parsing
    number_nf = flip_unit_prefix_in_number(number)

    rx = re.compile(
        r"^\s*(unit|flat)\s*([A-Za-z0-9]+)\s*/\s*([0-9]+[A-Za-z]?(?:\s*-\s*[0-9]+[A-Za-z]?)?)\s*$",
        re.IGNORECASE,
    )
    um = rx.match((number_nf or "").strip())
    if not um:
        return addr

    kind, unit_token, house = um.groups()
    kind = (kind or "Unit").strip().title()  # "Unit" or "Flat"
    unit_token = (unit_token or "").strip().upper()
    house = re.sub(r"\s*-\s*", "-", (house or "").strip())

    street = correct_suffix_typos(street).title()
    suburb = suburb.title()

    parts = street.split()
    if parts and parts[-1] in street_suffix_map:
        parts[-1] = street_suffix_map[parts[-1]]
    street = " ".join(parts).strip()

    return f"{house} {street}, {kind} {unit_token}, {suburb}, Auckland"



_UNIT_PREFIX_RE = re.compile(
    r"^\s*Unit\s*([A-Za-z0-9]+)\s*/\s*([0-9]+[A-Za-z]?(?:\s*-\s*[0-9]+[A-Za-z]?)?)\s*$",
    re.IGNORECASE
)


# =============================================================================
# Number + street normalization used by LINZ and external calls
# =============================================================================

_RANGE_RX  = re.compile(r"^\s*(\d+[A-Za-z]?)[\s-]+(\d+[A-Za-z]?)\s*$")
_SIMPLE_RX = re.compile(r"^\s*(\d+)([A-Za-z]?)\s*$")
_SLASH_RX  = re.compile(r"^\s*(\d+[A-Za-z]?)\s*/\s*(\d+[A-Za-z]?)\s*$")

def normalize_number(number_val: str) -> str:
    """
    Normalizes NZ unit/house numbers consistently (GoogleSheets-friendly).

    Key behavior:
    - Converts month codes (Jan–Dec) to Unit1–Unit12 based on correct month index.
    - Handles letter suffixes (37B → UnitB/37).
    - Cleans separators (~, _, -, etc.) into '/'.
    - Ensures Unit prefix, uppercased.
    - ALSO flips  '12/UnitA' -> 'UnitA/12'  (preferred for GoogleSheets flows).

    IMPORTANT PATCH:
    - If input is house-first (e.g. "12/UnitA" or "12/FlatB"), flip it EARLY
      before any "prepend Unit" logic runs. This prevents corrupt forms like
      "Unit12/UnitA" or "UnitA/Unit12" which break LINZ DB matching.
    """
    number = (number_val or "").strip()
    number = re.sub(r"\s+", "", number)  # collapse spaces

    # --- PATCH: normalize house-first unit forms early (e.g. 12/UnitA -> UnitA/12) ---
    try:
        number = flip_unit_prefix_in_number(number)
    except Exception:
        pass

    month_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5,
        "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10,
        "nov": 11, "dec": 12
    }

    # Match patterns like "1-Nov", "2-Oct", "Nov-41", or just "Nov"
    m = re.match(r"^(\d*)[-_/]*([A-Za-z]{3})(?:[-_/]*(\d+))?$", number, re.IGNORECASE)
    if m:
        unit_part, month_abbr, trailing_num = m.groups()
        month_num = month_map.get(month_abbr.lower(), 1)

        if unit_part:
            out = f"Unit{unit_part}/{month_num}"
            return flip_unit_prefix_in_number(out)
        elif trailing_num:
            out = f"Unit{month_num}/{trailing_num}"
            return flip_unit_prefix_in_number(out)
        else:
            out = f"Unit{month_num}"
            return flip_unit_prefix_in_number(out)

    # Letter suffix (e.g., 37B → UnitB/37)
    m = re.match(r"^(\d+)([A-Za-z])$", number)
    if m:
        out = f"Unit{m.group(2).upper()}/{m.group(1)}"
        return flip_unit_prefix_in_number(out)

    # Replace odd separators with '/'
    number = re.sub(r"[~_\-,.\\:;!\=\+\"'\(\)]", "/", number)

    # Prepend 'Unit' if there’s a slash but no Unit/Flat prefix
    # (Safe now because house-first forms were flipped early above)
    if "/" in number and not number.lower().startswith(("unit", "flat")):
        parts = number.split("/", 1)
        number = f"Unit{parts[0]}/{parts[1]}"

    # Normalize casing
    if number.lower().startswith("unit"):
        prefix = "Unit"
        remainder = "".join(ch.upper() if ch.isalpha() else ch for ch in number[4:])
        number = prefix + remainder
    elif number.lower().startswith("flat"):
        prefix = "Flat"
        remainder = "".join(ch.upper() if ch.isalpha() else ch for ch in number[4:])
        number = prefix + remainder
    else:
        number = "".join(ch.upper() if ch.isalpha() else ch for ch in number)

    # Final: enforce GoogleSheets preferred Unit-first form if it’s flipped
    return flip_unit_prefix_in_number(number)


def flip_unit_prefix_in_number_house_first(number: str) -> str:
    """
    Legacy-style flip:
      UnitA/12 -> 12/UnitA
    Leaves non-matching values unchanged.
    """
    s = (number or "").strip()
    m = _UNIT_PREFIX_RE.match(s)
    if not m:
        return s
    unit_token = m.group(1).upper()
    house = re.sub(r"\s*-\s*", "-", m.group(2))
    return f"{house}/Unit{unit_token}"

def flip_unit_prefix_in_number_unit_first(number: str) -> str:
    """
    Explicit alias for the GoogleSheets-preferred unit-first normal form:
      12/UnitA -> UnitA/12
    """
    return flip_unit_prefix_in_number(number)

def merge_number_with_street(number_val, street_val):
    """
    Combines and normalizes NZ unit/house numbers with streets (copied behavior).
    """
    num_clean = re.sub(r"\s+", "", (number_val or "").strip())

    m = re.match(r"^(\d+)([A-Za-z])$", num_clean)
    if m:
        num_clean = f"Unit{m.group(2).upper()}/{m.group(1)}"

    m2 = re.match(r"^\s*(\d+)\s+(.*)$", (street_val or "").strip())
    if m2:
        street_num, street_name = m2.groups()
        if street_num == re.sub(r"\D", "", num_clean):
            street_val = street_name

    street_val = re.sub(r"bucklands\s*beach", "Bucklands Beach", street_val or "", flags=re.IGNORECASE)

    parts = (street_val or "").strip().title().split()
    if parts and parts[-1] in street_suffix_map:
        parts[-1] = street_suffix_map[parts[-1]]
    street_val = " ".join(parts)

    return num_clean, street_val


# =============================================================================
# Distance + tuple validators
# =============================================================================

def haversine_distance(lat1, lon1, lat2, lon2) -> float:
    R = 6371000
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    d_phi = math.radians(float(lat2) - float(lat1))
    d_lambda = math.radians(float(lon2) - float(lon1))
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _maybe_swap_latlon(lat, lon):
    try:
        la = float(lat); lo = float(lon)
    except Exception:
        return lat, lon

    if abs(la) > 90 and abs(lo) <= 90:
        return lo, la
    if 170.0 <= abs(la) <= 180.0 and (-47.0 <= lo <= -34.0):
        return lo, la

    if is_in_auckland(lo, la) and not is_in_auckland(la, lo):
        return lo, la

    return la, lo


def _is_valid_geocode_tuple(t) -> bool:
    """(addr, lat, lon, postal) with real lat/lon."""
    try:
        return (
            isinstance(t, tuple) and len(t) == 4 and
            t[0] and t[1] is not None and t[2] is not None and
            not (str(t[1]).strip() == "" or str(t[2]).strip() == "")
        )
    except Exception:
        return False


# =============================================================================
# LINZ DB path + helpers
# =============================================================================

def _default_linz_db_path() -> str:
    # Preferred: alongside app folder:  <app>/Street Database/linz_auckland.sqlite
    here = Path(__file__).resolve().parent
    candidate = here / "Street Database" / "linz_auckland.sqlite"
    if candidate.exists():
        return str(candidate)
    # fallback: alongside file
    candidate2 = here / "linz_auckland.sqlite"
    return str(candidate2)

LINZ_DB = os.environ.get("LINZ_DB_PATH", _default_linz_db_path())


def linz_suffixes_for_base(base):
    """Return set of suffixes observed in LINZ for a given base, e.g. 'Arrowsmith' -> {'Drive','Road'}"""
    conn = None
    try:
        with _db_lock:
            conn = sqlite3.connect(LINZ_DB, check_same_thread=False, timeout=30.0)
            rows = conn.execute(
                "SELECT DISTINCT Street FROM addresses WHERE Street LIKE ? ESCAPE '\\' COLLATE NOCASE",
                (f"{base} %",)
            ).fetchall()

        return {str(r[0]).split()[-1].title() for r in rows if r and r[0]}
    except Exception:
        return set()
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass



# =============================================================================
# LINZ geocode (SQLite local) + parallel wrapper
# =============================================================================

def geocode_linz(address, memory_conn=None):
    """
    LINZ local geocode with safer number matching + index-friendly predicates.
    Returns: (formatted_address, lat, lon, postal)
    """
    def _base_and_suffix(st):
        st = (st or "").strip().title()
        parts = st.split()
        if not parts:
            return st, ""
        return " ".join(parts[:-1]).strip(), parts[-1].title()

    m = ADDRESS_PARSE_RX.match(address or "")
    if not m:
        return None, None, None, None

    num, street, suburb = [x.strip() for x in m.groups()]

    try:
        # Normalize into GoogleSheets-friendly unit-first form
        num = normalize_number(num)

        # ALSO compute the legacy / DB-common house-first form (12/UnitA)
        num_house_first = flip_unit_prefix_in_number_house_first(num)

        # Keep your existing behavior
        num, street = merge_number_with_street(num, street)
        street = correct_suffix_typos(street).strip().title()
        suburb = suburb.strip().title()
    except Exception:
        num_house_first = flip_unit_prefix_in_number_house_first(num)
        street = (street or "").strip().title()
        suburb = (suburb or "").strip().title()

    base, _suffix = _base_and_suffix(street)

    row = None
    like_patterns = []
    digits = re.sub(r"\D", "", num or "")
    if digits:
        # Keep the legacy LIKE patterns (covers both forms)
        like_patterns = [f"Unit%/{digits}", f"{digits}/%", f"%/{digits}/%"]

    # For exact matches, try BOTH number formats
    exact_numbers = []
    if num:
        exact_numbers.append(num)
    if num_house_first and num_house_first != num:
        exact_numbers.append(num_house_first)

    conn = None
    try:
        with _db_lock:
            conn = sqlite3.connect(LINZ_DB, check_same_thread=False, timeout=30.0)
            c = conn.cursor()

            # 1) Exact match (try both number forms)
            for n_exact in exact_numbers:
                c.execute(
                    """
                    SELECT Street, Suburb, Latitude, Longitude, Postalcode
                      FROM addresses
                     WHERE Street = ? COLLATE NOCASE
                       AND Suburb = ? COLLATE NOCASE
                       AND Number = ?
                     LIMIT 1
                    """,
                    (street, suburb, n_exact),
                )
                row = c.fetchone()
                if row:
                    break

            # 2) Guarded LIKE patterns for unit/house formats
            if not row and like_patterns:
                placeholders = " OR ".join(["Number LIKE ?"] * len(like_patterns))
                c.execute(
                    f"""
                    SELECT Street, Suburb, Latitude, Longitude, Postalcode
                      FROM addresses
                     WHERE Street = ? COLLATE NOCASE
                       AND Suburb = ? COLLATE NOCASE
                       AND ({placeholders})
                     LIMIT 1
                    """,
                    (street, suburb, *like_patterns),
                )
                row = c.fetchone()

            # 3) Base-prefix search (suffix-agnostic) — also try both number forms
            has_suburb = bool(suburb and suburb.lower() != "auckland")
            if not row and base:
                for n_exact in exact_numbers or [num]:
                    if has_suburb:
                        c.execute(
                            """
                            SELECT Street, Suburb, Latitude, Longitude, Postalcode
                              FROM addresses
                             WHERE Street LIKE ? ESCAPE '\\' COLLATE NOCASE
                               AND Suburb = ? COLLATE NOCASE
                               AND Number = ?
                             LIMIT 1
                            """,
                            (f"{base} %", suburb, n_exact),
                        )
                    else:
                        c.execute(
                            """
                            SELECT Street, Suburb, Latitude, Longitude, Postalcode
                              FROM addresses
                             WHERE Street LIKE ? ESCAPE '\\' COLLATE NOCASE
                               AND Number = ?
                             LIMIT 1
                            """,
                            (f"{base} %", n_exact),
                        )
                    row = c.fetchone()
                    if row:
                        break

            # 4) suburb-loosen fallback — also try both number forms
            if (not row) and base and has_suburb:
                for n_exact in exact_numbers or [num]:
                    c.execute(
                        """
                        SELECT Street, Suburb, Latitude, Longitude, Postalcode
                          FROM addresses
                         WHERE Street LIKE ? ESCAPE '\\' COLLATE NOCASE
                           AND Number = ?
                         LIMIT 1
                        """,
                        (f"{base} %", n_exact),
                    )
                    row = c.fetchone()
                    if row:
                        break

        if row:
            s, sub, lat, lon, postal = row
            lat = float(lat); lon = float(lon)
            return f"{str(s).strip().title()}, {str(sub).strip().title()}, Auckland", lat, lon, (postal or "")
    except Exception:
        pass
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass

    # Optional: memory DB (same behavior as your original)
    if memory_conn:
        try:
            mc = memory_conn.cursor()
            has_suburb = bool(suburb and suburb.lower() != "auckland")

            # base-prefix number match (try both number forms)
            if base:
                for n_exact in exact_numbers or [num]:
                    if has_suburb:
                        mc.execute(
                            """
                            SELECT street, suburb, latitude, longitude, postalcode
                              FROM other_addresses
                             WHERE street LIKE ? ESCAPE '\\' COLLATE NOCASE
                               AND suburb = ? COLLATE NOCASE
                               AND number = ?
                             LIMIT 1
                            """,
                            (f"{base} %", suburb, n_exact),
                        )
                    else:
                        mc.execute(
                            """
                            SELECT street, suburb, latitude, longitude, postalcode
                              FROM other_addresses
                             WHERE street LIKE ? ESCAPE '\\' COLLATE NOCASE
                               AND number = ?
                             LIMIT 1
                            """,
                            (f"{base} %", n_exact),
                        )
                    row = mc.fetchone()
                    if row:
                        break

            # guarded LIKE on number (unchanged)
            if (not row) and like_patterns:
                placeholders = " OR ".join(["number LIKE ?"] * len(like_patterns))
                if has_suburb:
                    mc.execute(
                        f"""
                        SELECT street, suburb, latitude, longitude, postalcode
                          FROM other_addresses
                         WHERE street LIKE ? ESCAPE '\\' COLLATE NOCASE
                           AND suburb LIKE ? ESCAPE '\\' COLLATE NOCASE
                           AND ({placeholders})
                         LIMIT 1
                        """,
                        (f"%{street}%", f"%{suburb}%", *like_patterns),
                    )
                else:
                    mc.execute(
                        f"""
                        SELECT street, suburb, latitude, longitude, postalcode
                          FROM other_addresses
                         WHERE street LIKE ? ESCAPE '\\' COLLATE NOCASE
                           AND ({placeholders})
                         LIMIT 1
                        """,
                        (f"%{street}%", *like_patterns),
                    )
                row = mc.fetchone()

            if row:
                s, sub, lat, lon, postal = row
                lat = float(lat); lon = float(lon)
                return f"{str(s).strip().title()}, {str(sub).strip().title()}, Auckland", lat, lon, (postal or "")
        except Exception:
            pass

    return None, None, None, None




def geocode_linz_parallel(address, memory_conn=None):
    """
    Run LINZ SQLite and memory DB lookups in parallel.
    Returns: (label, lat, lon, postal) with lat/lon floats, Auckland-gated.

    PATCH:
    - Records a miss reason into LAST_GEOCODE_REASON[address] when LINZ misses,
      including parse failures vs true "not found" vs gated-out.
    """
    def _normalize_and_gate(tpl):
        if not (isinstance(tpl, tuple) and len(tpl) == 4):
            return None
        label, lat, lon, postal = tpl
        try:
            la = float(lat); lo = float(lon)
        except Exception:
            return None
        la, lo = _maybe_swap_latlon(la, lo)
        if not is_in_auckland(la, lo):
            return None
        return (label, la, lo, postal or "")

    def try_sqlite():
        return geocode_linz(address), "LINZ_SQLITE"

    def try_memory():
        if memory_conn:
            return geocode_linz(address, memory_conn=memory_conn), "LINZ_MEMORY"
        return (("", "", "", ""), "LINZ_MEMORY")

    from concurrent.futures import ThreadPoolExecutor, as_completed

    addr_key = (address or "").strip()

    # Pre-check parse. If parse fails, LINZ can never hit.
    try:
        if addr_key and not ADDRESS_PARSE_RX.match(addr_key):
            _set_geocode_reason(addr_key, "LINZ: address parse failed (ADDRESS_PARSE_RX no match)")
    except Exception:
        pass

    with ThreadPoolExecutor(max_workers=2) as executor:
        futs = [executor.submit(fn) for fn in (try_sqlite, try_memory)]
        for fut in as_completed(futs):
            try:
                result, source = fut.result()
            except Exception as e:
                # Track which LINZ branch errored (rare, but helpful)
                try:
                    _set_geocode_reason(addr_key, f"LINZ: {source} exception {type(e).__name__}: {e}")
                except Exception:
                    pass
                continue

            norm = _normalize_and_gate(result)
            if norm:
                try:
                    with geocode_lock:
                        geocode_sources_used[source] += 1
                except Exception:
                    pass
                try:
                    log_correction("Geocode Success", f"{addr_key} → matched in {source}")
                except Exception:
                    pass
                return norm

    # If we get here, LINZ did not return an Auckland-valid tuple.
    # If parse was OK and we don't already have a specific reason, record "not found / gated".
    try:
        if addr_key and not get_last_geocode_reason(addr_key):
            if ADDRESS_PARSE_RX.match(addr_key):
                _set_geocode_reason(addr_key, "LINZ: no match in SQLite/memory OR result outside Auckland gate")
            else:
                _set_geocode_reason(addr_key, "LINZ: parse failed (ADDRESS_PARSE_RX)")
    except Exception:
        pass

    try:
        log_correction("LINZ Miss", f"{addr_key} → {get_last_geocode_reason(addr_key)}")
    except Exception:
        pass

    return ("", "", "", "")



# =============================================================================
# External geocoders
# =============================================================================

PHOTON_URL = "https://photon.komoot.io/api/"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
GEOCODEXYZ_URL = "https://geocode.xyz"

def geocode_photon(address):
    try:
        resp = requests.get(
            PHOTON_URL,
            params={
                "q": address,
                "limit": 1,
                "lang": "en",
                "bbox": f"{AUCKLAND_LON_MIN},{AUCKLAND_LAT_MIN},{AUCKLAND_LON_MAX},{AUCKLAND_LAT_MAX}",
            },
            timeout=5,
        )
        if resp.status_code != 200:
            return None
        data = resp.json() or {}
        feats = data.get("features") or []
        if not feats:
            return None
        f0 = feats[0] or {}
        geom = (f0.get("geometry") or {}).get("coordinates") or []
        if len(geom) != 2:
            return None
        lon, lat = geom[0], geom[1]
        lat, lon = _maybe_swap_latlon(lat, lon)
        if not is_in_auckland(lat, lon):
            return None
        props = f0.get("properties") or {}
        label = props.get("name") or address
        return (str(label), float(lat), float(lon), "")
    except Exception:
        return None


def geocode_nominatim(address):
    try:
        headers = {"User-Agent": "NZAddressCleaner/1.0"}
        params = {
            "q": address,
            "format": "jsonv2",
            "addressdetails": 1,
            "limit": 1,
            "countrycodes": "nz",
            "viewbox": f"{AUCKLAND_LON_MIN},{AUCKLAND_LAT_MAX},{AUCKLAND_LON_MAX},{AUCKLAND_LAT_MIN}",
            "bounded": 1,
        }
        resp = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        arr = resp.json() or []
        if not arr:
            return None
        r0 = arr[0] or {}
        lat = r0.get("lat"); lon = r0.get("lon")
        if lat is None or lon is None:
            return None
        lat, lon = _maybe_swap_latlon(float(lat), float(lon))
        if not is_in_auckland(lat, lon):
            return None
        label = r0.get("display_name") or address
        postcode = ""
        try:
            postcode = (r0.get("address") or {}).get("postcode") or ""
        except Exception:
            postcode = ""
        return (str(label), float(lat), float(lon), str(postcode))
    except Exception:
        return None


def geocode_geocodexyz(address):
    try:
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
        lat, lon = _maybe_swap_latlon(float(lat), float(lon))
        if not is_in_auckland(lat, lon):
            return None
        label = data.get("standard", {}).get("addresst") or address
        return (str(label), float(lat), float(lon), "")
    except Exception:
        return None


# =============================================================================
# High-level chooser
# =============================================================================

def get_lat_long(address, memory_conn=None, known_geocodes_by_street=None):
    """
    Returns a 4-tuple: (label, lat, lon, postal)

    Current strategy (enhanced):
      0) Canonicalize address (fmt_addr_str) which includes Auckland once
      1) LINZ (parallel) using canonical form
      2) External providers using 3 query variants:
           - to_external_query(addr_fmt)
           - unit_word_variant(addr_fmt)
           - addr_fmt
      3) NEW: retry external providers WITHOUT trailing ", Auckland"
      4) NEW: if still miss and house number is a simple integer:
             probe ±1..±5 neighboring house numbers
             - try LINZ first (fast)
             - then try Nominatim (best coverage) with and without Auckland

    Notes:
      - LINZ parsing expects the canonical "... , Auckland" style; we keep it for LINZ.
      - "without Auckland" is applied only to external providers.
      - Keeps original API and gating semantics (Auckland-bounded providers).
    """
    addr = (address or "").strip()
    if not addr:
        return ("", "", "", "")

    # Canonical "..., Auckland" form for ALL sources (LINZ parsing depends on ADDRESS_PARSE_RX).
    addr_fmt = fmt_addr_str(addr)

    # Provider-friendly variants (non-LINZ)
    addr_ext = addr_fmt
    addr_unit_words = addr_fmt
    try:
        addr_ext = to_external_query(addr_fmt)
    except Exception:
        addr_ext = addr_fmt
    try:
        addr_unit_words = unit_word_variant(addr_fmt)
    except Exception:
        addr_unit_words = addr_fmt

    def _strip_trailing_auckland(s: str) -> str:
        s = (s or "").strip()
        if not s:
            return s
        # remove a single trailing ", Auckland" (case-insensitive)
        if re.search(r",\s*auckland\s*$", s, flags=re.IGNORECASE):
            s = re.sub(r",\s*auckland\s*$", "", s, flags=re.IGNORECASE).strip()
        return s

    def _try_provider(fn, provider_name: str, *queries: str):
        seen = set()
        last_reason = ""
        for q in queries:
            q2 = (q or "").strip()
            if not q2 or q2 in seen:
                continue
            seen.add(q2)
            try:
                out = fn(q2)
            except Exception as e:
                last_reason = f"{provider_name}: exception {type(e).__name__}: {e}"
                continue

            if out is None:
                last_reason = f"{provider_name}: no result (None)"
                continue

            if not _is_valid_geocode_tuple(out):
                last_reason = f"{provider_name}: returned invalid tuple"
                continue

            return out, ""

        return None, (last_reason or f"{provider_name}: no usable result")

    # -------------------------
    # 0) LINZ (fast local) — canonical form
    # -------------------------
    try:
        res = geocode_linz_parallel(addr_fmt, memory_conn=memory_conn)
        if _is_valid_geocode_tuple(res):
            try:
                _set_geocode_reason(addr_fmt, "")
            except Exception:
                pass
            return res
        else:
            if not get_last_geocode_reason(addr_fmt):
                _set_geocode_reason(addr_fmt, "LINZ: returned empty/invalid tuple")
    except Exception as e:
        _set_geocode_reason(addr_fmt, f"LINZ: exception {type(e).__name__}: {e}")

    # -------------------------
    # 1) Photon (with Auckland)
    # -------------------------
    try:
        res, why = _try_provider(geocode_photon, "PHOTON", addr_ext, addr_unit_words, addr_fmt)
        if _is_valid_geocode_tuple(res):
            with geocode_lock:
                geocode_sources_used["PHOTON"] += 1
            return res
        if why:
            _set_geocode_reason(addr_fmt, why)
    except Exception as e:
        _set_geocode_reason(addr_fmt, f"PHOTON: exception {type(e).__name__}: {e}")

    # -------------------------
    # 2) Nominatim (with Auckland)
    # -------------------------
    try:
        res, why = _try_provider(geocode_nominatim, "NOMINATIM", addr_ext, addr_unit_words, addr_fmt)
        if _is_valid_geocode_tuple(res):
            with geocode_lock:
                geocode_sources_used["NOMINATIM"] += 1
            return res
        if why:
            _set_geocode_reason(addr_fmt, why)
    except Exception as e:
        _set_geocode_reason(addr_fmt, f"NOMINATIM: exception {type(e).__name__}: {e}")

    # -------------------------
    # 3) Geocode.xyz (with Auckland)
    # -------------------------
    try:
        res, why = _try_provider(geocode_geocodexyz, "GEOCODEXYZ", addr_ext, addr_unit_words, addr_fmt)
        if _is_valid_geocode_tuple(res):
            with geocode_lock:
                geocode_sources_used["GEOCODEXYZ"] += 1
            return res
        if why:
            _set_geocode_reason(addr_fmt, why)
    except Exception as e:
        _set_geocode_reason(addr_fmt, f"GEOCODEXYZ: exception {type(e).__name__}: {e}")

    # -------------------------
    # 4) NEW: retry WITHOUT trailing ", Auckland" (external providers only)
    # -------------------------
    try:
        addr_fmt_no = _strip_trailing_auckland(addr_fmt)
        addr_ext_no = _strip_trailing_auckland(addr_ext)
        addr_unit_no = _strip_trailing_auckland(addr_unit_words)

        # Photon without Auckland
        res, _ = _try_provider(geocode_photon, "PHOTON", addr_ext_no, addr_unit_no, addr_fmt_no)
        if _is_valid_geocode_tuple(res):
            with geocode_lock:
                geocode_sources_used["PHOTON_NO_AUCKLAND"] += 1
            try:
                _set_geocode_reason(addr_fmt, "")
            except Exception:
                pass
            return res

        # Nominatim without Auckland
        res, _ = _try_provider(geocode_nominatim, "NOMINATIM", addr_ext_no, addr_unit_no, addr_fmt_no)
        if _is_valid_geocode_tuple(res):
            with geocode_lock:
                geocode_sources_used["NOMINATIM_NO_AUCKLAND"] += 1
            try:
                _set_geocode_reason(addr_fmt, "")
            except Exception:
                pass
            return res

        # Geocode.xyz without Auckland
        res, _ = _try_provider(geocode_geocodexyz, "GEOCODEXYZ", addr_ext_no, addr_unit_no, addr_fmt_no)
        if _is_valid_geocode_tuple(res):
            with geocode_lock:
                geocode_sources_used["GEOCODEXYZ_NO_AUCKLAND"] += 1
            try:
                _set_geocode_reason(addr_fmt, "")
            except Exception:
                pass
            return res
    except Exception:
        pass

    # -------------------------
    # 5) NEW: ±5 neighboring house-number probing (only for plain integer house numbers)
    # -------------------------
    try:
        num_s, street_s, suburb_s = _to_parts(addr_fmt)
        num_s = (num_s or "").strip()
        street_s = (street_s or "").strip()
        suburb_s = (suburb_s or "").strip()

        # Only probe when the number is a simple integer (no Unit/Flat, no slash, no range, no letter)
        if num_s.isdigit() and street_s:
            base = int(num_s)
            # Probe deltas: 1..5, checking + then - for each delta (keeps it deterministic)
            for d in range(1, 6):
                for cand in (base + d, base - d):
                    if cand <= 0:
                        continue

                    # Build candidate canonical query for LINZ
                    cand_fmt = fmt_addr_parts(str(cand), street_s, suburb_s)

                    # 5a) LINZ first (fast + authoritative)
                    try:
                        res = geocode_linz_parallel(cand_fmt, memory_conn=memory_conn)
                        if _is_valid_geocode_tuple(res):
                            with geocode_lock:
                                geocode_sources_used["LINZ_NEARBY_NUMBER"] += 1
                            try:
                                _set_geocode_reason(addr_fmt, "")
                            except Exception:
                                pass
                            return res
                    except Exception:
                        pass

                    # 5b) Nominatim (with and without Auckland) — best chance for “street exists, numbers patchy”
                    cand_no = _strip_trailing_auckland(cand_fmt)
                    try:
                        res, _ = _try_provider(geocode_nominatim, "NOMINATIM", cand_fmt, cand_no)
                        if _is_valid_geocode_tuple(res):
                            with geocode_lock:
                                geocode_sources_used["NOMINATIM_NEARBY_NUMBER"] += 1
                            try:
                                _set_geocode_reason(addr_fmt, "")
                            except Exception:
                                pass
                            return res
                    except Exception:
                        pass
    except Exception:
        pass

    # Final miss
    if not get_last_geocode_reason(addr_fmt):
        _set_geocode_reason(addr_fmt, "All sources missed (LINZ/PHOTON/NOMINATIM/GEOCODEXYZ), incl. no-Auckland + ±5 probe")

    try:
        log_correction("Geocode Miss", f"{addr_fmt} → {get_last_geocode_reason(addr_fmt)}")
    except Exception:
        pass

    return ("", "", "", "")




from GoogleSheets_Log import autowrap_module  # noqa: E402

# Only wrap functions defined in THIS module (prevents wrapping imported callables)
try:
    autowrap_module(__name__, include_private=True, only_defined_here=True)
except TypeError:
    # Backward compatible with older GoogleSheets_Log.autowrap_module signatures
    autowrap_module(__name__, include_private=True)

