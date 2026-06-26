#!/usr/bin/env python3
"""
GoogleSheets_Verify.py

Purpose
-------
Verification helpers for the Google Sheets cleaner/splitter.

This module contains ONLY the "verify split matches clean" tooling:
  - Build comparable address keys from CSV rows
  - Read keys from output_clean.csv
  - Read keys from suburb folder CSVs (excluding "*failed*.csv")
  - Compare the sets + detect duplicates across suburb files

Design / Imports
----------------
- Imports GoogleSheets_Utils (canonicalization helper) only.
- Does NOT import Flows or Menu (prevents circular imports).

Behavior compatibility
----------------------
The function bodies are copied verbatim from Clean_GoogleSheets.py so output/logic
matches your legacy script.

Temp-dir warning behavior
-------------------------
verify_split_matches_clean() references these module-level globals:
  - _SUPPRESS_TEMP_DIR_WARNINGS
  - _SUBURB_DIR_NEW
  - _SUBURB_DIR_OTHER

These defaults match the legacy script, but Flows may override them at runtime:
  import GoogleSheets_Verify as verify
  verify._SUPPRESS_TEMP_DIR_WARNINGS = True/False
  verify._SUBURB_DIR_NEW = Path("...")
  verify._SUBURB_DIR_OTHER = Path("...")
"""

from __future__ import annotations

import os
import csv
from pathlib import Path
from collections import Counter

# --- Logging: record module import as early as possible ---
from GoogleSheets_Log import module_loaded  # noqa: E402
module_loaded(__name__)

# =============================================================================
# Imports from Utils (canon/caching)
# =============================================================================
from GoogleSheets_Utils import _canon_text_cached, _split_unit_house



# =============================================================================
# Legacy-compatible globals (referenced by verify_split_matches_clean)
# =============================================================================

# Default matches Clean_GoogleSheets.py
_SUPPRESS_TEMP_DIR_WARNINGS: bool = True

# Temp split folders used by the routed flows (Options 3/4)
_SUBURB_DIR_NEW: Path = Path("New_Addresses_By_Suburb__NEW")
_SUBURB_DIR_OTHER: Path = Path("New_Addresses_By_Suburb__OTHER")


# =============================================================================
# Key helpers
# =============================================================================

def _addr_key(row: dict) -> tuple[str, str, str, str]:
    """
    Verification address key:
      (ApartmentNumber, HouseNumber, Street, Suburb) canonicalized.

    Parity fix:
    - Unifies representations where Unit is stored in ApartmentNumber vs baked into Number.
      Examples that become identical keys:
        * ApartmentNumber="A", Number="12"
        * ApartmentNumber="",  Number="UnitA/12"
        * Unit="A",            Number="12"
        * Number="12/UnitA"
    - Uses _split_unit_house() (true unit/house detection, not "any slash").
    - Produces a canonical (ap, house) pair instead of forcing a merged "UnitX/NN" string.
    """
    def canon(x: str) -> str:
        return _canon_text_cached((x or "").strip())

    def _strip_unitish_prefix(s: str) -> str:
        s = (s or "").strip()
        if not s:
            return ""
        lo = s.lower()
        for pref in ("unit", "flat", "apt", "apartment"):
            if lo.startswith(pref):
                return s[len(pref):].strip()
        return s

    # Apartment/unit can appear under different headers depending on export
    ap = (row.get("ApartmentNumber") or "").strip()
    if not ap:
        ap = (row.get("Unit") or "").strip()
    if not ap:
        ap = (row.get("Apartment") or "").strip()
    if not ap:
        ap = (row.get("Flat") or "").strip()

    num = (row.get("Number") or "").strip()

    ap_norm = _strip_unitish_prefix(ap)
    house_norm = (num or "").strip()

    # If Number is merged like "UnitA/12" or "12/UnitA", split it.
    try:
        ap_guess, num_guess = _split_unit_house(num)
    except Exception:
        ap_guess, num_guess = ("", "")

    if num_guess:
        ap_guess_norm = _strip_unitish_prefix(ap_guess)

        # If ap missing, take it from merged number
        if (not ap_norm) and ap_guess_norm:
            ap_norm = ap_guess_norm
            house_norm = num_guess

        # If ap present and matches guessed unit, keep ap and use house from split
        elif ap_norm and ap_guess_norm and canon(ap_norm) == canon(ap_guess_norm):
            house_norm = num_guess

        # If ap present but doesn't match the split unit, we still trust the split house
        else:
            house_norm = num_guess

    return (
        canon(ap_norm),
        canon(house_norm),
        canon(row.get("Street", "")),
        canon(row.get("Suburb", "")),
    )




