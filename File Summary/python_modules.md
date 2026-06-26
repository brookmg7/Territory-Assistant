# Python/BAT Module Map (compact)

## Flow Logic docs detected (from 'File Summary' folder)

- `[no .md files found in 'File Summary']`

---

## Shared CSV contracts + IO dependency graph (heuristic)

If a change affects a CSV field or decision outcome, always check:
- `Analyzer → Decision → Journal → Export` (in that order)

### Shared CSV contracts

- None detected

### Tiny IO dependency edges (producer → consumer via same file)

- None detected

---

## Group 1 (size=65)

### Start Here

- `Clean_NewWorldScheduler.py`
- `Menu.py`
- `Other_Functions.py`
- `Street Database/bin/gdal/python/osgeo_utils/auxiliary/batch_creator.py`
- `Street Database/bin/gdal/python/osgeo_utils/auxiliary/gdal_argparse.py`
- `Street Database/bin/gdal/python/osgeo_utils/gdal2tiles.py`
- `Street Database/bin/gdal/python/osgeo_utils/gdal2xyz.py`
- `Street Database/bin/gdal/python/osgeo_utils/gdal_calc.py`

### Critical paths (heuristic)

- `Clean_NewWorldScheduler.py` → `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- `Clean_NewWorldScheduler.py` → `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` → `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`
- `Clean_NewWorldScheduler.py` → `Other_Functions.py`
- `Menu.py` → `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- `Menu.py` → `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` → `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`
- `Menu.py`

### Subsystems

- **BAT / Launchers** (1)
- **Broker / Execution** (2)
- **Core / Other** (20)
- **Exports / Reporting** (3)
- **Filesystem / I/O** (5)
- **Journal / Audit** (1)
- **Risk / Gates** (4)
- **Runtime / Entrypoints** (29)

### Subsystem dependency map (collapsed)

- **Runtime / Entrypoints** → **Risk / Gates** (edges≈24)
- **Core / Other** → **Journal / Audit** (edges≈18)
- **Core / Other** → **Runtime / Entrypoints** (edges≈17)
- **Runtime / Entrypoints** → **Filesystem / I/O** (edges≈17)
- **Exports / Reporting** → **Risk / Gates** (edges≈3)
- **Runtime / Entrypoints** → **Exports / Reporting** (edges≈3)
- **Broker / Execution** → **Risk / Gates** (edges≈2)
- **Filesystem / I/O** → **Risk / Gates** (edges≈2)
- **Runtime / Entrypoints** → **Core / Other** (edges≈2)
- **BAT / Launchers** → **Runtime / Entrypoints** (edges≈1)
- **Filesystem / I/O** → **Core / Other** (edges≈1)
- **Journal / Audit** → **Core / Other** (edges≈1)

### File-level dependency map (collapsed)

- `Clean_NewWorldScheduler.py` → { `Other_Functions.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Menu.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Run_Menu.bat` → { `Menu.py` }
- `Street Database/bin/gdal/python/osgeo/gdal.py` → { `Street Database/bin/gdal/python/osgeo/gdalconst.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/osgeo/gdal_array.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/osgeo/gdalnumeric.py` → { `Street Database/bin/gdal/python/osgeo/gdal_array.py` }
- `Street Database/bin/gdal/python/osgeo/gnm.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/osgeo/ogr.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/osgeo/osr.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/osgeo_utils/auxiliary/batch_creator.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py` }
- `Street Database/bin/gdal/python/osgeo_utils/auxiliary/color_palette.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py` }
- `Street Database/bin/gdal/python/osgeo_utils/auxiliary/color_table.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/color_palette.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/osgeo_utils/auxiliary/extent_util.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/rectangle.py` }
- `Street Database/bin/gdal/python/osgeo_utils/auxiliary/numpy_util.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/array_util.py` }
- `Street Database/bin/gdal/python/osgeo_utils/auxiliary/osr_util.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/array_util.py` }
- `Street Database/bin/gdal/python/osgeo_utils/auxiliary/progress.py` → { `Street Database/bin/gdal/python/osgeo/gdal.py` }
- `Street Database/bin/gdal/python/osgeo_utils/auxiliary/raster_creation.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py` }
- `Street Database/bin/gdal/python/osgeo_utils/gdal2tiles.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/osgeo_utils/gdal2xyz.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/gdal_argparse.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/numpy_util.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/progress.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/osgeo_utils/gdal_calc.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/color_table.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/extent_util.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/gdal_argparse.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/rectangle.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/osgeo_utils/gdal_edit.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/osgeo_utils/gdal_fillnodata.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/gdal_argparse.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/osgeo_utils/gdal_merge.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/osgeo_utils/gdal_pansharpen.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/osgeo_utils/gdal_polygonize.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/gdal_argparse.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/osgeo_utils/gdal_proximity.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/osgeo_utils/gdal_retile.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/osgeo_utils/gdal_sieve.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/osgeo_utils/gdalattachpct.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/color_table.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/osgeo_utils/gdalcompare.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/osgeo_utils/gdalmove.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/osgeo_utils/ogr_layer_algebra.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/osgeo_utils/ogrmerge.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/osgeo_utils/pct2rgb.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/color_palette.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/color_table.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/gdal_argparse.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/osgeo_utils/rgb2pct.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/color_table.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/gdal_argparse.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/osgeo_utils/samples/epsg_tr.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/gdal_argparse.py` }
- `Street Database/bin/gdal/python/osgeo_utils/samples/esri2wkt.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/gdal_argparse.py` }
- `Street Database/bin/gdal/python/osgeo_utils/samples/gdal_minmax_location.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/gdal_argparse.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/osgeo_utils/samples/gdalbuildvrtofvrt.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/gdal_argparse.py` }
- `Street Database/bin/gdal/python/osgeo_utils/samples/gdallocationinfo.py` → { `Street Database/bin/gdal/python/osgeo/gdal_array.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/array_util.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/gdal_argparse.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/numpy_util.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/osr_util.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/osgeo_utils/samples/tile_extent_from_raster.py` → { `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py` }
- `Street Database/bin/gdal/python/scripts/gdal2xyz.py` → { `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal2xyz.py` }
- `Street Database/bin/gdal/python/scripts/gdal_calc.py` → { `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_calc.py` }
- `Street Database/bin/gdal/python/scripts/gdal_edit.py` → { `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_edit.py` }
- `Street Database/bin/gdal/python/scripts/gdal_fillnodata.py` → { `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_fillnodata.py` }
- `Street Database/bin/gdal/python/scripts/gdal_merge.py` → { `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_merge.py` }
- `Street Database/bin/gdal/python/scripts/gdal_pansharpen.py` → { `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_pansharpen.py` }
- `Street Database/bin/gdal/python/scripts/gdal_polygonize.py` → { `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_polygonize.py` }
- `Street Database/bin/gdal/python/scripts/gdal_proximity.py` → { `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_proximity.py` }
- `Street Database/bin/gdal/python/scripts/gdal_retile.py` → { `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_retile.py` }
- `Street Database/bin/gdal/python/scripts/gdal_sieve.py` → { `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_sieve.py` }
- `Street Database/bin/gdal/python/scripts/gdalattachpct.py` → { `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/gdalattachpct.py` }
- `Street Database/bin/gdal/python/scripts/gdalcompare.py` → { `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/gdalcompare.py` }
- `Street Database/bin/gdal/python/scripts/gdalmove.py` → { `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/gdalmove.py` }
- `Street Database/bin/gdal/python/scripts/ogr_layer_algebra.py` → { `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/ogr_layer_algebra.py` }
- `Street Database/bin/gdal/python/scripts/ogrmerge.py` → { `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/ogrmerge.py` }
- `Street Database/bin/gdal/python/scripts/pct2rgb.py` → { `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/pct2rgb.py` }
- `Street Database/bin/gdal/python/scripts/rgb2pct.py` → { `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/rgb2pct.py` }

### Modules

#### `Clean_NewWorldScheduler.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `broker/execution/orders`, `analysis/scoring/setups`, `journaling/audit/logging`, `exports/reports (csv/json/md/txt)`, `risk/position sizing/rr/gates`, `time/session/scheduling`
- **Internal imports:** `Other_Functions.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `[none detected]`
- **IO label:** `boundary`
- **Creates/writes files (heuristic):** `output_clean.csv`, `output_fail.csv`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `requests (HTTP)`
- **Inside:** classes: AsyncRateLimiter, oth • funcs: _log_header_has_street, log_correction, _safe_float, _digits_int, _point_in_poly, merge_publisher_notes_into_notes, _point_on_segment, _dist_point_to_segment, _min_dist_to_polygon, _load_kml_polygons, _assign_point_to_polygons, _pick_nearest_number_target, split_cleaned_by_polygon_and_include_failed, _asyncio_exception_handler, _load_module_from_path, _load_option9_plugin, log_field_change, _to_parts, +207 more • consts: VERBOSE_PRE=<call get(... )>, INPUT_NWS='input_nws.csv', SUBURB_RESOLVE_MAX_PTS_PER_STREET=80, SUBURB_RESOLVE_PROBE_BUDGET=50, RESULT_ONLY_LOGS=True, PRESERVE_FREEFORM_FIELDS=<set len≈2>, USE_LINZ_MEMORY=True, _BASE_DIR=<attr parent>, _OPTION9_MOD=<call _load_option9_plugin(... )>, BASE_DIR=<attr parent>, GEOCODE_DEBUG=False, ADDRESS_PARSE_RX=<call compile(... )>, +49 more

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems; ⚠️ boundary module (network/MT5)
  - Side effects: `top-level assign from call: <call get(... )>`; `top-level assign from call: <call get(... )>`; `top-level assign from call: <call get(... )>`; `top-level assign from call: <call Lock(... )>`

#### `Menu.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `broker/execution/orders`, `analysis/scoring/setups`, `journaling/audit/logging`, `time/session/scheduling`, `filesystem/path I/O`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: _app_root, _force_cwd_to_app_root, resource_path, _touch_file_with, _ensure_required_files_here, _print_runtime_info, _set_proj_lib_local, _check_path, _check_module, _scan_requirements, bootstrap_setup, _load_module, _call_entry, open_clean_new_world_scheduler, open_clean_google_sheets, open_geopackage_borders, open_finding_new_addresses, open_other_functions, +2 more • consts: OK='✅', BAD='❌', APP_ROOT=<call _app_root(... )>, FILE_TEMPLATES=<dict len≈5>, REQUIREMENTS=<dict len≈5>

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems
  - Side effects: `top-level assign from call: <call _app_root(... )>`

#### `Other_Functions.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `journaling/audit/logging`, `exports/reports (csv/json/md/txt)`, `risk/position sizing/rr/gates`, `filesystem/path I/O`
- **Internal imports:** `[none detected]`
- **Imported by:** `Clean_NewWorldScheduler.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Why it exists (docstring/intent):**

```text
# Python Expert
Other_Functions.py — utilities for Export / Cleanup / Cache

This module hosts the four "Other" tools that used to live in Territory_Assistant.py:
  9) Export Script/Log Into Sections
 10) Remove All Output Files
 11) Remove All Files In 'New_Addresses_By_Suburb' Folder
 12) Delete 'geocode_cache.json' File

