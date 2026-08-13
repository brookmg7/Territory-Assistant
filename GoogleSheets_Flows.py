#!/usr/bin/env python3
"""
GoogleSheets_Flows.py

Purpose
-------
High-level runnable flows and split/merge helpers extracted from Clean_GoogleSheets.py.

This module contains:
- Routed and non-routed "clean + split" workflows
- Split/merge + temp-dir helpers
- Final status summary

Design / Imports
----------------
- Imports: GoogleSheets_Utils, GoogleSheets_Master, GoogleSheets_Verify, GoogleSheets_CoreLite.
- Does NOT import GoogleSheets_Menu (Menu imports Flows only).

Compatibility
-------------
All flow function bodies below are copied verbatim from Clean_GoogleSheets.py
(except for this header and the import/bootstrap section).

"""

from __future__ import annotations

import os
import re
import csv
import shutil
from datetime import datetime
from pathlib import Path
from collections import Counter as _Counter

from GoogleSheets_Utils import enforce_outputs_routing

# --- Logging: record module import as early as possible ---
from GoogleSheets_Log import module_loaded  # noqa: E402
module_loaded(__name__)


# Progress bars (tqdm) — ON by default (disable per-call with tqdm(..., disable=True))

# We keep tqdm installed/usable, but default to disable=True so it won't print bars.
try:
    from tqdm import tqdm as _tqdm  # type: ignore


    def tqdm(iterable=None, **kwargs):
        """
        Progress bars: ON by default.

        Why:
        - Your logs show stages, but bars were forcibly disabled here.
        - Works better in Windows console + PyInstaller (dynamic_ncols).
        - leave=True so you can actually see the final bar state.

        You can still silence a specific bar by calling: tqdm(..., disable=True)
        """
        kwargs.setdefault("disable", False)  # ✅ show bars by default
        kwargs.setdefault("leave", True)  # ✅ keep final bar line visible
        kwargs.setdefault("dynamic_ncols", True)  # ✅ adapt to console width
        kwargs.setdefault("miniters", 1)
        kwargs.setdefault("unit", kwargs.get("unit", "row"))

        return _tqdm(iterable, **kwargs)


except Exception:  # pragma: no cover
    def tqdm(iterable=None, **kwargs):
        return iterable if iterable is not None else range(0)


# CoreLite (drop-in replacement for Clean_NewWorldScheduler "core")
import GoogleSheets_CoreLite as core

# Utils / Master / Verify dependencies
from GoogleSheets_Utils import (
    _canon_text,
    _canon_text_cached,
    _tokens_core,
    _has_digits,
    _strip_trailing_postcode,
    _merge_notes,
    normalize_number,
    _combine_unit_and_number,
    _coords_in_auckland,
    _choose_best_coordinate,
    _accept_geocode_update,
    _append_other_notes,
    _canon_suburb_sheets,
    _postal_for_suburb_sheets,
    gs_strip_leading_duplicate_number_from_street,
    NEW_STREET_DETECT_RX,
    NEW_STREET_MSG,
    HOUSE_FLIP_A,
    HOUSE_FLIP_B,
    SEP_SQUASH_RX_1,
    SEP_SQUASH_RX_2,
    SEP_SQUASH_RX_3,
    LANG_LETTERS_ONLY_RX,
    backfill_suburb_postcode_for_row,

)

from GoogleSheets_Master import (
    _load_master_index,
    _repair_corrupted_street,
    run_master_db_duplicate_audit,          # ✅ ADD THIS
    run_final_master_duplicate_filter,
    run_verify_fail_against_master,
)


from GoogleSheets_Verify import (
    _addr_key,
    verify_split_matches_clean as _verify_split_matches_clean,
)


# --- Small regex helpers used in hot paths (copied from legacy) ---
SLASH_DIGITS_RX = re.compile(r'/\s*(\d+)')

# --- Split output folder written by core.split_cleaned_by_polygon_and_include_failed(...) ---
# Temp NEW/OTHER dirs are retired (Menu no longer uses the temp-dir pipeline).
_SUBURB_BASE = Path("New_Addresses_By_Suburb")


def verify_split_matches_clean(
    clean_csv: str = "output_clean.csv",
    suburb_dir: str | Path = "New_Addresses_By_Suburb",
) -> bool:
    """
    Flows wrapper used by Menu Option 2.

    NOTE:
    - The legacy NEW/OTHER temp-dir pipeline is retired.
    - We no longer sync Verify's temp-dir globals (_SUBURB_DIR_NEW/_SUBURB_DIR_OTHER).
    - Verification is performed against the final suburb_dir only.
    """
    from GoogleSheets_Log import decision, log_exception

    try:
        ok = bool(_verify_split_matches_clean(clean_csv=clean_csv, suburb_dir=suburb_dir))
        decision(
            "VERIFY_RESULT",
            module=__name__,
            fn="verify_split_matches_clean",
            extra={"ok": ok, "clean_csv": str(clean_csv), "suburb_dir": str(suburb_dir)},
        )
        return ok
    except Exception:
        log_exception(
            "VERIFY_EXCEPTION",
            module=__name__,
            fn="verify_split_matches_clean",
            extra={"clean_csv": str(clean_csv), "suburb_dir": str(suburb_dir)},
        )
        return False



# =============================================================================
# Legacy helper defs required by flows (copied verbatim)
# =============================================================================

def _numbers_match(old_unit: str, old_number: str, new_number: str) -> bool:
    """Does new Number equal the normalized combination of old Unit+Number?"""
    expected = _combine_unit_and_number(old_unit, old_number)
    lhs = normalize_number(expected)
    rhs = normalize_number(new_number or "")
    return lhs == rhs

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
        from GoogleSheets_Utils import audit_log_only_keys  # preferred
        deny |= set(audit_log_only_keys())
    except Exception:
        try:
            from GoogleSheets_Utils import _AUDIT_LOG_ONLY_KEYS  # fallback
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

    # Reader with encoding fallbacks (reuse Utils helper if present)
    def _open_in(p: str):
        try:
            from GoogleSheets_Utils import _open_csv_text_best_effort
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
                    from GoogleSheets_Utils import strip_audit_columns_from_row
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

    clear_set = {"mandarin", "chinese", "chinesemandarin", "mandarinchinese"}

    if lang_norm in clear_set:
        rec["Language"] = ""


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
        # Non-fatal; continue
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass


# =============================================================================
# Flow / routing helpers (copied verbatim)
# =============================================================================

def _notes_has_new_street_ci(notes: str) -> bool:
    notes = (notes or "")
    return bool(NEW_STREET_DETECT_RX.search(notes))


def _notes_has_new_street(notes: str) -> bool:
    """
    Kept for compatibility: the legacy code had both a CI and a "simple" checker.
    This version preserves prior behavior by delegating to the CI regex.
    """
    return _notes_has_new_street_ci(notes)


def _stemmed_outputs_for(base_out_clean: str, base_out_fail: str, stem: str) -> tuple[str, str]:
    """
    Produce output filenames like:
      output_clean.csv + stem "other" => output_clean.other.csv
    """
    def stemmed(path: str) -> str:
        p = Path(path)
        return str(p.with_name(f"{p.stem}.{stem}{p.suffix}"))

    return stemmed(base_out_clean), stemmed(base_out_fail)