def _dup_key_from_cleaned(rec: dict) -> tuple[str, str, str, str]:
    """
    Duplicate key for Sheets runs (pre-write), based on the *cleaned* values.

    Parity fix:
    - Same normalization as _addr_key().
    - Produces canonical (ApartmentNumber, HouseNumber, Street, Suburb) instead of merged strings.
    """
    def canon(x: str) -> str:
        return _canon_text_cached((x or "").strip())

    def _strip_unitish_prefix(s: str) -> str:
        s = (s or "").strip()
        if not s:
            return ""
        lo = s.lower()
        for pref in ("unit", "flat", "apt", "apartment"):
            if lo.startswith(pref):
                return s[len(pref):].strip()
        return s

    apt = (rec.get("ApartmentNumber") or "").strip()
    if not apt:
        apt = (rec.get("Unit") or "").strip()
    if not apt:
        apt = (rec.get("Apartment") or "").strip()
    if not apt:
        apt = (rec.get("Flat") or "").strip()

    num = (rec.get("Number") or "").strip()

    ap_norm = _strip_unitish_prefix(apt)
    house_norm = (num or "").strip()

    try:
        ap_guess, num_guess = _split_unit_house(num)
    except Exception:
        ap_guess, num_guess = ("", "")

    if num_guess:
        ap_guess_norm = _strip_unitish_prefix(ap_guess)

        if (not ap_norm) and ap_guess_norm:
            ap_norm = ap_guess_norm
            house_norm = num_guess
        elif ap_norm and ap_guess_norm and canon(ap_norm) == canon(ap_guess_norm):
            house_norm = num_guess
        else:
            house_norm = num_guess

    return (
        canon(ap_norm),
        canon(house_norm),
        canon((rec.get("Street") or "").strip()),
        canon((rec.get("Suburb") or "").strip()),
    )


# =============================================================================
# Readers
# =============================================================================