It exposes a small sub‑menu via `open_menu()` so Territory_Assistant can call it.
All functions are self‑contained and avoid depending on globals from the main app.
```
- **Inside:** funcs: option_2_split_js_html, _choose_script_file_jshtml, _safe_title, _preferred_script_path, backup_csv_files, remove_files, remove_files_in_folder, export_script_parts, export_bundle_after_parts, print_created_files, export_script_and_logs, prompt_delete_cache, _module_dir, _resolve_in_module_dir, _discover_scripts, _choose_script_file, _find_split_points, split_script_evenly, +3 more • consts: JS_HTML_DIR='C:\\script\\JavaScript HTML', APP_SCRIPT_HEADER_HINT="#App Script Expert- Here's my script in different parts, please read as one..., BACKUP_CSV_DIR='C:\\script\\Backup CSV Files', SPLIT_HEADER_HINT="#Python Expert - Here's my script in different parts, please read as one fil..., SPLIT_HINT_LINES=<call int(... )>, OUTPUT_FILES=<list len≈4>, SUBURB_DIR='New_Addresses_By_Suburb', DEFAULT_EXPORT_DIR='Exported Files', CORE_SCRIPT='Clean_NewWorldScheduler.py'

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems
  - Side effects: `top-level assign from call: <call int(... )>`

### `Run_Menu.bat`
- **Role:** `BAT`
- **Responsibilities:** `runs python scripts`, `sets env/runtime flags`
- **Env vars:** `"APPROOT=%~dp0"`, `"PYTHONPATH=%APPROOT%"`, `"PROJ_LIB="`, `"PROJ_LIB=%APPROOT%Street Database\share\proj"`, `"PROJ_LIB=%APPROOT%Street Database\proj"`, `"PROJ_LIB=%APPROOT%Street Database\bin"`, `"RC=%ERRORLEVEL%"`, `"RC=%ERRORLEVEL%"`
- **Python calls:** `echo [RUN] EXE not found. Running Python: Menu.py`, `echo [EXIT] Python returned code: !RC!`
- **References:** `Menu.py`

#### `Street Database/bin/gdal/python/osgeo/gdal.py`
- **Role:** `LIB`
- **Responsibilities:** `journaling/audit/logging`, `exports/reports (csv/json/md/txt)`, `config/env/constants`, `risk/position sizing/rr/gates`, `filesystem/path I/O`, `tests/harness/verification`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo/gdalconst.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/progress.py`, `Street Database/bin/gdal/python/scripts/gdal2xyz.py`, `Street Database/bin/gdal/python/scripts/gdal_calc.py`, `Street Database/bin/gdal/python/scripts/gdal_edit.py`, `Street Database/bin/gdal/python/scripts/gdal_fillnodata.py`, `Street Database/bin/gdal/python/scripts/gdal_merge.py`, `Street Database/bin/gdal/python/scripts/gdal_pansharpen.py`, `Street Database/bin/gdal/python/scripts/gdal_polygonize.py`, `Street Database/bin/gdal/python/scripts/gdal_proximity.py`, `Street Database/bin/gdal/python/scripts/gdal_retile.py`, `Street Database/bin/gdal/python/scripts/gdal_sieve.py`, `Street Database/bin/gdal/python/scripts/gdalattachpct.py`, `Street Database/bin/gdal/python/scripts/gdalcompare.py`, `Street Database/bin/gdal/python/scripts/gdalmove.py`, `Street Database/bin/gdal/python/scripts/ogr_layer_algebra.py`, `Street Database/bin/gdal/python/scripts/ogrmerge.py`, `Street Database/bin/gdal/python/scripts/pct2rgb.py`, `Street Database/bin/gdal/python/scripts/rgb2pct.py`
- **IO label:** `boundary`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `requests (HTTP)`
- **Inside:** classes: _SwigNonDynamicMeta, ExceptionMgr, VSIFile, DirEntry, VSILFILE, StatBuf, MajorObject, Driver, ColorEntry, GCP, VirtualMem, AsyncReader, Dataset, RasterAttributeTable, Group, Statistics, MDArray, Attribute, +28 more • funcs: _swig_repr, _swig_setattr_nondynamic_instance_variable, _swig_setattr_nondynamic_class_variable, _swig_add_metaclass, deprecation_warn, RGBFile2PCTFile, listdir, GetUseExceptions, _GetExceptionsLocal, _SetExceptionsLocal, _UseExceptions, _DontUseExceptions, _UserHasSpecifiedIfUsingExceptions, _has_gdal_array, UseExceptions, DontUseExceptions, VSIFReadL, VSIGetMemFileBuffer_unsafe, +241 more • consts: VSI_STAT_EXISTS_FLAG=<attr VSI_STAT_EXISTS_FLAG>, VSI_STAT_NATURE_FLAG=<attr VSI_STAT_NATURE_FLAG>, VSI_STAT_SIZE_FLAG=<attr VSI_STAT_SIZE_FLAG>, VSI_STAT_SET_ERROR_FLAG=<attr VSI_STAT_SET_ERROR_FLAG>, VSI_STAT_CACHE_ONLY=<attr VSI_STAT_CACHE_ONLY>, VSI_RANGE_STATUS_UNKNOWN=<attr VSI_RANGE_STATUS_UNKNOWN>, VSI_RANGE_STATUS_DATA=<attr VSI_RANGE_STATUS_DATA>, VSI_RANGE_STATUS_HOLE=<attr VSI_RANGE_STATUS_HOLE>, GEDTST_NONE=<attr GEDTST_NONE>, GEDTST_JSON=<attr GEDTST_JSON>, GEDTC_NUMERIC=<attr GEDTC_NUMERIC>, GEDTC_STRING=<attr GEDTC_STRING>, +4 more

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ boundary module (network/MT5)
  - Side effects: `top-level call: <call DirEntry_swigregister(... )>`; `top-level call: <call VSILFILE_swigregister(... )>`; `top-level call: <call StatBuf_swigregister(... )>`; `top-level call: <call MajorObject_swigregister(... )>`

#### `Street Database/bin/gdal/python/osgeo/gdal_array.py`
- **Role:** `LIB`
- **Responsibilities:** `analysis/scoring/setups`, `exports/reports (csv/json/md/txt)`, `risk/position sizing/rr/gates`, `filesystem/path I/O`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `Street Database/bin/gdal/python/osgeo/gdalnumeric.py`, `Street Database/bin/gdal/python/osgeo_utils/samples/gdallocationinfo.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: _SwigNonDynamicMeta, VirtualMem, ExceptionMgr • funcs: _swig_repr, _swig_setattr_nondynamic_instance_variable, _swig_setattr_nondynamic_class_variable, _swig_add_metaclass, GetUseExceptions, _GetExceptionsLocal, _SetExceptionsLocal, _UseExceptions, _DontUseExceptions, _UserHasSpecifiedIfUsingExceptions, _has_gdal_array, UseExceptions, DontUseExceptions, TermProgress_nocb, OpenNumPyArray, OpenMultiDimensionalNumPyArray, GetArrayFilename, BandRasterIONumPy, +26 more

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call VirtualMem_swigregister(... )>`; `top-level call: <call AllRegister(... )>`

#### `Street Database/bin/gdal/python/osgeo/gdalconst.py`
- **Role:** `LIB`
- **Responsibilities:** `general`
- **Internal imports:** `[none detected]`
- **Imported by:** `Street Database/bin/gdal/python/osgeo/gdal.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: _SwigNonDynamicMeta • funcs: _swig_repr, _swig_setattr_nondynamic_instance_variable, _swig_setattr_nondynamic_class_variable, _swig_add_metaclass • consts: GRIORA_RMS=<attr GRIORA_RMS>, GRA_RMS=<attr GRA_RMS>, GRA_Q1=<attr GRA_Q1>, GRA_Q3=<attr GRA_Q3>, GPI_RGB=<attr GPI_RGB>, GPI_CMYK=<attr GPI_CMYK>, GPI_HLS=<attr GPI_HLS>, OF_ALL=<attr OF_ALL>, OF_RASTER=<attr OF_RASTER>, OF_VECTOR=<attr OF_VECTOR>, OF_GNM=<attr OF_GNM>, OF_MULTIDIM_RASTER=<attr OF_MULTIDIM_RASTER>, +117 more

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.

#### `Street Database/bin/gdal/python/osgeo/gdalnumeric.py`
- **Role:** `MODULE`
- **Responsibilities:** `risk/position sizing/rr/gates`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo/gdal_array.py`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call warn(... )>`

#### `Street Database/bin/gdal/python/osgeo/gnm.py`
- **Role:** `LIB`
- **Responsibilities:** `risk/position sizing/rr/gates`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: _SwigNonDynamicMeta, ExceptionMgr, Network, GenericNetwork • funcs: _swig_repr, _swig_setattr_nondynamic_instance_variable, _swig_setattr_nondynamic_class_variable, _swig_add_metaclass, GetUseExceptions, _GetExceptionsLocal, _SetExceptionsLocal, _UseExceptions, _DontUseExceptions, _UserHasSpecifiedIfUsingExceptions, _has_gdal_array, UseExceptions, DontUseExceptions, _WarnIfUserHasNotSpecifiedIfUsingExceptions, CastToNetwork, CastToGenericNetwork • consts: GNM_EDGE_DIR_BOTH=<attr GNM_EDGE_DIR_BOTH>, GNM_EDGE_DIR_SRCTOTGT=<attr GNM_EDGE_DIR_SRCTOTGT>, GNM_EDGE_DIR_TGTTOSRC=<attr GNM_EDGE_DIR_TGTTOSRC>

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call Network_swigregister(... )>`; `top-level call: <call GenericNetwork_swigregister(... )>`

#### `Street Database/bin/gdal/python/osgeo/ogr.py`
- **Role:** `LIB`
- **Responsibilities:** `runtime/orchestration/loops`, `broker/execution/orders`, `journaling/audit/logging`, `exports/reports (csv/json/md/txt)`, `config/env/constants`, `risk/position sizing/rr/gates`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: _SwigNonDynamicMeta, ExceptionMgr, MajorObject, StyleTable, ArrowArray, ArrowSchema, ArrowArrayStream, Layer, Feature, FeatureDefn, FieldDefn, GeomFieldDefn, Geometry, PreparedGeometry, GeomTransformer, FieldDomain, GeomCoordinatePrecision • funcs: _swig_repr, _swig_setattr_nondynamic_instance_variable, _swig_setattr_nondynamic_class_variable, _swig_add_metaclass, GetUseExceptions, _GetExceptionsLocal, _SetExceptionsLocal, _UseExceptions, _DontUseExceptions, _UserHasSpecifiedIfUsingExceptions, _has_gdal_array, UseExceptions, DontUseExceptions, _WarnIfUserHasNotSpecifiedIfUsingExceptions, GetGEOSVersionMajor, GetGEOSVersionMinor, GetGEOSVersionMicro, CreateGeometryFromWkb, +47 more • consts: OFSTJSON=<attr OFSTJSON>, OFSTUUID=<attr OFSTUUID>, OFDT_CODED=<attr OFDT_CODED>, OFDT_RANGE=<attr OFDT_RANGE>, OFDT_GLOB=<attr OFDT_GLOB>, OFDSP_DEFAULT_VALUE=<attr OFDSP_DEFAULT_VALUE>, OFDSP_DUPLICATE=<attr OFDSP_DUPLICATE>, OFDSP_GEOMETRY_RATIO=<attr OFDSP_GEOMETRY_RATIO>, OFDMP_DEFAULT_VALUE=<attr OFDMP_DEFAULT_VALUE>, OFDMP_SUM=<attr OFDMP_SUM>, OFDMP_GEOMETRY_WEIGHTED=<attr OFDMP_GEOMETRY_WEIGHTED>, ALTER_NAME_FLAG=<attr ALTER_NAME_FLAG>, +41 more

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call MajorObject_swigregister(... )>`; `top-level call: <call StyleTable_swigregister(... )>`; `top-level call: <call ArrowArray_swigregister(... )>`; `top-level call: <call ArrowSchema_swigregister(... )>`

#### `Street Database/bin/gdal/python/osgeo/osr.py`
- **Role:** `LIB`
- **Responsibilities:** `exports/reports (csv/json/md/txt)`, `risk/position sizing/rr/gates`, `filesystem/path I/O`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: _SwigNonDynamicMeta, ExceptionMgr, AreaOfUse, SpatialReference, CoordinateTransformationOptions, CoordinateTransformation, CRSInfo • funcs: _swig_repr, _swig_setattr_nondynamic_instance_variable, _swig_setattr_nondynamic_class_variable, _swig_add_metaclass, GetUseExceptions, _GetExceptionsLocal, _SetExceptionsLocal, _UseExceptions, _DontUseExceptions, _UserHasSpecifiedIfUsingExceptions, _has_gdal_array, UseExceptions, DontUseExceptions, _WarnIfUserHasNotSpecifiedIfUsingExceptions, GetWellKnownGeogCSAsWKT, GetUserInputAsWKT, OSRAreaOfUse_west_lon_degree_get, OSRAreaOfUse_south_lat_degree_get, +29 more • consts: SRS_WKT_WGS84_LAT_LONG=<attr SRS_WKT_WGS84_LAT_LONG>, SRS_PT_ALBERS_CONIC_EQUAL_AREA=<attr SRS_PT_ALBERS_CONIC_EQUAL_AREA>, SRS_PT_AZIMUTHAL_EQUIDISTANT=<attr SRS_PT_AZIMUTHAL_EQUIDISTANT>, SRS_PT_CASSINI_SOLDNER=<attr SRS_PT_CASSINI_SOLDNER>, SRS_PT_CYLINDRICAL_EQUAL_AREA=<attr SRS_PT_CYLINDRICAL_EQUAL_AREA>, SRS_PT_BONNE=<attr SRS_PT_BONNE>, SRS_PT_ECKERT_I=<attr SRS_PT_ECKERT_I>, SRS_PT_ECKERT_II=<attr SRS_PT_ECKERT_II>, SRS_PT_ECKERT_III=<attr SRS_PT_ECKERT_III>, SRS_PT_ECKERT_IV=<attr SRS_PT_ECKERT_IV>, SRS_PT_ECKERT_V=<attr SRS_PT_ECKERT_V>, SRS_PT_ECKERT_VI=<attr SRS_PT_ECKERT_VI>, +178 more

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call AreaOfUse_swigregister(... )>`; `top-level call: <call SpatialReference_swigregister(... )>`; `top-level call: <call CoordinateTransformationOptions_swigregister(... )>`; `top-level call: <call CoordinateTransformation_swigregister(... )>`

