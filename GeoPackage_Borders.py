# Python Expert
# GeoPackage_Borders.py

import subprocess
import re
import json
import csv
import time
import math
import random
import difflib
from pathlib import Path
from contextlib import contextmanager
from tqdm import tqdm
import os
import sys
import argparse
import os, re, json, subprocess, difflib
from pathlib import Path
from tqdm import tqdm
import warnings

# Silence pyogrio’s KML “layer adjusted for XML validity” spam
warnings.filterwarnings(
    "ignore",
    message=r"Layer name '.*' adjusted to '.*' for XML validity\.",
    category=RuntimeWarning,
    module=r".*pyogrio\.raw"
)

# Silence “More than one layer found … Specify layer parameter …”
warnings.filterwarnings(
    "ignore",
    message=r"More than one layer found in .* Specify layer parameter to avoid this warning\.",
    category=UserWarning,
    module=r".*pyogrio\.geopandas"
)



script_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))


def _ogr2(cmd_list, env=None):
    env2 = os.environ.copy()
    if env:
        env2.update(env)
    cmd2 = [str(cmd_list[0])]
    if env2.get("PROJ_LIB"):  cmd2 += ["--config", "PROJ_LIB",  env2["PROJ_LIB"]]
    if env2.get("PROJ_DATA"): cmd2 += ["--config", "PROJ_DATA", env2["PROJ_DATA"]]
    if env2.get("GDAL_DATA"): cmd2 += ["--config", "GDAL_DATA", env2["GDAL_DATA"]]
    cmd2 += ["--config", "OGR_SQLITE_LOAD_EXTENSIONS", "YES"]
    if env2.get("OGR_SQLITE_EXT_PATH"):
        cmd2 += ["--config", "OGR_SQLITE_EXT_PATH", env2["OGR_SQLITE_EXT_PATH"]]
    return run_utf8(cmd2 + [str(x) for x in cmd_list[1:]], env=env2)



def _ni(value, fallback):
    return fallback if NON_INTERACTIVE else value



# ---------- Non-interactive defaults ----------
NON_INTERACTIVE = False  # set False if you ever want the prompts back

def _coalesce(*vals):
    for v in vals:
        if v is None:
            continue
        if isinstance(v, str) and v.strip() == "":
            continue
        return v
    return None

# --- Parse CLI BEFORE using _CLI anywhere ---
def _parse_cli_args():
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("-s", "--suburb", dest="suburb", help="Suburb name/fragment (e.g., 'Howick')")
    p.add_argument("--concave", type=float, help="Concave hull ratio (0..1)")
    p.add_argument("--color-idx", dest="color_idx",
                   help="Comma-separated color indices, e.g. '1,3,5'")
    p.add_argument("--tone", choices=["light", "medium"], help="KML fill tone")
    p.add_argument("--road-buffer", type=float, dest="road_buffer",
                   help="Road clipping buffer in meters")
    p.add_argument("--clip-mode", choices=["include_parks", "roads"],
                   dest="clip_mode", help="Full polygon vs road-corridor clipping")
    try:
        args, _ = p.parse_known_args()
    except SystemExit:
        class _Empty: pass
        args = _Empty()
        args.suburb = None; args.concave = None; args.color_idx = None
        args.tone = None; args.road_buffer = None; args.clip_mode = None
    return args

_CLI = _parse_cli_args()  # <-- make sure this is defined first

# you can override via env or CLI args (SAFE to use _CLI from here down)
DEFAULT_SUBURB = _coalesce(os.environ.get("SUBURB"), getattr(_CLI, "suburb", None))

DEFAULT_CONCAVE = float(
    _coalesce(os.environ.get("CONCAVE"),
              getattr(_CLI, "concave", None),
              "0.60")
)

def _parse_color_idx(src: str | None):
    if not src:
        return []
    return [int(x) for x in src.split(",") if x.strip().isdigit()]

_cli_color = _parse_color_idx(getattr(_CLI, "color_idx", None))
_env_color = _parse_color_idx(os.environ.get("COLOR_IDX", "1"))
DEFAULT_COLOR_IDX = (_cli_color or _env_color) or [1]

DEFAULT_TONE = _coalesce(os.environ.get("TONE"), getattr(_CLI, "tone", None), "light")  # light | medium

DEFAULT_ROAD_BUFFER = float(
    _coalesce(os.environ.get("ROAD_BUFFER"),
              getattr(_CLI, "road_buffer", None),
              "50")
)

DEFAULT_CLIP_MODE = _coalesce(os.environ.get("CLIP_MODE"),
                              getattr(_CLI, "clip_mode", None),
                              "include_parks")  # include_parks | roads


# --- quiet KML reading helpers ---
def _preferred_kml_layer(path_str: str) -> str | None:
    try:
        from pyogrio import list_layers
        layers = list_layers(path_str) or []
        # prefer “*.final” if present, else first layer
        for name in layers:
            if str(name).lower().endswith(".final"):
                return name
        return layers[0] if layers else None
    except Exception:
        return None

def _gpd_read_kml_quiet(path_str: str):
    import warnings
    import geopandas as gpd
    lyr = _preferred_kml_layer(path_str)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        return gpd.read_file(path_str, layer=lyr) if lyr else gpd.read_file(path_str)


def _parse_cli_args():
    """
    Lightweight CLI to drive non-interactive defaults without touching the rest
    of the script. We only parse known args and ignore the rest.
    """
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("-s", "--suburb", dest="suburb", help="Suburb name/fragment (e.g., 'Howick')")
    p.add_argument("--concave", type=float, help="Concave hull ratio (0..1)")
    p.add_argument("--color-idx", dest="color_idx",
                   help="Comma-separated color indices, e.g. '1,3,5'")
    p.add_argument("--tone", choices=["light", "medium"], help="KML fill tone")
    p.add_argument("--road-buffer", type=float, dest="road_buffer",
                   help="Road clipping buffer in meters")
    p.add_argument("--clip-mode", choices=["include_parks", "roads"],
                   dest="clip_mode", help="Full polygon vs road-corridor clipping")
    try:
        args, _ = p.parse_known_args()
    except SystemExit:
        # In case something calls parse_args() elsewhere; don't exit the script.
        class _Empty: pass
        args = _Empty()
        args.suburb = None; args.concave = None; args.color_idx = None
        args.tone = None; args.road_buffer = None; args.clip_mode = None
    return args

_CLI = _parse_cli_args()



# --- UTF-8 safe subprocess wrapper ------------------------------------------
def run_utf8(cmd, *, env=None, check=False):
    """
    Run a command and always decode stdout/stderr as UTF-8 (replacing bad bytes).
    Prevents Windows cp1252 decode crashes with GDAL/OGR output.
    """
    return subprocess.run(
        [str(x) for x in cmd],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=check
    )

# --- Auto configure PROJ_LIB for GDAL/PROJ -----------------------------------
# Script base directory
script_dir = os.path.dirname(os.path.abspath(__file__))

# Default: assume proj.db is in "bin" under the script folder
proj_dir = os.path.join(script_dir, "bin")

# Fallback: force the absolute Windows path
if not os.path.exists(os.path.join(proj_dir, "proj.db")):
    proj_dir = r"C:\Script\Street Database\bin"

# Set PROJ_LIB
os.environ["PROJ_LIB"] = proj_dir
print(f"✅ PROJ_LIB set to: {proj_dir}")

# Safety check
if not os.path.exists(os.path.join(proj_dir, "proj.db")):
    print("⚠️ proj.db NOT FOUND in:", proj_dir)
    print("   CRS transforms will still fail.")

def _build_gdal_env(gdal_bin: Path) -> dict:
    """
    Build env for GDAL subprocesses (finds GDAL_DATA and PROJ_LIB/PROJ_DATA).
    Searches typical locations and falls back to a recursive search for proj.db.
    """
    env = os.environ.copy()

    root = gdal_bin.resolve()
    base = root.parent  # "<Street Database>"

    # --- helpers
    def _first_dir(paths):
        for p in paths:
            if p and Path(p).exists():
                return str(Path(p))
        return None

    def _find_proj_db(start_dirs):
        # Search a few likely trees for proj.db
        for sd in start_dirs:
            try:
                for hit in Path(sd).rglob("proj.db"):
                    return str(hit)
            except Exception:
                pass
        return None

    # Candidates for GDAL data
    gdal_dirs = [
        root / "gdal-data",
        root / "data",
        base / "gdal-data",
        base / "share" / "gdal",
        base / "share",
        Path(env.get("GDAL_DATA", "")),
    ]
    gdal_data = _first_dir(gdal_dirs)

    # Candidates for PROJ data (try common folders first)
    proj_dirs = [
        root / "proj",
        root / "proj-data",
        base / "proj",
        base / "share" / "proj",
        Path(env.get("PROJ_LIB", "")),
        Path(env.get("PROJ_DATA", "")),
    ]
    proj_dir = _first_dir(proj_dirs)

    # If not found, scan recursively for proj.db starting from a few roots
    if not proj_dir:
        proj_db = _find_proj_db([
            root, base,
            Path(env.get("OSGEO4W_ROOT", "")),
            Path(env.get("QGIS_PREFIX_PATH", "")),
            Path(env.get("CONDA_PREFIX", "")),
            Path("C:/OSGeo4W64"),
            Path("C:/Program Files"),
        ])
        if proj_db:
            proj_dir = str(Path(proj_db).parent)

    # Export into env if found
    if gdal_data:
        env["GDAL_DATA"] = gdal_data
    if proj_dir:
        env["PROJ_LIB"] = proj_dir
        env["PROJ_DATA"] = proj_dir  # some builds still read PROJ_DATA

    # Optional: quiet network lookups in some builds
    env.setdefault("PROJ_NETWORK", "OFF")

    # Encourage UTF-8 everywhere
    env.setdefault("GDAL_FILENAME_IS_UTF8", "YES")
    env.setdefault("SHAPE_ENCODING", "UTF-8")
    # env["CPL_DEBUG"] = "ON"  # enable for verbose GDAL logs

    return env

def _clip_to_land(in_geojson: Path, out_geojson: Path, gdal_bin: Path, env: dict) -> Path | None:
    """
    Intersect a polygon GeoJSON with a coastline/land mask so the result contains land only.
    - Works whether the mask is POLYGON land or LINE coastlines (auto-polygonizes).
    - Prefers fast SQLite/SpatiaLite path when available; otherwise falls back to pure
      GeoPandas/Shapely (no extensions required).
    - Operates in EPSG:2193 internally; exports EPSG:4326.

    Env:
      LAND_MASK_PATH   → path to mask (defaults to "<Street Database>/nz-coastlines-topo-150k.gpkg")
      LAND_MASK_LAYER  → optional layer name in the mask dataset
      LAND_MIN_AREA_M2 → optional area filter (drop tiny fragments before dissolve), default 0
    Returns out_geojson on success, else None.
    """
    import os, json

    ogr2ogr = gdal_bin / "ogr2ogr.exe"
    ogrinfo = gdal_bin / "ogrinfo.exe"

    if not in_geojson or not Path(in_geojson).exists():
        print(f"❌ _clip_to_land: input GeoJSON missing: {in_geojson}")
        return None
    if not ogr2ogr.exists() or not ogrinfo.exists():
        print("❌ _clip_to_land: Missing GDAL tools (ogr2ogr/ogrinfo).")
        return None

    # ----- Resolve coastline mask -----
    land_path = (os.environ.get("LAND_MASK_PATH") or "").strip()
    if not land_path:
        # Prefer polygons+islands; fall back to the old coastlines lines
        for cand in (
                "nz-coastlines-and-islands-polygons-topo-150k.gpkg",
                "nz-coastlines-topo-150k.gpkg",
        ):
            p = (gdal_bin.parent / cand).resolve()
            if p.exists():
                land_path = str(p)
                break

    land_layer = (os.environ.get("LAND_MASK_LAYER") or "").strip() or None
    try:
        min_area_m2 = float((os.environ.get("LAND_MIN_AREA_M2") or "0").strip() or 0.0)
    except Exception:
        min_area_m2 = 0.0

    land_ds = Path(land_path)
    if not land_ds.exists():
        print(f"❌ _clip_to_land: LAND_MASK_PATH not found: {land_ds}")
        return None

    # ----- Build env (& neutralize bad extension var that causes "Cannot load extension YES") -----
    env2 = (env or os.environ).copy()
    # this env var is the usual culprit; remove it entirely
    env2.pop("OGR_SQLITE_EXTENSIONS", None)

    # Best-effort: find a SpatiaLite module next to binaries
    def _find_spatialite():
        for name in ("mod_spatialite.dll","spatialite.dll","libspatialite.dll",
                     "mod_spatialite.so","libspatialite.so",
                     "mod_spatialite.dylib","libspatialite.dylib"):
            p = gdal_bin / name
            if p.exists():
                return str(p)
        return os.environ.get("SPATIALITE_PATH")
    spat = _find_spatialite()

    if spat:
        env2.setdefault("OGR_SQLITE_LOAD_EXTENSIONS", "YES")
        env2.setdefault("OGR_SQLITE_EXT_PATH", spat)
        env2.setdefault("SPATIALITE_SECURITY", "relaxed")
        env2.setdefault("SQLITE_EXTRA_EXTENSIONS", spat)
    else:
        # hard OFF when we don't have a real .dll/.so — avoids "Cannot load extension YES"
        env2["OGR_SQLITE_LOAD_EXTENSIONS"] = "NO"
        env2.pop("OGR_SQLITE_EXT_PATH", None)
        env2.pop("SQLITE_EXTRA_EXTENSIONS", None)

    # ----- Runner that injects --config flags (also hard-overrides OGR_SQLITE_EXTENSIONS to empty) -----
    def _run(cmd_list):
        cmd2 = [str(cmd_list[0])]
        if env2.get("PROJ_LIB"):  cmd2 += ["--config","PROJ_LIB",  env2["PROJ_LIB"]]
        if env2.get("PROJ_DATA"): cmd2 += ["--config","PROJ_DATA", env2["PROJ_DATA"]]
        if env2.get("GDAL_DATA"): cmd2 += ["--config","GDAL_DATA", env2["GDAL_DATA"]]
        # Neutralize any system OGR_SQLITE_EXTENSIONS=YES by explicitly setting it empty:
        cmd2 += ["--config","OGR_SQLITE_EXTENSIONS",""]
        if env2.get("OGR_SQLITE_LOAD_EXTENSIONS","NO") == "YES":
            cmd2 += ["--config","OGR_SQLITE_LOAD_EXTENSIONS","YES"]
            if env2.get("OGR_SQLITE_EXT_PATH"):
                cmd2 += ["--config","OGR_SQLITE_EXT_PATH", env2["OGR_SQLITE_EXT_PATH"]]
            if env2.get("SQLITE_EXTRA_EXTENSIONS"):
                cmd2 += ["--config","SQLITE_EXTRA_EXTENSIONS", env2["SQLITE_EXTRA_EXTENSIONS"]]
        else:
            cmd2 += ["--config","OGR_SQLITE_LOAD_EXTENSIONS","NO"]
        return run_utf8(cmd2 + [str(x) for x in cmd_list[1:]], env=env2)

    def _feat_count(ds: Path, layer: str) -> int:
        r = _run([ogrinfo, "-json", str(ds), layer])
        if r.returncode != 0: return 0
        try:
            info = json.loads(r.stdout)
            return (info.get("layers") or [{}])[0].get("featureCount", 0) or 0
        except Exception:
            return 0

    # ----- Scratch workspace -----
    work = Path(in_geojson).resolve().parent
    tmp = work / "_tmp_landclip.gpkg"
    try:
        if tmp.exists(): tmp.unlink()
    except Exception:
        pass

    GEOM = "geom"
    NZTM = "EPSG:2193"
    WGS  = "EPSG:4326"

    # 1) Import suburb → reproject to 2193
    r = _run([ogr2ogr, "-f","GPKG", str(tmp), str(in_geojson),
              "-nln","suburb4326", "-overwrite",
              "-lco", f"GEOMETRY_NAME={GEOM}",
              "-lco","IDENTIFIER=suburb4326","-lco","DESCRIPTION="])
    if r.returncode != 0:
        print("❌ _clip_to_land: import suburb failed:", r.stderr or r.stdout)
        return None

    r = _run([ogr2ogr, "-f","GPKG", str(tmp), str(tmp), "suburb4326",
              "-nln","suburb2193", "-t_srs", NZTM, "-overwrite",
              "-lco", f"GEOMETRY_NAME={GEOM}",
              "-lco","IDENTIFIER=suburb2193","-lco","DESCRIPTION="])
    if r.returncode != 0:
        print("❌ _clip_to_land: reproject suburb failed:", r.stderr or r.stdout)
        return None

    # 2) Import land/coast source as land_src
    import_args = [str(land_ds)]
    if land_layer: import_args.append(land_layer)

    r = _run([ogr2ogr, "-f","GPKG", str(tmp), *import_args,
              "-nln","land_src", "-overwrite",
              "-lco", f"GEOMETRY_NAME={GEOM}",
              "-lco","IDENTIFIER=land_src","-lco","DESCRIPTION="])
    if r.returncode != 0:
        print("❌ _clip_to_land: import land source failed:", r.stderr or r.stdout)
        return None

    # Detect geometry type of land_src
    info = _run([ogrinfo, "-json", str(tmp), "land_src"])
    if info.returncode != 0:
        print("❌ _clip_to_land: cannot inspect land_src:", info.stderr or info.stdout)
        return None
    try:
        gtyp = ((json.loads(info.stdout).get("layers") or [{}])[0].get("geometryType") or "").lower()
    except Exception:
        gtyp = ""
    is_polygonish = ("poly" in gtyp) or ("area" in gtyp)

    # ---------- Fast SQL path (requires SpatiaLite) ----------
    sql_possible = (env2.get("OGR_SQLITE_LOAD_EXTENSIONS","NO") == "YES")
    sql_ok = False

    if sql_possible:
        if is_polygonish:
            r = _run([ogr2ogr, "-f","GPKG", str(tmp), str(tmp), "land_src",
                      "-nln","landP2193", "-t_srs", NZTM, "-overwrite",
                      "-lco", f"GEOMETRY_NAME={GEOM}",
                      "-lco","IDENTIFIER=landP2193","-lco","DESCRIPTION="])
            sql_ok = (r.returncode == 0 and _feat_count(tmp,"landP2193") > 0)
        else:
            r = _run([ogr2ogr, "-f","GPKG", str(tmp), str(tmp), "land_src",
                      "-nln","coastL2193", "-t_srs", NZTM, "-overwrite",
                      "-lco", f"GEOMETRY_NAME={GEOM}",
                      "-lco","IDENTIFIER=coastL2193","-lco","DESCRIPTION="])
            if r.returncode == 0:
                sql_poly = f"""
                WITH
                  C AS (SELECT ST_UnaryUnion({GEOM}) AS g FROM coastL2193),
                  P AS (SELECT (ST_Dump(ST_Polygonize(g))).geom AS g FROM C),
                  S AS (SELECT ST_UnaryUnion({GEOM}) AS g FROM suburb2193)
                SELECT g AS {GEOM} FROM P
                WHERE ST_Intersects(g, (SELECT g FROM S))
                """
                sql_poly_legacy = (sql_poly
                                   .replace("ST_UnaryUnion","UnaryUnion")
                                   .replace("ST_Polygonize","Polygonize")
                                   .replace("ST_Dump","Dump")
                                   .replace("ST_Intersects","Intersects"))
                r = _run([ogr2ogr, "-f","GPKG", str(tmp), str(tmp), "coastL2193",
                          "-nln","landP2193", "-overwrite",
                          "-dialect","SQLite", "-sql", sql_poly,
                          "-lco", f"GEOMETRY_NAME={GEOM}",
                          "-lco","IDENTIFIER=landP2193","-lco","DESCRIPTION="])
                if r.returncode != 0 or _feat_count(tmp,"landP2193") == 0:
                    r = _run([ogr2ogr, "-f","GPKG", str(tmp), str(tmp), "coastL2193",
                              "-nln","landP2193", "-overwrite",
                              "-dialect","SQLite", "-sql", sql_poly_legacy,
                              "-lco", f"GEOMETRY_NAME={GEOM}",
                              "-lco","IDENTIFIER=landP2193","-lco","DESCRIPTION="])
            sql_ok = (r.returncode == 0 and _feat_count(tmp,"landP2193") > 0)

        if sql_ok:
            sql_ix = f"""
            WITH
              S AS (SELECT ST_UnaryUnion({GEOM}) AS s FROM suburb2193),
              L AS (SELECT ST_UnaryUnion({GEOM}) AS l FROM landP2193),
              I AS (SELECT (ST_Dump(ST_Intersection((SELECT s FROM S),(SELECT l FROM L)))).geom AS g)
            SELECT g AS {GEOM} FROM I
            WHERE g IS NOT NULL AND ST_IsEmpty(g)=0
            """
            sql_ix_legacy = (sql_ix
                             .replace("ST_UnaryUnion","UnaryUnion")
                             .replace("ST_Intersection","Intersection")
                             .replace("ST_Dump","Dump")
                             .replace("ST_IsEmpty","IsEmpty"))
            r = _run([ogr2ogr, "-f","GPKG", str(tmp), str(tmp), "landP2193",
                      "-nln","suburb_on_land2193", "-overwrite",
                      "-dialect","SQLite", "-sql", sql_ix,
                      "-lco", f"GEOMETRY_NAME={GEOM}",
                      "-lco","IDENTIFIER=suburb_on_land2193","-lco","DESCRIPTION="])
            if r.returncode != 0 or _feat_count(tmp,"suburb_on_land2193") == 0:
                r = _run([ogr2ogr, "-f","GPKG", str(tmp), str(tmp), "landP2193",
                          "-nln","suburb_on_land2193", "-overwrite",
                          "-dialect","SQLite", "-sql", sql_ix_legacy,
                          "-lco", f"GEOMETRY_NAME={GEOM}",
                          "-lco","IDENTIFIER=suburb_on_land2193","-lco","DESCRIPTION="])
                sql_ok = (r.returncode == 0 and _feat_count(tmp,"suburb_on_land2193") > 0)

            if sql_ok:
                sql_diss = f"""
                SELECT ST_UnaryUnion({GEOM}) AS {GEOM}
                FROM suburb_on_land2193
                {"WHERE ST_Area(" + GEOM + f") >= {float(min_area_m2)}" if min_area_m2 > 0 else ""}
                """
                sql_diss_legacy = (sql_diss
                                   .replace("ST_UnaryUnion","UnaryUnion")
                                   .replace("ST_Area","Area"))
                r = _run([ogr2ogr, "-f","GPKG", str(tmp), str(tmp), "suburb_on_land2193",
                          "-nln","suburb_on_land2193_diss", "-overwrite",
                          "-dialect","SQLite", "-sql", sql_diss,
                          "-lco", f"GEOMETRY_NAME={GEOM}",
                          "-lco","IDENTIFIER=suburb_on_land2193_diss","-lco","DESCRIPTION="])
                if r.returncode != 0 or _feat_count(tmp,"suburb_on_land2193_diss") == 0:
                    r = _run([ogr2ogr, "-f","GPKG", str(tmp), str(tmp), "suburb_on_land2193",
                              "-nln","suburb_on_land2193_diss", "-overwrite",
                              "-dialect","SQLite", "-sql", sql_diss_legacy,
                              "-lco", f"GEOMETRY_NAME={GEOM}",
                              "-lco","IDENTIFIER=suburb_on_land2193_diss","-lco","DESCRIPTION="])
                    sql_ok = (r.returncode == 0 and _feat_count(tmp,"suburb_on_land2193_diss") > 0)

    # ---------- Python fallback (no extensions needed) ----------
    if not sql_ok:
        try:
            import geopandas as gpd
            from shapely.ops import unary_union, polygonize
            from shapely.ops import transform as shp_transform
            from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
            from shapely.errors import GEOSException

            def _force_2d(g):
                if g is None or g.is_empty:
                    return g
                try:
                    return shp_transform(lambda x, y, z=None: (x, y), g)
                except GEOSException:
                    return g

            # Read suburb (2193)
            suburb_gdf = gpd.read_file(str(tmp), layer="suburb2193").to_crs(2193)
            if suburb_gdf.empty:
                print("❌ _clip_to_land: suburb layer empty in fallback.")
                return None
            suburb_union = _force_2d(suburb_gdf.unary_union)

            # Read land/coast
            if land_layer:
                land_gdf = gpd.read_file(str(land_ds), layer=land_layer)
            else:
                land_gdf = gpd.read_file(str(land_ds))
            if land_gdf.empty:
                print("❌ _clip_to_land: land/coast layer empty in fallback.")
                return None
            land_gdf = land_gdf.to_crs(2193)
            land_gdf["geometry"] = land_gdf.geometry.apply(_force_2d)
            land_gdf = land_gdf[~land_gdf.geometry.is_empty & land_gdf.geometry.notnull()]
            if land_gdf.empty:
                print("❌ _clip_to_land: no valid geometries in land/coast.")
                return None

            if land_gdf.geom_type.isin(["Polygon","MultiPolygon"]).any():
                # polygon mask → dissolve
                land_union = _force_2d(land_gdf.unary_union)
                inter = land_union.intersection(suburb_union)
                if inter.is_empty:
                    print("❌ _clip_to_land: intersection empty (fallback).")
                    return None
                geom_out = inter
            else:
                # line coast → polygonize → keep polygons that touch suburb
                lines = _force_2d(unary_union(list(land_gdf.geometry)))
                polys = list(polygonize(lines))
                if not polys:
                    print("❌ _clip_to_land: polygonize produced no polygons (fallback).")
                    return None
                # keep only polygons intersecting suburb
                touching = [p for p in polys if (p.is_valid and not p.is_empty and p.intersects(suburb_union))]
                if not touching:
                    print("❌ _clip_to_land: no polygonized pieces intersect suburb (fallback).")
                    return None
                geom_out = _force_2d(unary_union(touching).intersection(suburb_union))
                if geom_out.is_empty:
                    print("❌ _clip_to_land: intersection empty after polygonize (fallback).")
                    return None

            # drop tiny slivers if requested
            def _drop_small(g):
                if min_area_m2 <= 0: return g
                if isinstance(g, Polygon):
                    return g if g.area >= min_area_m2 else None
                if isinstance(g, MultiPolygon):
                    parts = [p for p in g.geoms if p.area >= min_area_m2]
                    if not parts: return None
                    return unary_union(parts)
                return g

            geom_out = _drop_small(geom_out)
            if geom_out is None or geom_out.is_empty:
                print("❌ _clip_to_land: all pieces below area threshold.")
                return None

            out_gdf = gpd.GeoDataFrame(geometry=[geom_out], crs=2193).to_crs(4326)
            try:
                if out_geojson.exists(): out_geojson.unlink()
            except Exception:
                pass
            out_gdf.to_file(out_geojson, driver="GeoJSON")
            print(f"✅ Land-only polygon (fallback) → {out_geojson}")
            return out_geojson

        except Exception as e:
            print(f"❌ _clip_to_land fallback failed: {e}")
            # fall through to final export attempt if any SQL path partially succeeded

    # ---------- If SQL path succeeded, export to GeoJSON ----------
    if sql_ok and _feat_count(tmp,"suburb_on_land2193_diss") > 0:
        try:
            if out_geojson.exists(): out_geojson.unlink()
        except Exception:
            pass
        r = _run([ogr2ogr, "-f","GeoJSON", str(out_geojson), str(tmp), "suburb_on_land2193_diss",
                  "-t_srs", WGS, "-overwrite"])
        if r.returncode == 0:
            print(f"✅ Land-only polygon → {out_geojson}")
            return out_geojson
        print("❌ _clip_to_land: export failed:", r.stderr or r.stdout)

    print("ℹ️ _clip_to_land: no land-clip produced.")
    return None


