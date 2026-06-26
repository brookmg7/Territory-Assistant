#!/usr/bin/env python3
"""
GoogleSheets_CoreLite.py

Purpose
-------
Drop-in replacement for the subset of Clean_NewWorldScheduler "core" that the
GoogleSheets split depends on.

This file is intentionally:
- The ONLY module GoogleSheets_* imports as "core":
      import GoogleSheets_CoreLite as core
- A thin runtime layer + façade:
    • cancel/run wrapper
    • unit flipping
    • small logging helpers used by geocoders
    • imports + re-exports the polygon and geocode primitives so callers can use:
          core.<function_or_const>

Line-limit rule
---------------
To keep this module small and portable, the heavy logic lives in:
  - GoogleSheets_CoreLite_Polygons.py
  - GoogleSheets_CoreLite_Geocode.py

This module re-exports their public names.

Design rules
------------
- CoreLite modules import only stdlib + requests (in Geocode).
- CoreLite must not import GoogleSheets_Utils/Master/Verify/Flows/Menu (no circulars).
"""

from __future__ import annotations

import threading
from typing import Any, Callable
import os
import csv
from pathlib import Path


from GoogleSheets_Log import module_loaded  # noqa: E402
module_loaded(__name__)

# =============================================================================
# Defaults for shared state (must exist before getattr fallbacks)
# =============================================================================
geocode_lock = threading.Lock()
_db_lock = threading.Lock()
geocode_sources_used: dict[str, int] = {}

# =============================================================================
# Cancel / run wrapper
# =============================================================================

# Shared cancel flag (thread-safe)
cancel_flag = threading.Event()


def listen_for_quit_key() -> None:
    """
    Background listener: press 'q' to request cancellation.

    Console policy:
    - Do NOT print directly here (avoids messing with tqdm bars / menu output).
    - Log to GoogleSheets_Log instead.

    Legacy-safe behavior:
    - Does NOT use input() (won't steal stdin).
    - On Windows uses msvcrt for non-blocking single-key polling.
    - Thread stays alive across runs.
    - Avoid 100% CPU spin when cancel_flag is set.
    """
    # NOTE: import inside to avoid any logger circulars during early startup
    try:
        from GoogleSheets_Log import decision, log_exception
    except Exception:
        decision = None  # type: ignore
        log_exception = None  # type: ignore

    if os.name != "nt":
        # Non-Windows / no console: safest fallback is do nothing.
        if decision:
            decision("QUIT_KEY_LISTENER_SKIPPED_NON_WINDOWS", module=__name__, fn="listen_for_quit_key")
        return

    try:
        import time
        import msvcrt  # type: ignore
    except Exception:
        if log_exception:
            log_exception("QUIT_KEY_LISTENER_IMPORT_FAILED", module=__name__, fn="listen_for_quit_key")
        return

    if decision:
        decision("QUIT_KEY_LISTENER_STARTED", module=__name__, fn="listen_for_quit_key")

    announced = False

    while True:
        try:
            # If already cancelled, idle without pegging CPU.
            if cancel_flag.is_set():
                if not announced:
                    # Log once per cancel cycle
                    if decision:
                        decision("CANCEL_REQUESTED_BY_Q", module=__name__, fn="listen_for_quit_key")
                    announced = True
                time.sleep(0.15)
                continue

            announced = False

            # Poll keyboard
            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                if (ch or "").lower() == "q":
                    cancel_flag.set()
                    # Keep thread alive for future runs.

            time.sleep(0.05)

        except Exception:
            if log_exception:
                log_exception("QUIT_KEY_LISTENER_LOOP_FAILED", module=__name__, fn="listen_for_quit_key")
            return