#### `Street Database/bin/gdal/python/osgeo_utils/auxiliary/array_util.py`
- **Role:** `UTILITY`
- **Responsibilities:** `risk/position sizing/rr/gates`
- **Internal imports:** `[none detected]`
- **Imported by:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/numpy_util.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/osr_util.py`, `Street Database/bin/gdal/python/osgeo_utils/samples/gdallocationinfo.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: array_dist

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.

#### `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`
- **Role:** `MODULE`
- **Responsibilities:** `filesystem/path I/O`
- **Internal imports:** `[none detected]`
- **Imported by:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/batch_creator.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/color_palette.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/color_table.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/raster_creation.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal2xyz.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_calc.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_sieve.py`, `Street Database/bin/gdal/python/osgeo_utils/gdalattachpct.py`, `Street Database/bin/gdal/python/osgeo_utils/gdalcompare.py`, `Street Database/bin/gdal/python/osgeo_utils/ogrmerge.py`, `Street Database/bin/gdal/python/osgeo_utils/pct2rgb.py`, `Street Database/bin/gdal/python/osgeo_utils/rgb2pct.py`, `Street Database/bin/gdal/python/osgeo_utils/samples/esri2wkt.py`, `Street Database/bin/gdal/python/osgeo_utils/samples/gdallocationinfo.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: enum_to_str, is_path_like, get_suffix, get_extension, get_byte, path_join, num, num_or_none, is_true • consts: T=<call TypeVar(... )>

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level assign from call: <call TypeVar(... )>`

#### `Street Database/bin/gdal/python/osgeo_utils/auxiliary/batch_creator.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `filesystem/path I/O`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: batch_creator, get_sub_modules, batch_creator_by_modules, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

#### `Street Database/bin/gdal/python/osgeo_utils/auxiliary/color_palette.py`
- **Role:** `MODULE`
- **Responsibilities:** `filesystem/path I/O`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`
- **Imported by:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/color_table.py`, `Street Database/bin/gdal/python/osgeo_utils/pct2rgb.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: ColorPalette • funcs: xml_to_color_file, get_file_from_strings, get_color_palette

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.

#### `Street Database/bin/gdal/python/osgeo_utils/auxiliary/color_table.py`
- **Role:** `MODULE`
- **Responsibilities:** `filesystem/path I/O`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/color_palette.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `Street Database/bin/gdal/python/osgeo_utils/gdal_calc.py`, `Street Database/bin/gdal/python/osgeo_utils/gdalattachpct.py`, `Street Database/bin/gdal/python/osgeo_utils/pct2rgb.py`, `Street Database/bin/gdal/python/osgeo_utils/rgb2pct.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: get_color_table_from_raster, color_table_from_color_palette, get_color_table, is_fixed_color_table, get_fixed_color_table, are_equal_color_table, write_color_table_to_file

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.

#### `Street Database/bin/gdal/python/osgeo_utils/auxiliary/extent_util.py`
- **Role:** `UTILITY`
- **Responsibilities:** `filesystem/path I/O`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/rectangle.py`
- **Imported by:** `Street Database/bin/gdal/python/osgeo_utils/gdal_calc.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: Extent, GT • funcs: parse_extent, gt_diff, calc_geotransform_and_dimensions, make_temp_vrt

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.

#### `Street Database/bin/gdal/python/osgeo_utils/auxiliary/gdal_argparse.py`
- **Role:** `ENTRYPOINT` • `argparse`
- **Responsibilities:** `risk/position sizing/rr/gates`
- **Internal imports:** `[none detected]`
- **Imported by:** `Street Database/bin/gdal/python/osgeo_utils/gdal2xyz.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_calc.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_fillnodata.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_polygonize.py`, `Street Database/bin/gdal/python/osgeo_utils/pct2rgb.py`, `Street Database/bin/gdal/python/osgeo_utils/rgb2pct.py`, `Street Database/bin/gdal/python/osgeo_utils/samples/epsg_tr.py`, `Street Database/bin/gdal/python/osgeo_utils/samples/esri2wkt.py`, `Street Database/bin/gdal/python/osgeo_utils/samples/gdal_minmax_location.py`, `Street Database/bin/gdal/python/osgeo_utils/samples/gdalbuildvrtofvrt.py`, `Street Database/bin/gdal/python/osgeo_utils/samples/gdallocationinfo.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: ExtendAction, GDALArgumentParser, GDALScript

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

#### `Street Database/bin/gdal/python/osgeo_utils/auxiliary/numpy_util.py`
- **Role:** `UTILITY`
- **Responsibilities:** `analysis/scoring/setups`, `exports/reports (csv/json/md/txt)`, `risk/position sizing/rr/gates`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/array_util.py`
- **Imported by:** `Street Database/bin/gdal/python/osgeo_utils/gdal2xyz.py`, `Street Database/bin/gdal/python/osgeo_utils/samples/gdallocationinfo.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: GDALTypeCodeToNumericTypeCodeEx, GDALTypeCodeAndNumericTypeCodeFromDataSet, array_dist

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.

#### `Street Database/bin/gdal/python/osgeo_utils/auxiliary/osr_util.py`
- **Role:** `UTILITY`
- **Responsibilities:** `broker/execution/orders`, `risk/position sizing/rr/gates`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/array_util.py`
- **Imported by:** `Street Database/bin/gdal/python/osgeo_utils/samples/gdallocationinfo.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: get_srs, get_axis_order_from_gis_order, get_gis_order_from_axis_order, set_default_axis_order, get_default_axis_order, get_srs_pj, are_srs_equivalent, get_transform, transform_points • consts: OAMS_AXIS_ORDER=<Name>

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.

#### `Street Database/bin/gdal/python/osgeo_utils/auxiliary/progress.py`
- **Role:** `LIB`
- **Responsibilities:** `general`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo/gdal.py`
- **Imported by:** `Street Database/bin/gdal/python/osgeo_utils/gdal2xyz.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: PredefinedProgressCallback • funcs: simple_term_progress, term_progress_from_to, get_py_term_progress_callback, get_progress_callback

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.

#### `Street Database/bin/gdal/python/osgeo_utils/auxiliary/raster_creation.py`
- **Role:** `MODULE`
- **Responsibilities:** `filesystem/path I/O`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: create_flat_raster, get_creation_options, copy_raster_and_add_overviews

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.

#### `Street Database/bin/gdal/python/osgeo_utils/auxiliary/rectangle.py`
- **Role:** `MODULE`
- **Responsibilities:** `general`
- **Internal imports:** `[none detected]`
- **Imported by:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/extent_util.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_calc.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: GeoRectangle • funcs: get_points_extent

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.

#### `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Role:** `UTILITY`
- **Responsibilities:** `risk/position sizing/rr/gates`, `filesystem/path I/O`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`
- **Imported by:** `Clean_NewWorldScheduler.py`, `Menu.py`, `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo/gdal_array.py`, `Street Database/bin/gdal/python/osgeo/gnm.py`, `Street Database/bin/gdal/python/osgeo/ogr.py`, `Street Database/bin/gdal/python/osgeo/osr.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/color_table.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/raster_creation.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal2tiles.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal2xyz.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_calc.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_edit.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_fillnodata.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_merge.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_pansharpen.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_polygonize.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_proximity.py` (+12 more)
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: OpenDS • funcs: enable_gdal_exceptions, DoesDriverHandleExtension, GetOutputDriversFor, GetOutputDriverFor, open_ds, get_ovr_count, get_pixel_size, get_sizes_factors_resolutions, get_best_ovr_by_resolutions, get_ovr_idx, get_data_type, get_raster_bands, get_band_types, get_band_minimum, get_raster_band, get_raster_minimum, get_raster_min_max, get_nodatavalue, +8 more

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.

#### `Street Database/bin/gdal/python/osgeo_utils/gdal2tiles.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `analysis/scoring/setups`, `journaling/audit/logging`, `exports/reports (csv/json/md/txt)`, `risk/position sizing/rr/gates`, `filesystem/path I/O`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: VSIFile, UnsupportedTileMatrixSet, TileMatrixSet, GlobalMercator, GlobalGeodetic, Zoomify, GDALError, TileDetail, TileJobInfo, Gdal2TilesError, GDAL2Tiles, ProgressBar, DividedCache • funcs: makedirs, isfile, my_open, get_profile_list, exit_with_error, set_cache_max, generate_kml, scale_query_to_tile, setup_no_data_values, setup_input_srs, setup_output_srs, has_georeference, reproject_dataset, add_gdal_warp_options_to_string, update_no_data_values, add_alpha_band_to_string_vrt, update_alpha_value_for_non_alpha_inputs, nb_data_bands, +15 more • consts: MAXZOOMLEVEL=32

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems
  - Side effects: `top-level assign from call: <call getLogger(... )>`; `top-level assign from call: <call local(... )>`

#### `Street Database/bin/gdal/python/osgeo_utils/gdal2xyz.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/gdal_argparse.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/numpy_util.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/progress.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/gdal2xyz.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: GDAL2XYZ • funcs: gdal2xyz, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

#### `Street Database/bin/gdal/python/osgeo_utils/gdal_calc.py`
- **Role:** `ENTRYPOINT` • `has __main__` • `argparse`
- **Responsibilities:** `runtime/orchestration/loops`, `filesystem/path I/O`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/color_table.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/extent_util.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/gdal_argparse.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/rectangle.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/gdal_calc.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: GDALCalc • funcs: Calc, doit, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems
  - Side effects: `top-level assign from call: <call list(... )>`; `top-level assign from call: <call tuple(... )>`

#### `Street Database/bin/gdal/python/osgeo_utils/gdal_edit.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/gdal_edit.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, ArgIsNumeric, gdal_edit, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

#### `Street Database/bin/gdal/python/osgeo_utils/gdal_fillnodata.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/gdal_argparse.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/gdal_fillnodata.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: GDALFillNoData • funcs: CopyBand, gdal_fillnodata, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

#### `Street Database/bin/gdal/python/osgeo_utils/gdal_merge.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `time/session/scheduling`, `filesystem/path I/O`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/gdal_merge.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: file_info • funcs: raster_copy, raster_copy_with_nodata, raster_copy_with_mask, names_to_fileinfos, Usage, gdal_merge, _gdal_merge, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

#### `Street Database/bin/gdal/python/osgeo_utils/gdal_pansharpen.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `filesystem/path I/O`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/gdal_pansharpen.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, main, gdal_pansharpen, parse_spectral_names

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

#### `Street Database/bin/gdal/python/osgeo_utils/gdal_polygonize.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/gdal_argparse.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/gdal_polygonize.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: GDALPolygonize • funcs: gdal_polygonize, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

#### `Street Database/bin/gdal/python/osgeo_utils/gdal_proximity.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/gdal_proximity.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, main, gdal_proximity

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