# 2 - ✂️  Divide Boundary Into Sections (from KML)

def _find_spatialite_binary(gdal_bin: "Path") -> str | None:
    """
    Try to find a SpatiaLite library to load for SQLite dialect geometry ops.
    Priority:
      - Env override: SPATIALITE_PATH
      - In provided gdal_bin dir
      - Anywhere on PATH
    """
    import os, shutil, sys
    from pathlib import Path

    # 1) explicit override
    env_override = os.environ.get("SPATIALITE_PATH")
    if env_override and Path(env_override).exists():
        return env_override

    # 2) next to GDAL binaries
    candidates = [
        "mod_spatialite.dll", "spatialite.dll", "libspatialite.dll",  # Windows
        "mod_spatialite.so", "libspatialite.so",                      # Linux
        "mod_spatialite.dylib", "libspatialite.dylib",                # macOS
    ]
    for name in candidates:
        p = gdal_bin / name
        if p.exists():
            return str(p)

    # 3) search PATH
    # (Windows: these dlls usually won't be found by shutil.which, but try anyway.)
    for name in candidates:
        w = shutil.which(name)
        if w:
            return w

    # Nothing found
    return None


def divide_boundary_into_sections_from_kml():
    """
    Option 2: Split a polygon in a KML by one or more cut lines and export 1..K KMLs.
    - Uses fixed file 'GeoPackage Borders/Divide Boundary Into Sections.kml' (overridable).
    - Outputs KMLs into 'GeoPackage Borders/Output KML/'.
    - Also (optionally) clips roads per-section via GeoPandas/Shapely and exports:
        * Output Roads/<slug>_section_XX_roads_inside.gpkg (layer roads_inside_XX)
        * Output Roads/<slug>_section_XX_road_names.csv
        * Output Roads/<slug>_section_XX_road_lengths.csv

    Env toggles (unchanged):
      KML_CUT_SNAP_M, KML_CUT_NEAR_M, KML_PART_MIN_M2, KML_CUT_TOL_MIN_M, KML_CUT_TOL_CAP_M
      KML_DEBUG=1
      KML_CLIP_ROADS, KML_ROADS_PATH, KML_ROADS_LAYER, KML_NAME_COL, KML_EXCLUDE_EMPTY_NAMES
      KML_POLYGON_PATH, KML_CUTS_PATH
      SPATIALITE_PATH
    """
    from pathlib import Path
    import os, json, re, subprocess

    # ---------------- Tunables (metres, NZTM) ----------------
    SNAP_TOL_M    = float(os.environ.get("KML_CUT_SNAP_M", "5"))
    NEAR_DIST_M   = float(os.environ.get("KML_CUT_NEAR_M", "200"))
    MIN_SLIVER_M2 = float(os.environ.get("KML_PART_MIN_M2", "0.5"))
    TOL_MIN_M     = float(os.environ.get("KML_CUT_TOL_MIN_M", "0.5"))
    TOL_CAP_M     = float(os.environ.get("KML_CUT_TOL_CAP_M", str(NEAR_DIST_M)))

    RUN_ROAD_CLIP   = (os.environ.get("KML_CLIP_ROADS", "1").strip() == "1")
    ROADS_LAYER     = os.environ.get("KML_ROADS_LAYER", None)
    NAME_COL_FORCED = os.environ.get("KML_NAME_COL", None)
    EXCLUDE_EMPTY   = (os.environ.get("KML_EXCLUDE_EMPTY_NAMES", "0").strip() == "1")

    # --- helpers (fallbacks if missing) ---
    try:
        _build_gdal_env  # type: ignore[name-defined]
    except NameError:
        def _build_gdal_env(gdal_bin: "Path") -> dict:
            return os.environ.copy()

    try:
        run_utf8  # type: ignore[name-defined]
    except NameError:
        def run_utf8(cmd_list, env=None) -> subprocess.CompletedProcess:
            return subprocess.run(
                [str(x) for x in cmd_list],
                env=env, capture_output=True, text=True, encoding="utf-8", errors="replace"
            )

    try:
        _find_spatialite_binary  # type: ignore[name-defined]
    except NameError:
        def _find_spatialite_binary(gdal_bin: "Path") -> str | None:
            import shutil
            override = os.environ.get("SPATIALITE_PATH")
            if override and Path(override).exists():
                return override
            candidates = [
                "mod_spatialite.dll", "spatialite.dll", "libspatialite.dll",
                "mod_spatialite.so", "libspatialite.so",
                "mod_spatialite.dylib", "libspatialite.dylib"
            ]
            for name in candidates:
                p = gdal_bin / name
                if p.exists():
                    return str(p)
            for name in candidates:
                w = shutil.which(name)
                if w:
                    return w
            return None

    try:
        DEFAULT_TONE  # type: ignore[name-defined]
    except NameError:
        DEFAULT_TONE = "light"
    try:
        DEFAULT_COLOR_IDX  # type: ignore[name-defined]
    except NameError:
        DEFAULT_COLOR_IDX = [1, 2, 3, 4, 5, 6, 7]

    base_dir = Path(__file__).resolve().parent
    db_dir   = base_dir / "Street Database"
    gdal_bin = db_dir / "bin"
    ogr2ogr  = gdal_bin / "ogr2ogr.exe"
    ogrinfo  = gdal_bin / "ogrinfo.exe"

    roads_default = db_dir / "nz-roads-road-section-geometry.gpkg"
    roads_path = Path(os.environ.get("KML_ROADS_PATH", str(roads_default))).resolve()

    if not ogr2ogr.exists() or not ogrinfo.exists():
        print(f"❌ Missing GDAL tools. Need both:\n   - {ogr2ogr}\n   - {ogrinfo}")
        return

    # ---------------- GDAL env (+ SpatiaLite) ----------------
    env = _build_gdal_env(gdal_bin).copy()
    spat_path = _find_spatialite_binary(gdal_bin)
    if spat_path:
        env["OGR_SQLITE_LOAD_EXTENSIONS"] = "YES"
        env["OGR_SQLITE_EXT_PATH"] = spat_path
        env["SPATIALITE_SECURITY"] = "relaxed"
        env["SQLITE_EXTRA_EXTENSIONS"] = spat_path
    else:
        env["OGR_SQLITE_LOAD_EXTENSIONS"] = "NO"

    print(f"ℹ️ SpatiaLite: {spat_path if spat_path else 'NOT LOADED'}")

    def _ogr(cmd_list):
        cmd2 = [str(cmd_list[0])]
        if env.get("PROJ_LIB"):  cmd2 += ["--config", "PROJ_LIB",  env["PROJ_LIB"]]
        if env.get("PROJ_DATA"): cmd2 += ["--config", "PROJ_DATA", env["PROJ_DATA"]]
        if env.get("GDAL_DATA"): cmd2 += ["--config", "GDAL_DATA", env["GDAL_DATA"]]
        if env.get("OGR_SQLITE_LOAD_EXTENSIONS", "NO") == "YES":
            cmd2 += ["--config", "OGR_SQLITE_LOAD_EXTENSIONS", "YES"]
            if env.get("OGR_SQLITE_EXT_PATH"):
                cmd2 += ["--config", "OGR_SQLITE_EXT_PATH", env["OGR_SQLITE_EXT_PATH"]]
            if env.get("SQLITE_EXTRA_EXTENSIONS"):
                cmd2 += ["--config", "SQLITE_EXTRA_EXTENSIONS", env["SQLITE_EXTRA_EXTENSIONS"]]
        else:
            cmd2 += ["--config", "OGR_SQLITE_LOAD_EXTENSIONS", "NO"]
        return run_utf8(cmd2 + [str(x) for x in cmd_list[1:]], env=env)

    def _feature_count(layer):
        r = _ogr([ogrinfo, str(tmp), layer, "-al", "-so"])
        if r.returncode != 0:
            return 0
        m = re.search(r"Feature Count:\s+(\d+)", r.stdout or "")
        return int(m.group(1)) if m else 0

    # ---------------- IO paths ----------------
    out_dir = base_dir / "GeoPackage Borders"
    out_dir.mkdir(parents=True, exist_ok=True)
    output_kml_dir = out_dir / "Output KML"
    output_kml_dir.mkdir(parents=True, exist_ok=True)
    output_roads_dir = out_dir / "Output Roads"
    output_roads_dir.mkdir(parents=True, exist_ok=True)

    poly_kml_override = os.environ.get("KML_POLYGON_PATH", "").strip()
    cuts_kml_override = os.environ.get("KML_CUTS_PATH", "").strip()
    kml_path = Path(poly_kml_override) if poly_kml_override else (out_dir / "Divide Boundary Into Sections.kml")
    cuts_alt = Path(cuts_kml_override) if cuts_kml_override else (out_dir / "Divide Boundary Into Sections - Cuts.kml")

    if not kml_path.exists():
        print(f"❌ Required KML is missing: {kml_path}")
        print("   Tip: set KML_POLYGON_PATH env var to point to your file.")
        return

    # tmp gpkg scratch
    tmp = out_dir / "_tmp_split_from_kml.gpkg"
    try:
        tmp.unlink()
    except Exception:
        pass

    # ---------------- Import KML ----------------
    poly_filter = (
        "OGR_GEOMETRY LIKE '%Poly%' OR OGR_GEOMETRY LIKE '%POLY%' OR "
        "OGR_GEOMETRY='Polygon' OR OGR_GEOMETRY='POLYGON' OR "
        "OGR_GEOMETRY='MultiPolygon' OR OGR_GEOMETRY='MULTIPOLYGON'"
    )
    r = _ogr([ogr2ogr, "-f", "GPKG", str(tmp), str(kml_path),
              "-nln", "poly4326", "-overwrite",
              "-where", poly_filter])
    if r.returncode != 0:
        print("❌ Could not import polygon(s) from KML.")
        return

    line_filter = (
        "OGR_GEOMETRY LIKE '%Line%' OR OGR_GEOMETRY LIKE '%LINE%' OR "
        "OGR_GEOMETRY='LineString' OR OGR_GEOMETRY='LINESTRING' OR "
        "OGR_GEOMETRY='MultiLineString' OR OGR_GEOMETRY='MULTILINESTRING' OR "
        "OGR_GEOMETRY LIKE '%Track%' OR OGR_GEOMETRY LIKE '%TRACK%'"
    )
    r = _ogr([ogr2ogr, "-f", "GPKG", str(tmp), str(kml_path),
              "-nln", "cuts4326", "-overwrite",
              "-where", line_filter])
    if r.returncode != 0:
        print("❌ Could not import cut line(s) from KML.")
        return
    print("ℹ️ cuts4326:", _feature_count("cuts4326"))

    # ---------------- Reproject to NZTM ----------------
    _ogr([ogr2ogr, "-f", "GPKG", str(tmp), str(tmp), "poly4326",
          "-nln", "poly2193", "-t_srs", "EPSG:2193", "-overwrite"])
    r = _ogr([ogr2ogr, "-f", "GPKG", str(tmp), str(tmp), "cuts4326",
              "-nln", "cuts2193", "-t_srs", "EPSG:2193", "-overwrite"])
    if r.returncode != 0:
        print("❌ Could not reproject cut lines to 2193.")
        return
    print("ℹ️ cuts2193:", _feature_count("cuts2193"))

    # --- Normalize cuts to pure linework: cutsL2193 ---
    def _normalize_cuts(tmp: Path, ogr2ogr: Path) -> bool:
        """
        Normalize cut geometries into linework (cutsL2193 layer).
        Handles various SpatiaLite function variants and polygon boundaries automatically.
        Returns True if normalization produced features, else False.
        """

        def _feature_count(layer: str) -> int:
            """Count features in a given layer using ogrinfo -json."""
            r = _ogr([ogrinfo, "-json", str(tmp), layer])
            if r.returncode != 0:
                return 0
            try:
                info = json.loads(r.stdout)
                return info.get("layers", [{}])[0].get("featureCount", 0)
            except Exception:
                return 0

        # --- Try modern ST_* line merge + unary union ---
        sqlA = """
        WITH S AS (SELECT ST_Force2D(geom) AS g FROM cuts2193),
             X AS (
                SELECT ST_CollectionExtract(g, 2) AS l FROM S
                UNION ALL
                SELECT g AS l FROM S WHERE ST_Dimension(g)=1
             )
        SELECT ST_LineMerge(ST_UnaryUnion(l)) AS geom
        FROM X
        WHERE l IS NOT NULL
        """
        for sql in (
                sqlA,
                # Legacy builds (no ST_ prefix)
                sqlA.replace("ST_LineMerge", "LineMerge")
                        .replace("ST_UnaryUnion", "UnaryUnion")
                        .replace("ST_Force2D", "Force2D")
                        .replace("ST_CollectionExtract", "CollectionExtract")
                        .replace("ST_Dimension", "Dimension"),
                # Unary union only (no line merge)
                sqlA.replace("ST_LineMerge(ST_UnaryUnion", "ST_UnaryUnion")
        ):
            r = _ogr([ogr2ogr, "-f", "GPKG", str(tmp), str(tmp), "cuts2193",
                      "-nln", "cutsL2193", "-overwrite",
                      "-dialect", "SQLite", "-sql", sql])
            if r.returncode == 0 and _feature_count("cutsL2193") > 0:
                return True

        # --- Include polygon boundary from poly2193 as extra linework ---
        sqlD = """
        WITH
          P AS (SELECT ST_Buffer(ST_MakeValid(ST_Force2D(geom)), 0.0) AS g FROM poly2193),
          PB AS (SELECT ST_Boundary(g) AS l FROM P),
          C AS (SELECT ST_Force2D(geom) AS g FROM cuts2193),
          CL AS (SELECT ST_CollectionExtract(g, 2) AS l FROM C
                 UNION ALL
                 SELECT g AS l FROM C WHERE ST_Dimension(g)=1),
          L AS (SELECT l FROM CL UNION ALL SELECT l FROM PB)
        SELECT ST_UnaryUnion(l) AS geom FROM L WHERE l IS NOT NULL
        """
        r = _ogr([ogr2ogr, "-f", "GPKG", str(tmp), str(tmp),
                  "-nln", "cutsL2193", "-overwrite",
                  "-dialect", "SQLite", "-sql", sqlD])
        if r.returncode == 0 and _feature_count("cutsL2193") > 0:
            print("ℹ️ Using polygon boundary from poly2193 as cut linework.")
            return True

        # --- Last resort: explode collections and extract lines ---
        sqlE = "SELECT ST_CollectionExtract(geom, 2) AS geom FROM cuts2193 WHERE ST_Dimension(geom)=1"
        r = _ogr([ogr2ogr, "-f", "GPKG", str(tmp), str(tmp),
                  "-nln", "cutsL2193", "-overwrite",
                  "-explodecollections", "-dialect", "SQLite", "-sql", sqlE])
        if r.returncode == 0 and _feature_count("cutsL2193") > 0:
            return True

        # --- All failed ---
        print("🚨 cuts normalization failed.")
        try:
            print("stdout:\n", r.stdout)
            print("stderr:\n", r.stderr)
        except Exception:
            pass
        return False




    if os.environ.get("KML_DEBUG","").strip()=="1":
        sql_dbg_lnear = (
            "WITH "
            "P AS (SELECT ST_Buffer(ST_MakeValid(ST_Force2D(geom)), 0.0) AS geom FROM poly2193), "
            "PU AS (SELECT ST_Union(geom) AS geom FROM P), "
            "B AS (SELECT ST_Boundary(geom) AS b FROM PU), "
            "L0 AS (SELECT geom FROM cutsL2193), "
            f"LNEAR AS (SELECT ST_Intersection((SELECT geom FROM L0), ST_Buffer((SELECT geom FROM PU), {NEAR_DIST_M})) AS geom) "
            "SELECT ST_AsBinary(geom) AS g FROM LNEAR WHERE geom IS NOT NULL"
        )
        _ogr([ogr2ogr, "-f", "GeoJSON", str(out_dir / "_debug_lnear.geojson"), str(tmp),
              "-dialect", "SQLite", "-sql", sql_dbg_lnear, "-t_srs", "EPSG:4326", "-overwrite"])

        sql_dbg_lsnap = (
            "WITH "
            "P AS (SELECT ST_Buffer(ST_MakeValid(ST_Force2D(geom)), 0.0) AS geom FROM poly2193), "
            "PU AS (SELECT ST_Union(geom) AS geom FROM P), "
            "B AS (SELECT ST_Boundary(geom) AS b FROM PU), "
            "L0 AS (SELECT geom FROM cutsL2193), "
            f"LSNAP AS (SELECT ST_Snap((SELECT geom FROM L0), (SELECT b FROM B), {SNAP_TOL_M}) AS geom) "
            "SELECT ST_AsBinary(geom) AS g FROM LSNAP WHERE geom IS NOT NULL"
        )
        _ogr([ogr2ogr, "-f", "GeoJSON", str(out_dir / "_debug_lsnap.geojson"), str(tmp),
              "-dialect", "SQLite", "-sql", sql_dbg_lsnap, "-t_srs", "EPSG:4326", "-overwrite"])

    # Try to recover linework from MultiGeometry if needed
    if _feature_count("cuts2193") == 0:
        r = _ogr([
            ogr2ogr, "-f", "GPKG", str(tmp), str(kml_path),
            "-nln", "all4326_cuts", "-overwrite",
            "-explodecollections"
        ])
        if r.returncode == 0:
            _ogr([
                ogr2ogr, "-f", "GPKG", str(tmp), str(tmp), "all4326_cuts",
                "-nln", "cuts2193", "-t_srs", "EPSG:2193", "-overwrite",
                "-dialect", "SQLite",
                "-sql", (
                    "WITH X AS ("
                    "  SELECT ST_CollectionExtract(geom, 2) AS g FROM all4326_cuts "
                    "  UNION ALL "
                    "  SELECT geom AS g FROM all4326_cuts WHERE ST_Dimension(geom)=1"
                    ") "
                    "SELECT ST_LineMerge(ST_UnaryUnion(g)) AS geom FROM X "
                    "WHERE g IS NOT NULL"
                )
            ])

    if _feature_count("cuts2193") == 0 and cuts_alt.exists():
        _ogr([ogr2ogr, "-f", "GPKG", str(tmp), str(cuts_alt),
              "-nln", "cuts4326", "-overwrite",
              "-where", line_filter])
        _ogr([ogr2ogr, "-f", "GPKG", str(tmp), str(tmp), "cuts4326",
              "-nln", "cuts2193", "-t_srs", "EPSG:2193", "-overwrite"])

    if not _normalize_cuts(tmp, ogr2ogr):
        print("❌ No usable cut linework found.")
        return

    def _has_layer_feats(name): return _feature_count(name) > 0

    if not _has_layer_feats("poly2193"):
        print("ℹ️ No polygons after initial import; trying MultiGeometry extraction...")
        _ogr([
            ogr2ogr, "-f", "GPKG", str(tmp), str(kml_path),
            "-nln", "all4326", "-overwrite",
            "-explodecollections"
        ])
        _ogr([
            ogr2ogr, "-f", "GPKG", str(tmp), str(tmp), "all4326",
            "-nln", "poly2193", "-t_srs", "EPSG:2193", "-overwrite",
            "-dialect", "SQLite",
            "-sql", (
                "SELECT ST_CollectionExtract(geom, 3) AS geom "
                "FROM all4326 "
                "WHERE ST_IsEmpty(ST_CollectionExtract(geom, 3)) = 0"
            )
        ])

    if not _has_layer_feats("poly2193") and _has_layer_feats("cuts2193"):
        print("ℹ️ Still no polygons; polygonizing closed linework to derive boundary...")
        _ogr([
            ogr2ogr, "-f", "GPKG", str(tmp), str(tmp),
            "-nln", "poly2193", "-overwrite",
            "-dialect", "SQLite",
            "-sql", (
                "WITH L AS (SELECT ST_Force2D(geom) AS geom FROM cuts2193), "
                "UL AS (SELECT ST_UnaryUnion(geom) AS geom FROM L), "
                "P AS (SELECT (ST_Dump(ST_Polygonize(geom))).geom AS geom FROM UL) "
                "SELECT geom FROM P "
                "ORDER BY ST_Area(geom) DESC LIMIT 1"
            )
        ])

    if _feature_count("poly2193") == 0:
        print("❌ No polygon features found in the KML (even after recovery).")
        return
    if _feature_count("cutsL2193") == 0:
        print("❌ No LineString features found in the KML (after normalization).")
        return

    if os.environ.get("KML_DEBUG", "").strip() == "1":
        _ogr([ogr2ogr, "-f", "GeoJSON", str(out_dir / "_debug_poly.geojson"), str(tmp), "poly2193",
              "-t_srs", "EPSG:4326", "-overwrite"])
        _ogr([ogr2ogr, "-f", "GeoJSON", str(out_dir / "_debug_cuts.geojson"), str(tmp), "cutsL2193",
              "-t_srs", "EPSG:4326", "-overwrite"])

    parts_geojson = out_dir / f"{kml_path.stem}_parts.geojson"
    try:
        parts_geojson.unlink()
    except Exception:
        pass

    # ---------------- Split after Snap (Preferred) — uses PU union ----------------
    sql_split_snap = (
        "WITH "
        "P  AS (SELECT ST_Buffer(ST_MakeValid(ST_Force2D(geom)), 0.0) AS geom FROM poly2193), "
        "PU AS (SELECT ST_Union(geom) AS geom FROM P), "
        "B  AS (SELECT ST_Boundary(geom) AS geom FROM PU), "
        "L0 AS (SELECT geom FROM cutsL2193), "
        f"LNEAR AS (SELECT ST_Intersection((SELECT geom FROM L0), ST_Buffer((SELECT geom FROM PU), {NEAR_DIST_M})) AS geom), "
        f"LSNAP AS (SELECT ST_Snap((SELECT geom FROM LNEAR), (SELECT geom FROM B), {SNAP_TOL_M}) AS geom) "
        "SELECT ST_AsBinary((ST_Dump(ST_Split((SELECT geom FROM PU), (SELECT geom FROM LSNAP)))).geom) AS g "
        "FROM PU"
    )
    r = _ogr([ogr2ogr, "-f", "GeoJSON", str(parts_geojson), str(tmp),
              "-dialect", "SQLite", "-sql", sql_split_snap,
              "-t_srs", "EPSG:4326", "-overwrite"])

    # ---------------- Fallback #2: Polygonize with auto-connect (uses PU) ------
    if r.returncode != 0 or not parts_geojson.exists() or parts_geojson.stat().st_size == 0:
        print("ℹ️ Split after snapping produced no parts; trying auto-connect polygonize fallback.")
        try:
            parts_geojson.unlink()
        except Exception:
            pass

        sql_poly_ex_bridge = (
            "WITH "
            "P  AS (SELECT ST_Buffer(ST_MakeValid(ST_Force2D(geom)), 0.0) AS geom FROM poly2193), "
            "PU AS (SELECT ST_Union(geom) AS geom FROM P), "
            "B  AS (SELECT ST_Boundary(geom) AS b FROM PU), "
            "LRAW AS (SELECT ST_Force2D(geom) AS geom FROM cutsL2193), "
            f"LNEAR AS (SELECT ST_Intersection(l.geom, ST_Buffer((SELECT geom FROM PU), {NEAR_DIST_M})) AS geom "
            f"         FROM LRAW l WHERE ST_Intersects(l.geom, ST_Buffer((SELECT geom FROM PU), {NEAR_DIST_M}))), "
            "L0    AS (SELECT ST_LineMerge(ST_UnaryUnion(geom)) AS geom FROM LNEAR), "
            f"LSNAP AS (SELECT ST_Snap((SELECT geom FROM L0), (SELECT b FROM B), {SNAP_TOL_M}) AS geom), "
            "LDUMP AS (SELECT (ST_Dump(geom)).geom AS g FROM LSNAP), "
            "EP    AS (SELECT ST_StartPoint(g) AS p FROM LDUMP UNION ALL SELECT ST_EndPoint(g) AS p FROM LDUMP), "
            f"LBRIDGE AS (SELECT ST_ShortestLine(p, (SELECT b FROM B)) AS geom FROM EP "
            f"            WHERE ST_Distance(p, (SELECT b FROM B)) > {SNAP_TOL_M}), "
            "LCOL  AS (SELECT ST_UnaryUnion(ST_Collect(geom)) AS g FROM (SELECT geom FROM LSNAP UNION ALL SELECT geom FROM LBRIDGE)), "
            "W     AS (SELECT ST_Collect((SELECT b FROM B), (SELECT g FROM LCOL)) AS geom), "
            "F     AS (SELECT (ST_Dump(ST_Polygonize(geom))).geom AS geom FROM W), "
            "I     AS (SELECT (ST_Dump(ST_Intersection(F.geom, (SELECT geom FROM PU)))).geom AS geom "
            "      FROM F WHERE ST_Intersects(F.geom, (SELECT geom FROM PU))) "
            "SELECT ST_AsBinary(geom) AS g FROM I WHERE geom IS NOT NULL"
        )

        r = _ogr([ogr2ogr, "-f", "GeoJSON", str(parts_geojson), str(tmp),
                  "-dialect", "SQLite", "-sql", sql_poly_ex_bridge,
                  "-t_srs", "EPSG:4326", "-overwrite"])

    # ---------------- Fallback #3: Corridor-difference (uses PU) --------------
    if r.returncode != 0 or not parts_geojson.exists() or parts_geojson.stat().st_size == 0:
        print("ℹ️ Polygonize failed; trying corridor-difference fallback.")
        try:
            parts_geojson.unlink()
        except Exception:
            pass

        sql_diff_corridor = (
            "WITH "
            "P  AS (SELECT ST_Buffer(ST_MakeValid(ST_Force2D(geom)), 0.0) AS geom FROM poly2193), "
            "PU AS (SELECT ST_Union(geom) AS geom FROM P), "
            "B  AS (SELECT ST_Boundary(geom) AS b FROM PU), "
            "L0 AS (SELECT ST_Force2D(geom) AS geom FROM cutsL2193), "
            f"LNEAR AS (SELECT ST_Intersection((SELECT geom FROM L0), ST_Buffer((SELECT geom FROM PU), {NEAR_DIST_M})) AS geom), "
            f"LSNAP AS (SELECT ST_Snap((SELECT geom FROM LNEAR), (SELECT b FROM B), {SNAP_TOL_M}) AS geom), "
            "M AS (SELECT ST_Distance((SELECT geom FROM L0), (SELECT b FROM B)) AS m), "
            f"T AS (SELECT MIN({NEAR_DIST_M - 1.0}, MIN({TOL_CAP_M}, MAX({TOL_MIN_M}, COALESCE(m, {NEAR_DIST_M/2}) + 2.0))) AS tol FROM M), "
            "D AS (SELECT ST_Difference((SELECT geom FROM PU), "
            "                           ST_Buffer((SELECT geom FROM LSNAP), (SELECT tol FROM T))) AS geom) "
            "SELECT ST_AsBinary((ST_Dump(ST_MakeValid(geom))).geom) AS g FROM D "
            "WHERE geom IS NOT NULL"
        )

        r = _ogr([ogr2ogr, "-f", "GeoJSON", str(parts_geojson), str(tmp),
                  "-dialect", "SQLite", "-sql", sql_diff_corridor,
                  "-t_srs", "EPSG:4326", "-overwrite"])

    # ---------------- Fallback #4: Shapely split (no SQL/GEOS required) ------
    if r.returncode != 0 or not parts_geojson.exists() or parts_geojson.stat().st_size == 0:
        print("▶ Falling back to Shapely split…")
        try:
            import geopandas as gpd
            from shapely.ops import split
            # Read in 2193
            poly_gdf = gpd.read_file(str(tmp), layer="poly2193").to_crs(2193)
            cuts_gdf = gpd.read_file(str(tmp), layer="cutsL2193").to_crs(2193)
            if poly_gdf.empty or cuts_gdf.empty:
                raise RuntimeError("Empty poly or cuts")

            poly_union = poly_gdf.unary_union
            near = cuts_gdf[cuts_gdf.geometry.distance(poly_union) <= NEAR_DIST_M]
            if near.empty:
                raise RuntimeError("No near cut segments")

            linework = near.unary_union
            result = split(poly_union, linework)
            if not result or len(result.geoms) == 0:
                raise RuntimeError("Split produced no parts")

            gpd.GeoDataFrame(geometry=list(result.geoms), crs=2193)\
               .to_crs(4326).to_file(parts_geojson, driver="GeoJSON")
            print("✅ Shapely split fallback succeeded.")
        except Exception as e:
            print(f"❌ Could not produce parts from the cut line(s) after all fallbacks. ({e})")
            return

    # --- local area helper if not already defined ---
    try:
        _ring_area_m2_ll  # type: ignore[name-defined]
    except NameError:
        import math as _math
        def _ring_area_m2_ll(ring_xy_ll):
            if not ring_xy_ll or len(ring_xy_ll) < 3:
                return 0.0
            lat_avg = sum(y for _, y in ring_xy_ll) / len(ring_xy_ll)
            mx = 111320.0 * _math.cos(_math.radians(lat_avg))
            my = 110574.0
            pts = [(x * mx, y * my) for x, y in ring_xy_ll]
            area = 0.0
            for i in range(len(pts)):
                x1, y1 = pts[i]
                x2, y2 = pts[(i + 1) % len(pts)]
                area += x1 * y2 - x2 * y1
            return abs(area) * 0.5

    # ---------------- Read parts → outer rings ----------------
    def _ensure_closed(r): return r if (len(r) >= 3 and r[0] == r[-1]) else (r + [r[0]])

    try:
        with open(parts_geojson, "r", encoding="utf-8") as f:
            gj = json.load(f)
    except Exception:
        print("❌ Failed to read parts GeoJSON.")
        return

    feats = gj.get("features") or []
    if not feats:
        print("❌ No polygon parts created (empty features).")
        return

    rings = []
    for feat in feats:
        g = (feat.get("geometry") or {})
        if g.get("type") == "Polygon":
            polys = [g.get("coordinates") or []]
        elif g.get("type") == "MultiPolygon":
            polys = (g.get("coordinates") or [])
        else:
            continue

        best_ring, best_a = None, -1.0
        for poly in polys:
            if not poly or not poly[0]:
                continue
            r0 = poly[0][:-1]
            a = abs(_ring_area_m2_ll(r0))
            if a > best_a:
                best_a, best_ring = a, r0
        if best_ring and best_a >= MIN_SLIVER_M2:
            rings.append([(float(x), float(y)) for x, y in best_ring if isinstance(x, (int, float))])

    if len(rings) < 1:
        print("❌ No polygon parts created after filtering.")
        return
    if len(rings) == 1:
        print("ℹ️ The cut line(s) did not split the polygon (still 1 part).")

    rings.sort(key=lambda r: -abs(_ring_area_m2_ll(r)))  # stable numbering

    # ---------------- KML writeout ----------------
    COLORS = [
        ("blue",   "ff0000"),
        ("green",  "00ff00"),
        ("red",    "0000ff"),
        ("purple", "800080"),
        ("grey",   "808080"),
        ("yellow", "00ffff"),
        ("orange", "00a5ff"),
    ]
    ALPHA = {"light": "66", "medium": "cc"}
    try:
        tone = (os.environ.get("TONE", DEFAULT_TONE) or "light").strip().lower()
    except Exception:
        tone = "light"
    tone = tone if tone in ALPHA else "light"
    outline_width = 2
    outline_alpha = "ff"

    try:
        chosen_idx = [i for i in DEFAULT_COLOR_IDX if 1 <= i <= len(COLORS)] or [1]
    except Exception:
        chosen_idx = [1]

    suburb_slug = re.sub(r'[^a-z0-9_]+','_', kml_path.stem.lower())
    def _color_for_idx(i):
        idx = chosen_idx[(i % len(chosen_idx))]
        return COLORS[idx - 1]

    K = len(rings)
    for si, ring in enumerate(rings, start=1):
        cname, bbggrr = _color_for_idx(si - 1)
        fill_color  = f"{ALPHA[tone]}{bbggrr}"
        line_color  = f"{outline_alpha}{bbggrr}"
        kml_name    = f"{kml_path.stem} — Section {si}/{K}"
        label_text  = f"{kml_path.stem} {si}"
        kml_path_out = output_kml_dir / f"{suburb_slug}_section_{si:02d}.kml"
        txt_coords   = out_dir / f"{suburb_slug}_section_{si:02d}_coords.txt"

        with open(txt_coords, "w", encoding="utf-8") as outf:
            for x, y in (ring + [ring[0]] if ring and ring[0] != ring[-1] else ring):
                outf.write(f"{x},{y}\n")

        def _kml_multigeom_with_label(rings_ll, poly_name, label_text, line_color, poly_color, width):
            altitude_m = 100
            def _area_weighted_centroid(rings_ll):
                A = Cx = Cy = 0.0
                for r in rings_ll:
                    c = _ensure_closed(r)
                    Ai = Cxi = Cyi = 0.0
                    for i in range(len(c) - 1):
                        x1, y1 = c[i]; x2, y2 = c[i + 1]
                        cross = x1 * y2 - x2 * y1
                        Ai  += cross
                        Cxi += (x1 + x2) * cross
                        Cyi += (y1 + y2) * cross
                    Ai *= 0.5
                    if abs(Ai) < 1e-12:
                        xs = [x for x, _ in r]; ys = [y for _, y in r]
                        cx = sum(xs) / len(xs); cy = sum(ys) / len(ys)
                    else:
                        cx = Cxi / (6.0 * Ai); cy = Cyi / (6.0 * Ai)
                    a = abs(Ai); A += a; Cx += cx * a; Cy += cy * a
                return ((Cx / A, Cy / A) if A > 0 else (0.0, 0.0))

            cx, cy = _area_weighted_centroid(rings_ll)
            parts_xml = []
            for r in rings_ll:
                coords = " ".join(f"{x},{y},{altitude_m}" for x, y in _ensure_closed(r))
                parts_xml.append(f"""<Placemark>
  <Style>
    <LineStyle><color>{line_color}</color><width>{width}</width></LineStyle>
    <PolyStyle><color>{poly_color}</color><fill>1</fill><outline>1</outline></PolyStyle>
  </Style>
  <Polygon>
    <tessellate>1</tessellate>
    <altitudeMode>relativeToGround</altitudeMode>
    <outerBoundaryIs><LinearRing><coordinates>{coords}</coordinates></LinearRing></outerBoundaryIs>
  </Polygon>
</Placemark>""")
            return f"""<?xml version="1.0" encoding="utf-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
  <name>{poly_name}</name>
  {''.join(parts_xml)}
  <Placemark>
    <name>{label_text}</name>
    <Point><altitudeMode>relativeToGround</altitudeMode><coordinates>{cx},{cy},{altitude_m}</coordinates></Point>
  </Placemark>
</Document>
</kml>"""

        kml_xml = _kml_multigeom_with_label([ring], kml_name, label_text, line_color, fill_color, outline_width)
        kml_path_out.write_text(kml_xml, encoding="utf-8")
        print(f"✅ Section {si}/{K} → {kml_path_out}")
        print(f"📝 Section {si} coords → {txt_coords}")

    print(f"✅ Done. Created {K} section KMLs in: {output_kml_dir}")

    # ----------------------- GeoPandas road clipping -------------------------
    if not RUN_ROAD_CLIP:
        print("ℹ️ KML_CLIP_ROADS=0 → skipping road clipping.")
        return
    try:
        import geopandas as gpd
        import pandas as pd
        from shapely.geometry import Polygon
        from shapely.ops import unary_union, transform
        from shapely.errors import GEOSException
    except Exception as e:
        print(f"ℹ️ Road clipping skipped (GeoPandas/Shapely not available): {e}")
        return

    NZTM = 2193
    def _force_2d_gdf(gdf: 'gpd.GeoDataFrame') -> 'gpd.GeoDataFrame':
        def _to2d(geom):
            if geom is None or geom.is_empty:
                return geom
            try:
                return transform(lambda x, y, z=None: (x, y), geom)
            except GEOSException:
                return geom
        gdf = gdf.copy()
        gdf["geometry"] = gdf.geometry.apply(_to2d)
        return gdf

    def _read_roads(roads_path: str | Path, layer: str | None = None) -> 'gpd.GeoDataFrame':
        rp = str(roads_path)
        gdf = gpd.read_file(rp, layer=layer) if layer else gpd.read_file(rp)
        if gdf.empty:
            raise RuntimeError("Roads layer is empty.")
        gdf = _force_2d_gdf(gdf)
        gdf["geometry"] = gdf.geometry.buffer(0)
        gdf = gdf[~gdf.geometry.is_empty & gdf.geometry.notnull()]
        return gdf.to_crs(NZTM)

    def _pick_name_column(gdf: 'gpd.GeoDataFrame', override: str | None = None) -> str | None:
        if override and override in gdf.columns:
            return override
        candidates = [
            "road_name","RoadName","full_road_name","rd_name",
            "name","Name","street","Street","streetname","StreetName",
            "ROAD_NAME","NAME"
        ]
        for c in candidates:
            if c in gdf.columns: return c
        for c in gdf.columns:
            if "name" in str(c).lower(): return c
        return None

    def _normalize_names(series: 'pd.Series') -> 'pd.Series':
        s = series.astype("string").fillna("").str.strip()
        s = s.str.replace(r"\s+", " ", regex=True)
        s = s.apply(lambda t: t if t.isupper() else t.title())
        s = s.replace({"": pd.NA}).dropna()
        return s

    try:
        roads_gdf = _read_roads(roads_path, ROADS_LAYER)
    except Exception as e:
        print(f"⚠️ Could not read roads dataset '{roads_path}': {e}")
        return

    for si, ring in enumerate(rings, start=1):
        try:
            poly_geom = Polygon(ring + [ring[0]])
            if not poly_geom.is_valid:
                poly_geom = poly_geom.buffer(0)
            import geopandas as gpd
            poly_gdf = gpd.GeoDataFrame({"id":[1]}, geometry=[poly_geom], crs=4326).to_crs(NZTM)
        except Exception as e:
            print(f"⚠️ Section {si}: could not build polygon: {e}")
            continue

        bbox = poly_gdf.geometry.iloc[0].bounds
        roads_pref = roads_gdf.cx[bbox[0]:bbox[2], bbox[1]:bbox[3]]
        if roads_pref.empty:
            roads_pref = roads_gdf

        try:
            hits = gpd.sjoin(roads_pref, poly_gdf, predicate="intersects", how="inner")
            if "index_right" in hits.columns:
                hits = hits.drop(columns="index_right", errors="ignore")
        except Exception:
            hits = roads_pref

        try:
            inside = gpd.overlay(hits, poly_gdf, how="intersection", keep_geom_type=True)
        except Exception as e:
            print(f"⚠️ Section {si}: overlay failed: {e}")
            continue

        if inside.empty:
            print(f"ℹ️ Section {si}: no road segments intersect the polygon.")
            continue

        suburb_slug = re.sub(r'[^a-z0-9_]+','_', kml_path.stem.lower())
        out_gpkg = output_roads_dir / f"{suburb_slug}_section_{si:02d}_roads_inside.gpkg"
        out_layer = f"roads_inside_{si:02d}"
        try:
            inside.to_file(out_gpkg, layer=out_layer, driver="GPKG")
            print(f"✅ Section {si}: wrote clipped roads → {out_gpkg} (layer='{out_layer}')  [{len(inside)} features]")
        except Exception as e:
            print(f"⚠️ Section {si}: failed to write GPKG: {e}")
            continue

        name_col = _pick_name_column(inside, NAME_COL_FORCED)
        if not name_col:
            print(f"ℹ️ Section {si}: no obvious name column; skipping CSV exports.")
            continue

        inside["__name"] = _normalize_names(inside[name_col])
        if EXCLUDE_EMPTY:
            inside = inside[inside["__name"].notna() & (inside["__name"] != "")]

        names_csv = output_roads_dir / f"{suburb_slug}_section_{si:02d}_road_names.csv"
        try:
            names = (inside["__name"]
                     .dropna()
                     .drop_duplicates()
                     .sort_values()
                     .reset_index(drop=True)
                     .to_frame(name="street_name"))
            names.to_csv(names_csv, index=False)
            print(f"✅ Section {si}: wrote unique street names → {names_csv}  [{len(names)} names]")
        except Exception as e:
            print(f"⚠️ Section {si}: failed to write names CSV: {e}")

        lengths_csv = output_roads_dir / f"{suburb_slug}_section_{si:02d}_road_lengths.csv"
        try:
            inside["length_m"] = inside.geometry.length
            lengths = (inside.dropna(subset=["__name"])
                             .groupby("__name", as_index=False)["length_m"]
                             .sum()
                             .rename(columns={"__name": "street_name"})
                             .sort_values("length_m", ascending=False))
            lengths.to_csv(lengths_csv, index=False)
            print(f"✅ Section {si}: wrote per-street lengths → {lengths_csv}")
        except Exception as e:
            print(f"⚠️ Section {si}: failed to write lengths CSV: {e}")

    print(f"✅ Road clipping complete. Outputs in: {output_roads_dir}")