def run_with_cancel(fn: Callable[[], Any]) -> Any:
    """
    Run a function while allowing user cancellation.

    Behavior:
    - If cancel_flag is already set before starting, do not run the function.
    - If user presses Ctrl+C, set cancel_flag and re-raise KeyboardInterrupt.
    - We do NOT auto-clear cancel_flag (menu controls lifecycle).

    Logging:
    - Records START/SKIP/DONE/CANCELLED/EXCEPTION decisions.
    """
    try:
        from GoogleSheets_Log import decision, log_exception
    except Exception:
        decision = None  # type: ignore
        log_exception = None  # type: ignore

    fn_name = getattr(fn, "__name__", "<callable>")
    fn_qual = getattr(fn, "__qualname__", fn_name)

    if cancel_flag.is_set():
        if decision:
            decision(
                "RUN_WITH_CANCEL_SKIPPED_FLAG_ALREADY_SET",
                module=__name__,
                fn="run_with_cancel",
                extra={"target": fn_qual},
            )
        return None

    if decision:
        decision("RUN_WITH_CANCEL_START", module=__name__, fn="run_with_cancel", extra={"target": fn_qual})

    try:
        out = fn()

        if decision:
            cancelled = False
            try:
                cancelled = bool(cancel_flag.is_set())
            except Exception:
                cancelled = False

            decision(
                "RUN_WITH_CANCEL_DONE",
                module=__name__,
                fn="run_with_cancel",
                extra={"target": fn_qual, "cancelled": cancelled},
            )
        return out

    except KeyboardInterrupt:
        try:
            cancel_flag.set()
        except Exception:
            pass

        if decision:
            decision(
                "RUN_WITH_CANCEL_KEYBOARD_INTERRUPT",
                module=__name__,
                fn="run_with_cancel",
                extra={"target": fn_qual},
            )
        raise

    except Exception:
        if log_exception:
            log_exception(
                "RUN_WITH_CANCEL_EXCEPTION",
                module=__name__,
                fn="run_with_cancel",
                extra={"target": fn_qual},
            )
        raise




# =============================================================================
# Logging helpers (used by copied geocoders)
# =============================================================================

_log_lock = threading.Lock()
RESULT_ONLY_LOGS = True
GEOCODE_DEBUG = False



def _log_quiet(event: str, details: str = "", *, street: str = "", important: bool = False) -> None:
    """
    Legacy-compatible quiet logger:
      _log_quiet(event, details, street=..., important=...)

    Policy:
    - Never print from here.
    - Avoid log explosion at INFO level (RESULT_ONLY_LOGS), BUT:
      if the global logger level is DEBUG, we still write DEBUG events to file.
    """
    # Best-effort read of global log level (no hard dependency)
    gs_level = None
    try:
        import GoogleSheets_Log as _GSL  # type: ignore
        gs_level = getattr(_GSL, "_LEVEL", None)
    except Exception:
        gs_level = None

    # If RESULT_ONLY_LOGS is on and not important:
    # - At INFO/WARN/ERROR: suppress (legacy behavior)
    # - At DEBUG: allow through (so "log absolutely everything" works when GS_LOG_LEVEL=DEBUG)
    if RESULT_ONLY_LOGS and not important:
        if not (isinstance(gs_level, int) and gs_level <= 10):
            return

    try:
        from GoogleSheets_Log import _log_quiet as _gs_log_quiet  # preferred
        _gs_log_quiet(str(event), details=str(details), important=bool(important), street=str(street))
        return
    except Exception:
        pass

    # Fallback to structured file logging
    try:
        from GoogleSheets_Log import log_debug, log_info
        if isinstance(gs_level, int) and gs_level <= 10:
            log_debug(
                "CORELITE_QUIET",
                module=__name__,
                fn="_log_quiet",
                extra={"event": str(event), "details": str(details), "street": str(street), "important": bool(important)},
            )
        else:
            log_info(
                "CORELITE_QUIET",
                module=__name__,
                fn="_log_quiet",
                extra={"event": str(event), "details": str(details), "street": str(street), "important": bool(important)},
            )
    except Exception:
        pass