#### `Street Database/bin/gdal/python/osgeo_utils/gdal_retile.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `exports/reports (csv/json/md/txt)`, `filesystem/path I/O`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/gdal_retile.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: AffineTransformDecorator, DataSetCache, tile_info, mosaic_info, RetileGlobals • funcs: getTileIndexFromFiles, getTargetDir, tileImage, copyTileIndexToDisk, copyTileIndexToCSV, _createTempFileName, _renameDataset, createPyramidTile, createTile, createTileIndex, addFeature, closeTileIndex, buildPyramid, buildPyramidLevel, getTileName, UsageFormat, Usage, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

#### `Street Database/bin/gdal/python/osgeo_utils/gdal_sieve.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/gdal_sieve.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, main, gdal_sieve

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

#### `Street Database/bin/gdal/python/osgeo_utils/gdalattachpct.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/color_table.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/gdalattachpct.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, main, doit

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

#### `Street Database/bin/gdal/python/osgeo_utils/gdalcompare.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `risk/position sizing/rr/gates`, `filesystem/path I/O`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/gdalcompare.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: compare_metadata, compare_image_pixels, compare_band, compare_srs, compare_db, compare_sds, find_diff, Usage, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

#### `Street Database/bin/gdal/python/osgeo_utils/gdalmove.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/gdalmove.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: fmt_loc, move, Usage, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

#### `Street Database/bin/gdal/python/osgeo_utils/ogr_layer_algebra.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/ogr_layer_algebra.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, EQUAL, CreateLayer, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

#### `Street Database/bin/gdal/python/osgeo_utils/ogrmerge.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `exports/reports (csv/json/md/txt)`, `config/env/constants`, `risk/position sizing/rr/gates`, `filesystem/path I/O`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/ogrmerge.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: XMLWriter • funcs: Usage, _VSIFPrintfL, EQUAL, _GetGeomType, _Esc, process, _build_layer_name_non_single_mode, _quote_literal, _quote_id, _gpkg_get_src_table_size, _gpkg_has_spatial_index, _gpkg_get_estimated_final_size, _gpkg_get_srs_id, _gpkg_ogrmerge, ogrmerge, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

#### `Street Database/bin/gdal/python/osgeo_utils/pct2rgb.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/color_palette.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/color_table.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/gdal_argparse.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/pct2rgb.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: PCT2RGB • funcs: pct2rgb, doit, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

#### `Street Database/bin/gdal/python/osgeo_utils/rgb2pct.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `filesystem/path I/O`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/color_table.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/gdal_argparse.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/rgb2pct.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: RGB2PCT • funcs: rgb2pct, doit, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

#### `Street Database/bin/gdal/python/osgeo_utils/samples/epsg_tr.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/gdal_argparse.py`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: EPSG_Table • funcs: Usage, trHandleCode, epsg_tr, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

#### `Street Database/bin/gdal/python/osgeo_utils/samples/esri2wkt.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/gdal_argparse.py`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: ESRI2WKT • funcs: Usage, esri2wkt, esri2wkt_multi, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

#### `Street Database/bin/gdal/python/osgeo_utils/samples/gdal_minmax_location.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/gdal_argparse.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: GDALMinMaxLocation • funcs: gdalminmaxlocation_util, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

#### `Street Database/bin/gdal/python/osgeo_utils/samples/gdalbuildvrtofvrt.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/gdal_argparse.py`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: GDALBuildVRTOfVRT • funcs: main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems
  - Side effects: `top-level call: <call UseExceptions(... )>`

#### `Street Database/bin/gdal/python/osgeo_utils/samples/gdallocationinfo.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `risk/position sizing/rr/gates`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/array_util.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/base.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/gdal_argparse.py`, `Street Database/bin/gdal/python/osgeo/gdal_array.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/numpy_util.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/osr_util.py`, `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: LocationInfoSRS, LocationInfoOutput, GDALLocationInfo • funcs: gdallocationinfo, gdallocationinfo_util, val_at_coord, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

#### `Street Database/bin/gdal/python/osgeo_utils/samples/tile_extent_from_raster.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo_utils/auxiliary/util.py`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

#### `Street Database/bin/gdal/python/scripts/gdal2xyz.py`
- **Role:** `MODULE`
- **Responsibilities:** `general`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal2xyz.py`, `Street Database/bin/gdal/python/scripts/gdal2xyz.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/gdal2xyz.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call deprecation_warn(... )>`; `top-level call: <call exit(... )>`

#### `Street Database/bin/gdal/python/scripts/gdal_calc.py`
- **Role:** `MODULE`
- **Responsibilities:** `general`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_calc.py`, `Street Database/bin/gdal/python/scripts/gdal_calc.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/gdal_calc.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call deprecation_warn(... )>`; `top-level call: <call exit(... )>`

#### `Street Database/bin/gdal/python/scripts/gdal_edit.py`
- **Role:** `MODULE`
- **Responsibilities:** `general`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_edit.py`, `Street Database/bin/gdal/python/scripts/gdal_edit.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/gdal_edit.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call deprecation_warn(... )>`; `top-level call: <call exit(... )>`

#### `Street Database/bin/gdal/python/scripts/gdal_fillnodata.py`
- **Role:** `DATA`
- **Responsibilities:** `general`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_fillnodata.py`, `Street Database/bin/gdal/python/scripts/gdal_fillnodata.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/gdal_fillnodata.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call deprecation_warn(... )>`; `top-level call: <call exit(... )>`

#### `Street Database/bin/gdal/python/scripts/gdal_merge.py`
- **Role:** `MODULE`
- **Responsibilities:** `general`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_merge.py`, `Street Database/bin/gdal/python/scripts/gdal_merge.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/gdal_merge.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call deprecation_warn(... )>`; `top-level call: <call exit(... )>`

#### `Street Database/bin/gdal/python/scripts/gdal_pansharpen.py`
- **Role:** `MODULE`
- **Responsibilities:** `general`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_pansharpen.py`, `Street Database/bin/gdal/python/scripts/gdal_pansharpen.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/gdal_pansharpen.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call deprecation_warn(... )>`; `top-level call: <call exit(... )>`

#### `Street Database/bin/gdal/python/scripts/gdal_polygonize.py`
- **Role:** `MODULE`
- **Responsibilities:** `general`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_polygonize.py`, `Street Database/bin/gdal/python/scripts/gdal_polygonize.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/gdal_polygonize.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call deprecation_warn(... )>`; `top-level call: <call exit(... )>`

#### `Street Database/bin/gdal/python/scripts/gdal_proximity.py`
- **Role:** `MODULE`
- **Responsibilities:** `general`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_proximity.py`, `Street Database/bin/gdal/python/scripts/gdal_proximity.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/gdal_proximity.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call deprecation_warn(... )>`; `top-level call: <call exit(... )>`

#### `Street Database/bin/gdal/python/scripts/gdal_retile.py`
- **Role:** `MODULE`
- **Responsibilities:** `general`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_retile.py`, `Street Database/bin/gdal/python/scripts/gdal_retile.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/gdal_retile.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call deprecation_warn(... )>`; `top-level call: <call exit(... )>`

#### `Street Database/bin/gdal/python/scripts/gdal_sieve.py`
- **Role:** `MODULE`
- **Responsibilities:** `general`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/gdal_sieve.py`, `Street Database/bin/gdal/python/scripts/gdal_sieve.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/gdal_sieve.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call deprecation_warn(... )>`; `top-level call: <call exit(... )>`

#### `Street Database/bin/gdal/python/scripts/gdalattachpct.py`
- **Role:** `MODULE`
- **Responsibilities:** `general`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/gdalattachpct.py`, `Street Database/bin/gdal/python/scripts/gdalattachpct.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/gdalattachpct.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call deprecation_warn(... )>`; `top-level call: <call exit(... )>`

#### `Street Database/bin/gdal/python/scripts/gdalcompare.py`
- **Role:** `MODULE`
- **Responsibilities:** `general`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/gdalcompare.py`, `Street Database/bin/gdal/python/scripts/gdalcompare.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/gdalcompare.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call deprecation_warn(... )>`; `top-level call: <call exit(... )>`

#### `Street Database/bin/gdal/python/scripts/gdalmove.py`
- **Role:** `MODULE`
- **Responsibilities:** `general`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/gdalmove.py`, `Street Database/bin/gdal/python/scripts/gdalmove.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/gdalmove.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call deprecation_warn(... )>`; `top-level call: <call exit(... )>`

#### `Street Database/bin/gdal/python/scripts/ogr_layer_algebra.py`
- **Role:** `MODULE`
- **Responsibilities:** `general`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/ogr_layer_algebra.py`, `Street Database/bin/gdal/python/scripts/ogr_layer_algebra.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/ogr_layer_algebra.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call deprecation_warn(... )>`; `top-level call: <call exit(... )>`

#### `Street Database/bin/gdal/python/scripts/ogrmerge.py`
- **Role:** `MODULE`
- **Responsibilities:** `general`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/ogrmerge.py`, `Street Database/bin/gdal/python/scripts/ogrmerge.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/ogrmerge.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call deprecation_warn(... )>`; `top-level call: <call exit(... )>`

#### `Street Database/bin/gdal/python/scripts/pct2rgb.py`
- **Role:** `MODULE`
- **Responsibilities:** `general`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/pct2rgb.py`, `Street Database/bin/gdal/python/scripts/pct2rgb.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/pct2rgb.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call deprecation_warn(... )>`; `top-level call: <call exit(... )>`

#### `Street Database/bin/gdal/python/scripts/rgb2pct.py`
- **Role:** `MODULE`
- **Responsibilities:** `general`
- **Internal imports:** `Street Database/bin/gdal/python/osgeo/gdal.py`, `Street Database/bin/gdal/python/osgeo_utils/rgb2pct.py`, `Street Database/bin/gdal/python/scripts/rgb2pct.py`
- **Imported by:** `Street Database/bin/gdal/python/scripts/rgb2pct.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call deprecation_warn(... )>`; `top-level call: <call exit(... )>`

## Group 2 (size=10)

### Start Here

- `GoogleSheets_Menu.py`

### Critical paths (heuristic)

- `GoogleSheets_Menu.py` → `GoogleSheets_Flows.py` → `GoogleSheets_Log.py`
- `GoogleSheets_Menu.py` → `GoogleSheets_Flows.py` → `GoogleSheets_CoreLite.py`
- `GoogleSheets_Menu.py` → `GoogleSheets_Flows.py` → `GoogleSheets_Utils.py`
- `GoogleSheets_Menu.py` → `GoogleSheets_Flows.py`
- `GoogleSheets_Menu.py` → `GoogleSheets_Flows.py` → `GoogleSheets_Master.py`
- `GoogleSheets_Menu.py`

### Subsystems

- **BAT / Launchers** (1)
- **Journal / Audit** (8)
- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- **BAT / Launchers** → **Runtime / Entrypoints** (edges≈1)
- **Runtime / Entrypoints** → **Journal / Audit** (edges≈1)

### File-level dependency map (collapsed)

- `GoogleSheets_CoreLite.py` → { `GoogleSheets_Log.py` }
- `GoogleSheets_CoreLite_Geocode.py` → { `GoogleSheets_Log.py` }
- `GoogleSheets_CoreLite_Polygons.py` → { `GoogleSheets_Log.py` }
- `GoogleSheets_Flows.py` → { `GoogleSheets_CoreLite.py`, `GoogleSheets_Log.py`, `GoogleSheets_Master.py`, `GoogleSheets_Utils.py`, `GoogleSheets_Verify.py` }
- `GoogleSheets_Master.py` → { `GoogleSheets_Log.py` }
- `GoogleSheets_Menu.py` → { `GoogleSheets_Flows.py` }
- `GoogleSheets_Utils.py` → { `GoogleSheets_CoreLite.py`, `GoogleSheets_Log.py` }
- `GoogleSheets_Verify.py` → { `GoogleSheets_Log.py`, `GoogleSheets_Utils.py` }
- `Run_GoogleSheets.bat` → { `GoogleSheets_Menu.py` }

### Modules

#### `GoogleSheets_CoreLite.py`
- **Role:** `MODULE`
- **Responsibilities:** `journaling/audit/logging`, `exports/reports (csv/json/md/txt)`, `risk/position sizing/rr/gates`, `filesystem/path I/O`
- **Internal imports:** `GoogleSheets_Log.py`
- **Imported by:** `GoogleSheets_Flows.py`, `GoogleSheets_Utils.py`
- **IO label:** `boundary`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `requests (HTTP)`