from shapely.geometry import Polygon, LineString
from shapely.ops import split, unary_union
import fiona
from pathlib import Path
import json, re


from shapely.geometry import Polygon, LineString
from shapely.ops import split, unary_union
import geopandas as gpd
import re, os, json
from pathlib import Path


def divide_polygon_by_cut_lines_from_kml(kml_path: Path = None):
    """
    Reads a KML with one polygon and one or more cut lines.
    Automatically detects intersections, splits the polygon into multiple parts,
    and exports each part as KML + coordinates TXT.
    Uses tint/color selection similar to _finish_exports_from_geojson.
    """
    base_dir = Path(__file__).resolve().parent
    out_dir = base_dir / "GeoPackage Borders"
    output_kml_dir = out_dir / "Output KML"
    output_kml_dir.mkdir(parents=True, exist_ok=True)

    if kml_path is None:
        kml_path = out_dir / "Divide Boundary Into Sections.kml"
    if not kml_path.exists():
        print(f"❌ Missing KML file: {kml_path}")
        return

    # --- Read polygon + cut lines ---
    try:
        gdf = gpd.read_file(str(kml_path))
    except Exception as e:
        print(f"❌ Failed to read KML: {e}")
        return

    polys = gdf[gdf.geometry.geom_type.isin(["Polygon","MultiPolygon"])]
    lines = gdf[gdf.geometry.geom_type.isin(["LineString","MultiLineString"])]

    if polys.empty:
        print("❌ No polygon found in KML.")
        return
    if lines.empty:
        print("❌ No cut lines found in KML.")
        return

    poly_geom = polys.geometry.iloc[0]
    if poly_geom.geom_type == "MultiPolygon":
        poly_geom = max(poly_geom.geoms, key=lambda p: p.area)

    # Ensure the base polygon is land-only (uses LAND_MASK_PATH from Step 1)
    try:
        base_dir = Path(__file__).resolve().parent
        out_dir = base_dir / "GeoPackage Borders"
        out_dir.mkdir(parents=True, exist_ok=True)

        # minimal GDAL env to run _clip_to_land
        db_dir = base_dir / "Street Database"
        gdal_bin = db_dir / "bin"
        env = _build_gdal_env(gdal_bin)

        tmp_in = out_dir / "_tmp_kml_poly_in.geojson"
        tmp_out = out_dir / "_tmp_kml_poly_land.geojson"

        # write current polygon → GeoJSON (WGS84)
        gpd.GeoDataFrame(geometry=[poly_geom], crs=gdf.crs).to_crs(4326).to_file(tmp_in, driver="GeoJSON")

        landed = _clip_to_land(tmp_in, tmp_out, gdal_bin=gdal_bin, env=env)
        if landed and landed.exists():
            from shapely.geometry import shape
            gj = json.loads(landed.read_text(encoding="utf-8"))
            feats = gj.get("features") or []
            if feats:
                poly_geom = shape(feats[0]["geometry"])
    except Exception as _e:
        print(f"ℹ️ KML land-clip skipped: {_e}")

    cut_geom = unary_union(lines.geometry)

    # --- Split polygon ---
    try:
        result = split(poly_geom, cut_geom)
    except Exception as e:
        print(f"❌ Split failed: {e}")
        return

    if len(result.geoms) < 2:
        print("⚠️ Split produced less than 2 parts. Check if cut lines intersect properly.")
        return

    print(f"✅ Split into {len(result.geoms)} parts.")

    # --- Tint/color logic (same as Option 1) ---
    COLORS = [
        ("blue", "ff0000"),
        ("green", "00ff00"),
        ("red", "0000ff"),
        ("purple", "800080"),
        ("grey", "808080"),
        ("yellow", "00ffff"),
        ("orange", "00a5ff"),
    ]
    ALPHA = {"light": "66", "medium": "cc"}
    outline_width = 2
    outline_alpha = "ff"

    tone = (os.environ.get("TONE", DEFAULT_TONE) or "light").strip().lower()
    tone = tone if tone in ALPHA else "light"

    print("\nTint colors (Pick A Colour):")
    for ci, (name, _) in enumerate(COLORS, 1):
        print(f"  {ci}. {name.title()}")
    print(f"  (Default index(es): {DEFAULT_COLOR_IDX} | Tone: {tone})")

    if NON_INTERACTIVE:
        chosen_idx = [i for i in DEFAULT_COLOR_IDX if 1 <= i <= len(COLORS)] or [1]
        print(f"Select color(s) by number: (1-7) [auto]: {','.join(str(i) for i in chosen_idx)}")
    else:
        sel = input("Select color(s) by number: (1-7, comma-separated) [default: 1]: ").strip()
        if not sel:
            chosen_idx = [1]
            print("Using default: 1")
        else:
            chosen_idx = [int(s) for s in sel.split(",") if s.strip().isdigit()]
            chosen_idx = [n for n in chosen_idx if 1 <= n <= len(COLORS)] or [1]

    # --- Helper for writing KML ---
    def _write_kml(coords, out_path: Path, label: str, line_color: str, poly_color: str):
        coords_str = " ".join(f"{x},{y},100" for x, y in coords)  # altitude fixed 100
        kml = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
  <name>{label}</name>
  <Placemark>
    <name>{label}</name>
    <Style>
      <LineStyle><color>{line_color}</color><width>{outline_width}</width></LineStyle>
      <PolyStyle><color>{poly_color}</color></PolyStyle>
    </Style>
    <Polygon>
      <tessellate>1</tessellate>
      <outerBoundaryIs>
        <LinearRing>
          <coordinates>{coords_str}</coordinates>
        </LinearRing>
      </outerBoundaryIs>
    </Polygon>
  </Placemark>