def _read_clean_keys(clean_csv: str) -> tuple[set[tuple[str, str, str, str]], Counter]:
    """
    Read keys from output_clean.csv.

    CANONICAL RULE (matches your new pipeline invariant):
      - output_clean.csv should contain ONLY Final Status Pass/OK rows.
      - Verification should therefore build the "clean key set" from Pass/OK rows only.

    Behavior:
      - If non-pass rows are found in output_clean.csv, we LOG_WARN with counts/examples.
      - We still return keys/counts for Pass/OK rows only (prevents false verify failures
        caused by leaked Duplicate/Fail rows in clean).

    Returns:
      (keys_set, counts)
    so verification can detect duplicates in the clean output too.
    """
    from GoogleSheets_Log import log_warn  # local import

    keys: set[tuple[str, str, str, str]] = set()
    counts = Counter()

    if not os.path.exists(clean_csv):
        return keys, counts

    # Prefer the shared canonical helper if available
    try:
        from GoogleSheets_Utils import final_status_is_pass_ok  # type: ignore
    except Exception:
        final_status_is_pass_ok = None  # type: ignore

    def _is_pass_ok(row: dict) -> bool:
        if callable(final_status_is_pass_ok):
            try:
                return bool(final_status_is_pass_ok(row))
            except Exception:
                return False
        # Fallback: local check
        try:
            v = row.get("Final Status") or row.get("final_status") or row.get("FinalStatus") or ""
            s = str(v).strip().lower()
            return s in ("pass", "ok")
        except Exception:
            return False

    nonpass_count = 0
    nonpass_examples: list[dict] = []

    with open(clean_csv, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            if not _is_pass_ok(row):
                nonpass_count += 1
                if len(nonpass_examples) < 50:
                    nonpass_examples.append({
                        "Final Status": (row.get("Final Status") or row.get("final_status") or row.get("FinalStatus") or ""),
                        "ApartmentNumber": (row.get("ApartmentNumber") or ""),
                        "Number": (row.get("Number") or ""),
                        "Street": (row.get("Street") or ""),
                        "Suburb": (row.get("Suburb") or ""),
                    })
                continue

            k = _addr_key(row)
            keys.add(k)
            counts[k] += 1

    if nonpass_count:
        log_warn(
            "VERIFY_NONPASS_ROWS_IN_CLEAN_OUTPUT",
            module=__name__,
            fn="_read_clean_keys",
            extra={
                "clean_csv": clean_csv,
                "nonpass_rows": int(nonpass_count),
                "examples": nonpass_examples,
                "note": "output_clean.csv should contain only Pass/OK rows; upstream routing may still be leaking.",
            },
        )

    return keys, counts


def _read_suburb_keys_and_counts(suburb_dir: Path) -> tuple[set[tuple[str, str, str, str]], Counter]:
    keys: set[tuple[str, str, str, str]] = set()
    counts = Counter()
    if not suburb_dir.exists():
        return set(), counts

    def _is_generated_failed_file(p: Path) -> bool:
        """
        Only exclude files that are the generated failure outputs:
          "<name> failed.csv"  (suffix-based)
        Avoid false positives like "Failed Bay.csv".
        """
        stem = (p.stem or "").strip().lower()
        return stem.endswith(" failed")

    for p in suburb_dir.glob("*.csv"):
        # Ignore generated "failed" outputs when matching against output_clean.csv
        if _is_generated_failed_file(p):
            continue
        try:
            with open(p, newline="", encoding="utf-8") as f:
                r = csv.DictReader(f)
                for row in r:
                    k = _addr_key(row)
                    keys.add(k)
                    counts[k] += 1
        except Exception as e:
            from GoogleSheets_Log import log_error
            log_error(
                "FAILED_READING_SUBURB_CSV",
                module=__name__,
                fn="_read_suburb_keys_and_counts",
                extra={"file": str(p), "error": str(e)},
            )
            continue

    return keys, counts


# =============================================================================
# Main verifier
# =============================================================================

def verify_split_matches_clean(
    clean_csv: str = "output_clean.csv",
    suburb_dir: str | Path = "New_Addresses_By_Suburb"
) -> bool:
    """
    Compares output_clean.csv to merged suburb CSVs.
    Also scans __NEW and __OTHER for stray rows and reports them.

    Console policy:
    - Only STAGE + ERROR print (via GoogleSheets_Log)
    - No direct print() calls here

    Returns True only when:
      - unique key sets match
      - total row counts match (i.e. multiplicity matches)
      - no duplicates are found across suburb CSVs
      - no duplicates are found in output_clean.csv
    """
    from GoogleSheets_Log import decision, stage, log_warn, log_error  # local import

    suburb_dir = Path(suburb_dir)

    stage(
        "Verify split vs clean started",
        module=__name__,
        fn="verify_split_matches_clean",
        extra={"clean_csv": clean_csv, "suburb_dir": str(suburb_dir)},
    )

    decision(
        "VERIFY_START",
        module=__name__,
        fn="verify_split_matches_clean",
        extra={
            "clean_csv": clean_csv,
            "suburb_dir": str(suburb_dir),
            "suppress_temp_warnings": _SUPPRESS_TEMP_DIR_WARNINGS,
        },
    )

    clean_keys, clean_counts = _read_clean_keys(clean_csv)
    suburb_keys, suburb_counts = _read_suburb_keys_and_counts(suburb_dir)

    ok = False  # default to not-ok; flip to True on perfect match

    if not clean_keys:
        log_warn(
            "CLEAN_EMPTY_OR_MISSING",
            module=__name__,
            fn="verify_split_matches_clean",
            extra={"clean_csv": clean_csv},
        )

    if not suburb_dir.exists():
        log_warn(
            "SUBURB_DIR_MISSING",
            module=__name__,
            fn="verify_split_matches_clean",
            extra={"suburb_dir": str(suburb_dir)},
        )

    if clean_keys and suburb_dir.exists():
        missing = clean_keys - suburb_keys
        extras = suburb_keys - clean_keys

        # duplicates in suburb dir (same key appears more than once across all suburb csvs)
        suburb_dups = {k for k, c in suburb_counts.items() if c > 1}

        # duplicates in clean output
        clean_dups = {k for k, c in clean_counts.items() if c > 1}

        clean_total_rows = int(sum(clean_counts.values()))
        suburb_total_rows = int(sum(suburb_counts.values()))

        # multiplicity mismatch: same keys but different total rows implies duplication/loss
        multiplicity_ok = (clean_total_rows == suburb_total_rows)

        decision(
            "VERIFY_COUNTS",
            module=__name__,
            fn="verify_split_matches_clean",
            extra={
                "clean_unique": len(clean_keys),
                "suburb_unique": len(suburb_keys),
                "clean_total_rows": clean_total_rows,
                "suburb_total_rows": suburb_total_rows,
                "missing": len(missing),
                "extras": len(extras),
                "suburb_dups": len(suburb_dups),
                "clean_dups": len(clean_dups),
                "multiplicity_ok": multiplicity_ok,
            },
        )

        if missing:
            log_warn(
                "VERIFY_MISSING_IN_SUBURB_DIR",
                module=__name__,
                fn="verify_split_matches_clean",
                extra={"count": len(missing), "examples": list(missing)[:50]},
            )

        if extras:
            log_warn(
                "VERIFY_EXTRA_IN_SUBURB_DIR",
                module=__name__,
                fn="verify_split_matches_clean",
                extra={"count": len(extras), "examples": list(extras)[:50]},
            )

        if suburb_dups:
            examples = []
            for k in list(suburb_dups)[:50]:
                examples.append({"key": k, "count": int(suburb_counts[k])})
            log_warn(
                "VERIFY_DUPLICATES_IN_SUBURB_DIR",
                module=__name__,
                fn="verify_split_matches_clean",
                extra={"count": len(suburb_dups), "examples": examples},
            )

        if clean_dups:
            examples = []
            for k in list(clean_dups)[:50]:
                examples.append({"key": k, "count": int(clean_counts[k])})
            log_warn(
                "VERIFY_DUPLICATES_IN_CLEAN_OUTPUT",
                module=__name__,
                fn="verify_split_matches_clean",
                extra={"count": len(clean_dups), "examples": examples},
            )

        # Perfect match conditions
        if (
            not missing
            and not extras
            and not suburb_dups
            and not clean_dups
            and len(clean_keys) == len(suburb_keys)
            and multiplicity_ok
        ):
            ok = True
            stage(
                "Verify OK: counts and sets match",
                module=__name__,
                fn="verify_split_matches_clean",
                extra={
                    "clean_unique": len(clean_keys),
                    "suburb_unique": len(suburb_keys),
                    "total_rows": clean_total_rows,
                },
            )
        else:
            log_error(
                "VERIFY_FAILED",
                module=__name__,
                fn="verify_split_matches_clean",
                extra={
                    "missing": len(missing),
                    "extras": len(extras),
                    "suburb_dups": len(suburb_dups),
                    "clean_dups": len(clean_dups),
                    "clean_unique": len(clean_keys),
                    "suburb_unique": len(suburb_keys),
                    "clean_total_rows": clean_total_rows,
                    "suburb_total_rows": suburb_total_rows,
                    "multiplicity_ok": multiplicity_ok,
                },
            )

        # Secondary: check temp folders for leftover CSVs (respects suppression flag)
        if not _SUPPRESS_TEMP_DIR_WARNINGS:
            for d in (_SUBURB_DIR_NEW, _SUBURB_DIR_OTHER):
                if d.exists():
                    _, counts = _read_suburb_keys_and_counts(d)
                    total = int(sum(counts.values()))
                    if total > 0:
                        log_warn(
                            "TEMP_DIR_HAS_ROWS",
                            module=__name__,
                            fn="verify_split_matches_clean",
                            extra={
                                "dir": str(d),
                                "rows": total,
                                "files": len(list(d.glob("*.csv"))),
                            },
                        )

    decision(
        "VERIFY_DONE",
        module=__name__,
        fn="verify_split_matches_clean",
        extra={"ok": ok},
    )

    stage(
        "Verify finished",
        module=__name__,
        fn="verify_split_matches_clean",
        extra={"ok": ok},
    )

    return ok



# --- Logging: wrap functions defined in THIS module (CALL/RETURN/EXCEPTION) ---
from GoogleSheets_Log import autowrap_module  # noqa: E402

try:
    autowrap_module(__name__, include_private=True, only_defined_here=True)
except TypeError:
    autowrap_module(__name__, include_private=True)