**Why it exists (docstring/intent):**

```text
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
          core.<...
```
- **Inside:** funcs: listen_for_quit_key, run_with_cancel, _log_quiet, _log_header_has_street, log_correction, start_quit_key_listener_once, flip_unit_prefix_in_number, normalize_number_unit_first, normalize_units_for_rows_unit_first, flip_units_for_rows_house_first, fmt_addr_parts • consts: RESULT_ONLY_LOGS=True, GEOCODE_DEBUG=False, _UNIT_PREFIX_RE_CORE=<call compile(... )>, _HOUSE_FIRST_RE_CORE=<call compile(... )>, NEARBY_SUBURBS=<call getattr(... )>, NEARBY_ALIAS=<call getattr(... )>, ADDRESS_PARSE_RX=<call getattr(... )>, UNIT_RX=<call getattr(... )>, _UNIT_PREFIX_RE=<call getattr(... )>, PHOTON_URL=<call getattr(... )>, NOMINATIM_URL=<call getattr(... )>, GEOCODEXYZ_URL=<call getattr(... )>, +2 more

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ boundary module (network/MT5)
  - Side effects: `top-level call: <call module_loaded(... )>`; `top-level assign from call: <call Lock(... )>`; `top-level assign from call: <call Lock(... )>`; `top-level assign from call: <call Event(... )>`

#### `GoogleSheets_CoreLite_Geocode.py`
- **Role:** `MODULE`
- **Responsibilities:** `journaling/audit/logging`, `exports/reports (csv/json/md/txt)`, `risk/position sizing/rr/gates`, `time/session/scheduling`, `filesystem/path I/O`
- **Internal imports:** `GoogleSheets_Log.py`
- **Imported by:** `[none detected]`
- **IO label:** `boundary`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `requests (HTTP)`

**Why it exists (docstring/intent):**

```text
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
- haversine_...
```
- **Inside:** funcs: log_correction, flip_unit_prefix_in_number, _log_quiet, _set_geocode_reason, get_last_geocode_reason, is_in_auckland, is_auckland_result, _to_parts, correct_suffix_typos, fmt_addr_parts, fmt_addr_str, to_external_query, unit_word_variant, normalize_number, flip_unit_prefix_in_number_house_first, flip_unit_prefix_in_number_unit_first, merge_number_with_street, haversine_distance, +10 more • consts: GEOCODE_DEBUG=False, RESULT_ONLY_LOGS=True, LAST_GEOCODE_REASON=<dict len≈0>, _LAST_REASON_LOCK=<call Lock(... )>, MAX_ALLOWED_DISTANCE=2000, ADDRESS_PARSE_RX=<call compile(... )>, UNIT_RX=<call compile(... )>, _UNIT_PREFIX_RE=<call compile(... )>, _RANGE_RX=<call compile(... )>, _SIMPLE_RX=<call compile(... )>, _SLASH_RX=<call compile(... )>, LINZ_DB=<call get(... )>, +3 more

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ boundary module (network/MT5)
  - Side effects: `top-level call: <call module_loaded(... )>`; `top-level assign from call: <call getattr(... )>`; `top-level ann-assign from call: <call defaultdict(... )>`; `top-level assign from call: <call Lock(... )>`

#### `GoogleSheets_CoreLite_Polygons.py`
- **Role:** `MODULE`
- **Responsibilities:** `journaling/audit/logging`, `filesystem/path I/O`
- **Internal imports:** `GoogleSheets_Log.py`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Why it exists (docstring/intent):**

```text
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
----------------------...
```
- **Inside:** funcs: _safe_float, _digits_int, canon_suburb, _point_on_segment, _point_in_poly, _dist_point_to_segment, _min_dist_to_polygon, _iter_kml_paths, _find_polygon_dirs, _read_kml_text, _load_kml_polygons, _assign_point_to_polygons, _pick_nearest_number_target, split_cleaned_by_polygon_and_include_failed, split_cleaned_by_suburb_and_include_failed • consts: NEARBY_ALIAS=<dict len≈6>, NEARBY_SUBURBS=<dict len≈3>, POLYGON_DIR_CANDIDATES=<list len≈4>

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call module_loaded(... )>`

#### `GoogleSheets_Flows.py`
- **Role:** `MODULE`
- **Responsibilities:** `journaling/audit/logging`, `exports/reports (csv/json/md/txt)`, `risk/position sizing/rr/gates`, `time/session/scheduling`, `filesystem/path I/O`, `tests/harness/verification`
- **Internal imports:** `GoogleSheets_CoreLite.py`, `GoogleSheets_Log.py`, `GoogleSheets_Master.py`, `GoogleSheets_Utils.py`, `GoogleSheets_Verify.py`
- **Imported by:** `GoogleSheets_Menu.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Why it exists (docstring/intent):**

```text
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
All flow function...
```
- **Inside:** funcs: verify_split_matches_clean, _numbers_match, _merge_csvs, _clean_notes_and_language, _clear_files_only, _clear_dir_contents, _notes_has_new_street_ci, _notes_has_new_street, _stemmed_outputs_for, _split_input_by_new_street, _invoke_core_option7_new_streets, _run_split_to_dir, _merge_suburb_dirs, _warn_if_temp_dirs_have_files, _delete_if_exists, cleanup_routed_intermediate_csvs, _delete_temp_suburb_dirs, _cleanup_temp_dirs_after_verify, +21 more • consts: SLASH_DIGITS_RX=<call compile(... )>, _SUBURB_BASE=<call Path(... )>

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call module_loaded(... )>`; `top-level assign from call: <call compile(... )>`; `top-level assign from call: <call Path(... )>`

#### `GoogleSheets_Log.py`
- **Role:** `JOURNAL`
- **Responsibilities:** `journaling/audit/logging`, `risk/position sizing/rr/gates`, `time/session/scheduling`, `filesystem/path I/O`
- **Internal imports:** `[none detected]`
- **Imported by:** `GoogleSheets_CoreLite.py`, `GoogleSheets_CoreLite_Geocode.py`, `GoogleSheets_CoreLite_Polygons.py`, `GoogleSheets_Flows.py`, `GoogleSheets_Master.py`, `GoogleSheets_Utils.py`, `GoogleSheets_Verify.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Why it exists (docstring/intent):**

```text
GoogleSheets_Log.py

Single-file logger for the GoogleSheets suite.

Goals
- One shared log text file for ALL modules.
- Log function calls/returns/exceptions with module + function identity.
- Easy "decision" breadcrumbs.
- Optional auto-wrap: wrap all functions in a module automatically.

No imports from your other modules (avoids circular imports).
Stdlib only.
```
- **Inside:** funcs: _noisy_signature, _should_echo_event_to_console, log_correction, _log_quiet, _get_depth, _inc_depth, _dec_depth, _now, _safe_repr, _clip, init_logger, console, consolef, get_log_path, module_loaded, install_excepthook, _write_line, _copy_wrapper_passthrough_attrs, +18 more • consts: _NOISY_EVENTS=<set len≈3>, _NOISY_TTL_SECONDS=30.0, _NOISY_MAX_KEYS=50000, _NOISY_SEEN=<dict len≈0>, _NOISY_LOCK=<call Lock(... )>, DEFAULT_LOG_DIRNAME='Log', DEFAULT_LOG_FILENAME='GoogleSheets_All.txt', MAX_REPR=600, MAX_TRACE=12000, MAX_LINE=4000, _LOCK=<call Lock(... )>, _RUN_ID=None, +4 more

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects audit truth / replay. Also scan reason-code registry + decision finalizer.
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level assign from call: <call Lock(... )>`; `top-level assign from call: <call Lock(... )>`; `top-level assign from call: <call local(... )>`; `top-level assign from call: <call Lock(... )>`

#### `GoogleSheets_Master.py`
- **Role:** `MODULE`
- **Responsibilities:** `journaling/audit/logging`, `exports/reports (csv/json/md/txt)`, `risk/position sizing/rr/gates`, `filesystem/path I/O`, `tests/harness/verification`
- **Internal imports:** `GoogleSheets_Log.py`
- **Imported by:** `GoogleSheets_Flows.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Why it exists (docstring/intent):**

```text
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
    • _repair_corrup...
```
- **Inside:** funcs: resolve_master_paths, _read_csv_header_best_effort, _canon_header_cols, _looks_like_master_csv, _pick_newest_csv, resolve_master_csv_path, _canon_street_suburb, _canon_triplet, _ensure_sqlite_from_csv, _load_master_index, _duplicate_status_against_master, _debug_probe_against_master, run_master_db_duplicate_audit, _open_csv_text_best_effort, run_final_master_duplicate_filter, run_verify_fail_against_master, _init_street_whitelist_from_master, _repair_corrupted_street • consts: DEFAULT_MASTER_CSV_NAME='Auckland East Mandarin Territory Addresses.csv', DEFAULT_MASTER_DB_NAME='Auckland_East_Mandarin_Addresses.db', MASTER_DIR=<BinOp>, MASTER_CSV_DIR=<Name>, MASTER_CSV_PATH=None, MASTER_DB_PATH=None, _MASTER_STSUB_TO_HOUSES=<dict len≈0>, _MASTER_HOUSEONLY_TO_ADDRS=<dict len≈0>, _MASTER_STREET_SUBURB_SET=<call set(... )>, _MASTER_TRIPLET_SET=<call set(... )>, _STREET_WHITELIST=<call set(... )>, _STREET_WHITELIST_INIT_ATTEMPTED=False, +2 more

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call module_loaded(... )>`; `top-level ann-assign from call: <call set(... )>`; `top-level ann-assign from call: <call set(... )>`; `top-level assign from call: <call set(... )>`

#### `GoogleSheets_Menu.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `exports/reports (csv/json/md/txt)`, `config/env/constants`, `time/session/scheduling`, `filesystem/path I/O`
- **Internal imports:** `GoogleSheets_Flows.py`
- **Imported by:** `[none detected]`
- **IO label:** `boundary`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `requests (HTTP)`

**Why it exists (docstring/intent):**

```text
GoogleSheets_Menu.py

Purpose
-------
Google Sheets submenu entrypoint (portable), extracted from Clean_GoogleSheets.py.

This module contains ONLY:
  - Menu rendering + input loop
  - Option wrappers:
      _run_option1_clean_only   (Full geocode check, no split)   [was old option 2]
      _run_option2_routed       (Full geocode check, split)      [was old option 4]
      _run_option3_routed       (Master DB duplicate audit)      [was old option 5]

Design rules (per your split plan)
-------...
```
- **Inside:** classes: _StageProgress • funcs: progress_stage, _start_heartbeat, _dump_stacks_after, _app_root, _ensure_dependencies_installed, _portable_bootstrap_here, _ensure_quit_listener_started_once, _core_cancel_flag, _print_run_banner, _run_option2_routed, _run_option3_routed, _run_option1_clean_only, render_menu, open_menu • consts: REQUIRED_PACKAGES=<list len≈9>, APP_ROOT=<call _app_root(... )>, _QUIT_LISTENER_STARTED=False, _QUIT_LISTENER_LOCK=<call Lock(... )>

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems; ⚠️ boundary module (network/MT5)
  - Side effects: `top-level assign from call: <call _app_root(... )>`; `top-level call: <call _portable_bootstrap_here(... )>`; `top-level assign from call: <call Lock(... )>`