def _log_header_has_street(path_or_header) -> bool:
    """
    Accepts either:
      - header list[str]
      - a CSV path (str/Path) to read the header from

    Legacy-safe improvement:
    - Uses encoding fallbacks so Windows master/outputs (cp1252/latin-1) don't break.
    - Still returns False on any failure (callers treat it as "no street column").
    """
    try:
        if isinstance(path_or_header, (str, Path)):
            p = str(path_or_header)
            if not os.path.exists(p):
                return False

            # encoding fallbacks (matches Master module approach)
            encodings = ("utf-8-sig", "utf-8", "cp1252", "latin-1")
            header = None
            for enc in encodings:
                try:
                    with open(p, newline="", encoding=enc) as f:
                        r = csv.reader(f)
                        header = next(r, [])
                    break
                except Exception:
                    header = None
                    continue

            if header is None:
                return False
        else:
            header = path_or_header

        h = [str(x or "").strip().lower() for x in (header or [])]
        return ("street" in h) or ("old street" in h)
    except Exception:
        return False




def log_correction(event: str, details: str = "", *, street: str = "") -> None:
    """
    Legacy-compatible correction logger:
      log_correction(event, details, street="")

    Policy:
    - Always write to the shared log file (so you can audit decisions later).
    - Never print directly here.
    - GEOCODE_DEBUG can be used by calling code to decide whether to emit *extra*
      debug details, but correction events themselves should always be recorded.
    """
    try:
        from GoogleSheets_Log import log_correction as _gs_log_correction
        _gs_log_correction(str(event), details=str(details), street=str(street))
        return
    except Exception:
        pass

    # Fallback: route through quiet logger
    _log_quiet("CORRECTION", f"{event}: {details}", street=street, important=True)


_quit_listener_started = False
_quit_listener_lock = threading.Lock()

def start_quit_key_listener_once() -> None:
    """
    Start the 'press q to cancel' listener at most once per process.
    Safe to call repeatedly.

    Console policy:
    - No print. Logs decisions via GoogleSheets_Log.
    """
    global _quit_listener_started
    try:
        from GoogleSheets_Log import decision, log_exception
    except Exception:
        decision = None  # type: ignore
        log_exception = None  # type: ignore

    with _quit_listener_lock:
        if _quit_listener_started:
            if decision:
                decision("QUIT_KEY_LISTENER_ALREADY_RUNNING", module=__name__, fn="start_quit_key_listener_once")
            return

        t = threading.Thread(target=listen_for_quit_key, daemon=True, name="GS_QuitKeyListener")
        try:
            t.start()
            _quit_listener_started = True
            if decision:
                decision("QUIT_KEY_LISTENER_THREAD_STARTED", module=__name__, fn="start_quit_key_listener_once")
        except Exception:
            if log_exception:
                log_exception("QUIT_KEY_LISTENER_THREAD_START_FAILED", module=__name__, fn="start_quit_key_listener_once")
            return



# =============================================================================
# Unit flipping (legacy-compatible with Clean_NewWorldScheduler)
# =============================================================================

import re

# CoreLite MUST use legacy house-first form: UnitA/12 -> 12/UnitA
# Use a CORE-specific name so it cannot be overwritten by Geocode re-exports.
_UNIT_PREFIX_RE_CORE = re.compile(
    r'^\s*Unit\s*([A-Za-z0-9]+)\s*/\s*([0-9]+[A-Za-z]?(?:\s*-\s*[0-9]+[A-Za-z]?)?)\s*$',
    re.IGNORECASE
)

def flip_unit_prefix_in_number(number: str) -> str:
    """
    Legacy behavior (Clean_NewWorldScheduler):
      'UnitA/12'      -> '12/UnitA'
      'Unit5A/12-14'  -> '12-14/Unit5A'
      otherwise unchanged
    """
    s = (number or "").strip()
    m = _UNIT_PREFIX_RE_CORE.match(s)
    if not m:
        return s
    unit_token = m.group(1).upper()
    house = re.sub(r'\s*-\s*', '-', m.group(2))
    return f"{house}/Unit{unit_token}"