def _split_input_by_new_street(input_file: str) -> tuple[str, str]:
    """
    Split input_file into two CSVs:
      - *.other.csv  (everything NOT New Street)
      - *.new.csv    (rows whose Notes contains "New Street(s)")
    Returns (other_path, new_path).
    """
    src = Path(input_file)
    other_path = str(src.with_name(f"{src.stem}.other{src.suffix}"))
    new_path = str(src.with_name(f"{src.stem}.new{src.suffix}"))

    add_row_audit_fields = _maybe_import_add_row_audit_fields()

    with open(input_file, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        fieldnames = _extend_fieldnames_with_audit(list(r.fieldnames or []), add_row_audit_fields)
        other_rows = []
        new_rows = []

        for row in r:
            notes = (row.get("Notes") or "")
            if _notes_has_new_street_ci(notes):
                new_rows.append(row)
            else:
                other_rows.append(row)

    def write(path: str, rows: list[dict]) -> None:
        with open(path, "w", newline="", encoding="utf-8", buffering=1024 * 1024) as fo:
            w = csv.DictWriter(fo, fieldnames=fieldnames)
            w.writeheader()
            for row in rows:
                w.writerow(_sanitize_row_for_write(row, fieldnames, add_row_audit_fields))


    write(other_path, other_rows)
    write(new_path, new_rows)

    return other_path, new_path


def _invoke_core_option7_new_streets(clean_csv: str, fail_csv: str) -> Path:
    """
    Delegate "Option 7 — New Streets" behavior to core if exposed, else fallback
    to the polygon split.

    Returns the folder path that contains suburb splits (typically New_Addresses_By_Suburb).
    """
    # Try multiple likely names first (legacy-safe)
    candidate_names = [
        "run_option7_new_streets",
        "option7_new_streets",
        "run_new_streets",
        "new_streets",
        # older/other variants seen in legacy cores:
        "run_clean_split_new_streets_full_geocode",
        "clean_split_new_streets_full_geocode",
        "option7_clean_split_new_streets",
        "run_option_7_new_streets",
        "run_new_streets_full_geocode",
    ]

    for fn_name in candidate_names:
        handler = getattr(core, fn_name, None)
        if callable(handler):
            try:
                # some variants accept different params; try flexible calls
                try:
                    handler(clean_csv, fail_csv)
                    return _SUBURB_BASE
                except TypeError:
                    handler(clean_csv, fail_csv, kml_dir="KML Boundaries")
                    return _SUBURB_BASE
            except Exception:
                # Non-fatal; we’ll fall back to splitter below
                pass

    # Fallback: polygon split into suburb dirs
    split = getattr(core, "split_cleaned_by_polygon_and_include_failed", None)
    if callable(split):
        # Prefer a "new streets only" feature flag when supported by the core
        try:
            split(clean_csv, fail_csv, kml_dir="KML Boundaries", new_streets_only=True)
            return _SUBURB_BASE
        except TypeError:
            pass
        except Exception:
            pass

        # Normal split fallback (no flag)
        try:
            split(clean_csv, fail_csv, kml_dir="KML Boundaries")
            return _SUBURB_BASE
        except TypeError:
            try:
                split(clean_csv, fail_csv)
                return _SUBURB_BASE
            except Exception:
                pass
        except Exception:
            pass

    # If even the splitter is missing/fails, still return the conventional base
    return _SUBURB_BASE



def _run_split_to_dir(out_clean: str, out_fail: str, *, label: str, kml_dir: str = "KML Boundaries") -> Path:
    """
    RETIRED (compat stub).

    Old behavior:
      - core split -> move New_Addresses_By_Suburb into NEW/OTHER temp dirs

    New behavior:
      - Menu no longer uses the temp-dir pipeline.
      - We run the split directly into the final folder and return that folder.
    """
    from GoogleSheets_Log import decision

    decision(
        "RETIRED_RUN_SPLIT_TO_DIR",
        module=__name__,
        fn="_run_split_to_dir",
        extra={"label": str(label), "out_clean": str(out_clean), "out_fail": str(out_fail)},
    )

    # Split into the final folder (fresh run behavior controlled inside _split_into_final_folder)
    try:
        _split_into_final_folder(out_clean, out_fail, kml_dir=kml_dir)
    except TypeError:
        _split_into_final_folder(out_clean, out_fail)

    return _SUBURB_BASE




def _merge_suburb_dirs(sources: list[Path], dest: Path) -> None:
    """
    RETIRED (compat stub).

    Old behavior merged multiple temp suburb folders into final.
    Menu now writes directly to final folder, so this is no longer needed.
    """
    from GoogleSheets_Log import decision

    decision(
        "RETIRED_MERGE_SUBURB_DIRS",
        module=__name__,
        fn="_merge_suburb_dirs",
        extra={"sources": [str(s) for s in (sources or [])], "dest": str(dest)},
    )

    # No-op by design.
    try:
        dest.mkdir(exist_ok=True)
    except Exception:
        pass




def _warn_if_temp_dirs_have_files() -> None:
    """
    RETIRED (compat stub).

    Temp NEW/OTHER dirs are no longer used.
    """
    from GoogleSheets_Log import decision
    decision("RETIRED_WARN_TEMP_DIRS", module=__name__, fn="_warn_if_temp_dirs_have_files")



def _delete_if_exists(path: str | Path) -> None:
    try:
        p = Path(path)
        if p.exists() and p.is_file():
            p.unlink()
    except Exception:
        pass


def cleanup_routed_intermediate_csvs(
    *,
    base_out_clean: str = "output_clean.csv",
    base_out_fail: str = "output_fail.csv",
    input_file: str | None = None,
    delete_full: bool = True,
) -> None:
    """
    Legacy behavior: routed runs may create intermediate artifacts:
      - output_clean.other.csv / output_fail.other.csv
      - output_clean.new.csv   / output_fail.new.csv
      - output_clean.full.csv  / output_fail.full.csv (optional)
      - input_file.other.csv / input_file.new.csv     (optional)
    This removes them so only the final base outputs remain.
    """
    stems = ["other", "new"]
    if delete_full:
        stems.append("full")

    # Delete output_*.<stem>.csv
    for stem in stems:
        c, f = _stemmed_outputs_for(base_out_clean, base_out_fail, stem)
        _delete_if_exists(c)
        _delete_if_exists(f)

    # Delete split input artifacts if provided
    if input_file:
        src = Path(str(input_file))
        _delete_if_exists(src.with_name(f"{src.stem}.other{src.suffix}"))
        _delete_if_exists(src.with_name(f"{src.stem}.new{src.suffix}"))


def _delete_temp_suburb_dirs() -> None:
    """
    RETIRED (compat stub).

    Temp NEW/OTHER dirs are no longer used.
    """
    from GoogleSheets_Log import decision
    decision("RETIRED_DELETE_TEMP_SUBURB_DIRS", module=__name__, fn="_delete_temp_suburb_dirs")



def _cleanup_temp_dirs_after_verify(ok: bool) -> None:
    """
    RETIRED (compat stub).

    Old policy deleted NEW/OTHER temp dirs depending on verification result.
    Temp dirs are no longer part of the Menu flow.
    """
    from GoogleSheets_Log import decision
    decision(
        "RETIRED_TEMP_DIR_CLEANUP_AFTER_VERIFY",
        module=__name__,
        fn="_cleanup_temp_dirs_after_verify",
        extra={"ok": bool(ok)},
    )



def _maybe_autowrap_flows_module() -> None:
    """
    Opt-in autowrap for Flows.

    Parity default: OFF (wrappers add overhead + can subtly affect timing).
    Enable by setting:
        GS_AUTOWRAP_FLOWS=1
    """
    from GoogleSheets_Log import autowrap_module, decision

    enabled = os.environ.get("GS_AUTOWRAP_FLOWS", "").strip().lower() in ("1", "true", "yes", "y")
    decision("AUTOWRAP_FLOWS_CHECK", module=__name__, fn="_maybe_autowrap_flows_module", extra={"enabled": enabled})

    if not enabled:
        return

    try:
        autowrap_module(__name__, include_private=False, only_defined_here=True)
        decision("AUTOWRAP_FLOWS_ENABLED", module=__name__, fn="_maybe_autowrap_flows_module")
    except TypeError:
        autowrap_module(__name__, include_private=False)
        decision("AUTOWRAP_FLOWS_ENABLED_COMPAT", module=__name__, fn="_maybe_autowrap_flows_module")
    except Exception:
        # Never break import due to wrapping
        from GoogleSheets_Log import log_exception
        log_exception("AUTOWRAP_FLOWS_FAILED", module=__name__, fn="_maybe_autowrap_flows_module")


def _ensure_temp_dirs_cleared_for_routed() -> None:
    """
    RETIRED (compat stub).

    Menu no longer uses NEW/OTHER temp dirs, but some older callers may still
    invoke this. Keep as safe no-op.
    """
    from GoogleSheets_Log import decision
    decision("RETIRED_ENSURE_TEMP_DIRS_CLEARED", module=__name__, fn="_ensure_temp_dirs_cleared_for_routed")


def _final_status_is_pass_ok(rec: dict) -> bool:
    v = (rec.get("Final Status") or "").strip().lower()
    return v in ("pass", "ok")

def _final_status_is_set_and_not_pass_ok(rec: dict) -> bool:
    v = (rec.get("Final Status") or "").strip()
    return bool(v) and not _final_status_is_pass_ok(rec)

def _route_by_final_status(*, rec: dict, clean_writer, fail_writer, make_safe_row_fn) -> None:
    """
    ROUTING POLICY (CANONICAL):
      - Pass/OK => output_clean
      - Anything else (Fail/Duplicate/Bad Geocode/etc) => output_fail

    This delegates to GoogleSheets_Utils.route_row_writers_by_final_status()
    so Flows cannot drift from the global rule.
    """
    try:
        from GoogleSheets_Utils import route_row_writers_by_final_status
        route_row_writers_by_final_status(
            rec,
            clean_writer=clean_writer,
            fail_writer=fail_writer,
            make_safe_row_fn=make_safe_row_fn,
        )
        return
    except Exception:
        pass

    # Fallback (must match canonical policy)
    try:
        v = (rec.get("Final Status") or rec.get("final_status") or rec.get("FinalStatus") or "")
        v = str(v).strip().lower()
        is_pass_ok = v in ("pass", "ok")
    except Exception:
        is_pass_ok = False

    safe = make_safe_row_fn(rec)
    if is_pass_ok:
        clean_writer.writerow(safe)
    else:
        fail_writer.writerow(safe)



def _dedupe_suburb_folder(folder: Path) -> tuple[int, int]:
    """
    Legacy-compatible:
    Deduplicate each non-failed CSV in `folder` by address key.

    Returns:
      (files_touched, rows_removed_total)
    """
    files_touched = 0
    rows_removed_total = 0

    if not folder.exists():
        return (0, 0)

    for p in folder.glob("*.csv"):
        stem = (p.stem or "").strip().lower()
        if stem.endswith(" failed"):
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

            if removed_this_file > 0 and kept_rows:
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

def _normalize_for_geocode(rec: dict) -> None:
    """
    Ensure Number is in unit-first canonical form for geocoding (UnitA/12).
    This prevents LINZ/unit lookups from missing due to house-first forms.
    Does NOT change final write-time flip behavior (legacy).
    """
    num = (rec.get("Number") or "").strip()
    if not num:
        return

    m = HOUSE_FLIP_B.match(num)
    if m:
        rec["Number"] = f"Unit{m.group(2).upper()}/{m.group(1)}"
        return


def _apply_new_street_overrides(rec: dict, notes_val: str = "", notes_pub_val: str = "") -> bool:
    """
    Legacy behavior:
    If Notes or NotesFromPublisher contains "New Street" (case-insensitive), then:
      - Notes  -> NEW_STREET_MSG
      - Status -> Custom3
      - Number -> ""  (clear)
    Returns True if applied.
    """
    if _notes_has_new_street_ci(notes_val) or _notes_has_new_street_ci(notes_pub_val):
        rec["Notes"] = NEW_STREET_MSG
        rec["Status"] = "Custom3"
        rec["Number"] = ""
        return True
    return False



def _summarize_final_status(clean_csv: str = "output_clean.csv",
                            fail_csv: str = "output_fail.csv",
                            *,
                            print_breakdown: bool = True) -> dict:
    """
    Legacy-compatible:
    Print + return a compact summary of Final Status results based on the merged outputs.
      - 'Pass' is counted from output_clean.csv
      - All other statuses are counted from output_fail.csv
    Returns a dict: {"total": int, "pass": int, "failed": int, "by_status": dict[str,int]}
    """
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
        print(f"❌ Total Failed: {total_fail}")

        if total_fail:
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

    by_status = dict(counts)
    return {
        "total": total_all,
        "pass": total_clean,
        "failed": total_fail,
        "by_status": by_status,
    }



def _split_into_final_folder(clean_csv: str, fail_csv: str, *, kml_dir: str = "KML Boundaries") -> None:
    """
    Split output_clean.csv + output_fail.csv into New_Addresses_By_Suburb,
    including failed rows in "* failed.csv" files.

    IMPORTANT BEHAVIOR FIX (verification correctness):
    - By default we DO NOT preserve/append any previous contents in New_Addresses_By_Suburb.
      Old runs lingering in the folder cause verify_split_matches_clean() to report
      extras/duplicates even when routing is correct.
    - If you *want* the legacy cumulative behavior, set:
        GS_SPLIT_PRESERVE_EXISTING=1

    Legacy-safe:
      - Tolerates cores that don't accept kml_dir kwarg.
    """
    dest = _SUBURB_BASE

    preserve_existing = os.environ.get("GS_SPLIT_PRESERVE_EXISTING", "").strip().lower() in ("1", "true", "yes", "y")

    # Fresh by default: clear previous run’s suburb files so verify compares apples-to-apples
    if dest.exists() and not preserve_existing:
        _clear_dir_contents(dest)

    def _snapshot_folder(folder: Path) -> dict[str, tuple[list[str], list[list[str]]]]:
        """
        Returns dict: {filename -> (header:list[str], rows:list[list[str]])}
        Only used when preserve_existing == True.
        """
        snap: dict[str, tuple[list[str], list[list[str]]]] = {}
        if not folder.exists():
            return snap

        for p in folder.glob("*.csv"):
            try:
                with open(p, "r", newline="", encoding="utf-8") as f:
                    r = csv.reader(f)
                    try:
                        header = next(r)
                    except StopIteration:
                        header, rows = [], []
                    else:
                        rows = [row for row in r]
                snap[p.name] = (header, rows)
            except Exception:
                continue
        return snap

    snapshot = _snapshot_folder(dest) if preserve_existing else {}

    # Run the splitter (tolerate cores that don't accept kml_dir kwarg)
    try:
        core.split_cleaned_by_polygon_and_include_failed(clean_csv, fail_csv, kml_dir=kml_dir)
    except TypeError:
        core.split_cleaned_by_polygon_and_include_failed(clean_csv, fail_csv)

    # Append snapshot back ONLY if explicitly preserving existing
    if preserve_existing and snapshot:
        for fname, (header, rows) in snapshot.items():
            if not header and not rows:
                continue

            target = dest / fname

            if target.exists():
                try:
                    with open(target, "a", newline="", encoding="utf-8") as fout:
                        w = csv.writer(fout)
                        for row in rows:
                            w.writerow(row)
                except Exception:
                    continue
            else:
                try:
                    with open(target, "w", newline="", encoding="utf-8") as fout:
                        w = csv.writer(fout)
                        if header:
                            w.writerow(header)
                        for row in rows:
                            w.writerow(row)
                except Exception:
                    continue





def run_sheets_clean_and_split_after_purge(
    input_file: str,
    do_split: bool = False,
    out_clean: str = "output_clean.csv",
    out_fail: str = "output_fail.csv",
    exclude_new: bool = False
) -> None:
    """
    Option 1 + routed-other half:
    Clean Google Sheets (light) after purge logic.

    ROUTING POLICY (centralized):
      - Final Status == "Fail" -> output_fail.csv
      - Otherwise -> output_clean.csv

    IMPORTANT FIX:
      - After writing outputs, run the canonical "final master filter" sweep to enforce:
          * Final Status == Fail => fail
          * Status == At Home AND (Number missing OR Street missing) => fail
          * Custom3 missing Number allowed in clean (Street required)
      - Then enforce routing again.
    """
    from GoogleSheets_Log import decision, stage, log_exception  # local import
    from GoogleSheets_Utils import enforce_outputs_routing  # local

    input_file = str(input_file)

    def _strict_is_fail(rec: dict) -> bool:
        return (rec.get("Final Status") or "").strip().lower() == "fail"

    def _strict_normalize_final_status(rec: dict) -> None:
        raw = (rec.get("Final Status") or "")
        s = raw.strip()
        if not s:
            return
        low = s.lower()
        if low == "fail":
            rec["Final Status"] = "Fail"
        elif low == "pass":
            rec["Final Status"] = "Pass"

    stage(
        "Flow started: Clean (light)",
        module=__name__,
        fn="run_sheets_clean_and_split_after_purge",
        extra={"input_file": input_file, "do_split": do_split, "exclude_new": exclude_new},
    )

    decision(
        "FLOW_START",
        module=__name__,
        fn="run_sheets_clean_and_split_after_purge",
        extra={"input_file": input_file, "do_split": do_split, "out_clean": out_clean, "out_fail": out_fail, "exclude_new": exclude_new},
    )

    try:
        # --- Purge / pre-clean master index ---
        try:
            _load_master_index.cache_clear()
        except Exception:
            pass

        stage("Loading master index", module=__name__, fn="run_sheets_clean_and_split_after_purge")
        _load_master_index()

        # --- Read input CSV ---
        stage("Loading input CSV", module=__name__, fn="run_sheets_clean_and_split_after_purge")
        with open(input_file, newline="", encoding="utf-8") as f:
            r = csv.DictReader(f)
            fieldnames = r.fieldnames or []
            rows = list(r)

        add_row_audit_fields = _maybe_import_add_row_audit_fields()
        fieldnames = _extend_fieldnames_with_audit(list(fieldnames), add_row_audit_fields)

        for must in ("Final Status", "Status", "Latitude", "Longitude", "Other Notes", "Type"):
            if must not in fieldnames:
                fieldnames.append(must)

        decision(
            "INPUT_LOADED",
            module=__name__,
            fn="run_sheets_clean_and_split_after_purge",
            extra={"rows": len(rows), "fields": len(fieldnames)},
        )

        # ---------------------------------------------------------------------
        # Coords restore index (keyed by normalized address)
        # ---------------------------------------------------------------------
        def _coord_key(row: dict) -> str:
            num = normalize_number((row.get("Number") or "").strip())
            street = _canon_text(row.get("Street") or "")
            suburb = _canon_suburb_sheets(row.get("Suburb") or "")
            return f"{num}|{street}|{suburb}"

        input_coords: dict[str, tuple[str, str]] = {}
        try:
            for raw in rows:
                lat0 = (raw.get("Latitude") or "").strip()
                lon0 = (raw.get("Longitude") or "").strip()
                if _has_digits(lat0) and _has_digits(lon0):
                    k = _coord_key(raw)
                    if k and k not in input_coords:
                        input_coords[k] = (lat0, lon0)
        except Exception:
            input_coords = {}

        def _restore_coords_if_missing(rec: dict) -> bool:
            latc = (rec.get("Latitude") or "").strip()
            lonc = (rec.get("Longitude") or "").strip()
            if _has_digits(latc) and _has_digits(lonc):
                return False
            try:
                k = _coord_key(rec)
                if not k:
                    return False
                hit = input_coords.get(k)
                if not hit:
                    return False
                rec["Latitude"], rec["Longitude"] = hit[0], hit[1]
                try:
                    _append_other_notes(rec, "Coords restored from input_googlesheets.csv")
                except Exception:
                    pass
                return True
            except Exception:
                return False

        def _flip_before_write(rec: dict) -> None:
            ap = (rec.get("ApartmentNumber") or "").strip()
            num = (rec.get("Number") or "").strip()
            if ap and num and "/" not in num:
                rec["Number"] = _combine_unit_and_number(ap, num)

            num = (rec.get("Number") or "").strip()
            if not num:
                return

            m = HOUSE_FLIP_B.match(num)
            if m:
                rec["Number"] = f"Unit{m.group(2).upper()}/{m.group(1)}"

        stage(
            "Writing cleaned outputs",
            module=__name__,
            fn="run_sheets_clean_and_split_after_purge",
            extra={"out_clean": out_clean, "out_fail": out_fail},
        )

        with open(out_clean, "w", newline="", encoding="utf-8", buffering=1024 * 1024) as fout_c, \
             open(out_fail,  "w", newline="", encoding="utf-8", buffering=1024 * 1024) as fout_f:

            wc = csv.DictWriter(fout_c, fieldnames=fieldnames); wc.writeheader()
            wf = csv.DictWriter(fout_f, fieldnames=fieldnames); wf.writeheader()

            for row in tqdm(rows, desc="Cleaning", unit="row"):
                if exclude_new and _notes_has_new_street_ci(row.get("Notes", "")):
                    continue

                _strict_normalize_final_status(row)

                _clean_notes_and_language(row)
                _default_type_house(row)

                row["Suburb"] = _canon_suburb_sheets(row.get("Suburb", ""))

                try:
                    backfill_suburb_postcode_for_row(
                        row,
                        kml_dir="KML Boundaries",
                        prefer_coords=False,
                        log_changes=False,
                    )
                except Exception:
                    pass

                pc = _postal_for_suburb_sheets(row.get("Suburb", ""))
                if "PostalCode" in fieldnames:
                    row["PostalCode"] = pc
                if "Postcode" in fieldnames:
                    row["Postcode"] = pc

                row["Street"] = _repair_corrupted_street(row.get("Street", ""))
                row["Street"] = _strip_trailing_postcode(row.get("Street", ""))
                row["Street"] = gs_strip_leading_duplicate_number_from_street(
                    row.get("Number", ""), row.get("Street", "")
                )

                _flip_before_write(row)

                lat, lon, src = _choose_best_coordinate(row)
                if lat is not None and lon is not None and src:
                    _accept_geocode_update(row, lat, lon, src)

                _restore_coords_if_missing(row)

                try:
                    backfill_suburb_postcode_for_row(
                        row,
                        kml_dir="KML Boundaries",
                        prefer_coords=True,
                        log_changes=False,
                    )
                except Exception:
                    pass

                reasons = _should_fail_row(
                    row,
                    row.get("Unit", ""),
                    row.get("Number", ""),
                    row.get("Street", ""),
                )

                if not _final_status_is_set_and_not_pass_ok(row):
                    if _strict_is_fail(row) or reasons:
                        row["Final Status"] = "Fail"
                    else:
                        row["Final Status"] = "Pass"

                if reasons and (row.get("Final Status") or "").strip().lower() == "fail":
                    try:
                        _append_other_notes(row, "Fail: " + ", ".join(reasons))
                    except Exception:
                        pass

                _flip_before_write(row)

                safe_fn = lambda r: _sanitize_row_for_write(r, fieldnames, add_row_audit_fields)
                _route_by_final_status(rec=row, clean_writer=wc, fail_writer=wf, make_safe_row_fn=safe_fn)

        # --- FINAL SWEEP (the missing piece for Option 1) ---
        try:
            # 1) First enforce strict pass/ok routing by Final Status
            enforce_outputs_routing(out_clean, out_fail)
        except Exception:
            pass

        try:
            # 2) Then apply the canonical Master rules (At Home + missing fields, Final Status Fail, etc)
            run_final_master_duplicate_filter(out_clean, out_fail)
        except Exception:
            pass

        try:
            # 3) And enforce again after moves
            enforce_outputs_routing(out_clean, out_fail)
        except Exception:
            pass

        if do_split:
            decision(
                "SPLIT_START",
                module=__name__,
                fn="run_sheets_clean_and_split_after_purge",
                extra={"kml_dir": "KML Boundaries"},
            )
            print("✅ Stage 3: Splitting By Territory Boundaries")
            _split_into_final_folder(out_clean, out_fail)

        _summarize_final_status(out_clean, out_fail)

        decision(
            "FLOW_DONE",
            module=__name__,
            fn="run_sheets_clean_and_split_after_purge",
            extra={"out_clean": out_clean, "out_fail": out_fail},
        )

        stage(
            "Flow finished: Clean (light)",
            module=__name__,
            fn="run_sheets_clean_and_split_after_purge",
            extra={"out_clean": out_clean, "out_fail": out_fail},
        )

    except Exception:
        log_exception(
            "FLOW_EXCEPTION",
            module=__name__,
            fn="run_sheets_clean_and_split_after_purge",
            extra={"input_file": input_file, "out_clean": out_clean, "out_fail": out_fail, "do_split": do_split},
        )
        raise





def run_sheets_clean_and_split_after_purge_verify(
    input_file: str,
    do_split: bool = False,
    out_clean: str = "output_clean.csv",
    out_fail: str = "output_fail.csv",
    exclude_new: bool = False,
) -> None:
    """
    Option 2 + routed-other verify half.

    ROUTING POLICY (CANONICAL):
      - Pass/OK -> output_clean.csv
      - Anything else (Fail/Duplicate/Bad Geocode/etc) -> output_fail.csv

    IMPORTANT:
      - We use the centralized routing helper (_route_by_final_status),
        which delegates to GoogleSheets_Utils.route_row_writers_by_final_status()
        when available, so this module cannot drift.

      - After writing, we run a canonical sequence:
          1) enforce_outputs_routing
          2) run_final_master_duplicate_filter
          3) enforce_outputs_routing
          4) run_verify_fail_against_master
          5) enforce_outputs_routing
    """
    from GoogleSheets_Log import stage, log_exception, decision
    from GoogleSheets_Utils import audit_blank_auckland_rows, _open_csv_text_best_effort
    from GoogleSheets_Utils import enforce_outputs_routing  # centralized

    input_file = str(input_file)

    def _strict_is_fail(rec: dict) -> bool:
        return (rec.get("Final Status") or "").strip().lower() == "fail"

    def _strict_normalize_final_status(rec: dict) -> None:
        raw = (rec.get("Final Status") or "")
        s = raw.strip()
        if not s:
            return
        low = s.lower()
        if low == "fail":
            rec["Final Status"] = "Fail"
        elif low == "pass":
            rec["Final Status"] = "Pass"
        elif low == "ok":
            rec["Final Status"] = "OK"

    stage(
        "Flow started: Clean (full verify)",
        module=__name__,
        fn="run_sheets_clean_and_split_after_purge_verify",
        extra={"input_file": input_file, "do_split": do_split, "exclude_new": exclude_new},
    )

    try:
        try:
            _load_master_index.cache_clear()
        except Exception:
            pass

        stage("Loading master index", module=__name__, fn="run_sheets_clean_and_split_after_purge_verify")
        _load_master_index()

        fieldnames = [
            "Old Number", "Unit",
            "Old Street",
            "ApartmentNumber", "Number", "Street",
            "Suburb", "PostalCode", "State",
            "Status", "Final Status",
            "Latitude", "Longitude",
            "Type", "Language", "Notes", "Other Notes",
        ]

        add_row_audit_fields = _maybe_import_add_row_audit_fields()
        fieldnames = _extend_fieldnames_with_audit(list(fieldnames), add_row_audit_fields)

        def _flip_before_write(rec: dict) -> None:
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
                return

        stage("Loading input CSV", module=__name__, fn="run_sheets_clean_and_split_after_purge_verify")
        f = None
        try:
            f = _open_csv_text_best_effort(input_file)
            r = csv.DictReader(f)
            rows = list(r)
        finally:
            try:
                if f is not None:
                    f.close()
            except Exception:
                pass

        try:
            audit_blank_auckland_rows(
                input_file,
                max_print=3,
                label="Option2 input audit",
                require_suburb_auckland_or_blank=True,
            )
        except Exception:
            pass

        def _canon_key(num: str, street: str, suburb: str) -> str:
            n = normalize_number((num or "").strip())
            s = _canon_text(street or "")
            sub = _canon_suburb_sheets(suburb or "")
            return f"{n}|{s}|{sub}"

        def _split_street_suburb(street_val: str):
            s = (street_val or "").strip()
            if "," in s:
                left, right = s.split(",", 1)
                return left.strip(), right.strip()
            return s, ""

        input_coords: dict[str, tuple[str, str]] = {}
        try:
            for raw in rows:
                lat0 = (raw.get("Latitude") or "").strip()
                lon0 = (raw.get("Longitude") or "").strip()
                if not (_has_digits(lat0) and _has_digits(lon0)):
                    continue

                num0 = (raw.get("Number") or "").strip()
                street0 = (raw.get("Street") or "").strip()
                suburb0 = (raw.get("Suburb") or "").strip()

                st_left, st_sub = _split_street_suburb(street0)
                suburb_eff = suburb0 or st_sub

                unit0 = (raw.get("Unit") or "").strip()
                merged0 = _combine_unit_and_number(unit0, num0)

                for k in (
                    _canon_key(num0, st_left, suburb_eff),
                    _canon_key(merged0, st_left, suburb_eff),
                ):
                    if k and k not in input_coords:
                        input_coords[k] = (lat0, lon0)
        except Exception:
            input_coords = {}

        def _restore_coords_if_missing(cleaned: dict, old_unit: str, old_number: str, old_street: str) -> bool:
            latc = (cleaned.get("Latitude") or "").strip()
            lonc = (cleaned.get("Longitude") or "").strip()
            if _has_digits(latc) and _has_digits(lonc):
                return False

            num_c = (cleaned.get("Number") or "").strip()
            st_c = (cleaned.get("Street") or "").strip()
            sub_c = (cleaned.get("Suburb") or "").strip()

            st_old_left, st_old_sub = _split_street_suburb(old_street)
            sub_old = (sub_c or st_old_sub or "").strip()

            merged_old = _combine_unit_and_number(old_unit, old_number)

            candidates = [
                _canon_key(num_c, st_c, sub_c),
                _canon_key(old_number, st_old_left, sub_old),
                _canon_key(merged_old, st_old_left, sub_old),
                _canon_key(old_number, st_old_left, sub_c),
                _canon_key(merged_old, st_old_left, sub_c),
            ]

            for k in candidates:
                if not k:
                    continue
                hit = input_coords.get(k)
                if hit:
                    cleaned["Latitude"], cleaned["Longitude"] = hit[0], hit[1]
                    try:
                        _append_other_notes(cleaned, "Coords restored from input_googlesheets.csv (robust match)")
                    except Exception:
                        pass
                    return True
            return False

        def _is_blank_addr_that_formats_to_comma_auckland(rec: dict) -> bool:
            num = (rec.get("Number") or "").strip()
            street = (rec.get("Street") or "").strip()
            suburb = (rec.get("Suburb") or "").strip()
            if num or street:
                return False
            if not suburb:
                return True
            return suburb.strip().lower() == "auckland"

        stage(
            "Writing cleaned outputs",
            module=__name__,
            fn="run_sheets_clean_and_split_after_purge_verify",
            extra={"out_clean": out_clean, "out_fail": out_fail},
        )

        with open(out_clean, "w", newline="", encoding="utf-8", buffering=1024 * 1024) as fout_c, \
             open(out_fail,  "w", newline="", encoding="utf-8", buffering=1024 * 1024) as fout_f:

            wc = csv.DictWriter(fout_c, fieldnames=fieldnames); wc.writeheader()
            wf = csv.DictWriter(fout_f, fieldnames=fieldnames); wf.writeheader()

            safe_fn = lambda r: _sanitize_row_for_write(r, fieldnames, add_row_audit_fields)

            for row in tqdm(rows, desc="Cleaning+Verify", unit="row"):
                if exclude_new and _notes_has_new_street_ci(row.get("Notes", "")):
                    continue

                old_unit   = (row.get("Unit") or "").strip()
                old_number = (row.get("Number") or "").strip()
                old_street = (row.get("Street") or "").strip()

                apartment_number = (row.get("Apartment/Business") or row.get("ApartmentNumber") or "").strip()
                notes_val = (row.get("Notes") or "").strip()
                language_val = (row.get("Language") or "").strip()
                type_val = (row.get("Type") or "").strip()

                incoming_status = (row.get("Status") or "").strip()
                status_val = "At Home" if incoming_status.lower() == "home" else (incoming_status or "At Home")

                suburb_in = (row.get("Suburb") or "").strip()
                street_val = old_street

                if (not suburb_in) and ("," in street_val):
                    left, right = street_val.split(",", 1)
                    left = left.strip()
                    right = right.strip()
                    if left and right:
                        street_val = left
                        suburb_in = right

                suburb_val = _canon_suburb_sheets(suburb_in)

                old_lat = (row.get("Latitude") or "").strip()
                old_lon = (row.get("Longitude") or "").strip()
                lat_val = old_lat if _has_digits(old_lat) else ""
                lon_val = old_lon if _has_digits(old_lon) else ""

                merged_number = _combine_unit_and_number(old_unit, old_number)

                cleaned = {
                    "Old Number": old_number,
                    "Unit": old_unit,
                    "Old Street": old_street,
                    "ApartmentNumber": apartment_number,
                    "Number": merged_number,
                    "Street": street_val,
                    "Suburb": suburb_val,
                    "PostalCode": _postal_for_suburb_sheets(suburb_val),
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

                _strict_normalize_final_status(cleaned)
                _clean_notes_and_language(cleaned)
                _default_type_house(cleaned)

                cleaned["Street"] = _repair_corrupted_street(cleaned.get("Street", ""))
                cleaned["Street"] = _strip_trailing_postcode(cleaned["Street"])
                cleaned["Street"] = gs_strip_leading_duplicate_number_from_street(
                    cleaned.get("Number", ""), cleaned.get("Street", "")
                )

                cleaned["Suburb"] = _canon_suburb_sheets(cleaned.get("Suburb", ""))
                cleaned["PostalCode"] = _postal_for_suburb_sheets(cleaned.get("Suburb", ""))

                if _is_blank_addr_that_formats_to_comma_auckland(cleaned):
                    cleaned["Final Status"] = "Fail"
                    _append_other_notes(cleaned, "Fail: blank Number+Street (would format ', Auckland')")
                    _flip_before_write(cleaned)
                    _route_by_final_status(rec=cleaned, clean_writer=wc, fail_writer=wf, make_safe_row_fn=safe_fn)
                    continue

                lat, lon, src = _choose_best_coordinate(cleaned, allow_outside_auckland=False)
                if lat is not None and lon is not None and src:
                    _accept_geocode_update(cleaned, lat, lon, src)

                _restore_coords_if_missing(cleaned, old_unit, old_number, old_street)

                try:
                    backfill_suburb_postcode_for_row(
                        cleaned,
                        kml_dir="KML Boundaries",
                        prefer_coords=True,
                        log_changes=False,
                    )
                except Exception:
                    pass

                cleaned["Suburb"] = _canon_suburb_sheets(cleaned.get("Suburb", ""))
                cleaned["PostalCode"] = _postal_for_suburb_sheets(cleaned.get("Suburb", ""))

                reasons = _should_fail_row(cleaned, old_unit, old_number, old_street)

                # Respect pre-set non-pass statuses; otherwise compute Pass/Fail.
                if not _final_status_is_set_and_not_pass_ok(cleaned):
                    if _strict_is_fail(cleaned) or reasons:
                        cleaned["Final Status"] = "Fail"
                    else:
                        cleaned["Final Status"] = "Pass"

                if reasons and (cleaned.get("Final Status") or "").strip().lower() == "fail":
                    _append_other_notes(cleaned, "Fail: " + ", ".join(reasons))

                _flip_before_write(cleaned)

                _route_by_final_status(rec=cleaned, clean_writer=wc, fail_writer=wf, make_safe_row_fn=safe_fn)

        # --- CANONICAL FINAL SWEEP SEQUENCE ---
        try:
            enforce_outputs_routing(out_clean, out_fail)
        except Exception:
            pass

        try:
            run_final_master_duplicate_filter(out_clean, out_fail)
        except Exception:
            pass

        try:
            enforce_outputs_routing(out_clean, out_fail)
        except Exception:
            pass

        try:
            run_verify_fail_against_master(out_clean, out_fail)
        except Exception:
            pass

        try:
            enforce_outputs_routing(out_clean, out_fail)
        except Exception:
            pass

        if do_split:
            decision("SPLIT_START", module=__name__, fn="run_sheets_clean_and_split_after_purge_verify", extra={"kml_dir": "KML Boundaries"})
            print("✅ Stage 3: Splitting By Territory Boundaries")
            _split_into_final_folder(out_clean, out_fail)

        _summarize_final_status(out_clean, out_fail)

        stage(
            "Flow finished: Clean (full verify)",
            module=__name__,
            fn="run_sheets_clean_and_split_after_purge_verify",
            extra={"out_clean": out_clean, "out_fail": out_fail},
        )

    except Exception:
        log_exception(
            "FLOW_EXCEPTION",
            module=__name__,
            fn="run_sheets_clean_and_split_after_purge_verify",
            extra={"input_file": input_file, "out_clean": out_clean, "out_fail": out_fail, "do_split": do_split},
        )
        raise





# C:\Users\brook\OneDrive\Desktop\Coding\Territory Assistant\GoogleSheets_Flows.py

def run_sheets_clean_and_split_new_streets_verify(
    input_file: str,
    do_split: bool = False,
    out_clean: str = "output_clean.csv",
    out_fail: str = "output_fail.csv",
) -> None:
    """
    NEW Streets + full verify.

    PATCHED:
    - Run an audit to print the exact input rows that would format to ", Auckland".
    - Hard-stop geocoding on rows that would produce ", Auckland" (Street blank and Number blank).
    - If Latitude/Longitude are missing in output_clean, restore them from the
      original input_googlesheets.csv when that row had coordinates.

    EXTRA SAFETY:
    - Guard core.cancel_flag (some cores don't expose it).
    """
    from GoogleSheets_Log import stage, log_exception, decision
    from GoogleSheets_Utils import audit_blank_auckland_rows, _open_csv_text_best_effort
    from GoogleSheets_Utils import route_row_writers_by_final_status

    input_file = str(input_file)

    stage(
        "Flow started: New Streets (full verify)",
        module=__name__,
        fn="run_sheets_clean_and_split_new_streets_verify",
        extra={"input_file": input_file, "do_split": do_split},
    )

    try:
        # Reuse the master index loaded/refreshed by the preceding OTHER phase.
        # Do not clear it here: Option 1/2 process OTHER first, so rebuilding the
        # same full master index again for NEW STREETS is redundant and expensive.
        _load_master_index()

        fieldnames = [
            "Old Number", "Unit",
            "Old Street",
            "ApartmentNumber", "Number", "Street",
            "Suburb", "PostalCode", "State",
            "Status", "Final Status",
            "Latitude", "Longitude",
            "Type", "Language", "Notes", "Other Notes",
        ]

        add_row_audit_fields = _maybe_import_add_row_audit_fields()
        fieldnames = _extend_fieldnames_with_audit(list(fieldnames), add_row_audit_fields)

        stage(
            "Loading input CSV",
            module=__name__,
            fn="run_sheets_clean_and_split_new_streets_verify",
        )

        f = None
        try:
            f = _open_csv_text_best_effort(input_file)
            r = csv.DictReader(f)
            rows = list(r)
        finally:
            try:
                if f is not None:
                    f.close()
            except Exception:
                pass

        try:
            audit_blank_auckland_rows(
                input_file,
                max_print=3,
                label="NewStreets input audit",
                require_suburb_auckland_or_blank=True,
            )
        except Exception:
            pass

        def _canon_key(num: str, street: str, suburb: str) -> str:
            n = normalize_number((num or "").strip())
            s = _canon_text(street or "")
            sub = _canon_suburb_sheets(suburb or "")
            return f"{n}|{s}|{sub}"

        def _split_street_suburb(street_val: str):
            s = (street_val or "").strip()

            if "," in s:
                left, right = s.split(",", 1)
                return left.strip(), right.strip()

            return s, ""

        input_coords: dict[str, tuple[str, str]] = {}

        try:
            for raw in rows:
                lat0 = (raw.get("Latitude") or "").strip()
                lon0 = (raw.get("Longitude") or "").strip()

                if not (_has_digits(lat0) and _has_digits(lon0)):
                    continue

                old_unit = (raw.get("Unit") or "").strip()
                old_number = (raw.get("Number") or "").strip()
                old_street = (raw.get("Street") or "").strip()
                suburb0 = (raw.get("Suburb") or "").strip()

                st_left, st_sub = _split_street_suburb(old_street)
                suburb_eff = suburb0 or st_sub

                merged_old = _combine_unit_and_number(old_unit, old_number)

                for k in (
                    _canon_key(old_number, st_left, suburb_eff),
                    _canon_key(merged_old, st_left, suburb_eff),
                ):
                    if k and k not in input_coords:
                        input_coords[k] = (lat0, lon0)

        except Exception:
            input_coords = {}

        def _restore_coords_if_missing(
            cleaned: dict,
            old_unit: str,
            old_number: str,
            old_street: str,
        ) -> bool:
            latc = (cleaned.get("Latitude") or "").strip()
            lonc = (cleaned.get("Longitude") or "").strip()

            if _has_digits(latc) and _has_digits(lonc):
                return False

            num_c = (cleaned.get("Number") or "").strip()
            st_c = (cleaned.get("Street") or "").strip()
            sub_c = (cleaned.get("Suburb") or "").strip()

            st_old_left, st_old_sub = _split_street_suburb(old_street)
            sub_old = (sub_c or st_old_sub or "").strip()
            merged_old = _combine_unit_and_number(old_unit, old_number)

            candidates = [
                _canon_key(num_c, st_c, sub_c),
                _canon_key(old_number, st_old_left, sub_old),
                _canon_key(merged_old, st_old_left, sub_old),
                _canon_key(old_number, st_old_left, sub_c),
                _canon_key(merged_old, st_old_left, sub_c),
            ]

            for k in candidates:
                if not k:
                    continue

                hit = input_coords.get(k)

                if hit:
                    cleaned["Latitude"], cleaned["Longitude"] = hit[0], hit[1]

                    try:
                        _append_other_notes(
                            cleaned,
                            "Coords restored from input_googlesheets.csv (robust match)",
                        )
                    except Exception:
                        pass

                    return True

            return False

        def _is_blank_addr_that_formats_to_comma_auckland(rec: dict) -> bool:
            num = (rec.get("Number") or "").strip()
            street = (rec.get("Street") or "").strip()
            suburb = (rec.get("Suburb") or "").strip()

            if num or street:
                return False

            if not suburb:
                return True

            return suburb.strip().lower() == "auckland"

        stage(
            "Writing cleaned outputs",
            module=__name__,
            fn="run_sheets_clean_and_split_new_streets_verify",
            extra={"out_clean": out_clean, "out_fail": out_fail},
        )

        cancel_flag = getattr(core, "cancel_flag", None)

        with open(
            out_clean,
            "w",
            newline="",
            encoding="utf-8",
            buffering=1024 * 1024,
        ) as fout_c, open(
            out_fail,
            "w",
            newline="",
            encoding="utf-8",
            buffering=1024 * 1024,
        ) as fout_f:

            wc = csv.DictWriter(fout_c, fieldnames=fieldnames)
            wc.writeheader()

            wf = csv.DictWriter(fout_f, fieldnames=fieldnames)
            wf.writeheader()

            def _flip_before_write(rec: dict) -> None:
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
                    return

            for row in tqdm(rows, desc="NewStreets+Verify", unit="row"):
                try:
                    if (
                        cancel_flag is not None
                        and getattr(cancel_flag, "is_set", None)
                        and cancel_flag.is_set()
                    ):
                        break
                except Exception:
                    pass

                old_unit = (row.get("Unit") or "").strip()
                old_number = (row.get("Number") or "").strip()
                old_street = (row.get("Street") or "").strip()

                apartment_number = (
                    row.get("Apartment/Business")
                    or row.get("ApartmentNumber")
                    or ""
                ).strip()

                notes_val = (row.get("Notes") or "").strip()
                notes_pub_val = (row.get("NotesFromPublisher") or "").strip()
                language_val = (row.get("Language") or "").strip()
                type_val = (row.get("Type") or "").strip()

                if not _notes_has_new_street_ci(notes_val):
                    continue

                merged_number = _combine_unit_and_number(old_unit, old_number)

                suburb_in = (row.get("Suburb") or "").strip()
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

                street_val = gs_strip_leading_duplicate_number_from_street(
                    merged_number,
                    street_val,
                )

                street_val = _strip_trailing_postcode(street_val)
                street_val = _repair_corrupted_street(street_val)

                old_lat = (row.get("Latitude") or "").strip()
                old_lon = (row.get("Longitude") or "").strip()

                lat_val = old_lat if _has_digits(old_lat) else ""
                lon_val = old_lon if _has_digits(old_lon) else ""

                postal_code = _postal_for_suburb_sheets(suburb_val)

                incoming_status = (row.get("Status") or "").strip()

                status_val = (
                    "At Home"
                    if incoming_status.lower() == "home"
                    else (incoming_status or "At Home")
                )

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
                    "Other Notes": "",
                }

                _clean_notes_and_language(cleaned)
                _default_type_house(cleaned)

                _apply_new_street_overrides(
                    cleaned,
                    notes_val,
                    notes_pub_val,
                )

                if _is_blank_addr_that_formats_to_comma_auckland(cleaned):
                    cleaned["Final Status"] = "Fail"

                    _append_other_notes(
                        cleaned,
                        "Fail: blank Number+Street (would format ', Auckland')",
                    )

                    _log_missing_coords(
                        cleaned,
                        stage=(
                            "run_sheets_clean_and_split_new_streets_verify:"
                            "FAIL_WRITE_BLANK_ADDR"
                        ),
                        reason="blank Number+Street (would format ', Auckland')",
                    )

                    _flip_before_write(cleaned)

                    route_row_writers_by_final_status(
                        cleaned,
                        clean_writer=wc,
                        fail_writer=wf,
                        make_safe_row_fn=lambda r: _sanitize_row_for_write(
                            r,
                            fieldnames,
                            add_row_audit_fields,
                        ),
                    )

                    continue

                geo_row = dict(cleaned)
                geo_row["Number"] = merged_number
                geo_row["Street"] = street_val
                geo_row["Suburb"] = suburb_val

                lat, lon, src = _choose_best_coordinate(
                    geo_row,
                    allow_outside_auckland=False,
                )

                if lat is not None and lon is not None and src:
                    _accept_geocode_update(
                        cleaned,
                        lat,
                        lon,
                        src,
                    )

                _restore_coords_if_missing(
                    cleaned,
                    old_unit,
                    old_number,
                    old_street,
                )

                try:
                    backfill_suburb_postcode_for_row(
                        cleaned,
                        kml_dir="KML Boundaries",
                        prefer_coords=True,
                        log_changes=False,
                    )
                except Exception:
                    pass

                cleaned["Suburb"] = _canon_suburb_sheets(
                    cleaned.get("Suburb", "")
                )

                cleaned["PostalCode"] = _postal_for_suburb_sheets(
                    cleaned.get("Suburb", "")
                )

                reasons = _should_fail_row(
                    cleaned,
                    old_unit,
                    old_number,
                    old_street,
                )

                if reasons:
                    cleaned["Final Status"] = "Fail"

                    _append_other_notes(
                        cleaned,
                        "Fail: " + ", ".join(reasons),
                    )

                    _log_missing_coords(
                        cleaned,
                        stage=(
                            "run_sheets_clean_and_split_new_streets_verify:"
                            "FAIL_WRITE"
                        ),
                        reason="; ".join(reasons),
                    )

                else:
                    cleaned["Final Status"] = "Pass"

                    _log_missing_coords(
                        cleaned,
                        stage=(
                            "run_sheets_clean_and_split_new_streets_verify:"
                            "CLEAN_WRITE"
                        ),
                        reason="passed_should_fail_row",
                    )

                _flip_before_write(cleaned)

                route_row_writers_by_final_status(
                    cleaned,
                    clean_writer=wc,
                    fail_writer=wf,
                    make_safe_row_fn=lambda r: _sanitize_row_for_write(
                        r,
                        fieldnames,
                        add_row_audit_fields,
                    ),
                )

                continue

        # Canonical final sweep
        try:
            enforce_outputs_routing(out_clean, out_fail)
        except Exception:
            pass

        try:
            run_final_master_duplicate_filter(out_clean, out_fail)
        except Exception:
            pass

        try:
            enforce_outputs_routing(out_clean, out_fail)
        except Exception:
            pass

        try:
            run_verify_fail_against_master(out_clean, out_fail)
        except Exception:
            pass

        try:
            enforce_outputs_routing(out_clean, out_fail)
        except Exception:
            pass

        if do_split:
            decision(
                "SPLIT_START",
                module=__name__,
                fn="run_sheets_clean_and_split_new_streets_verify",
                extra={"kml_dir": "KML Boundaries"},
            )

            print("✅ Stage 3: Splitting By Territory Boundaries")

            _split_into_final_folder(
                out_clean,
                out_fail,
            )

        _summarize_final_status(
            out_clean,
            out_fail,
        )

        stage(
            "Flow finished: New Streets (full verify)",
            module=__name__,
            fn="run_sheets_clean_and_split_new_streets_verify",
            extra={"out_clean": out_clean, "out_fail": out_fail},
        )

    except Exception:
        log_exception(
            "FLOW_EXCEPTION",
            module=__name__,
            fn="run_sheets_clean_and_split_new_streets_verify",
            extra={
                "input_file": input_file,
                "out_clean": out_clean,
                "out_fail": out_fail,
                "do_split": do_split,
            },
        )

        raise






def _log_missing_coords(row: dict, *, stage: str, reason: str = "") -> None:
    """
    FILE-ONLY breadcrumb for rows that STILL have missing/invalid coords
    at the point we are about to write them out.

    - NEVER prints to console
    - Uses DEBUG level so it stays silent in console
    """
    from GoogleSheets_Log import log_debug

    lat_raw = (row.get("Latitude") or "").strip()
    lon_raw = (row.get("Longitude") or "").strip()

    try:
        lat_ok = _has_digits(lat_raw)
        lon_ok = _has_digits(lon_raw)
    except Exception:
        lat_ok = bool(lat_raw)
        lon_ok = bool(lon_raw)

    if lat_ok and lon_ok:
        return  # nothing to log

    # Best-effort "what would we geocode?" query
    query = ""
    try:
        ap = (row.get("ApartmentNumber") or row.get("Apartment/Business") or "").strip()
        num = (row.get("Number") or "").strip()
        street = (row.get("Street") or "").strip()
        suburb = (row.get("Suburb") or "").strip()

        fmt = getattr(core, "fmt_addr_parts", None)
        if callable(fmt):
            query = fmt(ap, num, street, suburb)
        else:
            query = ", ".join([x for x in [ap, num, street, suburb, "Auckland"] if x]).strip(", ")
    except Exception:
        query = ""

    log_debug(
        "MISSING_COORDS_AFTER_PROCESSING",
        module=__name__,
        fn=stage,
        extra={
            "reason": (reason or "").strip(),
            "query": query,
            "lat_ok": bool(lat_ok),
            "lon_ok": bool(lon_ok),
            "ApartmentNumber": row.get("ApartmentNumber", "") or row.get("Apartment/Business", ""),
            "Number": row.get("Number", ""),
            "Street": row.get("Street", ""),
            "Suburb": row.get("Suburb", ""),
            "Old Street": row.get("Old Street", ""),
            "Final Status": row.get("Final Status", "") or row.get("Status", ""),
            "Notes": row.get("Notes", ""),
            "Other Notes": row.get("Other Notes", ""),
            "Latitude_raw": row.get("Latitude", ""),
            "Longitude_raw": row.get("Longitude", ""),
        },
    )

def _default_type_house(rec: dict) -> None:
    """
    Ensure `Type` is never blank at write time.
    Rule: missing/blank -> "House".
    """
    try:
        if "Type" not in rec:
            rec["Type"] = "House"
            return
        v = (rec.get("Type") or "").strip()
        if not v:
            rec["Type"] = "House"
    except Exception:
        # Never break a run due to Type defaulting
        try:
            rec["Type"] = rec.get("Type") or "House"
        except Exception:
            pass


def _maybe_import_add_row_audit_fields():
    """
    Local, safe import wrapper.
    Returns callable add_row_audit_fields(row) or None.
    """
    try:
        from GoogleSheets_Utils import add_row_audit_fields  # type: ignore
        return add_row_audit_fields
    except Exception:
        return None


def _extend_fieldnames_with_audit(fieldnames: list[str], add_row_audit_fields) -> list[str]:
    """
    Ensure output headers include audit columns even if the input schema doesn't.

    SAFETY:
    - Never emit private/internal keys (starting with "_").
    - Never emit audit/log-only keys (Utils._AUDIT_LOG_ONLY_KEYS).
    - Works even if the input file header is "infected" from an old run.
    """
    deny = set()
    try:
        from GoogleSheets_Utils import audit_log_only_keys  # preferred
        deny |= set(audit_log_only_keys())
    except Exception:
        try:
            from GoogleSheets_Utils import _AUDIT_LOG_ONLY_KEYS  # fallback
            deny |= set(_AUDIT_LOG_ONLY_KEYS)
        except Exception:
            pass

    deny |= {"_geocode_meta"}  # internal meta blob must never persist

    def allowed(k: str) -> bool:
        if not k:
            return False
        if str(k).startswith("_"):
            return False
        if k in deny:
            return False
        return True

    out: list[str] = []
    for k in list(fieldnames or []):
        if allowed(k) and k not in out:
            out.append(k)

    probe: dict = {}
    if callable(add_row_audit_fields):
        try:
            add_row_audit_fields(probe)  # may add "Missing Fields" only (ok)
        except Exception:
            probe = {}

    for k in list(probe.keys()):
        if allowed(k) and k not in out:
            out.append(k)

    return out


def _sanitize_row_for_write(row: dict, fieldnames: list[str], add_row_audit_fields) -> dict:
    """
    - Populate audit fields (if available)
    - Return dict limited to safe fieldnames only

    SAFETY:
    - Remove any audit/log-only keys + internal meta from the row (belt + suspenders),
      then only emit allowed columns.
    """
    if callable(add_row_audit_fields):
        try:
            add_row_audit_fields(row)
        except Exception:
            pass

    # Hard strip anything log-only/meta (centralized in Utils)
    try:
        from GoogleSheets_Utils import strip_audit_columns_from_row
        strip_audit_columns_from_row(row)
    except Exception:
        pass

    deny = set()
    try:
        from GoogleSheets_Utils import audit_log_only_keys
        deny |= set(audit_log_only_keys())
    except Exception:
        try:
            from GoogleSheets_Utils import _AUDIT_LOG_ONLY_KEYS
            deny |= set(_AUDIT_LOG_ONLY_KEYS)
        except Exception:
            pass

    deny |= {"_geocode_meta"}

    safe_fields = [
        k for k in (fieldnames or [])
        if k and not str(k).startswith("_") and k not in deny
    ]

    return {k: (row.get(k, "") if k is not None else "") for k in safe_fields}


def _flip_units_inplace(rows_or_row) -> int | bool:
    """
    Normalize Number into ONE stable form in-place.

    Canonical form: Unit-first (UnitA/12).
      - 12/UnitA  -> UnitA/12
      - UnitA/12  -> unchanged

    Returns:
      - bool in single-row mode
      - int (count flipped) in list-of-rows mode
    """
    # -------------------------
    # Single-row mode (returns bool)
    # -------------------------
    if isinstance(rows_or_row, dict):
        row = rows_or_row
        num = (row.get("Number") or "").strip()
        if not num:
            return False

        # House-first -> Unit-first
        m = HOUSE_FLIP_B.match(num)
        if m:
            row["Number"] = f"Unit{m.group(2).upper()}/{m.group(1)}"
            return True

        return False

    # -------------------------
    # List-of-rows mode (returns int)
    # -------------------------
    rows = list(rows_or_row) if rows_or_row is not None else []
    if not rows:
        return 0

    flipped = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        num = (row.get("Number") or "").strip()
        if not num:
            continue

        m = HOUSE_FLIP_B.match(num)
        if m:
            row["Number"] = f"Unit{m.group(2).upper()}/{m.group(1)}"
            flipped += 1

    return flipped



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


def _should_fail_row(cleaned: dict, old_unit: str, old_number: str, old_street: str) -> list[str]:
    """
    Legacy-compatible failure logic.

    IMPORTANT:
    - Google Sheets input often has NO "Old Number"/"Old Street" columns.
      In that case we must NOT fail rows just because old_* fields are blank.
    - Only enforce the "matches old" comparisons when old_* values are present.
    """
    reasons: list[str] = []

    # New-street special casing (legacy behavior)
    is_new_street = (cleaned.get("Status") == "Custom3" and cleaned.get("Notes") == NEW_STREET_MSG)

    # Required fields
    if not (cleaned.get("Number") or "").strip():
        if not is_new_street:
            reasons.append("missing Number")

    if not (cleaned.get("Street") or "").strip():
        reasons.append("missing Street")

    # Only enforce old-street comparison when we actually HAVE an old street value
    old_street_norm = (old_street or "").strip()
    if old_street_norm and (cleaned.get("Street") or "").strip():
        if not _street_suburb_matches_old(old_street, cleaned.get("Street", ""), cleaned.get("Suburb", "")):
            reasons.append("Street+Suburb does not match Old Street")

    # Only enforce old-number comparison when we actually HAVE an old number/unit
    old_number_norm = (old_number or "").strip()
    old_unit_norm = (old_unit or "").strip()

    if (cleaned.get("Number") or "").strip() and (old_number_norm or old_unit_norm):
        if not _numbers_match(old_unit, old_number, cleaned.get("Number", "")):
            reasons.append("Number does not match Old Number+Unit")

    return reasons


# --- Logging: wrap functions defined in THIS module (avoid imported callables) ---
# IMPORTANT:
# - Avoid import-time side effects by default (prevents circular-import issues).
# - Enable with: GS_AUTOWRAP_FLOWS=1
try:
    _maybe_autowrap_flows_module()
except Exception:
    # Never break import due to logging instrumentation
    pass