#### `GoogleSheets_Utils.py`
- **Role:** `UTILITY`
- **Responsibilities:** `runtime/orchestration/loops`, `journaling/audit/logging`, `exports/reports (csv/json/md/txt)`, `risk/position sizing/rr/gates`, `filesystem/path I/O`
- **Internal imports:** `GoogleSheets_CoreLite.py`, `GoogleSheets_Log.py`
- **Imported by:** `GoogleSheets_Flows.py`, `GoogleSheets_Verify.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Why it exists (docstring/intent):**

```text
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
- Does NOT import Flows...
```
- **Inside:** funcs: _normalize_polygon_suburb_name, _app_root, _portable_bootstrap_here, _canon_street_suburb, _strip_macrons, _canon_text_cached, _canon_text, _looks_like_just_suburb, _tokens_core, _has_digits, _coords_in_auckland, _merge_notes, _strip_trailing_postcode, _strip_common_suffix_word, normalize_number, _numbers_match, _clean_notes_and_language, _append_other_notes, +38 more • consts: POLY_OFFICIALSHP_TAIL_RX=<call compile(... )>, POLY_POLYGON_TAIL_RX=<call compile(... )>, POLY_OFFICIALSHP_ONLY_RX=<call compile(... )>, _POLYGON_SUBURB_FIXES=<dict len≈1>, APP_ROOT=<call _app_root(... )>, _COMMON_SUFFIX=<set len≈46>, TOKEN_RX=<call compile(... )>, COORD_RX=<call compile(... )>, TRAILING_NZ_POSTCODE_RX=<call compile(... )>, SEP_SQUASH_RX_1=<call compile(... )>, SEP_SQUASH_RX_2=<call compile(... )>, SEP_SQUASH_RX_3=<call compile(... )>, +12 more

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call module_loaded(... )>`; `top-level assign from call: <call compile(... )>`; `top-level assign from call: <call compile(... )>`; `top-level assign from call: <call compile(... )>`

#### `GoogleSheets_Verify.py`
- **Role:** `MODULE`
- **Responsibilities:** `journaling/audit/logging`, `exports/reports (csv/json/md/txt)`, `filesystem/path I/O`, `tests/harness/verification`
- **Internal imports:** `GoogleSheets_Log.py`, `GoogleSheets_Utils.py`
- **Imported by:** `GoogleSheets_Flows.py`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Why it exists (docstring/intent):**

```text
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
- Does NOT import Flo...
```
- **Inside:** funcs: _addr_key, _dup_key_from_cleaned, _read_clean_keys, _read_suburb_keys_and_counts, verify_split_matches_clean • consts: _SUPPRESS_TEMP_DIR_WARNINGS=True, _SUBURB_DIR_NEW=<call Path(... )>, _SUBURB_DIR_OTHER=<call Path(... )>

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call module_loaded(... )>`; `top-level ann-assign from call: <call Path(... )>`; `top-level ann-assign from call: <call Path(... )>`

### `Run_GoogleSheets.bat`
- **Role:** `BAT`
- **Responsibilities:** `runs python scripts`, `sets env/runtime flags`
- **Env vars:** `"APP_ROOT=%~dp0"`, `"SCRIPT=%APP_ROOT%GoogleSheets_Menu.py"`, `"RC=%ERRORLEVEL%"`, `"RC=%ERRORLEVEL%"`, `"RC=%ERRORLEVEL%"`, `"RC=9009"`, `"RC=1"`
- **Python calls:** `"%APP_ROOT%python\python.exe" -u "%SCRIPT%" %*`, `where python >nul 2>nul`, `python -u "%SCRIPT%" %*`, `echo ❌ No Python found.` (+2 more)
- **References:** `GoogleSheets_Menu.py`

## Group 3 (size=2)

### Start Here

- `FileSummaries.py`

### Critical paths (heuristic)

- `FileSummaries.py`

### Subsystems

- **BAT / Launchers** (1)
- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- **BAT / Launchers** → **Runtime / Entrypoints** (edges≈1)

### File-level dependency map (collapsed)

- `RunFileSummaries.bat` → { `FileSummaries.py` }

### Modules

#### `FileSummaries.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `broker/execution/orders`, `journaling/audit/logging`, `exports/reports (csv/json/md/txt)`, `risk/position sizing/rr/gates`, `time/session/scheduling`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `boundary`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `async network (asyncio)`, `MetaTrader5/MT5`, `requests (HTTP)`, `socket (TCP/UDP)`, `urllib (HTTP)`, `websocket`
- **Inside:** funcs: replace_file, is_binary_file, safe_read_text, mirror_folder, _truncate, _rel, _mql5_candidates_in_dir, parse_mql5_file, md_module_summary_mql5, _size_mb, _md_escape, _module_candidates_in_repo, _is_all_caps, _ast_name, _ast_preview, _detect_argparse, _detect_main_guard, _detect_top_level_sidefx, +46 more • consts: SCRIPT_DIR=<attr parent>, ROOT_FOLDER=<Name>, RECURSIVE=True, OUTPUT_DIR=<BinOp>, SUMMARY_MD=<BinOp>, MQL5_SCAN_DIR=<call Path(... )>, MQL5_EXTS=<set len≈3>, MQL5_SRC_DIR=<call Path(... )>, ONEDRIVE_DST_DIR=<call Path(... )>, MQL5_SCAN_DIR=<Name>, INCLUDE_FULL_CONTENT_DUMP=False, DUMP_MD=<BinOp>, +28 more

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems; ⚠️ boundary module (network/MT5)
  - Side effects: `top-level call: <call mkdir(... )>`; `top-level assign from call: <call Path(... )>`; `top-level assign from call: <call Path(... )>`; `top-level assign from call: <call Path(... )>`

### `RunFileSummaries.bat`
- **Role:** `BAT`
- **Responsibilities:** `runs python scripts`, `sets env/runtime flags`
- **Env vars:** `"ROOT=%~dp0"`
- **Python calls:** `python "%ROOT%FileSummaries.py"`
- **References:** `FileSummaries.py`

## Group 4 (size=1)

### Start Here

- [no entrypoints]

### Critical paths (heuristic)

- [no entrypoints → cannot compute critical paths]

### Subsystems

- **Journal / Audit** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Clean_GoogleSheets.py`
- **Role:** `MODULE`
- **Responsibilities:** `journaling/audit/logging`, `exports/reports (csv/json/md/txt)`, `risk/position sizing/rr/gates`, `time/session/scheduling`, `filesystem/path I/O`, `tests/harness/verification`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: _canon_street_suburb, _strip_macrons, _canon_text_cached, _looks_like_just_suburb, _notes_has_new_street_ci, _stemmed_outputs_for, _split_input_by_new_street, _flip_units_inplace, _tokens_core, _has_digits, _coords_in_auckland, _init_street_whitelist_from_master, _repair_corrupted_street, _merge_notes, _notes_has_new_street, _invoke_core_option7_new_streets, _run_split_to_dir, _merge_suburb_dirs, +61 more • consts: _MASTER_STSUB_TO_HOUSES=<dict len≈0>, HOUSE_ONLY_HEAD_RX=<call compile(... )>, SLASH_DIGITS_RX=<call compile(... )>, _MASTER_HOUSEONLY_TO_ADDRS=<dict len≈0>, _MASTER_STREET_SUBURB_SET=<call set(... )>, _MASTER_TRIPLET_SET=<call set(... )>, _COMMON_SUFFIX=<set len≈46>, TOKEN_RX=<call compile(... )>, COORD_RX=<call compile(... )>, TRAILING_NZ_POSTCODE_RX=<call compile(... )>, SEP_SQUASH_RX_1=<call compile(... )>, SEP_SQUASH_RX_2=<call compile(... )>, +24 more

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level assign from call: <call compile(... )>`; `top-level assign from call: <call compile(... )>`; `top-level ann-assign from call: <call set(... )>`; `top-level ann-assign from call: <call set(... )>`

## Group 5 (size=1)

### Start Here

- [no entrypoints]

### Critical paths (heuristic)

- [no entrypoints → cannot compute critical paths]

### Subsystems

- **Core / Other** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Exported Files/Clean_NewWorldScheduler - Part 1.py`
- **Role:** `MODULE` • **Status:** `FAILED`
  - Error: `AST parse failed: expected an indented block after 'try' statement on line 2409 (Clean_NewWorldScheduler - Part 1.py, line 2410)`

## Group 6 (size=1)

### Start Here

- [no entrypoints]

### Critical paths (heuristic)

- [no entrypoints → cannot compute critical paths]

### Subsystems

- **Core / Other** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Exported Files/Clean_NewWorldScheduler - Part 2.py`
- **Role:** `MODULE` • **Status:** `FAILED`
  - Error: `AST parse failed: unexpected indent (Clean_NewWorldScheduler - Part 2.py, line 2)`

## Group 7 (size=1)

### Start Here

- [no entrypoints]

### Critical paths (heuristic)

- [no entrypoints → cannot compute critical paths]

### Subsystems

- **Broker / Execution** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Exported Files/Clean_NewWorldScheduler - Part 3.py`
- **Role:** `LIB`
- **Responsibilities:** `broker/execution/orders`, `journaling/audit/logging`, `exports/reports (csv/json/md/txt)`, `risk/position sizing/rr/gates`, `time/session/scheduling`, `filesystem/path I/O`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `boundary`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `requests (HTTP)`
- **Inside:** classes: AsyncRateLimiter • funcs: split_corrections_log, export_bundle_after_parts, _addr_key_for_compare, write_missing_addresses_report, split_output_clean_if_large, _norm, delete_cache_by_street, run_clean_verify_and_split_newstreets_after_purge, run_clean_live_after_purge, run_clean_verify_live_after_purge, run_clean_and_split_after_purge_verify, _split_base_suffix, build_canon_suffix_map_from_outputs, _unify_crossfiles_postgeocode, _choose_from_all_rows, _choose_from_linz, _choose_from_external, ensure_suffix_via_sources, +45 more • consts: CANON_SUFFIX_BY_BASE=<dict len≈0>, PHOTON_URL='https://photon.komoot.io/api/', NOMINATIM_URL='https://nominatim.openstreetmap.org/search', GEOCODEXYZ_URL='https://geocode.xyz', CACHE_STREETS='auckland_streets.json', PROTECTED_STREETS=<set len≈2>, PROTECTED_FULL_STREETS=<set len≈6>, PROTECTED_BASES=<set len≈4>, DO_NOT_ALIAS_BASES=<set len≈2>, DEBUG_LOG='debug_log.txt', MANUAL_FINAL_STATUS_OVERRIDES=<dict len≈1>, _UNIT_PREFIX_RE=<call compile(... )>

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely touches output contracts (CSV/MD). Also scan ExportUtils + any *Export* modules that write the same CSV.
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ boundary module (network/MT5)
  - Side effects: `top-level assign from call: <call Lock(... )>`; `top-level assign from call: <call sorted(... )>`; `top-level assign from call: <call compile(... )>`

## Group 8 (size=1)

### Start Here

- `Exported Files/Clean_NewWorldScheduler - Part 4.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Exported Files/Clean_NewWorldScheduler - Part 4.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `exports/reports (csv/json/md/txt)`, `risk/position sizing/rr/gates`, `time/session/scheduling`, `filesystem/path I/O`, `tests/harness/verification`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: oth • funcs: resolve_bad_address, _in_akl_bbox, _maybe_swap_latlon, prune_auckland_coords_inplace, _retry_geocode, try_geocoders_with_variants, _street_stats, resolve_suburb, is_blank_or_zero, build_dominant_suburb_map_from_verified, build_global_dominant_suburb_map, fix_known_text_glitches, _segment_contains_forced_drop, _normalize_separators, _dedupe_segments_keep_njm, _pull_njm_from_parentheses, _strip_all_parentheses_content, _remove_non_ascii, +20 more • consts: _EAST_TAMAKI_RX=<call compile(... )>, _MONTHS_RX='(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*', _DATE_RX=<call compile(... )>, _NOTE_DROP_PATTERNS=<list len≈27>, _NOTE_DROP_RES=<ListComp>, _EXTRA_NOTE_DROPS=<list len≈12>, _EXTRA_TOKEN_WORDS=<list len≈4>, _EXTRA_TOKEN_RES=<ListComp>, _GRAMMAR_FIXES=<list len≈1>, EXPECTED_HEADERS=<list len≈7>

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely touches output contracts (CSV/MD). Also scan ExportUtils + any *Export* modules that write the same CSV.
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems
  - Side effects: `top-level assign from call: <call compile(... )>`; `top-level assign from call: <call compile(... )>`

## Group 9 (size=1)

### Start Here

- `FileSave_Generator_Territory.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `FileSave_Generator_Territory.py`
- **Role:** `ENTRYPOINT` • `has __main__` • `argparse`
- **Responsibilities:** `runtime/orchestration/loops`, `analysis/scoring/setups`, `journaling/audit/logging`, `risk/position sizing/rr/gates`, `time/session/scheduling`, `filesystem/path I/O`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Why it exists (docstring/intent):**

```text
FileSave_Generator_Territory.py