</Document>
</kml>"""
        out_path.write_text(kml, encoding="utf-8")

    # --- Export each resulting polygon ---
    suburb_name = polys.iloc[0].get('Name', 'section')
    suburb_slug = re.sub(r'[^a-z0-9_]+', '_', str(suburb_name).lower())

    for i, geom in enumerate(result.geoms, start=1):
        # convert to 2D coordinates, ignoring Z
        coords = [(x, y) for x, y, *rest in geom.exterior.coords]

        # TXT coordinates
        txt_path = out_dir / f"{suburb_slug}_section_{i:02d}_coords.txt"
        with open(txt_path, "w", encoding="utf-8") as outf:
            for x, y in coords:
                outf.write(f"{x},{y}\n")

        # choose color (cycle through chosen_idx if fewer colors than parts)
        color_name, bbggrr = COLORS[chosen_idx[(i-1) % len(chosen_idx)] - 1]
        fill_color = f"{ALPHA[tone]}{bbggrr}"
        line_color = f"{outline_alpha}{bbggrr}"

        kml_label = f"{suburb_name.title()} Section {i}"
        kml_path = output_kml_dir / f"{suburb_slug}_section_{i:02d}_{color_name}_{tone}.kml"
        _write_kml(coords, kml_path, kml_label, line_color, fill_color)

        print(f"✅ Section {i} KML → {kml_path}")
        print(f"📝 Section {i} coordinates → {txt_path}")

    print("✅ Done splitting via cut lines.")



def _write_kml_from_coords(coords, out_path: Path, label: str):
    """Helper to create a simple KML polygon with a label."""
    coords_str = " ".join(f"{x},{y},100" for x,y in coords)
    kml = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
  <name>{label}</name>
  <Placemark>
    <name>{label}</name>
    <Style>
      <LineStyle><color>ff0000ff</color><width>2</width></LineStyle>
      <PolyStyle><color>660000ff</color></PolyStyle>
    </Style>
    <Polygon>
      <tessellate>1</tessellate>
      <outerBoundaryIs>
        <LinearRing>
          <coordinates>{coords_str}</coordinates>
        </LinearRing>
      </outerBoundaryIs>
    </Polygon>
  </Placemark>
</Document>
</kml>"""
    out_path.write_text(kml, encoding="utf-8")



def density_valley_split(hull, points, k):
    """
    Split the hull into k compact bands by cutting along the principal axis
    (and its orthogonal), snapping the cut positions to density valleys.
    Returns (parts, method_tag) where method_tag is 'valley-axis' or 'valley-ortho'.
    """
    import math
    if not hull or not points or k < 2:
        return [hull], "valley"

    # --- local helpers (self-contained) ---
    def _poly_area(poly):
        if len(poly) < 3: return 0.0
        return 0.5 * sum(
            poly[i][0]*poly[(i+1)%len(poly)][1] - poly[(i+1)%len(poly)][0]*poly[i][1]
            for i in range(len(poly))
        )

    def _clip_halfplane(poly, a, b, c, keep_ge=True):
        if not poly: return []
        def side(x, y): return a*x + b*y + c
        keep = (lambda s: s >= 0) if keep_ge else (lambda s: s <= 0)
        out = []
        for i in range(len(poly)):
            x1, y1 = poly[i]; x2, y2 = poly[(i+1) % len(poly)]
            s1, s2 = side(x1, y1), side(x2, y2)
            i1, i2 = keep(s1), keep(s2)
            if i1 and i2:
                out.append((x2, y2))
            elif i1 and not i2:
                dx, dy = x2-x1, y2-y1; denom = a*dx + b*dy
                if denom != 0:
                    t = - (a*x1 + b*y1 + c) / denom
                    out.append((x1 + t*dx, y1 + t*dy))
            elif (not i1) and i2:
                dx, dy = x2-x1, y2-y1; denom = a*dx + b*dy
                if denom != 0:
                    t = - (a*x1 + b*y1 + c) / denom
                    out.append((x1 + t*dx, y1 + t*dy))
                out.append((x2, y2))
        if len(out) >= 3 and abs(_poly_area(out)) > 1e-12:
            return out
        return []

    def _partition_along_vector_bounds(hull, v, bounds):
        vx, vy = v
        parts=[]
        for i in range(len(bounds)-1):
            a1, a2 = bounds[i], bounds[i+1]
            poly = hull[:]
            poly = _clip_halfplane(poly, vx, vy, -a1, True)   # vx*x + vy*y >= a1
            poly = _clip_halfplane(poly, -vx, -vy, +a2, True) # vx*x + vy*y <= a2
            parts.append(poly)
        return parts

    def _principal_axis(points):
        n=len(points)
        mx=sum(x for x,_ in points)/n; my=sum(y for _,y in points)/n
        sxx=sum((x-mx)*(x-mx) for x,_ in points)/n
        syy=sum((y-my)*(y-my) for _,y in points)/n
        sxy=sum((x-mx)*(y-my) for x,y in points)/n
        angle = 0.5 * math.atan2(2*sxy, (sxx - syy))
        vx, vy = math.cos(angle), math.sin(angle)
        if vx < 0: vx, vy = -vx, -vy
        return (vx, vy)

    def _valley_bounds(points, v, k, bins=64, smooth=5):
        vx,vy=v
        projs=[vx*x+vy*y for x,y in points]
        lo,hi=min(projs),max(projs)
        if hi<=lo: return [lo,hi]
        bw=(hi-lo)/bins
        hist=[0]*bins
        for p in projs:
            idx=min(bins-1, max(0, int((p-lo)/bw)))
            hist[idx]+=1
        # smooth
        sh=[0]*bins
        for i in range(bins):
            s=c=0
            for j in range(i-smooth, i+smooth+1):
                if 0<=j<bins:
                    s+=hist[j]; c+=1
            sh[i]=s/float(max(1,c))
        # quantiles snapped to local minima
        total=sum(hist) or 1
        cum=[0]
        for h in hist: cum.append(cum[-1]+h)
        def quant_to_idx(q):
            target=q*total
            for i in range(1,len(cum)):
                if cum[i]>=target: return min(len(hist)-1,i-1)
            return len(hist)-1
        cuts=[]
        for i in range(1,k):
            qi=i/k
            ci=quant_to_idx(qi)
            window=range(max(0,ci-3), min(len(hist),ci+4))
            best=min(window, key=lambda j: (sh[j], abs(j-ci)))
            cuts.append(best)
        bounds=[lo]+[lo+(c+0.5)*bw for c in cuts]+[hi]
        return bounds

    def _worst_aspect_ratio(parts):
        ratios=[]
        for poly in parts:
            if len(poly)<3: continue
            xs=[x for x,_ in poly]; ys=[y for _,y in poly]
            w=max(xs)-min(xs); h=max(ys)-min(ys)
            r = max(w,h)/max(1e-9,min(w,h))
            ratios.append(r)
        return max(ratios) if ratios else 1e9

    # Try principal axis and its orthogonal; pick more compact tiling
    v1 = _principal_axis(points)
    v2 = (-v1[1], v1[0])
    b1 = _valley_bounds(points, v1, k)
    b2 = _valley_bounds(points, v2, k)
    parts1 = _partition_along_vector_bounds(hull, v1, b1)
    parts2 = _partition_along_vector_bounds(hull, v2, b2)
    return (parts1, "valley-axis") if _worst_aspect_ratio(parts1) <= _worst_aspect_ratio(parts2) else (parts2, "valley-ortho")


def ensure_roads_layer():
    base_dir = Path(__file__).resolve().parent
    db_dir   = base_dir / "Street Database"
    target   = db_dir / "nz-addresses.gpkg"
    source   = db_dir / "nz-roads-road-section-geometry.gpkg"
    ogr2ogr  = db_dir / "bin" / "ogr2ogr.exe"
    ogrinfo  = db_dir / "bin" / "ogrinfo.exe"

    env = _build_gdal_env(db_dir / "bin")

    # Already imported?
    try:
        j = run_utf8([str(ogrinfo), "-json", str(target)], check=True, env=env)
        data = json.loads(j.stdout)
        if any((lyr.get("name") == "nz_roads") for lyr in (data.get("layers") or [])):
            return
    except Exception:
        pass

    # Find a line layer in the source GPKG
    j = run_utf8([str(ogrinfo), "-json", str(source)], check=True, env=env)
    layers = (json.loads(j.stdout).get("layers") or [])
    src_layer = None
    for lyr in layers:
        g = (lyr.get("geometryType") or "").lower()
        if "line" in g:
            src_layer = lyr.get("name")
            break
    if not src_layer and layers:
        src_layer = layers[0].get("name")

    if not src_layer:
        print("❌ No line layer found in roads GPKG.")
        return

    # Build command with explicit --config flags (helps when env is ignored)
    cmd = [str(ogr2ogr)]
    if env.get("PROJ_LIB"):
        cmd += ["--config", "PROJ_LIB", env["PROJ_LIB"]]
    if env.get("PROJ_DATA"):
        cmd += ["--config", "PROJ_DATA", env["PROJ_DATA"]]
    if env.get("GDAL_DATA"):
        cmd += ["--config", "GDAL_DATA", env["GDAL_DATA"]]

    cmd += [
        "-f", "GPKG", str(target),
        "-t_srs", "EPSG:4326",
        "-nln", "nz_roads",
        str(source),
        src_layer
    ]

    r = run_utf8(cmd, env=env)
    if r.returncode != 0:
        print("❌ ogr2ogr error:\n", (r.stderr or r.stdout))
    else:
        print("✅ Imported roads layer → nz_roads")


def _clip_polygon_by_road_buffer(roads_gpkg: Path,
                                 suburb_geojson: Path,
                                 gdal_bin: Path,
                                 env: dict,
                                 buffer_m: float = 50.0) -> Path | None:
    """
    Build a 'road corridor' by buffering roads in NZTM2000 (EPSG:2193),
    dissolve to one mask, intersect with the suburb polygon, and export back
    to GeoJSON (EPSG:4326). Returns the clipped GeoJSON path or None.

    Strategy:
      1) Force a consistent geometry column name ('geom') across intermediates.
      2) Try fast SQL buffering (SpatiaLite/GEOS).
      3) If that fails, use a raster fallback (no SpatiaLite/GEOS).
    """
    GEOM_COL = "geom"  # enforce this everywhere

    ogr2ogr  = gdal_bin / "ogr2ogr.exe"
    ogrinfo  = gdal_bin / "ogrinfo.exe"
    gdal_ras = gdal_bin / "gdal_rasterize.exe"
    py_exe   = gdal_bin / "python.exe"  # typical for OSGeo4W/GDAL bundles
    gd_prox  = gdal_bin / "gdal_proximity.py"
    gd_calc  = gdal_bin / "gdal_calc.py"
    gd_poly  = gdal_bin / "gdal_polygonize.py"

    if not roads_gpkg.exists():
        print(f"⚠️ Roads GPKG not found: {roads_gpkg}")
        return None

    # --- Make a copy of env and attempt to enable SpatiaLite extensions ----
    env = (env or os.environ).copy()
    # Allow extension loading in SQLite dialect:
    env.setdefault("OGR_SQLITE_LOAD_EXTENSIONS", "YES")

    # Best-effort: point to a spatialite module if present in bin
    candidates = [
        gdal_bin / "mod_spatialite.dll",
        gdal_bin / "spatialite.dll",
        gdal_bin / "libspatialite.dll",
        gdal_bin / "mod_spatialite.so",   # linux
        gdal_bin / "libspatialite.so",    # linux
        gdal_bin / "mod_spatialite.dylib" # mac
    ]
    spat = next((str(p) for p in candidates if p.exists()), None)
    if spat:
        env.setdefault("OGR_SQLITE_EXT_PATH", spat)
        env.setdefault("SPATIALITE_SECURITY", "relaxed")

    def _run(cmd):
        cmd2 = [str(cmd[0])]
        if env.get("PROJ_LIB"):  cmd2 += ["--config", "PROJ_LIB",  env["PROJ_LIB"]]
        if env.get("PROJ_DATA"): cmd2 += ["--config", "PROJ_DATA", env["PROJ_DATA"]]
        if env.get("GDAL_DATA"): cmd2 += ["--config", "GDAL_DATA", env["GDAL_DATA"]]
        cmd2 += [str(x) for x in cmd[1:]]
        return run_utf8(cmd2, env=env)

    # --- Find a line layer in the roads GPKG --------------------------------
    try:
        j = run_utf8([str(ogrinfo), "-json", str(roads_gpkg)], check=True, env=env)
        layers = (json.loads(j.stdout).get("layers") or [])
    except Exception as e:
        print(f"⚠️ Could not inspect roads GPKG: {e}")
        return None

    road_layer = None
    for lyr in layers:
        g = (lyr.get("geometryType") or "").lower()
        nm = (lyr.get("name") or "")
        if "line" in g or "multiline" in g or "line" in nm.lower():
            road_layer = nm
            break
    if not road_layer and layers:
        road_layer = layers[0].get("name")

    if not road_layer:
        print("⚠️ No line layer found in roads GPKG.")
        return None

    work = suburb_geojson.parent
    tmp_gpkg = work / "tmp_roads_clip.gpkg"
    try:
        if tmp_gpkg.exists():
            tmp_gpkg.unlink()
    except Exception:
        pass

    # 1) Suburb (4326) → tmp GPKG (suburb4326), set GEOMETRY_NAME=geom
    r = _run([ogr2ogr, "-f", "GPKG", str(tmp_gpkg), str(suburb_geojson),
              "-nln", "suburb4326",
              "-lco", f"GEOMETRY_NAME={GEOM_COL}",
              "-lco", "IDENTIFIER=suburb4326",
              "-lco", "DESCRIPTION="])
    if r.returncode != 0:
        print("⚠️ Could not import suburb polygon:", r.stderr or r.stdout)
        return None

    # 2) Roads → 2193 (roads2193), GEOMETRY_NAME=geom
    r = _run([ogr2ogr, "-f", "GPKG", str(tmp_gpkg), str(roads_gpkg), road_layer,
              "-nln", "roads2193", "-t_srs", "EPSG:2193", "-overwrite",
              "-lco", f"GEOMETRY_NAME={GEOM_COL}",
              "-lco", "IDENTIFIER=roads2193",
              "-lco", "DESCRIPTION="])
    if r.returncode != 0:
        print("⚠️ Could not import/reproject roads:", r.stderr or r.stdout)
        return None

    # 3) Suburb → 2193 (suburb2193), GEOMETRY_NAME=geom
    r = _run([ogr2ogr, "-f", "GPKG", str(tmp_gpkg), str(tmp_gpkg), "suburb4326",
              "-nln", "suburb2193", "-t_srs", "EPSG:2193", "-overwrite",
              "-lco", f"GEOMETRY_NAME={GEOM_COL}",
              "-lco", "IDENTIFIER=suburb2193",
              "-lco", "DESCRIPTION="])
    if r.returncode != 0:
        print("⚠️ Could not reproject suburb to 2193:", r.stderr or r.stdout)
        return None

    # 4) Read suburb bbox and pad by buffer
    r = _run([ogrinfo, "-json", str(tmp_gpkg), "suburb2193"])
    if r.returncode != 0:
        print("⚠️ Could not read suburb layer bbox:", r.stderr or r.stdout)
        return None
    try:
        info = json.loads(r.stdout)
        ext = (((info.get("layers") or [])[0] or {}).get("extent") or {})

        minx, miny = ext.get("xmin"), ext.get("ymin")
        maxx, maxy = ext.get("xmax"), ext.get("ymax")
        if None in (minx, miny, maxx, maxy):
            raise ValueError("No extent")
        pad = max(50.0, float(buffer_m))
        minx -= pad; miny -= pad; maxx += pad; maxy += pad
    except Exception:
        minx = miny = maxx = maxy = None

    # 5) Crop roads to AOI (roadsCrop2193), GEOMETRY_NAME=geom
    if minx is not None:
        r = _run([ogr2ogr, "-f", "GPKG", str(tmp_gpkg), str(tmp_gpkg), "roads2193",
                  "-nln", "roadsCrop2193", "-overwrite",
                  "-spat", str(minx), str(miny), str(maxx), str(maxy),
                  "-lco", f"GEOMETRY_NAME={GEOM_COL}",
                  "-lco", "IDENTIFIER=roadsCrop2193",
                  "-lco", "DESCRIPTION="])
        if r.returncode != 0:
            print("⚠️ Roads bbox crop failed; using full roads2193:", r.stderr or r.stdout)
            r = _run([ogr2ogr, "-f", "GPKG", str(tmp_gpkg), str(tmp_gpkg), "roads2193",
                      "-nln", "roadsCrop2193", "-overwrite",
                      "-lco", f"GEOMETRY_NAME={GEOM_COL}",
                      "-lco", "IDENTIFIER=roadsCrop2193",
                      "-lco", "DESCRIPTION="])
            if r.returncode != 0:
                print("⚠️ Could not create roadsCrop2193:", r.stderr or r.stdout)
                return None
    else:
        r = _run([ogr2ogr, "-f", "GPKG", str(tmp_gpkg), str(tmp_gpkg), "roads2193",
                  "-nln", "roadsCrop2193", "-overwrite",
                  "-lco", f"GEOMETRY_NAME={GEOM_COL}",
                  "-lco", "IDENTIFIER=roadsCrop2193",
                  "-lco", "DESCRIPTION="])
        if r.returncode != 0:
            print("⚠️ Could not create roadsCrop2193:", r.stderr or r.stdout)
            return None

    # ----------------- PATH A: SQL / SpatiaLite (fast) ----------------------
    def _sql_buffer_union_intersect() -> bool:
        # Buffer
        sql_buf = f"SELECT ST_Buffer({GEOM_COL}, {float(buffer_m)}) AS {GEOM_COL} FROM roadsCrop2193"
        r = _run([ogr2ogr, "-f", "GPKG", str(tmp_gpkg), str(tmp_gpkg),
                  "-nln", "roadsBuf", "-overwrite",
                  "-dialect", "SQLite", "-sql", sql_buf,
                  "-lco", f"GEOMETRY_NAME={GEOM_COL}",
                  "-lco", "IDENTIFIER=roadsBuf",
                  "-lco", "DESCRIPTION="])
        if r.returncode != 0:
            print("ℹ️ SQL ST_Buffer failed (SpatiaLite/GEOS likely missing).")
            return False

        # Union
        sql_union = f"SELECT ST_Union({GEOM_COL}) AS {GEOM_COL} FROM roadsBuf"
        r = _run([ogr2ogr, "-f", "GPKG", str(tmp_gpkg), str(tmp_gpkg),
                  "-nln", "roadsUnion", "-overwrite",
                  "-dialect", "SQLite", "-sql", sql_union,
                  "-lco", f"GEOMETRY_NAME={GEOM_COL}",
                  "-lco", "IDENTIFIER=roadsUnion",
                  "-lco", "DESCRIPTION="])
        if r.returncode != 0:
            print("ℹ️ SQL ST_Union failed.")
            return False

        # Intersect
        sql_ix = (f"SELECT ST_Intersection(a.{GEOM_COL}, b.{GEOM_COL}) AS {GEOM_COL} "
                  f"FROM suburb2193 a, roadsUnion b")
        r = _run([ogr2ogr, "-f", "GPKG", str(tmp_gpkg), str(tmp_gpkg),
                  "-nln", "clipped2193", "-overwrite",
                  "-dialect", "SQLite", "-sql", sql_ix,
                  "-lco", f"GEOMETRY_NAME={GEOM_COL}",   # <-- fixed comma here
                  "-lco", "IDENTIFIER=clipped2193",
                  "-lco", "DESCRIPTION="])
        if r.returncode != 0:
            print("ℹ️ SQL ST_Intersection failed.")
            return False

        return True

    # Try SQL path first
    if _sql_buffer_union_intersect():
        out = suburb_geojson.with_name(suburb_geojson.stem + "_roadclipped.geojson")
        r = _run([ogr2ogr, "-f", "GeoJSON", str(out), str(tmp_gpkg), "clipped2193",
                  "-t_srs", "EPSG:4326", "-overwrite"])
        if r.returncode == 0:
            print(f"✅ Road-clipped polygon → {out}  (buffer={buffer_m} m)")
            return out
        print("⚠️ Could not export clipped polygon (SQL path).", r.stderr or r.stdout)

    # ---------------- PATH B: Raster fallback (no SpatiaLite) ----------------
    print("▶ Falling back to raster pipeline (no SpatiaLite/GEOS required)…")

    # Safety checks for tools
    missing = [p for p in [gdal_ras, py_exe, gd_prox, gd_calc, gd_poly] if not p.exists()]
    if missing:
        print("❌ Raster fallback not available; missing:", ", ".join(str(m) for m in missing))
        return None

    # Create a small working dir for rasters
    rdir = work / "_roads_raster_tmp"
    rdir.mkdir(exist_ok=True)

    # 5b) Rasterize roads into a 2193 raster covering AOI
    # Choose 2 m pixel size (adjust if you like); larger pixel -> faster, coarser buffer.
    px = 2.0
    roads_tif = rdir / "roads.tif"
    prox_tif  = rdir / "prox.tif"
    mask_tif  = rdir / "mask.tif"
    buf_gpkg  = rdir / "buf.gpkg"

    # Compute extent if not set; read from roadsCrop2193
    if minx is None:
        r = _run([ogrinfo, "-json", str(tmp_gpkg), "roadsCrop2193"])
        if r.returncode != 0:
            print("❌ Could not get roads extent for rasterization.")
            return None
        info = json.loads(r.stdout)
        ext = (((info.get("layers") or [])[0] or {}).get("extent") or {})

        minx, miny = ext.get("xmin"), ext.get("ymin")
        maxx, maxy = ext.get("xmax"), ext.get("ymax")

    # Rasterize lines (burn 1)
    r = run_utf8([str(gdal_ras),
                  "-a_nodata", "0",
                  "-ot", "Byte",
                  "-a_srs", "EPSG:2193",
                  "-te", str(minx), str(miny), str(maxx), str(maxy),
                  "-tr", str(px), str(px),
                  "-burn", "1",
                  "-l", "roadsCrop2193",
                  str(tmp_gpkg), str(roads_tif)],
                 env=env)

    if r.returncode != 0:
        print("❌ gdal_rasterize failed:", r.stderr or r.stdout)
        return None

    # Proximity (distance in GEO units == meters in 2193)
    r = run_utf8([str(py_exe), str(gd_prox), str(roads_tif), str(prox_tif),
                  "-distunits", "GEO", "-ot", "UInt16", "-values", "1", "-nodata", "0"],
                 env=env)
    if r.returncode != 0:
        print("❌ gdal_proximity.py failed:", r.stderr or r.stdout)
        return None

    # Threshold to mask: 1 where distance <= buffer_m, else 0
    r = run_utf8([str(py_exe), str(gd_calc),
                  "-A", str(prox_tif),
                  "--outfile", str(mask_tif),
                  "--type=Byte", "--NoDataValue=0",
                  f"--calc=(A<={float(buffer_m)})"],
                 env=env)
    if r.returncode != 0:
        print("❌ gdal_calc.py threshold failed:", r.stderr or r.stdout)
        return None

    # Polygonize mask to vector (buf.gpkg, layer 'buf')
    r = run_utf8([str(py_exe), str(gd_poly), str(mask_tif), "-b", "1",
                  "-f", "GPKG", str(buf_gpkg), "buf"],
                 env=env)
    if r.returncode != 0:
        print("❌ gdal_polygonize.py failed:", r.stderr or r.stdout)
        return None

    # Intersect raster buffer polygons with suburb (both in 2193)
    r = _run([
        ogr2ogr, "-f", "GPKG", str(tmp_gpkg), str(tmp_gpkg), "suburb2193",
        "-nln", "clip_from_mask", "-overwrite"
    ])
    if r.returncode != 0:
        print("❌ Prep copy for intersection failed:", r.stderr or r.stdout)
        return None

    sql_ix = (
        f"SELECT ST_Intersection(a.{GEOM_COL}, b.{GEOM_COL}) AS {GEOM_COL} "
        f"FROM clip_from_mask a, buf b"
    )
    r = _run([
        ogr2ogr, "-f", "GPKG", str(tmp_gpkg), str(buf_gpkg), "buf",
        "-nln", "clipped2193", "-overwrite",
        "-dialect", "SQLite", "-sql", sql_ix,
        "-lco", f"GEOMETRY_NAME={GEOM_COL}",
        "-lco", "IDENTIFIER=clipped2193",
        "-lco", "DESCRIPTION="
    ])

    if r.returncode != 0:
        print("❌ Intersect with raster buffer failed:", r.stderr or r.stdout)
        return None

    # Export back to GeoJSON (EPSG:4326)
    out = suburb_geojson.with_name(suburb_geojson.stem + "_roadclipped.geojson")
    r = _run([ogr2ogr, "-f", "GeoJSON", str(out), str(tmp_gpkg), "clipped2193",
              "-t_srs", "EPSG:4326", "-overwrite"])
    if r.returncode != 0:
        print("⚠️ Could not export clipped polygon:", r.stderr or r.stdout)
        return None

    print(f"✅ Road-clipped polygon (raster fallback) → {out}  (buffer={buffer_m} m, px={px} m)")
    return out