# --- Canonical form for THIS GoogleSheets pipeline: Unit-first (UnitA/12) ---
# Keep legacy house-first helper above intact, but provide an explicit unit-first normalizer.

_HOUSE_FIRST_RE_CORE = re.compile(
    r'^\s*([0-9]+[A-Za-z]?(?:\s*-\s*[0-9]+[A-Za-z]?)?)\s*/\s*Unit\s*([A-Za-z0-9]+)\s*$',
    re.IGNORECASE
)


def normalize_number_unit_first(number: str) -> str:
    """
    Project-canonical behavior (Flows/Verify expect stability here):
      '12/UnitA'     -> 'UnitA/12'
      '12-14/Unit5A' -> 'Unit5A/12-14'
      otherwise unchanged
    """
    s = (number or "").strip()
    m = _HOUSE_FIRST_RE_CORE.match(s)
    if not m:
        return s
    house = re.sub(r'\s*-\s*', '-', m.group(1))
    unit_token = m.group(2).upper()
    return f"Unit{unit_token}/{house}"


def normalize_units_for_rows_unit_first(rows: list[dict], number_field: str = "Number") -> int:
    """
    Normalize rows into Unit-first canonical form (UnitA/12).

    Use THIS in the GoogleSheets_* pipeline if you ever need a shared helper,
    because Flows/Verify are built around Unit-first stability.
    """
    flips = 0
    for r in rows or []:
        old = (r.get(number_field) or "").strip()
        if not old:
            continue
        new = normalize_number_unit_first(old)
        if new != old and new:
            r[number_field] = new
            try:
                _log_quiet(
                    "Normalize Unit (Unit-first)",
                    f"{old} → {new}",
                    street=(r.get("Street") or ""),
                    important=False,
                )
            except Exception:
                pass
            flips += 1
    return flips


def flip_units_for_rows_house_first(rows: list[dict], number_field: str = "Number") -> int:
    """
    Legacy behavior (Clean_NewWorldScheduler):
      'UnitA/12' -> '12/UnitA'
    Kept for compatibility with older code paths.
    """
    flips = 0
    for r in rows or []:
        old = (r.get(number_field) or "").strip()
        if not old:
            continue
        new = flip_unit_prefix_in_number(old)
        if new != old and new:
            r[number_field] = new
            try:
                _log_quiet(
                    "Flip Unit (house-first)",
                    f"{old} → {new}",
                    street=(r.get("Street") or ""),
                    important=False,
                )
            except Exception:
                pass
            flips += 1
    return flips

# Back-compat alias (keeps old imports working)
flip_units_for_rows = flip_units_for_rows_house_first

# =============================================================================
# Import the two heavy submodules and re-export their names
# =============================================================================

# Import as private module objects so we can delegate and also re-export explicitly.
try:
    import GoogleSheets_CoreLite_Polygons as _POLY
except Exception as e:
    raise ImportError("Missing GoogleSheets_CoreLite_Polygons.py (required for polygon splitting).") from e

try:
    import GoogleSheets_CoreLite_Geocode as _GEOCODE
except Exception as e:
    raise ImportError("Missing GoogleSheets_CoreLite_Geocode.py (required for geocoding/formatting).") from e

# =============================================================================
# Share state with Geocode module if it defines these (keeps legacy "core" behavior)
# =============================================================================
try:
    geocode_lock = getattr(_GEOCODE, "geocode_lock", geocode_lock)
except Exception:
    pass

try:
    _db_lock = getattr(_GEOCODE, "_db_lock", _db_lock)
except Exception:
    pass

try:
    geocode_sources_used = getattr(_GEOCODE, "geocode_sources_used", geocode_sources_used)
except Exception:
    pass