PASS 1:
- Scans whatever folder this script is in (or --root)
- Looks for MAIN folders (top-level dirs)
- Each MAIN folder is considered to contain Sub_### slots directly underneath its
- Finds the next EMPTY Sub_### slot (empty = no files anywhere under that Sub_### recursively)

PASS 2:
- Scans external folder:
  C:\\Users\\brook\\OneDrive\\Desktop\\Python_AI Bot

- Prints:
  (1) all code files (.py/.bat/.yaml/.yml) (recursive)
  (2) all OTHER items in that...
```
- **Inside:** funcs: ensure_default_suffix_on_subfolder, build_change_suffix, setup_logging, find_brook_t7_root, locate_filesave_generator, natural_key, ensure_dir, format_size, dir_size_bytes, open_in_explorer, close_all_open_sub_windows, open_sub_folder_exclusive, _strip_trailing_paren_suffix, prompt_rename_choice, rename_subfolder_append_suffix, collect_all_files, parse_backup_num, format_backup_name, +35 more • consts: EXCLUDE_DIR_NAMES=<set len≈3>, DEFAULT_RENAME_SUFFIX='In Progress', TERRITORY_ROOT=<call Path(... )>, DEFAULT_CHANGED_SUFFIX='New Update', DEFAULT_UNCHANGED_SUFFIX=<Name>, ONEDRIVE_ROOT=<call Path(... )>, COLOR_RESET='\x1b[0m', COLOR_BRIGHT_YELLOW='\x1b[93m', _DIGIT_RE=<call compile(... )>, _SUB_SLOT_RE=<call compile(... )>, RENAME_SUFFIX_OPTIONS=<list len≈13>, CODE_EXTS=<set len≈4>

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems
  - Side effects: `top-level assign from call: <call Path(... )>`; `top-level assign from call: <call Path(... )>`; `top-level assign from call: <call compile(... )>`; `top-level assign from call: <call compile(... )>`

## Group 10 (size=1)

### Start Here

- `Finding_New_Addresses.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Finding_New_Addresses.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `exports/reports (csv/json/md/txt)`, `time/session/scheduling`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Why it exists (docstring/intent):**

```text
Python Expert
Finding_New_Addresses.py
Utilities for exporting LINZ streets (Option 10) without circular imports.
```
- **Inside:** funcs: clean_exported_linz_streets, create_excel_for_new_addresses, export_linz_suburbs, export_linz_streets, find_missing_addresses, finding_new_addresses

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- **Risk notes:** ⚠️ executing may touch external systems

## Group 11 (size=1)

### Start Here