def _export_suburb_from_shp(shp_path: Path, name_fragment: str, out_geojson: Path,
                            gdal_bin: Path, env: dict, fields_hint=None) -> tuple[bool, str]:
    """
    Select a polygon from nz-suburbs-and-localities.shp by name fragment and export as EPSG:4326 GeoJSON.
    Returns (ok, field_used_or_'multi').

    Strategy:
      - Try `-where "<FIELD> ILIKE '%frag%'"` (works & is fast on Shapefile).
      - Fallback to SQLite dialect with lower(...) if needed.
      - If still nothing, try OR across all string fields.
    """
    ogr2ogr = gdal_bin / "ogr2ogr.exe"
    ogrinfo = gdal_bin / "ogrinfo.exe"

    def _run(cmd):
        cmd2 = [str(cmd[0])]
        if env.get("PROJ_LIB"):  cmd2 += ["--config", "PROJ_LIB",  env["PROJ_LIB"]]
        if env.get("PROJ_DATA"): cmd2 += ["--config", "PROJ_DATA", env["PROJ_DATA"]]
        if env.get("GDAL_DATA"): cmd2 += ["--config", "GDAL_DATA", env["GDAL_DATA"]]
        cmd2 += [str(x) for x in cmd[1:]]
        return run_utf8(cmd2, env=env)

    if not shp_path.exists():
        return False, ""

    # Inspect layer + fields
    try:
        j = _run([ogrinfo, "-json", str(shp_path)])
        j.check_returncode()
        layers = (json.loads(j.stdout).get("layers") or [])
        layer_name = (layers[0].get("name") if layers else None) or Path(shp_path).stem

        j2 = _run([ogrinfo, "-json", str(shp_path), layer_name, "-so"])
        j2.check_returncode()
        lyr = (json.loads(j2.stdout).get("layers") or [{}])[0]
        fdefs = (lyr.get("fields") or [])
        fields = [f.get("name") for f in fdefs if f and f.get("name")]
        string_fields = [f.get("name") for f in fdefs if f and f.get("name") and "string" in (f.get("type","").lower())]
    except Exception:
        fields = []
        string_fields = []
        layer_name = Path(shp_path).stem

    candidates = (fields_hint or
                  ["name","name_ascii","locality","locality_name","suburb","suburb_locality",
                   "major_name","major_na_1","territoria","territ_1","NAME","LOCALITY","SUBURB"])
    by_lower = {f.lower(): f for f in fields}
    try_fields = [by_lower[c.lower()] for c in candidates if c.lower() in by_lower]
    if not try_fields:
        try_fields = string_fields[:] or fields[:]

    frag_raw = name_fragment.strip()
    if not frag_raw:
        return False, ""
    frag_q = frag_raw.replace("'", "''")  # escape single quotes

    # Helper: WHERE with ILIKE (case-insensitive) — fast path on Shapefile
    def _ogr_where_ilike(field: str, sink: Path) -> subprocess.CompletedProcess:
        # Attribute filter; no -dialect; ILIKE is handled by OGR's expression engine.
        return _run([ogr2ogr, "-f", "GeoJSON", str(sink), str(shp_path),
                     layer_name, "-where", f"{field} ILIKE '%{frag_q}%'",
                     "-t_srs", "EPSG:4326", "-overwrite"])

    # Helper: SQLite fallback with lower(...)
    def _ogr_sql_lower(field: str, sink: Path) -> subprocess.CompletedProcess:
        sql = f'SELECT * FROM "{layer_name}" WHERE lower("{field}") LIKE \'%\' || lower(\'{frag_q}\') || \'%\''
        return _run([ogr2ogr, "-f", "GeoJSON", str(sink), str(shp_path),
                     "-dialect", "SQLite", "-sql", sql, "-t_srs", "EPSG:4326", "-overwrite"])

    # Try per-field match
    for fld in try_fields:
        out_tmp = out_geojson.with_suffix(".tmp.geojson")

        # 1) Try ILIKE
        r = _ogr_where_ilike(fld, out_tmp)
        ok = (r.returncode == 0 and out_tmp.exists() and out_tmp.stat().st_size > 0)
        if not ok:
            # 2) Fallback to SQLite lower(...)
            r = _ogr_sql_lower(fld, out_tmp)
            ok = (r.returncode == 0 and out_tmp.exists() and out_tmp.stat().st_size > 0)

        if ok:
            try:
                with open(out_tmp, "r", encoding="utf-8") as f:
                    gj = json.load(f)
                if (gj.get("features") or []):
                    out_geojson.write_text(json.dumps(gj), encoding="utf-8")
                    out_tmp.unlink(missing_ok=True)
                    return True, fld
            except Exception:
                pass

        try: out_tmp.unlink(missing_ok=True)
        except Exception: pass

    # OR across all string fields in one go (SQLite)
    if string_fields:
        ors = " OR ".join([f'lower("{f}") LIKE \'%\' || lower(\'{frag_q}\') || \'%\'' for f in string_fields])
        sql = f'SELECT * FROM "{layer_name}" WHERE ({ors})'
        out_tmp = out_geojson.with_suffix(".tmp.geojson")
        r = _run([ogr2ogr, "-f", "GeoJSON", str(out_tmp), str(shp_path),
                  "-dialect", "SQLite", "-sql", sql, "-t_srs", "EPSG:4326", "-overwrite"])
        if r.returncode == 0 and out_tmp.exists() and out_tmp.stat().st_size > 0:
            try:
                with open(out_tmp, "r", encoding="utf-8") as f:
                    gj = json.load(f)
                if (gj.get("features") or []):
                    out_geojson.write_text(json.dumps(gj), encoding="utf-8")
                    out_tmp.unlink(missing_ok=True)
                    return True, "multi"
            except Exception:
                pass
        try: out_tmp.unlink(missing_ok=True)
        except Exception: pass

    # Helpful suggestions if nothing matched
    try:
        # show a few candidate values to guide the user
        probe = _run([ogrinfo, str(shp_path), layer_name, "-al", "-geom=NO", "-limit", "500"])
        txt = probe.stdout or ""
        vals = []
        for line in txt.splitlines():
            line = line.strip()
            # crude scrape of common name-like fields
            if any(k in line.lower() for k in ["name", "major_name", "locality", "suburb"]):
                if "=" in line:
                    vals.append(line.split("=", 1)[1].strip())
        import difflib
        suggestions = difflib.get_close_matches(frag_raw, list(set(vals)), n=8, cutoff=0.6)
        if suggestions:
            print("💡 Did you mean one of:")
            for s in suggestions:
                print("  -", s)
    except Exception:
        pass

    if string_fields:
        print("⚠️ No matches. String-like fields in the SHP:\n  - " + "\n  - ".join(string_fields))
    else:
        print("⚠️ No matches and no string-like fields detected. Fields:", fields)
    return False, ""


def _norm_suburb_input(s: str) -> str:
    """
    Normalize a user-entered suburb string:
    - lowercase
    - keep letters/numbers/spaces
    - collapse whitespace
    """
    s = s or ""
    # allow letters/numbers/spaces only
    s = re.sub(r"[^a-zA-Z0-9\s]+", " ", s.lower())
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _input_or_default(prompt: str, default: str | None = None) -> str:
    """
    Returns input(prompt) unless NON_INTERACTIVE is True, then returns `default` (or "").
    Also echoes the chosen value so logs capture it.
    """
    if NON_INTERACTIVE:
        val = default or ""
        if prompt:
            print(f"{prompt}{val}")
        return val
    return input(prompt)


def _ns(s: str) -> str:
    """Normalize for equality checks: lowercase & remove spaces/hyphens."""
    return re.sub(r"[ \-]+", "", (s or "").lower()).strip()

def _collect_shp_name_candidates(suburbs_shp: Path, gdal_bin: Path, env: dict) -> list[str]:
    """
    Collect DISTINCT values from likely name fields using SQLite.
    Returns lowercase, minimally cleaned strings (keeps internal spaces).
    """
    ogrinfo = gdal_bin / "ogrinfo.exe"
    ogr2ogr  = gdal_bin / "ogr2ogr.exe"
    if not suburbs_shp.exists() or not ogrinfo.exists() or not ogr2ogr.exists():
        return []

    # Inspect layer & fields
    try:
        j = run_utf8([str(ogrinfo), "-json", str(suburbs_shp)], check=True, env=env)
        layers = (json.loads(j.stdout).get("layers") or [])
        layer_name = (layers[0].get("name") if layers else None) or suburbs_shp.stem

        j2 = run_utf8([str(ogrinfo), "-json", str(suburbs_shp), layer_name, "-so"], check=True, env=env)
        lyr = (json.loads(j2.stdout).get("layers") or [{}])[0]
        fdefs = (lyr.get("fields") or [])
        fields = [f.get("name") for f in fdefs if f and f.get("name")]
        types  = {f.get("name"): (f.get("type") or "").lower() for f in fdefs if f and f.get("name")}
    except Exception:
        fields, types, layer_name = [], {}, suburbs_shp.stem

    likely = ["name","name_ascii","locality","locality_name","suburb","suburb_locality",
              "major_name","major_na_1","territoria","territ_1","NAME","LOCALITY","SUBURB"]
    by_lower = {f.lower(): f for f in fields}
    target_fields = [by_lower[x.lower()] for x in likely if x.lower() in by_lower]
    if not target_fields:
        target_fields = [f for f in fields if "string" in (types.get(f,""))] or fields
    if not target_fields:
        return []

    vals = set()

    # Query DISTINCT for each field via SQLite; dump to temporary GeoJSON (ignored geometry).
    # We SELECT the field and a dummy geometry; ogr2ogr requires a geometry unless using -nln with -sql scalar.
    for fld in target_fields:
        sql = (
            f"SELECT DISTINCT {fld} AS val FROM \"{layer_name}\" "
            f"WHERE {fld} IS NOT NULL AND TRIM({fld}) <> ''"
        )
        # Use VRT trick to fetch as GeoJSON FeatureCollection with one Point(0 0) per row then parse properties
        tmp = suburbs_shp.with_suffix(f".{fld}.distinct.tmp.geojson")
        r = run_utf8([str(ogr2ogr), "-f", "GeoJSON", str(tmp), str(suburbs_shp),
                      "-dialect", "SQLite", "-sql", sql], check=False, env=env)
        if r.returncode == 0 and tmp.exists():
            try:
                with open(tmp, "r", encoding="utf-8") as f:
                    gj = json.load(f)
                for feat in (gj.get("features") or []):
                    v = (feat.get("properties") or {}).get("val")
                    if isinstance(v, str):
                        # keep spaces, drop weird punctuation at ends, lower
                        v2 = v.strip().lower()
                        if v2:
                            vals.add(v2)
            except Exception:
                pass
        try: tmp.unlink(missing_ok=True)
        except Exception: pass

    return sorted(vals)

def _ring_area_m2_ll(ring_ll: list[tuple[float,float]]) -> float:
    """Approx area in m² from lon/lat ring using a local equirectangular tangent plane."""
    import math
    if len(ring_ll) < 3:
        return 0.0
    # centroid for stable local frame
    lon0 = sum(x for x,_ in ring_ll)/len(ring_ll)
    lat0 = sum(y for _,y in ring_ll)/len(ring_ll)
    R = 6371000.0
    deg2rad = math.pi/180.0
    cosphi0 = max(1e-9, math.cos(lat0*deg2rad))

    def to_xy(lon, lat):
        x = R * (lon - lon0) * deg2rad * cosphi0
        y = R * (lat - lat0) * deg2rad
        return x, y

    pts = [to_xy(lon, lat) for lon,lat in ring_ll]
    pts = pts + [pts[0]]
    A = 0.0
    for i in range(len(pts)-1):
        x1,y1 = pts[i]; x2,y2 = pts[i+1]
        A += x1*y2 - x2*y1
    return abs(0.5*A)

def _rebalance_localswap(groups: list[list[list[tuple[float,float]]]],
                         area_fn,
                         iters: int = 10) -> None:
    """Tiny hill-climb: move smallest piece from heaviest bin to lightest if it helps."""
    for _ in range(max(0, iters)):
        sums = [sum(area_fn(r) for r in g) for g in groups]
        hi = max(range(len(groups)), key=lambda i: sums[i])
        lo = min(range(len(groups)), key=lambda i: sums[i])
        if not groups[hi]:
            break
        cand = min(groups[hi], key=area_fn)
        old_spread = max(sums) - min(sums)
        new_sums = sums[:]
        new_sums[hi] -= area_fn(cand)
        new_sums[lo] += area_fn(cand)
        new_spread = max(new_sums) - min(new_sums)
        if new_spread + 1e-6 < old_spread:
            groups[hi].remove(cand)
            groups[lo].append(cand)
        else:
            break