# ---------------- Polygon exports ----------------
split_cleaned_by_polygon_and_include_failed = _POLY.split_cleaned_by_polygon_and_include_failed
split_cleaned_by_suburb_and_include_failed = _POLY.split_cleaned_by_suburb_and_include_failed
_safe_float = _POLY._safe_float
_digits_int = _POLY._digits_int
_point_in_poly = _POLY._point_in_poly
_point_on_segment = _POLY._point_on_segment
_dist_point_to_segment = _POLY._dist_point_to_segment
_min_dist_to_polygon = _POLY._min_dist_to_polygon
_load_kml_polygons = _POLY._load_kml_polygons
_assign_point_to_polygons = _POLY._assign_point_to_polygons
_pick_nearest_number_target = _POLY._pick_nearest_number_target
canon_suburb = _POLY.canon_suburb

# Polygon-related constants (re-export if present)
NEARBY_SUBURBS = getattr(_POLY, "NEARBY_SUBURBS", {})
NEARBY_ALIAS = getattr(_POLY, "NEARBY_ALIAS", {})

# ---------------- Geocode exports ----------------
get_lat_long = _GEOCODE.get_lat_long
geocode_linz_parallel = _GEOCODE.geocode_linz_parallel
geocode_linz = _GEOCODE.geocode_linz
geocode_photon = _GEOCODE.geocode_photon
geocode_nominatim = _GEOCODE.geocode_nominatim
geocode_geocodexyz = _GEOCODE.geocode_geocodexyz

def fmt_addr_parts(apartment_or_unit: str, number: str, street: str, suburb: str) -> str:
    """
    GoogleSheets expects 4 args: (ApartmentNumber, Number, Street, Suburb)

    Geocode module fmt_addr_parts is the legacy 3-arg version: (Number, Street, Suburb).
    We combine apartment+number into a single number string then call the legacy formatter.

    PATCHED (bug fix):
    - If Number already contains a unit/house form, DO NOT merge ApartmentNumber again.
    - If Number is house-first (e.g., "12/UnitA"), normalize it to unit-first ("UnitA/12")
      for stability across caches and downstream logic.
    """
    ap = (apartment_or_unit or "").strip()
    num = (number or "").strip()

    # If the number already appears unit/house merged, ignore ApartmentNumber
    # to avoid "UnitA/UnitA/12" style corruption.
    if num and "/" in num:
        # normalize house-first -> unit-first when applicable
        try:
            num = normalize_number_unit_first(num)
        except Exception:
            pass
        ap = ""

    # Merge apartment/unit into number only when number is plain
    if ap and num:
        if not ap.lower().startswith(("unit", "flat")):
            ap = f"Unit{ap}"
        num = f"{ap}/{num}"
    elif ap and not num:
        num = ap

    return _GEOCODE.fmt_addr_parts(num, street, suburb)


_to_parts = _GEOCODE._to_parts
fmt_addr_str = _GEOCODE.fmt_addr_str
to_external_query = _GEOCODE.to_external_query
unit_word_variant = _GEOCODE.unit_word_variant
merge_number_with_street = _GEOCODE.merge_number_with_street
normalize_number = _GEOCODE.normalize_number
correct_suffix_typos = _GEOCODE.correct_suffix_typos
linz_suffixes_for_base = _GEOCODE.linz_suffixes_for_base

is_in_auckland = _GEOCODE.is_in_auckland
is_auckland_result = _GEOCODE.is_auckland_result
haversine_distance = _GEOCODE.haversine_distance
_maybe_swap_latlon = _GEOCODE._maybe_swap_latlon
_is_valid_geocode_tuple = _GEOCODE._is_valid_geocode_tuple

# Geocode constants/regexes (re-export if present)
ADDRESS_PARSE_RX = getattr(_GEOCODE, "ADDRESS_PARSE_RX", None)
UNIT_RX = getattr(_GEOCODE, "UNIT_RX", None)
_UNIT_PREFIX_RE = getattr(_GEOCODE, "_UNIT_PREFIX_RE", None)
PHOTON_URL = getattr(_GEOCODE, "PHOTON_URL", "")
NOMINATIM_URL = getattr(_GEOCODE, "NOMINATIM_URL", "")
GEOCODEXYZ_URL = getattr(_GEOCODE, "GEOCODEXYZ_URL", "")
LINZ_DB = getattr(_GEOCODE, "LINZ_DB", "")
street_suffix_map = getattr(_GEOCODE, "street_suffix_map", {})
MAX_ALLOWED_DISTANCE = getattr(_GEOCODE, "MAX_ALLOWED_DISTANCE", 0.0)

