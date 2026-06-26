# Part 3/4 Start
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

# Part 3/4 End