def extract_suburb_from_gpkg():
    """
    Build a suburb polygon (official SHP preferred; address points fallback).
    Now enforces:
      - ALWAYS show a list of closest matches (no auto-pick)
      - After a selection, ask for confirmation before proceeding
      - Progress bar starts only after confirmation

    Default behavior:
      - Exports the FULL suburb polygon (parks/reserves included).
      - To trim to a road corridor instead, set CLIP_MODE=roads.
    """
    # --------- Paths & binaries ----------
    base_dir = Path(__file__).resolve().parent
    db_dir   = base_dir / "Street Database"
    gpkg     = db_dir / "nz-addresses.gpkg"
    roads_gpkg = db_dir / "nz-roads-road-section-geometry.gpkg"
    gdal_bin = db_dir / "bin"
    ogr2ogr  = gdal_bin / "ogr2ogr.exe"
    ogrinfo  = gdal_bin / "ogrinfo.exe"
    suburbs_shp = db_dir / "nz-suburbs-and-localities.shp"
    # Land mask defaults so Option 1 never returns sea/beach
    # NEW: prefer polygons+islands; fall back to old lines if needed
    land_poly = (db_dir / "nz-coastlines-and-islands-polygons-topo-150k.gpkg").resolve()
    land_fallback = (db_dir / "nz-coastlines-topo-150k.gpkg").resolve()
    os.environ.setdefault("LAND_MASK_PATH", str(land_poly if land_poly.exists() else land_fallback))
    os.environ.setdefault("LAND_MIN_AREA_M2", "0")

    # Clipping mode:
    # - "include_parks" (default): export the full suburb polygon (parks/reserves kept)
    # - "roads": intersect with a road corridor buffer (legacy behavior)
    CLIP_MODE = os.environ.get("CLIP_MODE", DEFAULT_CLIP_MODE).strip().lower()
    DEFAULT_ROAD_BUFFER_M = float(os.environ.get("ROAD_BUFFER", "50") or 50.0)
    if CLIP_MODE != "roads":
        print("ℹ️ CLIP_MODE != 'roads' → exporting FULL suburb area (parks/reserves included).")

    # Build GDAL/PROJ environment
    env = _build_gdal_env(gdal_bin)

    # NEW: best-effort enable SpatiaLite/GEOS for land-clip & SQL helpers (avoids
    # "Cannot load extension YES" and CTE/Polygonize failures)
    try:
        env.setdefault("OGR_SQLITE_LOAD_EXTENSIONS", "YES")
        # Avoid accidental misuse of OGR_SQLITE_EXTENSIONS=YES (would try to load "YES" as a lib)
        if "OGR_SQLITE_EXTENSIONS" in env and env["OGR_SQLITE_EXTENSIONS"].strip().upper() == "YES":
            env.pop("OGR_SQLITE_EXTENSIONS", None)
        # Try to locate a spatialite module beside the GDAL binaries
        spat_candidates = [
            gdal_bin / "mod_spatialite.dll",
            gdal_bin / "spatialite.dll",
            gdal_bin / "libspatialite.dll",
            gdal_bin / "mod_spatialite.so",
            gdal_bin / "libspatialite.so",
            gdal_bin / "mod_spatialite.dylib",
        ]
        spat_path = next((str(p) for p in spat_candidates if p.exists()), None)
        if spat_path:
            env.setdefault("OGR_SQLITE_EXT_PATH", spat_path)
            env.setdefault("SPATIALITE_SECURITY", "relaxed")
        else:
            print("ℹ️ SpatiaLite library not found in /bin — SQL features may fall back.")
    except Exception:
        pass

    out_dir  = base_dir / "GeoPackage Borders"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ----------------- UPDATED INPUT FLOW (no early abort on empty) -----------------
    # Ask for suburb text (but don't abort if missing; we'll open the picker)
    raw_input_txt = _input_or_default(
        "Enter suburb name/fragment (e.g., Howick): ",
        (DEFAULT_SUBURB or "").strip() if NON_INTERACTIVE else None
    ).strip()

    # Normalize what the user typed (if anything)
    cleaned = _norm_suburb_input(raw_input_txt)
    words = cleaned.split()
    if len(words) >= 2 and all(w == words[0] for w in words):
        cleaned = words[0]

    # Prepare candidates list once (if SHP exists)
    candidates = []
    if suburbs_shp.exists():
        try:
            candidates = _collect_shp_name_candidates(suburbs_shp, gdal_bin, env) or []
        except Exception:
            candidates = []

    # Helper: always show picker and require confirmation
    def _force_picker_return_choice(candidates: list[str], query_text: str) -> str | None:
        """
        Always show top matches and require explicit selection.
        After selection, reconfirm. Returns the confirmed text or None to cancel.
        Accepts 'y' or 'yes' for confirmation; anything else cancels.
        """
        if not candidates:
            print("\n(No suggestion list available from SHP.)")
            reconf = input(
                f"Use what you typed → '{(query_text or '').title()}' ? "
                f"Type 'y' or 'yes' to confirm: "
            ).strip().lower()
            return query_text if reconf in ("y", "yes") else None

        target_sp = query_text or ""           # allow empty query
        target_ns = _ns(target_sp)
        q_tokens = set(target_sp.split())

        scored = []
        for cand in candidates:
            c_sp = cand
            c_ns = _ns(cand)

            # token overlap (order-insensitive)
            c_tokens = set(c_sp.split())
            j = 0.0
            if q_tokens and c_tokens:
                inter = len(q_tokens & c_tokens)
                union = len(q_tokens | c_tokens)
                j = inter / union if union else 0.0

            # string similarity (handles empty safely)
            r1 = difflib.SequenceMatcher(a=target_sp, b=c_sp).ratio()
            r2 = difflib.SequenceMatcher(a=target_ns, b=c_ns).ratio()
            r = max(r1, r2)

            # Final score; when empty query, r and j ~ 0, so alphabetical fallback via name sort
            score = max(r, min(0.96, 0.90 * j + 0.05))
            scored.append((score, c_sp))

        # If query empty, prefer alphabetical list; otherwise, keep score sort
        if target_sp:
            scored.sort(key=lambda x: (-x[0], x[1]))
        else:
            scored.sort(key=lambda x: x[1])

        options = [c for (_, c) in scored[:10]]  # show up to 10

        while True:
            print("\nClosest matches:")
            for i, opt in enumerate(options, 1):
                print(f"  {i}. {opt.title()}")
            print("  0. Cancel")

            pick = input("Choose a number 1-10 (no default): ").strip()
            if not pick.isdigit():
                print("  ↪ Please enter a valid number.")
                continue

            idx = int(pick)
            if idx == 0:
                return None
            if 1 <= idx <= len(options):
                chosen = options[idx - 1]
                reconf = input(
                    f"Confirm selection: '{chosen.title()}' — type 'y' or 'yes' to proceed: "
                ).strip().lower()
                return chosen if reconf in ("y", "yes") else None
            else:
                print("  ↪ Out of range. Try again.")

    # Decide the suburb text:
    # - If user typed something (or default provided), run the picker seeded with that text.
    # - If nothing provided, still open the picker with an empty query so the user can choose.
    if cleaned:
        chosen_text = _force_picker_return_choice(candidates, cleaned)
        if not chosen_text:
            print("❌ Cancelled by user.")
            return
    else:
        if not candidates:
            # No candidates to show and no input; last resort prompt
            print("⚠️ No suburb provided and no SHP candidate list available.")
            print("💡 Tip: set SUBURB env or pass --suburb, or place nz-suburbs-and-localities.shp.")
            return
        # Open picker with empty query → shows alphabetical top 10
        chosen_text = _force_picker_return_choice(candidates, "")
        if not chosen_text:
            print("❌ Cancelled by user.")
            return
    # ----------------- END UPDATED INPUT FLOW -----------------

    # Show a progress bar only after the user confirmed their selection
    bar = tqdm(total=100, bar_format="⏳ {desc}: |{bar}| {percentage:3.0f}% {elapsed}", ncols=70)
    bar.set_description_str("Preparing polygon")
    bar.update(5)

    # GDAL binaries are required
    if not ogr2ogr.exists() or not ogrinfo.exists():
        bar.close()
        print(f"❌ Missing GDAL tools. Need both:\n   - {ogr2ogr}\n   - {ogrinfo}")
        return

    # Try to keep roads imported (no-op if already present)
    try:
        ensure_roads_layer()
    except Exception:
        pass
    bar.update(5)  # 10%

    used_method = None
    suburb_slug = re.sub(r'[^a-z0-9_]+','_', chosen_text.lower())
    out_geojson = out_dir / f"{suburb_slug}_polygon.geojson"

    # ---------- SHP FAST-PATH (official polygons) ----------
    if suburbs_shp.exists():
        bar.set_description_str("Exporting from official SHP")
        ok_shp, fld_used = _export_suburb_from_shp(
            suburbs_shp, chosen_text, out_geojson, gdal_bin, env
        )
        bar.update(30)  # 40%

        if ok_shp and out_geojson.exists() and out_geojson.stat().st_size > 0:
            used_method = "official_shp"
            print(f"\n✅ Used official polygon from SHP (field: {fld_used or 'unknown'}) → {out_geojson}")

            # --- Optional road clipping (only if CLIP_MODE == 'roads')
            if CLIP_MODE == "roads" and roads_gpkg.exists():
                bar.set_description_str("Clipping to road corridor")
                clipped = _clip_polygon_by_road_buffer(
                    roads_gpkg=roads_gpkg,
                    suburb_geojson=out_geojson,
                    gdal_bin=gdal_bin,
                    env=env,
                    buffer_m=DEFAULT_ROAD_BUFFER_M
                )
                bar.update(25)  # 65%
                if clipped:
                    print(f"▶ Auto road-clip applied ({DEFAULT_ROAD_BUFFER_M} m).")
                    out_geojson = clipped
            else:
                # keep progress consistent when skipping road-clip
                bar.update(25)  # 65%

            # --- Land clip (ALWAYS but tolerant to failure)
            bar.set_description_str("Clipping to land mask")
            try:
                landed = _clip_to_land(
                    in_geojson=out_geojson,
                    out_geojson=out_geojson.with_name(out_geojson.stem + "_land.geojson"),
                    gdal_bin=gdal_bin,
                    env=env
                )
            except Exception as e:
                print(f"⚠️ Land-clip raised an exception; continuing without it: {e}")
                landed = None
            bar.update(5)
            if landed:
                out_geojson = landed
            else:
                print("ℹ️ Land-clip unavailable (missing SpatiaLite/GEOS or coastlines). Proceeding with unmasked polygon.")

            # Stop the progress bar before interactive prompts in _finish_exports_from_geojson
            bar.close()

            res = _finish_exports_from_geojson(
                out_geojson=out_geojson,
                frag_in=chosen_text,
                used_method=used_method,
                out_dir=out_dir
            )

            print("✅ Successfully completed.")
            return res

    # ---------- ADDRESS-POINTS FLOW (only if SHP failed/not used) ----------
    bar.set_description_str("Falling back to address points")
    bar.update(15)  # 55%

    if not gpkg.exists():
        bar.close()
        print(f"❌ GeoPackage not found at: {gpkg}")
        print("   Tip: If you only have the SHP and the roads GPKG, the SHP path should suffice.")
        return

    def _inject_gdal_config(cmd: list[str]) -> list[str]:
        if not cmd:
            return cmd
        exe = Path(cmd[0]).name.lower()
        if exe.startswith("ogr") or exe.startswith("gdalsrsinfo") or exe.startswith("gdal"):
            prefix = []
            if env.get("PROJ_LIB"):
                prefix += ["--config", "PROJ_LIB", env["PROJ_LIB"]]
            if env.get("PROJ_DATA"):
                prefix += ["--config", "PROJ_DATA", env["PROJ_DATA"]]
            if env.get("GDAL_DATA"):
                prefix += ["--config", "GDAL_DATA", env["GDAL_DATA"]]
            # We intentionally DO NOT push SQLite extension flags here; they are in the env.
            return [cmd[0]] + prefix + cmd[1:]
        return cmd

    def _run(cmd) -> subprocess.CompletedProcess:
        cmd = _inject_gdal_config(cmd)
        return run_utf8(cmd, env=env)

    # ---- Detect a POINT layer in the address GPKG ----
    try:
        j = run_utf8([str(ogrinfo), "-json", str(gpkg)], check=True, env=env)
        info_json = json.loads(j.stdout)
        layer_meta = info_json.get("layers") or []
    except Exception as e:
        bar.close()
        print(f"❌ Could not list layers: {e}")
        return

    def _geom_is_pointish(gt: str | None) -> bool:
        return bool(gt) and ("point" in gt.lower()) and ("line" not in gt.lower()) and ("poly" not in gt.lower())

    point_candidates = []
    for lyr in layer_meta:
        name = (lyr.get("name") or "").strip()
        gtyp = (lyr.get("geometryType") or "").strip()
        lname = name.lower()
        score = 0
        if _geom_is_pointish(gtyp): score += 10
        if any(k in lname for k in ["addr","address","addresses"]): score += 5
        if "point" in lname: score += 2
        if score > 0:
            point_candidates.append((score, name))

    if not point_candidates:
        bar.close()
        print("✋ No address POINT layers detected in nz-addresses.gpkg.")
        print("   Found layers:", ", ".join((lyr.get('name') or '?') for lyr in layer_meta) or "none")
        print("   Tip: Make sure your address GPKG actually contains address points,")
        print("        or just use the official SHP path (recommended).")
        return

    point_layer = sorted(point_candidates, key=lambda x: (-x[0], x[1]))[0][1]
    print(f"\n✅ Using point layer: {point_layer}")
    bar.update(10)  # 65%

    # ---- Field detection for suburb name ----
    fields, fields_meta = [], []
    try:
        j = _run([str(ogrinfo), "-json", str(gpkg), point_layer, "-so"])
        j.check_returncode()
        data = json.loads(j.stdout); lyr  = (data.get("layers") or [None])[0] or {}
        fdefs = (lyr.get("fields") or [])
        fields = [f.get("name") for f in fdefs if f and f.get("name")]
        fields_meta = [(f.get("name"), (f.get("type") or "").lower()) for f in fdefs if f and f.get("name")]
    except Exception:
        pass

    preferred = ["suburb_locality", "suburb", "locality", "locality_name", "name", "place"]
    by_lower  = {f.lower(): f for f in (fields or [])}
    chosen_field = next((by_lower[p] for p in preferred if p in by_lower), None)

    if not chosen_field:
        stringish = [n for (n,t) in (fields_meta or []) if ("string" in (t or ""))]
        chosen_field = stringish[0] if stringish else None

    if not chosen_field:
        bar.close()
        print("❌ No suburb-like field could be identified.")
        return

    print(f"🔎 Matching suburb against field: {chosen_field}")

    frag_in = chosen_text  # confirmed above

    # ------ colors & outputs ------
    suburb_slug = re.sub(r'[^a-z0-9_]+','_', frag_in.lower())
    out_coords  = out_dir / f"{suburb_slug}_polygon_coords.txt"

    # ---- Build hull (concave → convex → python) ----
    bar.set_description_str("Computing hull")
    concave_ratio = 0.60  # retain your default; could be env-driven
    frag_sql = (frag_in.replace("\\","\\\\").replace("%","\\%").replace("_","\\_").replace("'","''"))
    sql_concave = (
        f'SELECT ST_ConcaveHull(ST_Collect(geometry), {concave_ratio}) AS geometry '
        f'FROM "{point_layer}" '
        f'WHERE LOWER("{chosen_field}") LIKE \'%\' || LOWER(\'{frag_sql}\') || \'%\' ESCAPE \'\\\\\''
    )
    sql_convex = (
        f'SELECT ST_ConvexHull(ST_Collect(geometry)) AS geometry '
        f'FROM "{point_layer}" '
        f'WHERE LOWER("{chosen_field}") LIKE \'%\' || LOWER(\'{frag_sql}\') || \'%\' ESCAPE \'\\\\\''
    )

    def _run_sql_to_geojson(sql_text: str, sink: Path) -> tuple[bool, str]:
        cmd = [str(ogr2ogr), "-f", "GeoJSON", str(sink), str(gpkg),
               "-dialect", "SQLite", "-sql", sql_text]
        res = _run(cmd)
        ok = (res.returncode == 0) and sink.exists() and sink.stat().st_size > 0
        msg = (res.stderr or res.stdout or "").strip()
        return ok, msg

    used_method = None
    ok, _ = _run_sql_to_geojson(sql_concave, out_geojson)
    bar.update(15)  # 80%
    if ok:
        used_method = "concave"
    else:
        print("ℹ️ ST_ConcaveHull failed or not available; trying ST_ConvexHull…")
        ok2, _ = _run_sql_to_geojson(sql_convex, out_geojson)
        if ok2:
            used_method = "convex"
        else:
            print("⚠️ GDAL SQL hulls failed. Falling back to Python convex hull path.")
            used_method = None

    if used_method is None:
        # Dump matching points & make a Python convex hull (kept from your original)
        tmp_points  = out_dir / "tmp_points_for_hull.geojson"
        sql_pts = (
            f'SELECT * FROM "{point_layer}" '
            f'WHERE LOWER("{chosen_field}") LIKE \'%\' || LOWER(\'{frag_sql}\') || \'%\' ESCAPE \'\\\\\''
        )
        def _export_points_sql_to_geojson(sql_query: str, sink: Path) -> int:
            cmd = [str(ogr2ogr), "-f", "GeoJSON", str(sink), str(gpkg),
                   "-dialect", "SQLite", "-sql", sql_query]
            res = _run(cmd)
            if res.returncode != 0: return -1
            try:
                with open(sink, "r", encoding="utf-8") as f:
                    gj = json.load(f)
                return len(gj.get("features") or [])
            except Exception:
                return -1
        n_feat = _export_points_sql_to_geojson(sql_pts, tmp_points)
        if n_feat < 3:
            bar.close()
            print("❌ Not enough points to build hull.")
            try: tmp_points.unlink(missing_ok=True)
            except Exception: pass
            return

        with open(tmp_points, "r", encoding="utf-8") as f:
            gj = json.load(f)
        pts = []
        for feat in (gj.get("features") or []):
            geom = feat.get("geometry") or {}
            if geom.get("type") == "Point":
                c = geom.get("coordinates") or []
                if len(c) >= 2:
                    pts.append((float(c[0]), float(c[1])))

        def _cross(o, a, b): return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])
        pts_sorted = sorted(set(pts))
        if len(pts_sorted) < 3:
            bar.close()
            print("❌ Hull construction failed (degenerate).")
            try: tmp_points.unlink(missing_ok=True)
            except Exception: pass
            return
        lower, upper = [], []
        for p in pts_sorted:
            while len(lower) >= 2 and _cross(lower[-2], lower[-1], p) <= 0: lower.pop()
            lower.append(p)
        for p in reversed(pts_sorted):
            while len(upper) >= 2 and _cross(upper[-2], upper[-1], p) <= 0: upper.pop()
            upper.append(p)
        hull = lower[:-1] + upper[:-1]
        gjson = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {"method": "python_convex"},
                "geometry": {"type": "Polygon",
                             "coordinates": [[[x,y] for (x,y) in hull + [hull[0]]]]}
            }]
        }
        with open(out_geojson, "w", encoding="utf-8") as f:
            json.dump(gjson, f)
        used_method = "python_convex"
        try: tmp_points.unlink(missing_ok=True)
        except Exception: pass

    print(f"✅ GeoJSON polygon → {out_geojson}")
    print(f"✅ Built with method: {used_method}")
    bar.update(10)  # 90%

    # --- Optional road clipping (only if CLIP_MODE == 'roads') for fallback path too
    if CLIP_MODE == "roads" and roads_gpkg.exists():
        bar.set_description_str("Clipping to road corridor")
        clipped = _clip_polygon_by_road_buffer(
            roads_gpkg=roads_gpkg,
            suburb_geojson=out_geojson,
            gdal_bin=gdal_bin,
            env=env,
            buffer_m=DEFAULT_ROAD_BUFFER_M
        )
        if clipped:
            print(f"▶ Auto road-clip applied ({DEFAULT_ROAD_BUFFER_M} m).")
            out_geojson = clipped

    # --- Land clip (ALWAYS but tolerant to failure)
    bar.set_description_str("Clipping to land mask")
    try:
        landed = _clip_to_land(
            in_geojson=out_geojson,
            out_geojson=out_geojson.with_name(out_geojson.stem + "_land.geojson"),
            gdal_bin=gdal_bin,
            env=env
        )
    except Exception as e:
        print(f"⚠️ Land-clip raised an exception; continuing without it: {e}")
        landed = None
    if landed:
        out_geojson = landed
    else:
        print("ℹ️ Land-clip unavailable (missing SpatiaLite/GEOS or coastlines). Proceeding with unmasked polygon.")

    # Stop the progress bar before interactive prompts in _finish_exports_from_geojson
    bar.close()

    res = _finish_exports_from_geojson(
        out_geojson=out_geojson,
        frag_in=chosen_text,
        used_method=used_method,
        out_dir=out_dir
    )

    print("✅ Successfully completed.")
    return res



def _finish_exports_from_geojson(out_geojson: Path, frag_in: str, used_method: str, out_dir: Path):
    import math

    try:
        with open(out_geojson, "r", encoding="utf-8") as f:
            gj = json.load(f)
        feats = gj.get("features") or []
        if not feats:
            print("❌ No polygon feature created.")
            return
        geom = feats[0].get("geometry") or {}
        if geom.get("type") not in ("Polygon", "MultiPolygon"):
            print("❌ Output is not a polygon geometry.")
            return

        # ---------- geometry helpers ----------
        def _ensure_closed(r):
            return r if (len(r) >= 3 and r[0] == r[-1]) else (r + [r[0]])

        def _poly_area(coords):
            if len(coords) < 3: return 0.0
            c = _ensure_closed(coords)
            return 0.5 * sum(c[i][0]*c[i+1][1] - c[i+1][0]*c[i][1] for i in range(len(c)-1))

        def _poly_centroid(coords):
            A = 0.0; Cx = 0.0; Cy = 0.0
            c = _ensure_closed(coords)
            for i in range(len(c)-1):
                x1,y1 = c[i]; x2,y2 = c[i+1]
                cross = x1*y2 - x2*y1
                A  += cross
                Cx += (x1 + x2) * cross
                Cy += (y1 + y2) * cross
            A *= 0.5
            if abs(A) < 1e-12:
                xs = [x for x,_ in coords]; ys = [y for _,y in coords]
                return (sum(xs)/len(xs), sum(ys)/len(ys))
            Cx /= (6.0 * A); Cy /= (6.0 * A)
            return (Cx, Cy)

        def _kml_doc_polygon_with_label(coords, poly_name, label_text, line_color, poly_color, width):
            altitude_m = 100
            c = _ensure_closed(coords)
            coord_str = " ".join(f"{lon},{lat},{altitude_m}" for lon, lat in c)
            cx, cy = _poly_centroid(coords)
            return f"""<?xml version="1.0" encoding="utf-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
  <name>{poly_name}</name>
  <open>1</open>

  <Placemark>
    <name>{poly_name}</name>
    <Style>
      <LineStyle><color>{line_color}</color><width>{width}</width></LineStyle>
      <PolyStyle><color>{poly_color}</color><fill>1</fill><outline>1</outline></PolyStyle>
    </Style>
    <Polygon>
      <tessellate>1</tessellate>
      <altitudeMode>relativeToGround</altitudeMode>
      <outerBoundaryIs><LinearRing><coordinates>{coord_str}</coordinates></LinearRing></outerBoundaryIs>
    </Polygon>
  </Placemark>

  <Placemark>
    <name>{label_text}</name>
    <Point>
      <altitudeMode>relativeToGround</altitudeMode>
      <coordinates>{cx},{cy},{altitude_m}</coordinates>
    </Point>
  </Placemark>

</Document>
</kml>"""

        # Extract the outer ring
        rings = []
        if geom.get("type") == "Polygon":
            rings = geom.get("coordinates") or []
        else:
            for poly in (geom.get("coordinates") or []):
                if poly: rings.append(poly[0])
        if not rings:
            print("❌ Empty polygon.")
            return
        outer = max(rings, key=lambda r: abs(_poly_area(r)))

        # Folders: coords stay in root; all KMLs go to 'Output KML'
        output_kml_dir = out_dir / "Output KML"
        output_kml_dir.mkdir(parents=True, exist_ok=True)

        # Save coords txt (outer ring) in root
        suburb_slug = re.sub(r'[^a-z0-9_]+', '_', frag_in.strip().lower())
        out_coords  = out_dir / f"{suburb_slug}_polygon_coords.txt"
        with open(out_coords, "w", encoding="utf-8") as outf:
            for lon, lat in _ensure_closed(outer):
                outf.write(f"{lon},{lat}\n")
        print(f"📝 Polygon coordinates written → {out_coords}")

        # ---------- tint selection ----------
        COLORS = [
            ("blue", "ff0000"),
            ("green", "00ff00"),
            ("red", "0000ff"),
            ("purple", "800080"),
            ("grey", "808080"),
            ("yellow", "00ffff"),
            ("orange", "00a5ff"),
        ]
        ALPHA = {"light": "66", "medium": "cc"}

        tone = (os.environ.get("TONE", DEFAULT_TONE) or "light").strip().lower()
        tone = tone if tone in ALPHA else "light"

        outline_width = 2
        outline_alpha = "ff"

        print("\nTint colors (Pick A Colour):")
        for ci, (name, _) in enumerate(COLORS, 1):
            print(f"  {ci}. {name.title()}")
        print(f"  (Default index(es): {DEFAULT_COLOR_IDX}  | Tone: {tone})")

        sel = None
        if NON_INTERACTIVE:
            chosen_idx = [i for i in DEFAULT_COLOR_IDX if 1 <= i <= len(COLORS)] or [1]
            print(f"Select color(s) by number: (1-7) [auto]: {','.join(str(i) for i in chosen_idx)}")
        else:
            sel = input("Select color(s) by number: (1-7, comma-separated) [default: 1]: ").strip()
            if not sel:
                chosen_idx = [1]
                print("Using default: 1")
            else:
                chosen_idx = [int(s) for s in sel.split(",") if s.strip().isdigit()]
                chosen_idx = [n for n in chosen_idx if 1 <= n <= len(COLORS)] or [1]

        # Write the UNSPLIT whole KMLs into 'Output KML'
        label_text = re.sub(r"\s+", " ", (frag_in or "").strip()).title()
        kml_name = f"{label_text} (polygon: {used_method})"
        for ci in chosen_idx:
            color_name, bbggrr = COLORS[ci - 1]
            fill_color = f"{ALPHA[tone]}{bbggrr}"
            line_color = f"{outline_alpha}{bbggrr}"
            kml_path = output_kml_dir / f"{suburb_slug}_polygon_{color_name}_{tone}.kml"
            kml = _kml_doc_polygon_with_label(outer, kml_name, label_text, line_color, fill_color, outline_width)
            kml_path.write_text(kml, encoding="utf-8")
            print(f"✅ KML written → {kml_path}")

        # ---------- ask to split (AFTER writing unsplit variants) ----------
        do_split = input("\nDo you want to split the suburb into sections? [y/N]: ").strip().lower()
        if do_split not in ("y", "yes"):
            print("ℹ️ Skipping split. Done.")
            print("✅ Done.")
            return

        # how many + reconfirm
        while True:
            n_raw = input("How many sections do you want? Enter an integer ≥ 2: ").strip()
            if not (n_raw.isdigit() and int(n_raw) >= 2):
                print("  ↪ Please enter an integer ≥ 2.")
                continue
            k_parts = int(n_raw)
            reconf = input(f"Confirm: split into {k_parts} sections? Type 'y' or 'yes' to proceed: ").strip().lower()
            if reconf in ("y", "yes"):
                break

        # ---------- local helpers for splitting ----------
        def _ring_area_abs(r):
            return abs(_poly_area(r))

        def _area_weighted_centroid(rings: list[list[tuple[float,float]]]) -> tuple[float,float]:
            if not rings:
                return _poly_centroid(outer)
            A = 0.0; Cx = 0.0; Cy = 0.0
            for r in rings:
                a = _ring_area_abs(r)
                cx, cy = _poly_centroid(r)
                A += a; Cx += cx * a; Cy += cy * a
            if A <= 1e-12:
                return _poly_centroid(outer)
            return (Cx / A, Cy / A)

        def _write_coords_txt(path: Path, rings: list[list[tuple[float,float]]]):
            with open(path, "w", encoding="utf-8") as outf:
                first = True
                for ring in rings:
                    if not first:
                        outf.write("\n")
                    first = False
                    for lon, lat in _ensure_closed(ring):
                        outf.write(f"{lon},{lat}\n")

        def _kml_multigeom_with_label(rings: list[list[tuple[float,float]]],
                                      poly_name: str,
                                      label_text: str,
                                      line_color: str,
                                      poly_color: str,
                                      width: int) -> str:
            altitude_m = 100
            cx, cy = _area_weighted_centroid(rings)
            poly_parts = []
            for ring in rings:
                coords_str = " ".join(f"{lon},{lat},{altitude_m}" for lon,lat in _ensure_closed(ring))
                poly_parts.append(
                    f"""<Placemark>
  <Style>
    <LineStyle><color>{line_color}</color><width>{width}</width></LineStyle>
    <PolyStyle><color>{poly_color}</color><fill>1</fill><outline>1</outline></PolyStyle>
  </Style>
  <Polygon>
    <tessellate>1</tessellate>
    <altitudeMode>relativeToGround</altitudeMode>
    <outerBoundaryIs><LinearRing><coordinates>{coords_str}</coordinates></LinearRing></outerBoundaryIs>
  </Polygon>
</Placemark>"""
                )
            return f"""<?xml version="1.0" encoding="utf-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
  <name>{poly_name}</name>
  <open>1</open>
  {''.join(poly_parts)}
  <Placemark>
    <name>{label_text}</name>
    <Point>
      <altitudeMode>relativeToGround</altitudeMode>
      <coordinates>{cx},{cy},{altitude_m}</coordinates>
    </Point>
  </Placemark>
</Document>
</kml>"""

        def _principal_axis(points):
            n=len(points)
            mx=sum(x for x,_ in points)/n; my=sum(y for _,y in points)/n
            sxx=sum((x-mx)*(x-mx) for x,_ in points)/n
            syy=sum((y-my)*(y-my) for _,y in points)/n
            sxy=sum((x-mx)*(y-my) for x,y in points)/n
            angle = 0.5 * math.atan2(2*sxy, (sxx - syy))
            vx, vy = math.cos(angle), math.sin(angle)
            if vx < 0: vx, vy = -vx, -vy
            return (vx, vy)

        def _clip_halfplane(poly, a, b, c, keep_ge=True):
            if not poly: return []
            def side(x, y): return a*x + b*y + c
            keep = (lambda s: s >= 0) if keep_ge else (lambda s: s <= 0)
            out = []
            for i in range(len(poly)):
                x1, y1 = poly[i]; x2, y2 = poly[(i+1) % len(poly)]
                s1, s2 = side(x1, y1), side(x2, y2)
                i1, i2 = keep(s1), keep(s2)
                if i1 and i2:
                    out.append((x2, y2))
                elif i1 and not i2:
                    dx, dy = x2-x1, y2-y1; denom = a*dx + b*dy
                    if denom != 0:
                        t = - (a*x1 + b*y1 + c) / denom
                        out.append((x1 + t*dx, y1 + t*dy))
                elif (not i1) and i2:
                    dx, dy = x2-x1, y2-y1; denom = a*dx + b*dy
                    if denom != 0:
                        t = - (a*x1 + b*y1 + c) / denom
                        out.append((x1 + t*dx, y1 + t*dy))
                    out.append((x2, y2))
            return out

        def _split_equal_area_contiguous(poly_ring, k, v):
            if not poly_ring or len(poly_ring) < 3 or k < 2:
                return [poly_ring[:]]

            vx, vy = v
            projs = [vx*x + vy*y for x, y in poly_ring]
            u_lo, u_hi = min(projs), max(projs)
            if not math.isfinite(u_lo) or not math.isfinite(u_hi) or abs(u_hi - u_lo) < 1e-12:
                return [poly_ring[:]]

            def _clip_u_le(ring, t):
                p = ring[:]
                p = _clip_halfplane(p, -vx, -vy, +t, True)
                return p

            def _clip_band(ring, t1, t2):
                p = ring[:]
                p = _clip_halfplane(p,  vx,  vy, -t1, True)
                p = _clip_halfplane(p, -vx, -vy, +t2, True)
                return p

            total_area = _ring_area_m2_ll(poly_ring)
            if total_area <= 0:
                return [poly_ring[:]]
            target = total_area / float(k)

            def _area_u_le(t):
                r = _clip_u_le(poly_ring, t)
                return _ring_area_m2_ll(r) if len(r) >= 3 else 0.0

            cuts = []
            left = u_lo
            for i in range(1, k):
                goal = i * target
                lo, hi = left, u_hi
                for _ in range(60):
                    mid = 0.5 * (lo + hi)
                    a_mid = _area_u_le(mid)
                    if abs(a_mid - goal) <= max(1e-6, 1e-6 * total_area):
                        lo = hi = mid
                        break
                    if a_mid < goal:
                        lo = mid
                    else:
                        hi = mid
                t_i = 0.5 * (lo + hi)
                cuts.append(t_i)
                left = t_i

            bands = []
            prev = u_lo - 1e-12
            for t_i in cuts:
                b = _clip_band(poly_ring, prev, t_i)
                bands.append(b if len(b) >= 3 else [])
                prev = t_i
            b_last = _clip_band(poly_ring, prev, u_hi + 1e-12)
            bands.append(b_last if len(b_last) >= 3 else [])

            return bands

        def _split_by_vector(poly, v, k):
            vx, vy = v
            projs = [vx*x + vy*y for x,y in poly]
            lo, hi = min(projs), max(projs)
            if hi <= lo: return [poly[:]]
            bounds = [lo + (hi-lo)*i/k for i in range(k+1)]
            parts=[]
            for i in range(k):
                a1, a2 = bounds[i], bounds[i+1]
                p = poly[:]
                p = _clip_halfplane(p, vx, vy, -a1, True)
                p = _clip_halfplane(p, -vx, -vy, +a2, True)
                parts.append(p)
            return parts

        # ====== Availability-aware menu (roads/suburbs/density + fallbacks) ======
        base_dir2 = Path(__file__).resolve().parent
        db_dir2   = base_dir2 / "Street Database"
        roads_gpkg  = db_dir2 / "nz-roads-road-section-geometry.gpkg"
        suburbs_shp = db_dir2 / "nz-suburbs-and-localities.shp"
        gpkg_addr   = db_dir2 / "nz-addresses.gpkg"
        gdal_bin2   = db_dir2 / "bin"
        ogr2ogr2    = gdal_bin2 / "ogr2ogr.exe"
        ogrinfo2    = gdal_bin2 / "ogrinfo.exe"
        env2        = _build_gdal_env(gdal_bin2)

        have = {
            1: roads_gpkg.exists(),
            2: suburbs_shp.exists(),
            3: gpkg_addr.exists(),
            4: True,
            5: True,
            6: True
        }

        labels = {
            1: "Divide by main roads / highways",
            2: "Divide by smaller suburbs",
            3: "Divide by housing density",
            4: "Principal axis (auto) — equal-area contiguous bands",
            5: "North→South stripes (vertical bands)",
            6: "East→West stripes (horizontal bands)",
        }

        def _ogr2(cmd_list):
            cmd2 = [str(cmd_list[0])]
            if env2.get("PROJ_LIB"):  cmd2 += ["--config", "PROJ_LIB",  env2["PROJ_LIB"]]
            if env2.get("PROJ_DATA"): cmd2 += ["--config", "PROJ_DATA", env2["PROJ_DATA"]]
            if env2.get("GDAL_DATA"): cmd2 += ["--config", "GDAL_DATA", env2["GDAL_DATA"]]
            cmd2 += ["--config", "OGR_SQLITE_LOAD_EXTENSIONS", "YES"]
            if env2.get("OGR_SQLITE_EXT_PATH"):
                cmd2 += ["--config", "OGR_SQLITE_EXT_PATH", env2["OGR_SQLITE_EXT_PATH"]]
            return run_utf8(cmd2 + [str(x) for x in cmd_list[1:]], env=env2)

        # (wrappers unchanged, omitted here for brevity — use your existing ones from Part 2)
        # ... _split_by_roads_gdal, _split_by_suburbs_gdal, _split_by_density ...

        available_methods = [m for m in (1,2,3,4,5,6) if have[m]]
        print("\nSplit methods available:")
        shown_map = {}
        shown = 0
        for m in available_methods:
            shown += 1
            shown_map[shown] = m
            print(f"  {shown}) {labels[m]}")
        print("  0) Cancel")

        chosen_method = None
        while True:
            m_raw = input(f"Choose a method (1-{shown}): ").strip()
            if m_raw == "0":
                print("❌ Cancelled.")
                return
            if not (m_raw.isdigit() and 1 <= int(m_raw) <= shown):
                print("  ↪ Please choose a listed option.")
                continue
            chosen_method = shown_map[int(m_raw)]
            reconf = input(f"Confirm method '{labels[chosen_method]}'? Type 'y' or 'yes' to proceed: ").strip().lower()
            if reconf in ("y","yes"):
                break

        # ---------- attempt chosen method with salvage order ----------
        salvage_order = [1,2,3,4,5,6]
        salvage_order = [chosen_method] + [m for m in salvage_order if m != chosen_method]
        salvage_order = [m for m in salvage_order if have[m]]

        parts: list[list[tuple[float,float]]] = []
        used_method_idx = None

        for m in salvage_order:
            if m == 1:
                parts = _split_by_roads_gdal(out_geojson)
            elif m == 2:
                parts = _split_by_suburbs_gdal(out_geojson)
            elif m == 3:
                parts = _split_by_density(out_geojson, k_parts)
            elif m == 4:
                v1 = _principal_axis(outer)
                v2 = (-v1[1], v1[0])
                print("\nOption 4 orientation:")
                print("  V) Vertical bands (cuts advance along principal axis)")
                print("  H) Horizontal bands (cuts advance along orthogonal axis)")
                ori = input("Choose orientation [V/H, default V]: ").strip().lower()
                v_cut = v2 if ori == "h" else v1
                parts = _split_equal_area_contiguous(outer, k_parts, v_cut)
            elif m == 5:
                v = (1.0, 0.0); parts = _split_by_vector(outer, v, k_parts)
            elif m == 6:
                v = (0.0, 1.0); parts = _split_by_vector(outer, v, k_parts)

            parts = [p for p in parts if len(p) >= 3 and abs(_poly_area(p)) > 1e-12]
            if m in (4,5,6) and len(parts) == k_parts:
                used_method_idx = m
                break
            if parts:
                used_method_idx = m
                break

        if not parts:
            print("❌ No parts produced by any available method.")
            return

        # ---------- grouping (unchanged) ----------
        def _ring_area_abs_local(r):
            return abs(_poly_area(r))

        def _group_parts_area_balanced(rings, k, area_fn=None):
            if k <= 1:
                return [rings[:]]
            if area_fn is None:
                area_fn = _ring_area_abs_local
            items = [(area_fn(r), r) for r in rings]
            items.sort(key=lambda t: -t[0])
            groups = [([], 0.0) for _ in range(k)]
            for a, r in items:
                idx = min(range(k), key=lambda i: groups[i][1])
                groups[idx][0].append(r)
                groups[idx] = (groups[idx][0], groups[idx][1] + a)
            return [g[0] for g in groups]

        if used_method_idx in (1, 2):
            if len(parts) <= k_parts:
                groups = [[p] for p in parts]
                while len(groups) > k_parts:
                    sizes = [sum(_ring_area_abs_local(r) for r in g) for g in groups]
                    j = sizes.index(min(sizes))
                    candidates = [(i, sizes[i]) for i in range(len(groups)) if i != j]
                    i_min = min(candidates, key=lambda t: t[1])[0]
                    groups[i_min].extend(groups[j]); del groups[j]
                while len(groups) < k_parts:
                    groups.append([])
                write_groups = groups[:k_parts]
            else:
                write_groups = _group_parts_area_balanced(parts, k_parts)

        elif used_method_idx == 3:
            write_groups = _group_parts_area_balanced(parts, k_parts) \
                if len(parts) != k_parts else [[p] for p in parts]

        elif used_method_idx == 4:
            write_groups = [[p] for p in parts] if len(parts) == k_parts else _group_parts_area_balanced(parts, k_parts)

            # dissolve each group to a single border (same as your original)
            def _dissolve_groups_to_single_border(groups_ll):
                out_groups = []
                def _gj_fc_from_rings(rings):
                    return {
                        "type": "FeatureCollection",
                        "features": [{"type": "Feature", "properties": {},
                                      "geometry": {"type": "Polygon",
                                                   "coordinates": [[list(p) for p in _ensure_closed(r)]]}}
                                     for r in rings if len(r) >= 3]
                    }
                for gi, rings in enumerate(groups_ll, 1):
                    if not rings:
                        out_groups.append([])
                        continue
                    tmp_in4326 = out_dir / f"_tmp_grp_{gi}_in4326.geojson"
                    tmp_gpkg = out_dir / f"_tmp_grp_{gi}.gpkg"
                    tmp_2193 = out_dir / f"_tmp_grp_{gi}_2193.gpkg"
                    tmp_union4326 = out_dir / f"_tmp_grp_{gi}_union4326.geojson"

                    tmp_in4326.write_text(json.dumps(_gj_fc_from_rings(rings)), encoding="utf-8")

                    r = _ogr2([ogr2ogr2, "-f", "GPKG", str(tmp_gpkg), str(tmp_in4326),
                              "-nln", "grp4326", "-lco", "GEOMETRY_NAME=geom", "-overwrite"])
                    if r.returncode == 0:
                        r = _ogr2([ogr2ogr2, "-f", "GPKG", str(tmp_2193), str(tmp_gpkg), "grp4326",
                                  "-nln", "grp2193", "-t_srs", "EPSG:2193", "-overwrite"])

                    ok_union = False
                    if r.returncode == 0:
                        r = _ogr2([ogr2ogr2, "-f", "GeoJSON", str(tmp_union4326), str(tmp_2193),
                                  "-dialect", "SQLite",
                                  "-sql", "SELECT ST_Union(geom) AS geom FROM grp2193",
                                  "-t_srs", "EPSG:4326", "-overwrite"])
                        ok_union = (r.returncode == 0 and tmp_union4326.exists() and tmp_union4326.stat().st_size > 0)

                    ring_single = None
                    if ok_union:
                        try:
                            gj2 = json.loads(tmp_union4326.read_text(encoding="utf-8"))
                            feats2 = gj2.get("features") or []
                            if feats2:
                                g2 = (feats2[0].get("geometry") or {})
                                if g2.get("type") == "Polygon":
                                    ring_single = g2["coordinates"][0][:-1]
                                elif g2.get("type") == "MultiPolygon":
                                    polys = [(_ring_area_m2_ll(poly[0][:-1]), poly[0][:-1]) for poly in
                                             (g2.get("coordinates") or []) if poly and poly[0]]
                                    if polys: ring_single = max(polys, key=lambda t: t[0])[1]
                        except Exception:
                            ring_single = None
                    if not ring_single:
                        ring_single = max(rings, key=_ring_area_m2_ll) if rings else []

                    out_groups.append([ring_single])

                    for pth in (tmp_in4326, tmp_gpkg, tmp_2193, tmp_union4326):
                        try: pth.unlink(missing_ok=True)
                        except Exception: pass

                return out_groups

            write_groups = _dissolve_groups_to_single_border(write_groups)

            _areas = [sum(_ring_area_m2_ll(r) for r in g) for g in write_groups]
            _avg = sum(_areas) / len(_areas) if write_groups else 0.0
            _imb = (max(_areas) - min(_areas)) / _avg * 100 if _avg else 0.0
            print("Section areas (m²):", [f"{a:.0f}" for a in _areas])
            if _avg:
                tot = sum(_areas)
                print("Section % of total:", [f"{(a/tot*100):.1f}%" for a in _areas])
            print(f"Imbalance after dissolve: ±{_imb / 2:.1f}%")

        else:
            write_groups = [[p] for p in parts]

        # --- Normalize group count BEFORE dissolve/output ---
        if len(write_groups) > k_parts:
            write_groups = write_groups[:k_parts]
        elif len(write_groups) < k_parts:
            write_groups = write_groups + [[] for _ in range(k_parts - len(write_groups))]

        # ---------- write section KMLs + per-section coords ----------
        def _color_for_idx(i: int):
            idx = chosen_idx[(i % len(chosen_idx))]
            return COLORS[idx - 1]

        for si, group in enumerate(write_groups, start=1):
            cname, bbggrr = _color_for_idx(si-1)
            fill_color  = f"{ALPHA[tone]}{bbggrr}"
            line_color  = f"{outline_alpha}{bbggrr}"

            kml_name   = f"{frag_in.title()} — Section {si}/{len(write_groups)}"
            label_text = f"{frag_in.title()} {si}"
            kml_path   = output_kml_dir / f"{suburb_slug}_section_{si:02d}.kml"   # ← KMLs to Output KML
            txt_coords = out_dir / f"{suburb_slug}_section_{si:02d}_coords.txt"   # coords stay at root

            _write_coords_txt(txt_coords, group)
            kml = _kml_multigeom_with_label(group, kml_name, label_text, line_color, fill_color, outline_width)
            kml_path.write_text(kml, encoding="utf-8")

            print(f"✅ Section {si} KML → {kml_path}")
            print(f"📝 Section {si} coordinates → {txt_coords}")

        print(f"✅ Split done via: {labels[used_method_idx]}")
        print("✅ Done.")

    except Exception as e:
        print(f"⚠️ Export failed: {e}")