# NZ suburb canonical + postal lookups (GoogleSheets uses these)
macron_suburb_map = getattr(_GEOCODE, "macron_suburb_map", {})
nz_postal_lookup = getattr(_GEOCODE, "nz_postal_lookup", {})

# =============================================================================
# Compatibility names (keep GoogleSheets code unchanged)
# =============================================================================

forward_geocode_photon = geocode_photon
forward_geocode_nominatim = geocode_nominatim

# Some legacy cores had suburb_list; safe placeholder
suburb_list: list[str] = []


# =============================================================================
# Export surface
# =============================================================================

__all__ = [
    # Cancel / runtime
    "cancel_flag",
    "listen_for_quit_key",
    "run_with_cancel",

    # Unit flipping
    "flip_units_for_rows",
    "flip_units_for_rows_house_first",
    "flip_unit_prefix_in_number",


    # Logging helpers
    "_log_header_has_street",
    "log_correction",
    "_log_quiet",
    "_log_lock",
    "RESULT_ONLY_LOGS",
    "GEOCODE_DEBUG",

    # in __all__ list
    "start_quit_key_listener_once",

    # Locks / tracking
    "geocode_sources_used",
    "geocode_lock",
    "_db_lock",

    # Polygon API
    "split_cleaned_by_polygon_and_include_failed",
    "split_cleaned_by_suburb_and_include_failed",
    "_safe_float",
    "_digits_int",
    "_point_in_poly",
    "_point_on_segment",
    "_dist_point_to_segment",
    "_min_dist_to_polygon",
    "_load_kml_polygons",
    "_assign_point_to_polygons",
    "_pick_nearest_number_target",
    "canon_suburb",
    "NEARBY_SUBURBS",
    "NEARBY_ALIAS",

    # Geocode API
    "get_lat_long",
    "geocode_linz_parallel",
    "geocode_linz",
    "geocode_photon",
    "geocode_nominatim",
    "geocode_geocodexyz",
    "fmt_addr_parts",
    "_to_parts",
    "fmt_addr_str",
    "to_external_query",
    "unit_word_variant",
    "merge_number_with_street",
    "normalize_number",
    "correct_suffix_typos",
    "linz_suffixes_for_base",
    "is_in_auckland",
    "is_auckland_result",
    "haversine_distance",
    "_maybe_swap_latlon",
    "_is_valid_geocode_tuple",

    # Geocode constants
    "ADDRESS_PARSE_RX",
    "UNIT_RX",
    "_UNIT_PREFIX_RE",
    "PHOTON_URL",
    "NOMINATIM_URL",
    "GEOCODEXYZ_URL",
    "LINZ_DB",
    "street_suffix_map",
    "MAX_ALLOWED_DISTANCE",

    # NZ lookups
    "macron_suburb_map",
    "nz_postal_lookup",

    # Compatibility
    "forward_geocode_photon",
    "forward_geocode_nominatim",
    "suburb_list",
    "normalize_number_unit_first",
    "normalize_units_for_rows_unit_first",

]

from GoogleSheets_Log import autowrap_module  # noqa: E402

# Only wrap functions defined in THIS module (prevents wrapping imported callables / re-exports)
# Also skip infinite-loop thread target(s) to keep logs sane.
try:
    autowrap_module(
        __name__,
        include_private=True,
        only_defined_here=True,
        exclude_names={"listen_for_quit_key", "start_quit_key_listener_once"},

    )
except TypeError:
    # Backward compatible with older GoogleSheets_Log.autowrap_module signatures
    autowrap_module(__name__, include_private=True)