- `GeoPackage_Borders.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `GeoPackage_Borders.py`
- **Role:** `ENTRYPOINT` • `has __main__` • `argparse`
- **Responsibilities:** `runtime/orchestration/loops`, `broker/execution/orders`, `exports/reports (csv/json/md/txt)`, `config/env/constants`, `risk/position sizing/rr/gates`, `time/session/scheduling`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: _ogr2, _ni, _coalesce, _parse_cli_args, _parse_color_idx, _preferred_kml_layer, _gpd_read_kml_quiet, _parse_cli_args, run_utf8, _build_gdal_env, _clip_to_land, _find_spatialite_binary, divide_boundary_into_sections_from_kml, divide_polygon_by_cut_lines_from_kml, _write_kml_from_coords, density_valley_split, ensure_roads_layer, _clip_polygon_by_road_buffer, +19 more • consts: NON_INTERACTIVE=False, _CLI=<call _parse_cli_args(... )>, DEFAULT_SUBURB=<call _coalesce(... )>, DEFAULT_CONCAVE=<call float(... )>, DEFAULT_COLOR_IDX=<BoolOp>, DEFAULT_TONE=<call _coalesce(... )>, DEFAULT_ROAD_BUFFER=<call float(... )>, DEFAULT_CLIP_MODE=<call _coalesce(... )>, _CLI=<call _parse_cli_args(... )>

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely touches live execution. Also scan risk gates + journal events for trace completeness.
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems
  - Side effects: `top-level call: <call filterwarnings(... )>`; `top-level call: <call filterwarnings(... )>`; `top-level assign from call: <call getattr(... )>`; `top-level assign from call: <call _parse_cli_args(... )>`

## Group 12 (size=1)

### Start Here

- [no entrypoints]

### Critical paths (heuristic)

- [no entrypoints → cannot compute critical paths]

### Subsystems

- **BAT / Launchers** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

### `Run_NWS_UIA_Dump.bat`
- **Role:** `BAT`
- **Responsibilities:** `runs python scripts`, `sets env/runtime flags`
- **Env vars:** `"SCRIPT_DIR=%~dp0"`, `"PY=py"`, `"PY_ARGS=-3.12"`, `"PY=python"`, `"PY_ARGS="`
- **Python calls:** `echo Using Python:`, `echo Python exit code: %errorlevel%`, `echo ERROR: Python not found or not runnable: %PY% %PY_ARGS%`, `echo ERROR: pywinauto still not importable in this Python.` (+1 more)
- **References:** `Auto_NWS_UIA_Dump.py`

## Group 13 (size=1)

### Start Here

- [no entrypoints]

### Critical paths (heuristic)

- [no entrypoints → cannot compute critical paths]

### Subsystems

- **BAT / Launchers** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

### `RunAuto_NWS_Main.bat`
- **Role:** `BAT`
- **Responsibilities:** `runs python scripts`, `sets env/runtime flags`
- **Env vars:** `"SCRIPT_DIR=%~dp0"`, `"SCRIPT=%SCRIPT_DIR%Auto_NWS_Main.py"`
- **Python calls:** `where python >nul 2>&1 && (`, `python "%SCRIPT%"`, `echo ERROR: Python not found on this PC.`, `echo Install Python from https://www.python.org/downloads/windows/` (+1 more)
- **References:** `//www.py`, `Auto_NWS_Main.py`

## Group 14 (size=1)

### Start Here

- [no entrypoints]

### Critical paths (heuristic)

- [no entrypoints → cannot compute critical paths]

### Subsystems

- **Filesystem / I/O** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo/gdal_fsspec.py`
- **Role:** `MODULE`
- **Responsibilities:** `filesystem/path I/O`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Why it exists (docstring/intent):**

```text
Module exposing GDAL Virtual File Systems (VSI) as a "gdalvsi" fsspec implementation.

Importing "osgeo.gdal_fsspec" requires the Python "fsspec"
(https://filesystem-spec.readthedocs.io/en/latest/) module to be available.

A generic "gdalvsi" fsspec protocol is available. All GDAL VSI file names must be
simply prefixed with "gdalvsi://". For example:

- "gdalvsi://data/byte.tif" to access relative file "data/byte.tif"
- "gdalvsi:///home/user/byte.tif" to access absolute file "/home/user/byte....
```
- **Inside:** classes: VSIFileSystem • funcs: register_vsi_implementations

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call register_vsi_implementations(... )>`

## Group 15 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/assemblepoly.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/assemblepoly.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, doit, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 16 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/build_jp2_from_xml.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/build_jp2_from_xml.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `filesystem/path I/O`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: VSILFile • funcs: Usage, find_xml_node, get_attribute_val, get_node_content, hex_letter_to_number, write_hexstring_as_binary, parse_field, parse_jpc_marker, parse_jp2codestream, parse_jp2_box, parse_jp2file, build_file, main • consts: XML_TYPE_IDX=0, XML_VALUE_IDX=1, XML_FIRST_CHILD_IDX=2

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 17 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/classify.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/classify.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, doit, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 18 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/crs2crs2grid.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/crs2crs2grid.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `filesystem/path I/O`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: points_in_file, read_grid_crs_to_crs, new_create_grid, write_grid, write_gdal_grid, write_control, Usage, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 19 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/densify.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/densify.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `risk/position sizing/rr/gates`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: Translator, Densify • funcs: Usage, GetLength, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems
  - Side effects: `top-level call: <call UseExceptions(... )>`

## Group 20 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/dump_jp2.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/dump_jp2.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `analysis/scoring/setups`, `exports/reports (csv/json/md/txt)`, `filesystem/path I/O`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, dump_gmljp2, dump_crsdictionary, extract_all_xml_boxes, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 21 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/fft.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/fft.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, ParseType, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 22 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/fix_gpkg.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/fix_gpkg.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: fix, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 23 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/gcps2ogr.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/gcps2ogr.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 24 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/gcps2vec.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/gcps2vec.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, main, gcps2vec

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 25 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/gcps2wld.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/gcps2wld.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 26 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/gdal2grd.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/gdal2grd.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 27 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/gdal_auth.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/gdal_auth.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `time/session/scheduling`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, main • consts: SCOPES=<dict len≈3>

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 28 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/gdal_cp.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/gdal_cp.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: ScaledProgress • funcs: needsVSICurl, Usage, gdal_cp_single, gdal_cp_recurse, gdal_cp_pattern_match, gdal_cp, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 29 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/gdal_create_pdf.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/gdal_create_pdf.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, gdal_create_pdf, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 30 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/gdal_ls.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/gdal_ls.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `filesystem/path I/O`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: needsVSICurl, iszip, istgz, display_file, readDir, Usage, gdal_ls, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 31 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/gdal_lut.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/gdal_lut.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `filesystem/path I/O`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: read_lut, Usage, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 32 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/gdal_mkdir.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/gdal_mkdir.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, gdal_mkdir, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 33 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/gdal_remove_towgs84.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/gdal_remove_towgs84.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 34 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/gdal_rm.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/gdal_rm.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, gdal_rm_recurse, gdal_rm, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 35 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/gdal_rmdir.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/gdal_rmdir.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `exports/reports (csv/json/md/txt)`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, gdal_rm, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 36 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/gdal_vrtmerge.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/gdal_vrtmerge.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `filesystem/path I/O`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: file_info • funcs: names_to_fileinfos, Usage, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 37 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/gdalchksum.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/gdalchksum.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 38 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/gdalcopyproj.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/gdalcopyproj.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 39 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/gdalfilter.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/gdalfilter.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 40 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/gdalident.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/gdalident.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, ProcessTarget, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 41 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/gdalimport.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/gdalimport.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `filesystem/path I/O`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: progress_cb, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 42 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/gdalinfo.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/gdalinfo.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `exports/reports (csv/json/md/txt)`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, EQUAL, main, GDALInfoReportCorner

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 43 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/get_soundg.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/get_soundg.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 44 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/histrep.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/histrep.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 45 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/hsv_merge.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/hsv_merge.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: rgb_to_hsv, hsv_to_rgb, Usage, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 46 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/jpeg_in_tiff_extract.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/jpeg_in_tiff_extract.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, extract_tile, jpeg_in_tiff_extract, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 47 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/load2odbc.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/load2odbc.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 48 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/loslas2ntv2.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/loslas2ntv2.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `risk/position sizing/rr/gates`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: Options • funcs: Usage, TranslateLOSLAS, auto_noaa, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 49 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/magphase.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/magphase.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, doit, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 50 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/make_fuzzer_friendly_archive.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/make_fuzzer_friendly_archive.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 51 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/mkgraticule.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/mkgraticule.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: float_range, Usage, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 52 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/ogr2vrt.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/ogr2vrt.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `filesystem/path I/O`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: GeomType2Name, Esc, Usage, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 53 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/ogr_build_junction_table.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/ogr_build_junction_table.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, build_junction_table, process_layer, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 54 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/ogr_dispatch.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/ogr_dispatch.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: Options • funcs: Usage, EQUAL, wkbFlatten, GeometryTypeToName, get_out_lyr_name, get_layer_and_map, convert_layer, ogr_dispatch, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 55 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/ogrinfo.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/ogrinfo.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `exports/reports (csv/json/md/txt)`, `filesystem/path I/O`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: EQUAL, main, Usage, ReportOnLayer, DumpReadableFeature, DumpReadableGeometry

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 56 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/ogrupdate.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/ogrupdate.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `analysis/scoring/setups`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, ogrupdate_analyse_args, AreFeaturesEqual, ogrupdate_process, main • consts: DEFAULT=0, UPDATE_ONLY=1, APPEND_ONLY=2

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 57 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/rel.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/rel.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, ParseType, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 58 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/tigerpoly.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/tigerpoly.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: Module • funcs: Usage, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 59 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/tolatlong.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/tolatlong.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 60 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/val_repl.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/val_repl.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, ParseType, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 61 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/validate_cloud_optimized_geotiff.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/validate_cloud_optimized_geotiff.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `filesystem/path I/O`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: ValidateCloudOptimizedGeoTIFFException • funcs: Usage, full_check_band, check_tile_interleave, validate, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 62 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/validate_geoparquet.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/validate_geoparquet.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `exports/reports (csv/json/md/txt)`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `boundary`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `urllib (HTTP)`
- **Inside:** classes: GeoParquetValidator • funcs: check, Usage, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems; ⚠️ boundary module (network/MT5)

## Group 63 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/validate_gpkg.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/validate_gpkg.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `time/session/scheduling`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: GPKGCheckException, GPKGChecker • funcs: _esc_literal, _esc_id, _is_valid_data_type, check, Usage, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 64 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/validate_jp2.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/validate_jp2.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`, `exports/reports (csv/json/md/txt)`, `risk/position sizing/rr/gates`, `filesystem/path I/O`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: ErrorReport • funcs: Usage, find_xml_node, get_attribute_val, find_message, find_element_with_name, find_jp2box, find_marker, get_count_and_indices_of_jp2boxes, get_count_of_uuidboxes, find_field, get_element_val, get_field_val, gdalOpenWithOpenJPEGDriverPreferably, get_gmljp2, find_remaining_bytes, find_errors, validate_bitsize, int_or_none, +4 more • consts: XML_TYPE_IDX=0, XML_VALUE_IDX=1, XML_FIRST_CHILD_IDX=2

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 65 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/vec_tr.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/vec_tr.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: TransformPoint, WalkAndTransform, Usage, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 66 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/vec_tr_spat.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/vec_tr_spat.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 67 (size=1)

### Start Here

- `Street Database/bin/gdal/python/osgeo_utils/samples/wcs_virtds_params.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/osgeo_utils/samples/wcs_virtds_params.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `runtime/orchestration/loops`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: Usage, main

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 68 (size=1)

### Start Here

- `Street Database/bin/gdal/python/scripts/gdal2tiles-script.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/scripts/gdal2tiles-script.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `general`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: importlib_load_entry_point

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems
  - Side effects: `top-level call: <call setdefault(... )>`

## Group 69 (size=1)

### Start Here

- `Street Database/bin/gdal/python/scripts/gdal2tiles.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/scripts/gdal2tiles.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `general`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ executing may touch external systems

## Group 70 (size=1)

### Start Here

- `Street Database/bin/gdal/python/scripts/gdal2xyz-script.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/scripts/gdal2xyz-script.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `general`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: importlib_load_entry_point

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems
  - Side effects: `top-level call: <call setdefault(... )>`

## Group 71 (size=1)

### Start Here

- `Street Database/bin/gdal/python/scripts/gdal_calc-script.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/scripts/gdal_calc-script.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `general`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: importlib_load_entry_point

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems
  - Side effects: `top-level call: <call setdefault(... )>`

## Group 72 (size=1)

### Start Here

- `Street Database/bin/gdal/python/scripts/gdal_edit-script.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/scripts/gdal_edit-script.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `general`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: importlib_load_entry_point

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems
  - Side effects: `top-level call: <call setdefault(... )>`

## Group 73 (size=1)

### Start Here

- `Street Database/bin/gdal/python/scripts/gdal_fillnodata-script.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/scripts/gdal_fillnodata-script.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `general`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: importlib_load_entry_point

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems
  - Side effects: `top-level call: <call setdefault(... )>`

## Group 74 (size=1)

### Start Here

- `Street Database/bin/gdal/python/scripts/gdal_merge-script.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/scripts/gdal_merge-script.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `general`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: importlib_load_entry_point

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems
  - Side effects: `top-level call: <call setdefault(... )>`

## Group 75 (size=1)

### Start Here

- `Street Database/bin/gdal/python/scripts/gdal_pansharpen-script.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/scripts/gdal_pansharpen-script.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `general`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: importlib_load_entry_point

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems
  - Side effects: `top-level call: <call setdefault(... )>`

## Group 76 (size=1)

### Start Here

- `Street Database/bin/gdal/python/scripts/gdal_polygonize-script.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/scripts/gdal_polygonize-script.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `general`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: importlib_load_entry_point

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems
  - Side effects: `top-level call: <call setdefault(... )>`

## Group 77 (size=1)

### Start Here

- `Street Database/bin/gdal/python/scripts/gdal_proximity-script.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/scripts/gdal_proximity-script.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `general`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: importlib_load_entry_point

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems
  - Side effects: `top-level call: <call setdefault(... )>`

## Group 78 (size=1)

### Start Here

- `Street Database/bin/gdal/python/scripts/gdal_retile-script.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/scripts/gdal_retile-script.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `general`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: importlib_load_entry_point

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems
  - Side effects: `top-level call: <call setdefault(... )>`

## Group 79 (size=1)

### Start Here

- `Street Database/bin/gdal/python/scripts/gdal_sieve-script.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/scripts/gdal_sieve-script.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `general`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: importlib_load_entry_point

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems
  - Side effects: `top-level call: <call setdefault(... )>`

## Group 80 (size=1)

### Start Here

- `Street Database/bin/gdal/python/scripts/gdalattachpct-script.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/scripts/gdalattachpct-script.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `general`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: importlib_load_entry_point

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems
  - Side effects: `top-level call: <call setdefault(... )>`

## Group 81 (size=1)

### Start Here

- `Street Database/bin/gdal/python/scripts/gdalcompare-script.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/scripts/gdalcompare-script.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `general`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: importlib_load_entry_point

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems
  - Side effects: `top-level call: <call setdefault(... )>`

## Group 82 (size=1)

### Start Here

- `Street Database/bin/gdal/python/scripts/gdalmove-script.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/scripts/gdalmove-script.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `general`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: importlib_load_entry_point

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems
  - Side effects: `top-level call: <call setdefault(... )>`

## Group 83 (size=1)

### Start Here

- `Street Database/bin/gdal/python/scripts/ogr_layer_algebra-script.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/scripts/ogr_layer_algebra-script.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `general`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: importlib_load_entry_point

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems
  - Side effects: `top-level call: <call setdefault(... )>`

## Group 84 (size=1)

### Start Here

- `Street Database/bin/gdal/python/scripts/ogrmerge-script.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/scripts/ogrmerge-script.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `general`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: importlib_load_entry_point

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems
  - Side effects: `top-level call: <call setdefault(... )>`

## Group 85 (size=1)

### Start Here

- `Street Database/bin/gdal/python/scripts/pct2rgb-script.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/scripts/pct2rgb-script.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `general`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: importlib_load_entry_point

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems
  - Side effects: `top-level call: <call setdefault(... )>`

## Group 86 (size=1)

### Start Here

- `Street Database/bin/gdal/python/scripts/rgb2pct-script.py`

### Critical paths (heuristic)

- [no short critical paths detected]

### Subsystems

- **Runtime / Entrypoints** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/gdal/python/scripts/rgb2pct-script.py`
- **Role:** `ENTRYPOINT` • `has __main__`
- **Responsibilities:** `general`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** funcs: importlib_load_entry_point

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic); ⚠️ executing may touch external systems
  - Side effects: `top-level call: <call setdefault(... )>`

## Group 87 (size=1)

### Start Here

- [no entrypoints]

### Critical paths (heuristic)

- [no entrypoints → cannot compute critical paths]

### Subsystems

- **Strategy / Analysis** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

#### `Street Database/bin/ms/python/mapscript.py`
- **Role:** `LIB`
- **Responsibilities:** `analysis/scoring/setups`, `config/env/constants`, `risk/position sizing/rr/gates`, `filesystem/path I/O`
- **Internal imports:** `[none detected]`
- **Imported by:** `[none detected]`
- **IO label:** `internal`
- **Creates/writes files (heuristic):** `[none detected]`
- **Reads files (heuristic):** `[none detected]`
- **Network/MT5 touchpoints (heuristic):** `[none detected]`
- **Inside:** classes: _SwigNonDynamicMeta, intarray, CompositingFilter, LayerCompositer, fontSetObj, clusterObj, outputFormatObj, queryMapObj, webObj, styleObj, labelLeaderObj, labelObj, classObj, labelCacheMemberObj, markerCacheMemberObj, labelCacheSlotObj, labelCacheObj, resultObj, +24 more • funcs: _swig_repr, _swig_setattr_nondynamic_instance_variable, _swig_setattr_nondynamic_class_variable, _swig_add_metaclass, intarray_frompointer, msSaveImage, msFreeImage, msSetup, msCleanup, msLoadMapFromString, shapeObj_fromWKT, msGetErrorObj, msResetErrorList, msGetVersion, msGetVersionInt, msGetErrorString, msLoadConfig, msFreeConfig, +13 more • consts: MS_TRUE=<attr MS_TRUE>, MS_FALSE=<attr MS_FALSE>, MS_UNKNOWN=<attr MS_UNKNOWN>, MS_ON=<attr MS_ON>, MS_OFF=<attr MS_OFF>, MS_DEFAULT=<attr MS_DEFAULT>, MS_EMBED=<attr MS_EMBED>, MS_DELETE=<attr MS_DELETE>, MS_YES=<attr MS_YES>, MS_NO=<attr MS_NO>, MS_LAYER_ALLOCSIZE=<attr MS_LAYER_ALLOCSIZE>, MS_CLASS_ALLOCSIZE=<attr MS_CLASS_ALLOCSIZE>, +387 more

**Change Impact Hints (hard-coded):**
- If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).
- Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.
- **Risk notes:** ⚠️ import-time side effects (heuristic)
  - Side effects: `top-level call: <call intarray_swigregister(... )>`; `top-level call: <call CompositingFilter_swigregister(... )>`; `top-level call: <call LayerCompositer_swigregister(... )>`; `top-level call: <call fontSetObj_swigregister(... )>`

## Group 88 (size=1)

### Start Here

- [no entrypoints]

### Critical paths (heuristic)

- [no entrypoints → cannot compute critical paths]

### Subsystems

- **BAT / Launchers** (1)

### Subsystem dependency map (collapsed)

- [no cross-subsystem edges detected]

### File-level dependency map (collapsed)

- [no dependencies]

### Modules

### `Street Database/bin/SDKShell.bat`
- **Role:** `BAT`
- **Responsibilities:** `runs python scripts`, `sets env/runtime flags`
- **Env vars:** `SDK_ROOT=%~dp0`, `SDK_ROOT=%SDK_ROOT:\\=\%`, `ocipath=0`, `_path="%PATH:;=" "%"`, `"PATH=%SDK_ROOT%bin;%SDK_ROOT%bin\gdal\python\osgeo;%SDK_ROOT%bin\proj9\apps;%SDK_ROOT%bin\gdal\apps;%SDK_ROOT%bin\ms\apps;...`, `"GDAL_DATA=%SDK_ROOT%bin\gdal-data"`, `"GDAL_DRIVER_PATH=%SDK_ROOT%bin\gdal\plugins"`, `"PYTHONPATH=%SDK_ROOT%bin\gdal\python;%SDK_ROOT%bin\ms\python"` (+1 more)
- **References:** `SDKShell.bat`

## Failures / Skips

### Python failures/skips

- `Exported Files/Clean_NewWorldScheduler - Part 1.py` — `AST parse failed: expected an indented block after 'try' statement on line 2409 (Clean_NewWorldScheduler - Part 1.py, line 2410)`
- `Exported Files/Clean_NewWorldScheduler - Part 2.py` — `AST parse failed: unexpected indent (Clean_NewWorldScheduler - Part 2.py, line 2)`


---

## Run Stats

- Python files found: `156` • parsed ok: `154` • failed/skipped: `2`
- BAT files found: `6` • parsed ok: `6` • failed/skipped: `0`
- YAML files found: `0` • parsed ok: `0` • failed/skipped: `0`
- Output: `File Summary/python_modules.md`