def _do_export_suburb_boundary():
    """
    Wrapper for Option 1 – keeps any exceptions inside the function
    so the menu loop can continue cleanly.
    """
    try:
        extract_suburb_from_gpkg()
    except KeyboardInterrupt:
        print("\n↩️  Cancelled by user.")
    except Exception as e:
        print(f"⚠️ Unexpected error: {e}")

def reduce_boundary_points_in_folder():
    """
    Option 5: Reduce boundary points in all KML files under:
      GeoPackage Borders/Reduce Boundary Points
    Outputs simplified KMLs to:
      GeoPackage Borders/Reduced KML

    Strategy:
      - Prefer GDAL/OGR simplify (meters) via EPSG:2193
      - Binary search tolerance to hit target bytes without exceeding
        a max Hausdorff deviation (meters)
      - Fallback to GeoPandas/Shapely if GDAL binaries missing
      - NEW: Zero-deviation collinear pruning (in meters) before/after simplify
    """
    import os, json, uuid, math
    from pathlib import Path
    from subprocess import CalledProcessError

    base_dir = Path(__file__).resolve().parent
    in_dir   = base_dir / "GeoPackage Borders" / "Reduce Boundary Points"
    out_dir  = base_dir / "GeoPackage Borders" / "Reduced KML"
    out_dir.mkdir(parents=True, exist_ok=True)

    if not in_dir.exists():
        print(f"❌ Folder not found: {in_dir}")
        print("   Expected (Windows): C:\\Script\\GeoPackage Borders\\Reduce Boundary Points")
        return

    kmls = sorted([p for p in in_dir.glob("*.kml") if p.is_file()])
    if not kmls:
        print(f"ℹ️ No .kml files found in: {in_dir}")
        return

    # Targets / caps (env-overridable)
    try:
        TARGET_BYTES = int(os.environ.get("REDUCE_TARGET_BYTES", "3000"))
    except Exception:
        TARGET_BYTES = 3000
    try:
        MAX_TOL_M = float(os.environ.get("REDUCE_MAX_TOL_M", "50"))
    except Exception:
        MAX_TOL_M = 50.0
    try:
        MAX_HD_M = float(os.environ.get("REDUCE_MAX_HAUSDORFF_M", "5"))
    except Exception:
        MAX_HD_M = 5.0

    # Resolve GDAL
    gdal_bin = (base_dir / "Street Database" / "bin")
    def _exe(n: str) -> Path: return gdal_bin / (f"{n}.exe" if os.name == "nt" else n)
    ogr2ogr = _exe("ogr2ogr")
    ogrinfo = _exe("ogrinfo")

    env = _build_gdal_env(gdal_bin)
    # Best-effort SpatiaLite (not strictly required for -simplify, but handy)
    spat = _find_spatialite_binary(gdal_bin)
    if spat:
        env["OGR_SQLITE_LOAD_EXTENSIONS"] = "YES"
        env["OGR_SQLITE_EXT_PATH"] = spat
        env["SPATIALITE_SECURITY"] = "relaxed"

    def _run(cmd):
        # inject --config flags
        cmd2 = [str(cmd[0])]
        if env.get("PROJ_LIB"):  cmd2 += ["--config","PROJ_LIB",env["PROJ_LIB"]]
        if env.get("PROJ_DATA"): cmd2 += ["--config","PROJ_DATA",env["PROJ_DATA"]]
        if env.get("GDAL_DATA"): cmd2 += ["--config","GDAL_DATA",env["GDAL_DATA"]]
        return run_utf8(cmd2 + [str(x) for x in cmd[1:]], env=env)

    def _kml_size_bytes(path: Path) -> int:
        try:
            return len(path.read_bytes())
        except Exception:
            return 0

    def _vertex_count_from_kml(path: Path) -> int:
        # Quick and tolerant: read with geopandas if available; else rough regex
        try:
            import geopandas as gpd
            gdf = _gpd_read_kml_quiet(str(path))

            gdf = gdf[gdf.geometry.notnull()]
            if gdf.empty: return 0
            cnt = 0
            for g in gdf.geometry:
                if g is None: continue
                if g.geom_type == "Polygon":
                    cnt += len(g.exterior.coords)
                elif g.geom_type == "MultiPolygon":
                    for p in g.geoms:
                        cnt += len(p.exterior.coords)
            return cnt
        except Exception:
            # fallback: count commas inside <coordinates> tag as proxy for vertices
            try:
                txt = path.read_text(encoding="utf-8", errors="ignore")
                from re import findall
                coords = findall(r"<coordinates>(.*?)</coordinates>", txt, flags=re.S|re.I)
                verts = 0
                for block in coords:
                    # KML coords "lon,lat[,alt] lon,lat[,alt] ..."
                    verts += len([tok for tok in block.strip().split() if "," in tok])
                return verts
            except Exception:
                return 0

    def _hausdorff_m(orig_gj: Path, simp_gj: Path) -> float:
        """Compute Hausdorff distance in meters (2193)."""
        try:
            import geopandas as gpd
            o = gpd.read_file(str(orig_gj)).to_crs(2193)
            s = gpd.read_file(str(simp_gj)).to_crs(2193)
            if o.empty or s.empty: return math.inf
            # dissolve each then compute Hausdorff between exteriors
            ou = o.unary_union; su = s.unary_union
            return ou.hausdorff_distance(su)
        except Exception:
            return 0.0  # if we can't compute, don't block

    # ---------- NEW: zero-deviation collinear pruning helpers (EPSG:2193 meters) ----------
    def _prune_collinear_coords_ring_xy(coords_xy, tol=1e-7):
        """
        Strict straight-line pruning for a *closed* ring in planar coords (x,y in meters).

        Any vertex that lies on the straight line segment between its neighbors is removed,
        so straight segments always end up with exactly 2 points (the endpoints), no matter
        how short or long the segment is.

        tol: metric tolerance (meters). Leave very small (1e-7..1e-6) to avoid numeric noise.
        """
        if not coords_xy or len(coords_xy) < 4:
            return coords_xy[:]

        # ensure closed copy
        ring = coords_xy[:]
        if ring[0] != ring[-1]:
            ring.append(ring[0])

        def collinear_and_between(ax, ay, bx, by, cx, cy) -> bool:
            # Collinearity via cross product ≈ 0 (scaled by segment length)
            abx, aby = (bx - ax), (by - ay)
            acx, acy = (cx - ax), (cy - ay)
            cross = abx * acy - aby * acx
            seg = (abx * abx + aby * aby) ** 0.5
            # treat degenerate AB as not prunable (keep vertex)
            if seg <= tol:
                return False
            if abs(cross) > tol * seg:
                return False

            # Between test: B within bounding box expanded by tol
            xmin, xmax = (ax, cx) if ax <= cx else (cx, ax)
            ymin, ymax = (ay, cy) if ay <= cy else (cy, ay)
            if (bx < xmin - tol) or (bx > xmax + tol) or (by < ymin - tol) or (by > ymax + tol):
                return False

            # Also confirm via dot product that B sits between A and C along the line
            # (A->B)·(B->C) <= 0  ⇒ B is between or at an endpoint
            bcx, bcy = (cx - bx), (cy - by)
            bax, bay = (ax - bx), (ay - by)
            return (bax * bcx + bay * bcy) <= tol

        keep = [True] * len(ring)
        changed = True
        while changed:
            changed = False
            idxs = [i for i, k in enumerate(keep) if k]
            if len(idxs) <= 4:  # triangle + closure minimum
                break
            for j in range(len(idxs)):
                ip = idxs[(j - 1) % len(idxs)]
                ic = idxs[j]
                inx = idxs[(j + 1) % len(idxs)]
                ax, ay = ring[ip]
                bx, by = ring[ic]
                cx, cy = ring[inx]
                if collinear_and_between(ax, ay, bx, by, cx, cy):
                    keep[ic] = False
                    changed = True

        pruned = [ring[i] for i, k in enumerate(keep) if k]
        if pruned[0] != pruned[-1]:
            pruned.append(pruned[0])
        # ensure still a valid ring (triangle minimum)
        return pruned if len(pruned) >= 4 else coords_xy[:]

    def _prune_geom_collinear_2193(geom, tol=1e-7):
        """
        Apply strict straight-line pruning to a Shapely Polygon/MultiPolygon in EPSG:2193 (meters).
        Keeps holes; only removes interior collinear vertices along straight segments.
        """
        from shapely.geometry import Polygon, MultiPolygon

        if geom is None or geom.is_empty:
            return geom

        def prune_polygon(p: "Polygon"):
            if p.is_empty:
                return p
            ext = list(p.exterior.coords)
            ext_xy = [(float(x), float(y)) for x, y, *rest in ext]
            ext_p = _prune_collinear_coords_ring_xy(ext_xy, tol=tol)

            holes_p = []
            for r in p.interiors:
                crds = [(float(x), float(y)) for x, y, *rest in r.coords]
                pr = _prune_collinear_coords_ring_xy(crds, tol=tol)
                if len(pr) >= 4:
                    holes_p.append(pr)
            try:
                return Polygon(ext_p, holes_p)
            except Exception:
                # If numerical weirdness yields invalid shell, keep original polygon
                return p

        if geom.geom_type == "Polygon":
            return prune_polygon(geom)
        if geom.geom_type == "MultiPolygon":
            parts = [prune_polygon(g) for g in geom.geoms]
            parts = [g for g in parts if (g is not None and not g.is_empty)]
            try:
                return MultiPolygon(parts)
            except Exception:
                # fall back to unary union if MultiPolygon construction fails
                from shapely.ops import unary_union
                try:
                    return unary_union(parts)
                except Exception:
                    return geom
        return geom

    def _simplify_one_with_gdal(in_kml: Path, out_kml: Path) -> bool:
        """Binary search tolerance so size <= TARGET_BYTES (or best effort)."""
        tmp = out_kml.parent / f"__tmp_simplify_{uuid.uuid4().hex}.gpkg"
        tmp2= out_kml.parent / f"__tmp_simplify_{uuid.uuid4().hex}_2.gpkg"
        orig_gj = out_kml.parent / f"__tmp_orig_{uuid.uuid4().hex}.geojson"
        best_path = out_kml.parent / f"__tmp_best_{uuid.uuid4().hex}.kml"

        try:
            # Import polygonal only, keep 4326 layer
            r = _run([ogr2ogr, "-f","GPKG", str(tmp), str(in_kml),
                      "-nln","in4326","-overwrite",
                      "-where","OGR_GEOMETRY LIKE '%Poly%' OR OGR_GEOMETRY='Polygon' OR OGR_GEOMETRY='MultiPolygon'"])
            if r.returncode != 0: return False

            # Export original (for Hausdorff) as GeoJSON 4326
            r = _run([ogr2ogr, "-f","GeoJSON", str(orig_gj), str(tmp), "in4326",
                      "-t_srs","EPSG:4326","-overwrite"])
            if r.returncode != 0: return False

            # Reproject to 2193 once
            r = _run([ogr2ogr, "-f", "GPKG", str(tmp2), str(tmp), "in4326",
                      "-nln", "in2193", "-t_srs", "EPSG:2193", "-overwrite"])
            if r.returncode != 0: return False

            # 🔽 NEW: zero-deviation prune (requires shapely; if unavailable, skip silently)
            try:
                import geopandas as gpd
                gdf2193 = gpd.read_file(str(tmp2), layer="in2193")
                if not gdf2193.empty:
                    gdf2193["geometry"] = gdf2193["geometry"].apply(_prune_geom_collinear_2193)
                    # overwrite in2193 with pruned geometry
                    _run([ogr2ogr, "-f", "GPKG", str(tmp2), "/vsimem/_mem.gpkg", "-nln", "__empty__", "-overwrite"])
                    gdf2193.to_file(str(tmp2), layer="in2193", driver="GPKG")
            except Exception:
                pass

            # Binary search tolerance
            lo, hi = 0.0, MAX_TOL_M
            best_size = None
            best_tol  = 0.0
            iters = 12
            while iters > 0:
                iters -= 1
                mid = (lo + hi) / 2.0
                # simplify to 'simp2193'
                r = _run([ogr2ogr, "-f","GPKG", str(tmp2), str(tmp2), "in2193",
                          "-nln","simp2193","-overwrite","-simplify", f"{mid}",
                          "-lco","GEOMETRY_NAME=geom"])
                if r.returncode != 0:
                    # if simplify fails, tighten hi
                    hi = mid
                    continue

                # 🔽 NEW: prune the simplified layer too (may create fresh collinear runs)
                try:
                    import geopandas as gpd
                    gdf_s = gpd.read_file(str(tmp2), layer="simp2193")
                    if not gdf_s.empty:
                        gdf_s["geometry"] = gdf_s["geometry"].apply(_prune_geom_collinear_2193)
                        _run([ogr2ogr, "-f", "GPKG", str(tmp2), "/vsimem/_mem.gpkg", "-nln", "__empty__", "-overwrite"])
                        gdf_s.to_file(str(tmp2), layer="simp2193", driver="GPKG")
                except Exception:
                    pass

                # export to KML (4326) and measure size
                r = _run([ogr2ogr, "-f","KML", str(out_kml), str(tmp2), "simp2193",
                          "-t_srs","EPSG:4326","-overwrite"])
                if r.returncode != 0:
                    hi = mid
                    continue
                size = _kml_size_bytes(out_kml)

                # Hausdorff guard (export simplified to GeoJSON for measuring)
                simp_gj = out_kml.with_suffix(".tmp.geojson")
                _run([ogr2ogr, "-f","GeoJSON", str(simp_gj), str(tmp2), "simp2193",
                      "-t_srs","EPSG:4326","-overwrite"])
                hd = _hausdorff_m(orig_gj, simp_gj)
                try: simp_gj.unlink()
                except Exception: pass

                # If deviation too large, reduce tol
                if hd > MAX_HD_M:
                    hi = mid
                    continue

                # Acceptable; record best
                if best_size is None or size < best_size:
                    best_size = size
                    best_tol = mid
                    try:
                        best_path.write_bytes(out_kml.read_bytes())
                    except Exception:
                        pass

                # If we're already under target, try to simplify more (increase tol)
                if size <= TARGET_BYTES:
                    lo = mid  # try larger tol
                else:
                    hi = mid  # try smaller tol

            # Commit best (if any)
            if best_path.exists():
                out_kml.write_bytes(best_path.read_bytes())

                # Final safety pass: prune any remaining collinear points after writing best KML
                try:
                    import geopandas as gpd
                    s = gpd.read_file(str(out_kml))
                    if not s.empty:
                        s = s.to_crs(2193)
                        s["geometry"] = s["geometry"].apply(lambda g: _prune_geom_collinear_2193(g, tol=1e-7))
                        s = s.to_crs(4326)
                        tmp_final = out_kml.with_suffix(".final.kml")
                        s.to_file(tmp_final, driver="KML")
                        out_kml.write_bytes(tmp_final.read_bytes())
                        tmp_final.unlink(missing_ok=True)
                except Exception:
                    pass

                return True

            return False

        finally:
            for p in (tmp, tmp2, orig_gj, best_path):
                try: p.unlink(missing_ok=True)
                except Exception: pass

    def _simplify_one_with_geo(in_kml: Path, out_kml: Path) -> bool:
        try:
            import geopandas as gpd
            from shapely.ops import unary_union
            gdf = gpd.read_file(str(in_kml))
            gdf = gdf[gdf.geometry.geom_type.isin(["Polygon","MultiPolygon"])]
            if gdf.empty: return False
            gdf = gdf.to_crs(2193)
            geom = gdf.unary_union

            # 🔽 NEW: zero-deviation prune before simplify
            try:
                pruned = _prune_geom_collinear_2193(geom)
                if pruned and not pruned.is_empty:
                    geom = pruned
            except Exception:
                pass

            # Binary search tolerance
            lo, hi = 0.0, MAX_TOL_M
            best = None; best_size = None
            best_geom = None
            iters = 12
            while iters > 0:
                iters -= 1
                simp = geom.simplify(mid := (lo + hi) / 2.0, preserve_topology=True)

                # 🔽 NEW: prune simplified geometry too (no shape change, fewer vertices)
                try:
                    simp_p = _prune_geom_collinear_2193(simp)
                    if simp_p and not simp_p.is_empty:
                        simp = simp_p
                except Exception:
                    pass

                sdf = gpd.GeoSeries([simp], crs=2193).to_crs(4326)
                # write temp KML and measure
                tmpk = out_kml.parent / f"__tmp_{uuid.uuid4().hex}.kml"
                try:
                    sdf.to_file(tmpk, driver="KML")
                except Exception:
                    hi = mid
                    try: tmpk.unlink()
                    except Exception: pass
                    continue
                size = _kml_size_bytes(tmpk)
                # Hausdorff guard (approx via GeoSeries.distance if available)
                try:
                    hd = gpd.GeoSeries([geom], crs=2193).distance(gpd.GeoSeries([simp], crs=2193))[0]
                except Exception:
                    hd = 0.0
                if hd > MAX_HD_M:
                    hi = mid
                    tmpk.unlink(missing_ok=True)
                    continue
                if best is None or size < best_size:
                    best, best_size, best_geom = tmpk.read_bytes(), size, simp
                if size <= TARGET_BYTES:
                    lo = mid
                else:
                    hi = mid
                tmpk.unlink(missing_ok=True)

            if best:
                # 🔽 NEW: final prune + write from geometry for minimum vertices
                try:
                    s = gpd.GeoSeries([_prune_geom_collinear_2193(best_geom, tol=1e-7)], crs=2193).to_crs(4326)

                    tmp_final = out_kml.parent / f"__tmp_final_{uuid.uuid4().hex}.kml"
                    s.to_file(tmp_final, driver="KML")
                    out_kml.write_bytes(tmp_final.read_bytes())
                    tmp_final.unlink(missing_ok=True)
                    return True
                except Exception:
                    pass
                out_kml.write_bytes(best)
                return True
            return False
        except Exception as e:
            print(f"  ↪ GeoPandas fallback failed: {e}")
            return False

    print("\n▶ Reducing boundary points…")
    print(f"  Target size ≤ {TARGET_BYTES} bytes | max tol {MAX_TOL_M} m | max Hausdorff {MAX_HD_M} m\n")

    for kml in kmls:
        out_path = out_dir / kml.name
        orig_bytes = _kml_size_bytes(kml)
        orig_verts = _vertex_count_from_kml(kml)

        ok = False
        if ogr2ogr.exists() and ogrinfo.exists():
            ok = _simplify_one_with_gdal(kml, out_path)
        if not ok:
            ok = _simplify_one_with_geo(kml, out_path)

        if not ok:
            print(f"❌ {kml.name}: could not simplify (kept original).")
            # Copy original for consistency
            try: out_path.write_bytes(kml.read_bytes())
            except Exception: pass
            continue

        new_bytes = _kml_size_bytes(out_path)
        new_verts = _vertex_count_from_kml(out_path)
        delta_b   = orig_bytes - new_bytes
        delta_v   = orig_verts - new_verts

        status = "✅"
        warn = ""
        if new_bytes > TARGET_BYTES:
            status = "⚠️"
            warn = " (still above target)"
        print(f"✅ {kml.name}: {orig_verts}→{new_verts} verts ({delta_v:+}), {orig_bytes}→{new_bytes} bytes ({delta_b:+})")


    print("\n✅ Done Reducing Boundary Points")


def _prune_collinear_coords_ring_xy(coords_xy, eps=1e-7):
    """
    Remove consecutive collinear points from a *closed* ring in planar coords (x,y in meters).
    eps is area tolerance of the triangle formed by (prev,cur,next) / segment length scale.
    Keeps the ring closed and at least 4 vertices (min for a valid closed triangle ring).
    """
    if not coords_xy or len(coords_xy) < 4:
        return coords_xy[:]  # already minimal or degenerate

    # ensure closed
    ring = coords_xy[:]
    if ring[0] != ring[-1]:
        ring.append(ring[0])

    def tri_area2(ax, ay, bx, by, cx, cy):
        # 2x signed area = cross((B-A),(C-A))
        return (bx-ax)*(cy-ay) - (by-ay)*(cx-ax)

    keep = [True] * len(ring)
    changed = True
    # Iterate until no change to catch runs of almost-collinear points
    while changed:
        changed = False
        idxs = [i for i,k in enumerate(keep) if k]
        if len(idxs) <= 4:
            break
        for j in range(len(idxs)):
            i_prev = idxs[(j-1) % len(idxs)]
            i_cur  = idxs[j]
            i_next = idxs[(j+1) % len(idxs)]
            x1,y1 = ring[i_prev]
            x2,y2 = ring[i_cur]
            x3,y3 = ring[i_next]

            # If the three are collinear within eps, drop middle
            # Normalize by segment length to make eps scale-independent
            dx, dy = (x3-x1), (y3-y1)
            seg_len = (dx*dx + dy*dy) ** 0.5
            if seg_len == 0:
                # duplicate; safe to drop current
                keep[i_cur] = False
                changed = True
                continue

            area2 = abs(tri_area2(x1,y1,x2,y2,x3,y3))
            # area2 ~ 2 * area of triangle; compare against length-based scale
            if area2 <= eps * seg_len:
                keep[i_cur] = False
                changed = True

    pruned = [ring[i] for i,k in enumerate(keep) if k]
    # ensure closed & minimum
    if pruned[0] != pruned[-1]:
        pruned.append(pruned[0])
    if len(pruned) < 4:
        # cannot collapse below triangle; restore original
        return coords_xy[:]
    return pruned

def _prune_geom_collinear_2193(geom):
    """
    Shapely geometry in EPSG:2193 (meters). Returns a geometry with collinear vertices removed.
    Handles Polygon and MultiPolygon; preserves holes.
    """
    from shapely.geometry import Polygon, MultiPolygon, LinearRing
    from shapely.geometry.base import BaseGeometry

    if geom is None or geom.is_empty:
        return geom

    def prune_polygon(p):
        if p.is_empty:
            return p
        # exterior
        ext = list(p.exterior.coords)
        ext_p = _prune_collinear_coords_ring_xy([(float(x), float(y)) for x,y in ext], eps=1e-7)
        # interiors
        holes_p = []
        for r in p.interiors:
            crds = list(r.coords)
            crds_p = _prune_collinear_coords_ring_xy([(float(x), float(y)) for x,y in crds], eps=1e-7)
            # keep hole only if it still forms a valid ring
            if len(crds_p) >= 4:
                holes_p.append(crds_p)
        try:
            return Polygon(ext_p, holes_p)
        except Exception:
            # If invalid after pruning, fall back to original
            return p

    if geom.geom_type == "Polygon":
        return prune_polygon(geom)
    if geom.geom_type == "MultiPolygon":
        parts = [prune_polygon(g) for g in geom.geoms]
        return MultiPolygon([g for g in parts if (g is not None and not g.is_empty)])
    # pass-through for other types
    return geom



def join_kml_boundaries_from_folder():
    """
    Reads ALL *.kml files from 'GeoPackage Borders/Join KML Files' and merges
    them into one boundary. Prints the list and total before processing.
    Outputs:
      - GeoPackage Borders/joined_boundary.geojson
      - GeoPackage Borders/joined_boundary_coords.txt
      - GeoPackage Borders/Output KML/joined_boundary.kml
    Also prints a summary of which files were joined and which were skipped (with reasons).
    """
    from pathlib import Path
    import os, json

    base_dir = Path(__file__).resolve().parent
    out_dir = base_dir / "GeoPackage Borders"
    out_dir.mkdir(parents=True, exist_ok=True)
    kml_in_dir = out_dir / "Join KML Files"
    kml_out_dir = out_dir / "Output KML"
    kml_out_dir.mkdir(parents=True, exist_ok=True)

    if not kml_in_dir.exists():
        print(f"❌ Folder not found: {kml_in_dir}")
        print("   Expected (Windows): C:\\Script\\GeoPackage Borders\\Join KML Files")
        return

    kmls = sorted([p for p in kml_in_dir.glob("*.kml") if p.is_file()])
    if not kmls:
        print(f"⚠️ No .kml files found in: {kml_in_dir}")
        return

    print("📄 KML files to join:")
    for p in kmls:
        print(f"  • {p.name}")
    print(f"Total: {len(kmls)} file(s)\n")

    joined_files = []
    skipped_files: list[tuple[str, str]] = []  # (filename, reason)

    # ---------- GeoPandas/Shapely path ----------
    try:
        import geopandas as gpd
        from shapely.ops import unary_union
        from shapely.geometry import Polygon, MultiPolygon

        polys = []
        for p in kmls:
            try:
                gdf = gpd.read_file(str(p))
                if gdf.empty:
                    skipped_files.append((p.name, "empty file"))
                    continue
                gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
                if gdf.empty:
                    skipped_files.append((p.name, "no polygonal geometries"))
                    continue
                if gdf.crs is not None:
                    gdf = gdf.to_crs(4326)
                geom = gdf.unary_union
                if geom is None or geom.is_empty:
                    skipped_files.append((p.name, "geometry empty after dissolve"))
                    continue
                polys.append(geom)
                joined_files.append(p.name)
                print(f"  ✓ Added (GeoPandas): {p.name}")
            except Exception as e:
                skipped_files.append((p.name, f"read error: {e}"))

        if not polys:
            print("⚠️ All KMLs were empty or non-polygonal (GeoPandas path). Falling back to GDAL…\n")
            raise RuntimeError("geopandas_path_had_no_polygons")

        merged = unary_union(polys)

        # Write GeoJSON
        gj_path = out_dir / "joined_boundary.geojson"
        try:
            gpd.GeoSeries([merged], crs=4326).to_file(gj_path, driver="GeoJSON")
            print(f"\n✅ GeoJSON merged → {gj_path}")
        except Exception as e:
            print(f"⚠️ Could not write GeoJSON: {e}")
            # Still provide a summary before returning
            print_summary(joined_files, skipped_files)
            return

        # Extract largest outer ring (WGS84)
        def _largest_shell_xy(geom):
            if isinstance(geom, Polygon):
                return list(geom.exterior.coords)
            if isinstance(geom, MultiPolygon) and geom.geoms:
                big = max(list(geom.geoms), key=lambda poly: poly.area)
                return list(big.exterior.coords)
            return []

        ring = _largest_shell_xy(merged)
        if not ring:
            print("⚠️ Merged geometry has no valid outer ring.")
            print_summary(joined_files, skipped_files)
            return

        # Write coords (lon,lat)
        txt_path = out_dir / "joined_boundary_coords.txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            if ring[0] != ring[-1]:
                ring = ring + [ring[0]]
            for x, y, *rest in ring:
                f.write(f"{float(x)},{float(y)}\n")
        print(f"📝 Coords written → {txt_path}")

        # Simple styled KML
        def _kml_of_polygon(coords_ll, name="Joined Boundary"):
            coords_str = " ".join(f"{x},{y},100" for x, y, *rest in coords_ll)
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
  <name>{name}</name>
  <Placemark>
    <name>{name}</name>
    <Style>
      <LineStyle><color>ff0000ff</color><width>2</width></LineStyle>
      <PolyStyle><color>660000ff</color><fill>1</fill><outline>1</outline></PolyStyle>
    </Style>
    <Polygon>
      <tessellate>1</tessellate>
      <outerBoundaryIs><LinearRing><coordinates>{coords_str}</coordinates></LinearRing></outerBoundaryIs>
    </Polygon>
  </Placemark>
</Document>
</kml>"""

        out_kml = kml_out_dir / "joined_boundary.kml"
        out_kml.write_text(_kml_of_polygon(ring, name="Joined Boundary"), encoding="utf-8")
        print(f"✅ KML merged → {out_kml}")
        print_summary(joined_files, skipped_files)
        print("✅ Done.")
        return

    except Exception:
        # fall through to GDAL/ogr2ogr fallback
        pass

    # ---------- GDAL/ogr2ogr fallback ----------
    try:
        db_dir = (base_dir / "Street Database")
        gdal_bin = db_dir / "bin"
        ogr2ogr = gdal_bin / ("ogr2ogr.exe" if os.name == "nt" else "ogr2ogr")
        ogrinfo = gdal_bin / ("ogrinfo.exe" if os.name == "nt" else "ogrinfo")
        env = _build_gdal_env(gdal_bin)

        tmp = out_dir / "_tmp_join.gpkg"
        try:
            tmp.unlink()
        except Exception:
            pass

        imported_idx = []  # 1-based layer indexes that made it in
        for idx, path in enumerate(kmls, start=1):
            r = run_utf8([
                str(ogr2ogr),
                "--config","PROJ_LIB",env.get("PROJ_LIB",""),
                "--config","PROJ_DATA",env.get("PROJ_DATA",""),
                "--config","GDAL_DATA",env.get("GDAL_DATA",""),
                "-f","GPKG", str(tmp), str(path),
                "-nln", f"in_{idx}",
                "-overwrite",
                "-where", "OGR_GEOMETRY LIKE '%Poly%' OR OGR_GEOMETRY='Polygon' OR OGR_GEOMETRY='MultiPolygon'"
            ], env=env)
            if r.returncode == 0:
                info = run_utf8([str(ogrinfo), "-json", str(tmp), f"in_{idx}"], env=env)
                try:
                    fc = (json.loads(info.stdout).get("layers") or [{}])[0].get("featureCount", 0) or 0
                except Exception:
                    fc = 0
                if fc > 0:
                    imported_idx.append(idx)
                    joined_files.append(path.name)
                    print(f"  ✓ Added (GDAL): {path.name}")
                else:
                    skipped_files.append((path.name, "no polygonal features"))
            else:
                skipped_files.append((path.name, "ogr2ogr import failed"))

        if not imported_idx:
            print("⚠️ All KMLs missing/empty/non-polygonal (GDAL path).")
            print_summary(joined_files, skipped_files)
            return

        # Dissolve all imported layers into one geometry
        sql_union = " UNION ALL ".join([f"SELECT geom FROM in_{i}" for i in imported_idx])
        sql = f"WITH U AS (SELECT ST_Union(geom) AS geom FROM ({sql_union})) SELECT geom FROM U"
        gj_path = out_dir / "joined_boundary.geojson"
        r = run_utf8([
            str(ogr2ogr),
            "--config","PROJ_LIB",env.get("PROJ_LIB",""),
            "--config","PROJ_DATA",env.get("PROJ_DATA",""),
            "--config","GDAL_DATA",env.get("GDAL_DATA",""),
            "-f","GeoJSON", str(gj_path), str(tmp),
            "-dialect","SQLite", "-sql", sql,
            "-t_srs","EPSG:4326","-overwrite"
        ], env=env)
        if r.returncode != 0 or not gj_path.exists() or gj_path.stat().st_size == 0:
            print("❌ Union/export failed.")
            print_summary(joined_files, skipped_files)
            return
        print(f"\n✅ GeoJSON merged → {gj_path}")

        with open(gj_path, "r", encoding="utf-8") as f:
            gj = json.load(f)
        feats = gj.get("features") or []
        if not feats:
            print("⚠️ No merged feature present.")
            print_summary(joined_files, skipped_files)
            return
        geom = feats[0].get("geometry") or {}
        coords = []
        if geom.get("type") == "Polygon":
            coords = geom.get("coordinates", [[]])[0]
        elif geom.get("type") == "MultiPolygon":
            polys = [(len(p[0]) if p and p[0] else 0, p[0]) for p in geom.get("coordinates", [])]
            coords = max(polys, key=lambda t: t[0])[1] if polys else []

        if not coords:
            print("⚠️ Merged geometry has no outer ring.")
            print_summary(joined_files, skipped_files)
            return

        txt_path = out_dir / "joined_boundary_coords.txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            if coords[0] != coords[-1]:
                coords = coords + [coords[0]]
            for x, y, *rest in coords:
                f.write(f"{float(x)},{float(y)}\n")
        print(f"📝 Coords written → {txt_path}")

        def _kml(name, coords_ll):
            cs = " ".join(f"{x},{y},100" for x, y, *rest in coords_ll)
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
  <name>{name}</name>
  <Placemark>
    <name>{name}</name>
    <Style>
      <LineStyle><color>ff0000ff</color><width>2</width></LineStyle>
      <PolyStyle><color>660000ff</color><fill>1</fill><outline>1</outline></PolyStyle>
    </Style>
    <Polygon>
      <tessellate>1</tessellate>
      <outerBoundaryIs><LinearRing><coordinates>{cs}</coordinates></LinearRing></outerBoundaryIs>
    </Polygon>
  </Placemark>
</Document>
</kml>"""

        out_kml = kml_out_dir / "joined_boundary.kml"
        out_kml.write_text(_kml("Joined Boundary", coords), encoding="utf-8")
        print(f"✅ KML merged → {out_kml}")
        print_summary(joined_files, skipped_files)
        print("✅ Done.")

    except Exception as e:
        # Final catch: print the failure and a clear summary of what didn’t join
        print(f"❌ Join failed: {e}")
        print_summary(joined_files, skipped_files)


def print_summary(joined_files: list[str], skipped_files: list[tuple[str, str]]) -> None:
    """Helper: print a clean summary of which files made it and which didn’t."""
    print("\n— Summary —")
    print(f"Joined: {len(joined_files)} file(s)")
    for n in joined_files:
        print(f"  ✓ {n}")
    print(f"Skipped: {len(skipped_files)} file(s)")
    for n, reason in skipped_files:
        print(f"  • {n} — {reason}")



def delete_kml_boundaries_in_folder():
    """
    Deletes ALL *.kml files inside 'GeoPackage Borders/Join KML Files'.
    Prints each deleted filename and the total.
    (Keeps non-KML files intact.)
    """
    base_dir = Path(__file__).resolve().parent
    folder = base_dir / "GeoPackage Borders" / "Join KML Files"

    if not folder.exists():
        print(f"❌ Folder not found: {folder}")
        return

    kmls = sorted([p for p in folder.glob("*.kml") if p.is_file()])
    if not kmls:
        print(f"ℹ️ No .kml files to delete in: {folder}")
        return

    print("🗑️ Deleting KML files:")
    deleted = 0
    for p in kmls:
        try:
            p.unlink()
            print(f"  • {p.name}")
            deleted += 1
        except Exception as e:
            print(f"  ↪ Could not delete {p.name}: {e}")

    print(f"Total deleted: {deleted} file(s)")



# ================================
# Simple CLI Menu (adds Option 1)
# ================================

def render_menu():
    print("\n\033[4mGeoPackage Borders\033[0m")
    print("1 - 🗺️ Export Suburb Boundary")
    print("2 - ✂️  Divide Boundary Into Sections (from KML)")
    print("3 - 🔗 Join KML Boundaries (Join KML Files folder)")
    print("4 - 🗑️  Delete KML Boundaries (Join KML Files folder)")
    print("5 - 📉 Reduce Boundary Points (Reduce Boundary Points folder)")

def open_menu():
    while True:
        render_menu()
        choice = input("Choose an option: ").strip().lower()

        if choice == "0":
            print("👋 Bye!")
            break
        elif choice == "1":
            print("\n▶ Option 1: Export Suburb Boundary")
            _do_export_suburb_boundary()
        elif choice == "2":
            print("\n▶ Option 2: Divide Polygon By Cut Lines (from KML)")
            try: divide_polygon_by_cut_lines_from_kml()
            except KeyboardInterrupt: print("\n↩️  Cancelled by user.")
            except Exception as e: print(f"⚠️ Unexpected error: {e}")
        elif choice == "3":
            print("\n▶ Option 3: Join KML Boundaries (Join KML Files folder)")
            try: join_kml_boundaries_from_folder()
            except KeyboardInterrupt: print("\n↩️  Cancelled by user.")
            except Exception as e: print(f"⚠️ Unexpected error: {e}")
        elif choice == "4":
            print("\n▶ Option 4: Delete KML Boundaries (Join KML Files folder)")
            try: delete_kml_boundaries_in_folder()
            except KeyboardInterrupt: print("\n↩️  Cancelled by user.")
            except Exception as e: print(f"⚠️ Unexpected error: {e}")
        elif choice == "5":
            print("\n▶ Option 5: Reduce Boundary Points (Reduce Boundary Points folder)")
            try: reduce_boundary_points_in_folder()
            except KeyboardInterrupt: print("\n↩️  Cancelled by user.")
            except Exception as e: print(f"⚠️ Unexpected error: {e}")
        else:
            print("  ↪ Unknown option. Please choose again.")





def main():
    """
    Start the menu instead of calling the exporter directly.s
    """
    try:
        open_menu()
    except KeyboardInterrupt:
        print("\n👋 Bye!")

if __name__ == "__main__":
    main()
