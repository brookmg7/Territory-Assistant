# Part 2/4 Start
                    lat_old = float(latitude or "0")
                    lon_old = float(longitude or "0")
                    lat_new = float(fresh_lat or 0.0)
                    lon_new = float(fresh_lon or 0.0)
                except Exception:
                    lat_old = lon_old = lat_new = lon_new = 0.0

                old_in_akl = is_in_auckland(lat_old, lon_old)
                new_in_akl = is_in_auckland(lat_new, lon_new)

                if (not old_in_akl) and new_in_akl:
                    row["Latitude"] = lat_new
                    row["Longitude"] = lon_new
                    if is_blank_or_zero(row.get("PostalCode")):
                        row["PostalCode"] = fresh_postal or nz_postal_lookup.get(row['Suburb'].strip(), "")
                    log_correction("Geocode Correction Override",
                                   f"Business: replaced outside-AKL coords with AKL coords for {addr_query}")
                _adopt_label_suburb_and_postcode(row, fresh_addr, fresh_postal)
            elif fresh_addr and not has_original_coords:
                row["Latitude"] = fresh_lat
                row["Longitude"] = fresh_lon
                if is_blank_or_zero(row.get("PostalCode")):
                    row["PostalCode"] = fresh_postal or nz_postal_lookup.get(row['Suburb'].strip(), "")
                _adopt_label_suburb_and_postcode(row, fresh_addr, fresh_postal)
    else:
        # ---------- Non-business ----------
        if not fresh_addr:
            retry = targeted_geocode_retry(
                row=row,
                all_rows=all_rows,
                known_geocodes_by_street=known_geocodes_by_street
            )
            if retry:
                fresh_addr, fresh_lat, fresh_lon, fresh_postal = retry
                row["Latitude"] = fresh_lat
                row["Longitude"] = fresh_lon
                _adopt_label_suburb_and_postcode(row, fresh_addr, fresh_postal)
            else:
                row["Final Status"] = "Fail"
                log_street_fail(row, "Geocode not found after CSV-aware retry", addr_query)
                return row_result
        else:
            if is_blank_or_zero(row.get("Latitude")) or is_blank_or_zero(row.get("Longitude")):
                lat_new = float(fresh_lat or 0.0)
                lon_new = float(fresh_lon or 0.0)
                lat_new, lon_new = maybe_swap_into_auckland(lat_new, lon_new)
                if is_blank_or_zero(row.get("Latitude")):
                    row["Latitude"] = lat_new
                if is_blank_or_zero(row.get("Longitude")):
                    row["Longitude"] = lon_new
            _adopt_label_suburb_and_postcode(row, fresh_addr, fresh_postal)

        if verify_geocode:
            try:
                lat_old = float(latitude or "0")
                lon_old = float(longitude or "0")
                lat_new = float(fresh_lat or 0.0)
                lon_new = float(fresh_lon or 0.0)
                lat_new, lon_new = maybe_swap_into_auckland(lat_new, lon_new)

                lat_ok = not is_blank_or_zero(lat_old) and abs(lat_old - lat_new) < 0.0001
                lon_ok = not is_blank_or_zero(lon_old) and abs(lon_old - lon_new) < 0.0001
                should_replace = not (lat_ok and lon_ok)
                if should_replace:
                    street_key = (row["Street"].strip().title(), row["Suburb"].strip().title())
                    existing_coords = known_geocodes_by_street.get(street_key, []) if known_geocodes_by_street else []
                    if existing_coords:
                        distances = [haversine_distance(lat_new, lon_new, a, b) for (a, b) in existing_coords]
                        if all(d > MAX_ALLOWED_DISTANCE for d in distances):
                            should_replace = False
                if should_replace:
                    row["Latitude"] = lat_new
                    row["Longitude"] = lon_new
            except Exception as e:
                log_correction("Geocode Verification Error", f"{addr_query} → {str(e)}")
        else:
            if is_blank_or_zero(row.get("PostalCode")):
                row["PostalCode"] = fresh_postal or nz_postal_lookup.get(row['Suburb'].strip(), "")

    # --- Status filtering/duplicates ---
    status = (row.get("Status", "") or "").strip().lower()
    if status in {"custom1", "donotcall"}:
        if status == "custom1":
            row["Final Status"] = "Not Chinese"
        elif status == "donotcall":
            row["Final Status"] = "Do Not Call"
        return row_result

    full_key = (
        row.get("ApartmentNumber", "").strip(),
        row['Number'].strip(),
        row['Street'],
        row['Suburb']
    )
    # NEW: do NOT mark Duplicate here
    if seen_addresses is not None:
        # keep tracking if you still want a set, but don’t fail the row
        seen_addresses.add(addr_key)
    # continue normal processing...

    row['State'] = "Auckland"
    row = fix_lat_lon_if_swapped(row)
    row['PostalCode'] = row.get("PostalCode") or nz_postal_lookup.get(row['Suburb'].strip(), "")
    row['Status'] = "Available"
    row["Final Status"] = "Pass"
    row["Suburb"] = row["Suburb"].strip().title()

    if dominant_suburb_map and row.get("Street") in dominant_suburb_map:
        final = dominant_suburb_map[row["Street"]].strip().title()
        if row["Suburb"] != final:
            log_correction("Suburb Replaced", f"Enforced dominant suburb → {row['Suburb']} → {final} for {row['Street']}")
            row["Suburb"] = final

    row_result["status"] = "clean"
    return row_result

# ---------- PATCH: Lift embedded suburb from Street (all variants) ----------

# Aliases & neutral tails we should strip from the end of a Street field.
SUBURB_ALIASES = {
    # shortforms → canonical
    "gi": "Glen Innes",
    "st heliers": "St Heliers",
    "saint heliers": "St Heliers",
    "st johns": "St Johns",
    "saint johns": "St Johns",
    "mt wellington": "Mount Wellington",
    "mt  wellington": "Mount Wellington",
    "mtwellington": "Mount Wellington",
    "tamaki": "Tāmaki",
    "tāmaki": "Tāmaki",
}
NEUTRAL_TAILS = {"Auckland", "Auckland City", "New Zealand", "NZ"}

def _ascii_fold_patch(s: str) -> str:
    """ASCII-fold and lightly clean a string (keeps only letters/digits/spaces)."""
    import unicodedata, re
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^A-Za-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def _canon_suburb_name_patch(s: str, valid_suburbs_set):
    """
    Map 's' to a canonical suburb found in valid_suburbs_set.
    Handles aliases, case/space differences, ASCII/macron variants, and light fuzzy.
    Returns '' if no confident match.
    """
    import re
    if not s: return ""
    base = s.strip()

    # alias first (case/space-insensitive via folded key)
    key = re.sub(r"\s+", " ", _ascii_fold_patch(base)).lower()
    alias = SUBURB_ALIASES.get(key)
    if alias:
        base = alias

    # exact hit preserves macrons
    if base in valid_suburbs_set:
        return base

    # case-insensitive
    lowmap = {vs.lower(): vs for vs in valid_suburbs_set}
    hit = lowmap.get(base.lower())
    if hit:
        return hit

    # ascii-folded hit
    foldmap = {_ascii_fold_patch(vs).lower(): vs for vs in valid_suburbs_set}
    hit = foldmap.get(_ascii_fold_patch(base).lower())
    if hit:
        return hit

    # optional fuzzy (prefers your helper if present)
    try:
        if "safe_fuzzy_match" in globals() and callable(safe_fuzzy_match):
            cand = safe_fuzzy_match(base, list(valid_suburbs_set), threshold=88)
            if cand:
                return cand
        else:
            import difflib
            cand = difflib.get_close_matches(base, list(valid_suburbs_set), n=1, cutoff=0.88)
            if cand:
                return cand[0]
    except Exception:
        pass
    return ""

def lift_embedded_suburb_all(row: dict, valid_suburbs_iterable):
    """
    Pull ANY suburb that’s embedded in Street into Suburb.
    Handles: commas, dashes, slashes, parentheses, spaces-only tails,
    'Auckland/NZ' tails, RD/postcode tails, Mt↔Mount, Saint↔St, GI→Glen Innes,
    macron glitches. Leaves row unchanged if no safe match.

    Expected row keys: "Street", "Suburb".
    """
    import re

    # Prepare inputs
    street_in = fix_macron_corruption((row.get("Street") or "").strip())
    suburb_in = (row.get("Suburb") or "").strip()
    if not street_in or suburb_in:
        return row  # nothing to do

    valid_set = set(valid_suburbs_iterable or [])

    # 1) strip trailing RD/postcode/neutral country tails
    s = street_in
    s = re.sub(r"\bR\.?D\.?\s*\d+\b\s*$", "", s, flags=re.IGNORECASE)  # RD 1, RD1, R.D. 1
    s = re.sub(r"\b\d{4}\b\s*$", "", s)  # NZ 4-digit postcode (trailing)
    s = re.sub(
        r"(?:[,\s/\-–—()]*)(?:%s)\s*$" % "|".join(re.escape(t) for t in sorted(NEUTRAL_TAILS, key=len, reverse=True)),
        "",
        s,
        flags=re.IGNORECASE,
    ).strip()

    # 2) build candidates from delimiters and no-delimiter endings
    parts = re.split(r"[,/()\-–—]+", s)
    parts = [p.strip() for p in parts if p.strip()]
    candidates = []

    if len(parts) >= 2:
        # prefer the rightmost chunk, and also the last two chunks joined
        candidates.append(parts[-1])
        candidates.append(" ".join(parts[-2:]))

    words = s.split()
    # last 3/2/1 words (only if at least one word remains for the street)
    for k in (3, 2, 1):
        if len(words) >= k + 1:
            candidates.append(" ".join(words[-k:]))

    # 3) normalise candidates and try to find a suburb
    hit_suburb = ""
    for c in candidates:
        c_norm = c.strip(" ,")
        # Skip neutral tails
        if _ascii_fold_patch(c_norm).lower() in {t.lower() for t in NEUTRAL_TAILS}:
            continue
        # Normalise Saint/Mount variants commonly seen in tails
        c_norm = re.sub(r"(?i)^saint\s+", "St ", c_norm)
        c_norm = re.sub(r"(?i)^mt\s+", "Mount ", c_norm)

        cand = _canon_suburb_name_patch(c_norm, valid_set)
        if cand:
            hit_suburb = cand
            break

    if not hit_suburb:
        return row  # no confident suburb found; leave untouched

    # 4) remove the matched suburb token from the END of the street safely;
    #    allow optional delimiter and optional Auckland/NZ after it.
    pattern = r"""
        [\s,/()\-–—]*                 # optional delimiters
        %s                            # matched suburb name
        (?:[\s,/()\-–—]+(?:%s))?      # optional neutral tail (Auckland/NZ) after suburb
        \s*$                          # end of string
    """ % (re.escape(hit_suburb), "|".join(re.escape(t) for t in NEUTRAL_TAILS))
    new_street = re.sub(pattern, "", s, flags=re.IGNORECASE | re.VERBOSE).strip()

    # cleanup & guard
    new_street = re.sub(r"\s+", " ", new_street).strip()
    if not new_street:
        return row  # never blank the street

    # 5) write back with canon suburb (respect macrons)
    row["Street"] = new_street.title()
    row["Suburb"] = macron_suburb_map.get(hit_suburb, hit_suburb)
    return row
# ---------- END PATCH ----------




def _canonical_by_proximity_for_street(street_title, rows, radius_m=800, k_nearest=5):
    """
    Pick a single suburb for a street using proximity across BOTH buffers.
    Uses coords from any rows that already have them (clean > fail). Falls back to CSV counts.
    """
    from collections import Counter
    pts = []
    for r in rows:
        st = (r.get("Street") or "").strip().title()
        if st != street_title:
            continue
        sb = (r.get("Suburb") or "").strip().title() or "Auckland"
        la = safe_float(r.get("Latitude"), None)
        lo = safe_float(r.get("Longitude"), None)
        if la is None or lo is None or not is_in_auckland(la, lo):
            continue
        pts.append((la, lo, sb))

    # proximity vote if we have coordinates
    if pts:
        # centroid
        lat_c = sum(p[0] for p in pts)/len(pts)
        lon_c = sum(p[1] for p in pts)/len(pts)
        # k-nearest
        scored = []
        for la, lo, sb in pts:
            d = haversine_distance(la, lo, lat_c, lon_c)
            scored.append((d, sb))
        scored.sort(key=lambda x: x[0])
        topk = scored[:max(1, k_nearest)]
        # winner = most common suburb among nearest; tie → smallest avg distance
        from collections import Counter
        top_counts = Counter(sb for _, sb in topk)
        best, _ = top_counts.most_common(1)[0]
        return best

    # fallback: frequency in CSV if no coords
    subs = [ (r.get("Suburb") or "").strip().title()
             for r in rows if (r.get("Street") or "").strip().title() == street_title and (r.get("Suburb") or "").strip() ]
    if subs:
        return Counter(subs).most_common(1)[0][0]

    return ""


def unify_street_suburb_across_outputs(clean_rows, fail_rows, radius_m=800, k_nearest=5):
    """
    Enforce one-suburb-per-street across BOTH buffers before writing files.
    Returns (clean_rows, fail_rows, affected_streets_set).
    - Canonicalizes suburb strings before compare/lookup (handles macrons/variants).
    - Avoids preferring 'Auckland' unless it's the only viable label.
    """
    # Safe helpers present elsewhere in your codebase
    def _norm_street(s): return (s or "").strip().title()
    def _norm_suburb(s):  # canon + title for compare
        s0 = (s or "").strip().title()
        try:
            return macron_suburb_map.get(s0, s0)  # if you have it
        except Exception:
            return s0



    # Build a light index with normalized fields to cut repeated .strip().title() calls
    def _prep(rows):
        out = []
        for r in rows:
            st = _norm_street(r.get("Street"))
            sb_raw = (r.get("Suburb") or "").strip()
            sb = _norm_suburb(sb_raw) if sb_raw else ""   # keep truly blank as ""
            out.append((r, st, sb))
        return out

    clean_idx = _prep(clean_rows)
    fail_idx  = _prep(fail_rows)
    all_idx   = clean_idx + fail_idx

    streets = sorted({ st for (_r, st, _sb) in all_idx if st })

    affected = set()
    for st in streets:
        # Pull rows for this street
        rows_for_st = [(r, st2, sb2) for (r, st2, sb2) in all_idx if st2 == st]

        # Let proximity choose, but normalize and avoid defaulting to Auckland if others exist
        canonical_suburb = _canonical_by_proximity_for_street(
            st,
            [r for (r, _st2, _sb2) in rows_for_st],  # pass raw rows as your helper expects
            radius_m=radius_m,
            k_nearest=k_nearest
        ) or ""

        canonical_suburb = _norm_suburb(canonical_suburb)
        # If proximity returned 'Auckland' but we have non-empty, non-Auckland labels in this street,
        # prefer the most common non-Auckland suburb.
        if canonical_suburb == "Auckland":
            non_akls = [sb for (_r, _st2, sb) in rows_for_st if sb and sb != "Auckland"]
            if non_akls:
                from collections import Counter
                canonical_suburb = Counter(non_akls).most_common(1)[0][0]

        if not canonical_suburb:
            # Nothing to unify to
            continue

        # Is there any disagreement vs the canonical (treat blank suburb as blank, not 'Auckland')
        had_disagreement = any(
            sb != canonical_suburb
            for (_r, _st2, sb) in rows_for_st
        )

        if not had_disagreement:
            continue

        affected.add(st)

        # Postal: lookup using canonical (already canonized)
        pc = ""
        try:
            pc = nz_postal_lookup.get(canonical_suburb, "")  # safe if mapping exists
        except Exception:
            pc = ""

        def _apply(idx, rows):
            for (r, st2, sb2) in idx:
                if st2 != st:
                    continue
                if (sb2 or "Auckland") == canonical_suburb or sb2 == canonical_suburb:
                    continue  # already correct

                old_sb_raw = (r.get("Suburb") or "").strip()
                r["Suburb"] = canonical_suburb

                # Only set PostalCode if we actually have a canonical code and it's different
                if pc and (r.get("PostalCode", "") or "") != pc:
                    r["PostalCode"] = pc

                log_correction(
                    "Cross-Buffer Unify",
                    f"{old_sb_raw or '<blank>'} → {canonical_suburb}",
                    street=st
                )

        _apply(clean_idx, clean_rows)
        _apply(fail_idx,  fail_rows)

    return clean_rows, fail_rows, affected


async def collect_all_results(address, session, limiters):
    """
    Run LINZ, geocode.xyz, Nominatim, Photon concurrently, collect all results, then choose.

    Expected per-fetch return:
      - tuple like (label, lat, lon, postal) or (label, lat, lon)
      - or None / Exception

    Returns:
      - best tuple (label, lat, lon, postal) OR None
    """
    # ---- helpers (kept local so this is a drop-in replacement) ----
    def _as_float(x):
        try:
            if x is None:
                return None
            s = str(x).strip()
            if not s:
                return None
            return float(s)
        except Exception:
            return None

    def _norm_tuple(tpl):
        """
        Normalize provider output to (label, lat(float), lon(float), postal(str)).
        Return None if unusable.
        """
        if not isinstance(tpl, tuple):
            return None
        if len(tpl) < 3:
            return None

        label = tpl[0]
        lat = _as_float(tpl[1])
        lon = _as_float(tpl[2])
        postal = ""
        if len(tpl) >= 4 and tpl[3] is not None:
            postal = str(tpl[3]).strip()

        if not label or lat is None or lon is None:
            return None

        return (str(label).strip(), lat, lon, postal)

    async def _safe_call(coro):
        try:
            return await coro
        except Exception:
            return None

    # ---- limiter safety (avoid KeyError) ----
    lim_linz = (limiters or {}).get("linz")
    lim_xyz = (limiters or {}).get("geocodexyz")
    lim_nom = (limiters or {}).get("nominatim")
    lim_pho = (limiters or {}).get("photon")

    # ---- schedule tasks ----
    tasks = [
        _safe_call(fetch_linz(address, session, limiter=lim_linz)),
        _safe_call(fetch_geocodexyz(address, session, limiter=lim_xyz)),
        _safe_call(fetch_nominatim(address, session, limiter=lim_nom)),
        _safe_call(fetch_photon(address, session, limiter=lim_pho)),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=False)

    # ---- normalize + filter ----
    normalized = []
    for r in results:
        nt = _norm_tuple(r)
        if nt:
            normalized.append(nt)

    if not normalized:
        return None

    # ---- choose best (expects list of tuples) ----
    best = choose_best_geocode(normalized)

    # Some choose_best_geocode implementations might return the original provider tuple;
    # normalize again to guarantee the shape we return.
    best_norm = _norm_tuple(best)
    return best_norm




def reattempt_fail_geocodes_after_unify(
    fail_rows,
    affected_streets,
    all_rows,
    known_geocodes_by_street=None
):
    """
    Re-try ONLY rows whose Final Status is 'Fail' AND whose Status is retryable,
    and whose street is in affected_streets. Skip Duplicate/Not Chinese/Do Not Call/etc.
    """
    cleaned = []
    still_fail = []

    for r in fail_rows:
        st = (r.get("Street") or "").strip().title()
        if st not in affected_streets or not is_retryable_fail(r):
            still_fail.append(r)
            continue

        num = (r.get("Number") or "").strip()
        sb  = (r.get("Suburb") or "").strip().title()   # unified suburb already applied

        # Ensure suffix before retry
        r["Street"] = ensure_suffix_via_sources(num, r["Street"], sb, all_rows)

        # Targeted retry first
        hit = targeted_geocode_retry(r, all_rows, known_geocodes_by_street=known_geocodes_by_street)

        # Hard fallback: plain get_lat_long on unified address
        if not hit:
            hit = get_lat_long(fmt_addr_parts(num, r["Street"], sb),
                               known_geocodes_by_street=known_geocodes_by_street)

        if _is_valid_geocode_tuple(hit):
            addr, la, lo, pc = hit
            r["Latitude"] = la
            r["Longitude"] = lo
            if not (r.get("PostalCode") or "").strip() and pc:
                r["PostalCode"] = pc
            r["Final Status"] = "Pass"
            log_correction("Re-Geocode After Unify", f"Accepted '{addr}'", street=st)
            cleaned.append(r)
        else:
            still_fail.append(r)

    return cleaned, still_fail




def _norm_status(s: str) -> str:
    """Normalize status/final status for comparison."""
    import re
    return re.sub(r"\s+", "", (s or "").strip().lower())

# Skip list for both Status and Final Status checks
_NONRETRY_STATUSES = {
    "duplicate", "notchinese", "custom1", "donotcall",
    "cancelled", "moved", "deceased"
}

def is_retryable_fail(row) -> bool:
    """
    True if:
      - Final Status == 'Fail'
      - Status not in skip list
      - Final Status also not in skip list
    """
    fs = _norm_status(row.get("Final Status"))
    s  = _norm_status(row.get("Status"))

    # Skip if Status or Final Status matches non-retryable list
    if fs in _NONRETRY_STATUSES or s in _NONRETRY_STATUSES:
        return False

    return fs == "fail"




def load_cache():
    global _geocode_cache
    with _cache_lock:
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    _geocode_cache = json.load(f)   # ← no re-keying here
            except Exception:
                _geocode_cache = {}


def save_cache():
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with _cache_lock:
        # write normalized keys
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({k: v for k, v in _geocode_cache.items()}, f)



# ------------------- LINZ DB Setup -------------------
def ensure_linz_sqlite():
    """
    Import LINZ CSV into SQLite, normalizing columns and adding search-friendly folds:
    - Guarantees columns exist: Number, Postalcode, Latitude, Longitude, Street, Suburb
    - Splits LatLong if present
    - Adds StreetFold/SuburbFold (ASCII/diacritic-free, lowercase) for macron-insensitive search
    - Adds BaseFold (street base w/o suffix, folded) for fast suffix-agnostic queries
    - Creates indexes on the folded columns
    """
    import unicodedata, re

    def _fold(s: str) -> str:
        # diacritic-insensitive, ascii-ish, lowercase, single-spaced
        s = (s or "")
        s = unicodedata.normalize("NFKD", s)
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        s = s.encode("ascii", "ignore").decode("ascii")
        s = re.sub(r"\s+", " ", s).strip().lower()
        return s

    def _base_of(street: str) -> str:
        parts = (street or "").strip().split()
        return " ".join(parts[:-1]).strip() if len(parts) > 1 else (street or "").strip()

    needs_rebuild = False
    if os.path.exists(LINZ_DB):
        try:
            conn = sqlite3.connect(LINZ_DB)
            c = conn.cursor()
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='addresses';")
            has_table = bool(c.fetchone())
            if not has_table:
                needs_rebuild = True
            else:
                # If table exists but is empty OR missing new folded columns → rebuild
                c.execute("SELECT COUNT(*) FROM addresses;")
                if (c.fetchone() or [0])[0] == 0:
                    needs_rebuild = True
                else:
                    c.execute("PRAGMA table_info(addresses);")
                    cols = {row[1] for row in c.fetchall()}
                    required = {"StreetFold", "SuburbFold", "BaseFold"}
                    if not required.issubset(cols):
                        needs_rebuild = True
            conn.close()
        except Exception:
            needs_rebuild = True
    else:
        needs_rebuild = True

    if not needs_rebuild:
        return

    # Read CSV into DataFrame
    df = pd.read_csv(LINZ_FILE, dtype=str).fillna("")
    df = df.loc[:, ~df.columns.duplicated()]  # drop duplicate headings

    # Ensure mandatory columns exist
    for col in ["Number", "Postalcode", "Latitude", "Longitude", "Street", "Suburb"]:
        if col not in df.columns:
            df[col] = ""

    # Split "LatLong" if present
    if "LatLong" in df.columns:
        lat_lon_split = df["LatLong"].str.split(",", n=1, expand=True)
        df["Latitude"] = lat_lon_split[0].astype(str).str.strip()
        df["Longitude"] = lat_lon_split[1].astype(str).str.strip()

    # Build folded/search helper columns
    # Keep original Street/Suburb as-is for display; folds are for query joins
    df["StreetFold"] = df["Street"].apply(_fold)
    df["SuburbFold"] = df["Suburb"].apply(_fold)
    df["BaseFold"]   = df["Street"].apply(_base_of).apply(_fold)

    # Write to SQLite
    conn = sqlite3.connect(LINZ_DB)
    df.to_sql("addresses", conn, if_exists="replace", index=False)
    c = conn.cursor()

    # Helpful indexes (folds + Number for fast exact and base-prefix style lookups)
    c.execute("CREATE INDEX IF NOT EXISTS idx_number        ON addresses (Number)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_street_fold   ON addresses (StreetFold)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_suburb_fold   ON addresses (SuburbFold)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_base_fold     ON addresses (BaseFold)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_postalcode    ON addresses (Postalcode)")
    # Keep legacy indexes too (no harm, but folds will be used in new queries)
    c.execute("CREATE INDEX IF NOT EXISTS idx_street        ON addresses (Street)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_suburb        ON addresses (Suburb)")

    conn.commit()
    conn.close()

    log_correction("LINZ DB Rebuild",
                   f"Rebuilt from {os.path.basename(LINZ_FILE)} with {len(df)} rows (folded columns added)")




def get_linz_conn():
    ensure_linz_sqlite()
    with _db_lock:
        return sqlite3.connect(LINZ_DB)


def bulk_linz_lookup(addresses, linz_conn=None, memory_conn=None):
    if linz_conn is None:
        linz_conn = globals().get("linz_conn", None)
    if memory_conn is None:
        memory_conn = globals().get("memory_conn", None)

    results = {}

    # Parse and normalize wanted addresses
    parsed = []
    for addr in addresses:
        m = ADDRESS_PARSE_RX.match(addr)
        if not m:
            continue
        num, street, suburb = [x.strip() for x in m.groups()]
        try:
            num = normalize_number(num)
            num, street = merge_number_with_street(num, street)
            street = correct_suffix_typos(street).strip().title()
            suburb = suburb.strip().title()
        except Exception:
            pass
        parsed.append((addr, street.lower(), suburb.lower(), num))

    if not parsed:
        return results

    # What we want to match exactly
    wanted = {(s, sub, n) for _, s, sub, n in parsed}
    streets = list({p[1] for p in parsed})
    in_clause = ",".join(["?"] * len(streets))

    def run_query(conn, table_name="addresses"):
        if not conn:
            return []
        q = f"""
            SELECT Number, Street, Suburb, Latitude, Longitude, Postalcode
            FROM {table_name}
            WHERE LOWER(Street) IN ({in_clause})
        """
        try:
            return conn.execute(q, streets).fetchall()
        except Exception:
            return []

    linz_rows = run_query(linz_conn, "addresses")
    memory_rows = []
    if memory_conn:
        try:
            memory_rows = memory_conn.execute(f"""
                SELECT number, street, suburb, latitude, longitude, postalcode
                FROM other_addresses
                WHERE LOWER(street) IN ({in_clause})
            """, streets).fetchall()
        except Exception:
            memory_rows = []

    # Filter rows to only those we actually want, then emit results
    for number, street, suburb, lat, lon, postcode in (linz_rows + memory_rows):
        if lat in ("", None) or lon in ("", None):
            continue
        try:
            lat = float(lat); lon = float(lon)
        except Exception:
            continue

        street_l = (street or "").strip().lower()
        suburb_l = (suburb or "").strip().lower()
        number_n = normalize_number(str(number or ""))

        if (street_l, suburb_l, number_n) not in wanted:
            continue

        key = addr_key(number_n, street, suburb)
        results[key] = (
            f"{str(street).strip().title()}, {str(suburb).strip().title()}, Auckland",
            lat,
            lon,
            str(postcode or "")
        )

    return results


# --- External-friendly address helpers ---
UNIT_RX = re.compile(r'^Unit([A-Z0-9]+)/(\d+)$', re.IGNORECASE)

def to_external_query(addr: str) -> str:
    """Convert 'UnitB/246 Bucklands Beach Rd, Suburb' to '246B Bucklands Beach Road, Suburb'."""
    m = ADDRESS_PARSE_RX.match(addr.strip())
    if not m:
        return addr

    number, street, suburb = [x.strip() for x in m.groups()]
    street = correct_suffix_typos(street).title()
    suburb = suburb.title()

    um = UNIT_RX.match(number)
    if um:
        unit, base = um.groups()
        number_ext = f"{base}{unit.upper()}"
    else:
        number_ext = re.sub(r'\s+', '', number)

    # Expand suffix if in map
    parts = street.split()
    if parts and parts[-1] in street_suffix_map:
        parts[-1] = street_suffix_map[parts[-1]]
    street = " ".join(parts)

    return f"{number_ext} {street}, {suburb}, Auckland"


from collections import Counter, defaultdict
from fuzzywuzzy import fuzz
import re

def _letters_only(s: str) -> str:
    return re.sub(r"[^a-z]", "", (s or "").lower())

def _bases_similar_70(a: str, b: str) -> bool:
    a1, b1 = _letters_only(a), _letters_only(b)
    if not a1 or not b1:
        return False
    try:
        score = max(
            fuzz.token_set_ratio(a1, b1),
            fuzz.ratio(a1, b1),
            fuzz.partial_ratio(a1, b1),
        )
    except Exception:
        import difflib
        score = int(difflib.SequenceMatcher(None, a1, b1).ratio() * 100)
    return score >= 80

# >>> PATCH START: Unit/House number normaliser
import re


# Canonical patterns
_UNIT_PREFIX_RE = re.compile(
    r'^\s*Unit\s*([A-Za-z0-9]+)\s*/\s*([0-9]+[A-Za-z]?(?:\s*-\s*[0-9]+[A-Za-z]?)?)\s*$',
    re.IGNORECASE
)
_HOUSE_UNIT_SUFFIX_RE = re.compile(
    r'^\s*([0-9]+[A-Za-z]?(?:\s*-\s*[0-9]+[A-Za-z]?)?)\s*/\s*Unit\s*([A-Za-z0-9]+)\s*$',
    re.IGNORECASE
)

def normalize_unit_house_number(s: str) -> str:
    """
    Lossless normalizer for 'Number' that **never** swaps sides.
    - Keeps the semantics exactly as written: UnitX/HouseY ≠ UnitY/HouseX.
    - Cleans spacing and dash/slash formatting.
    - Uppercases the unit token.
    - If the *reverse* form 'House/UnitX' is supplied, it is converted
      to the canonical internal form 'UnitX/House' (no inference).
    - Does not try to "fix" ambiguous forms like '26/3' (no 'Unit' keyword).
    """
    s = (s or "").strip()
    if not s:
        return ""

    # strip any leading punctuation noise (e.g., ". Unit15/3")
    s = re.sub(r"^[^\w]+", "", s)

    # tidy spaces around slash and dash
    s = re.sub(r"\s*/\s*", "/", s)
    s = re.sub(r"\s*-\s*", "-", s)

    # 1) Unit-prefix form: keep sides, normalize token + house formatting
    m = _UNIT_PREFIX_RE.match(s)
    if m:
        unit_token = m.group(1).upper()
        house_part = m.group(2)
        return f"Unit{unit_token}/{house_part}"

    # 2) Reverse form 'House/UnitX' → canonical 'UnitX/House' (no guesswork)
    m = _HOUSE_UNIT_SUFFIX_RE.match(s)
    if m:
        house_part = m.group(1)
        unit_token = m.group(2).upper()
        return f"Unit{unit_token}/{house_part}"

    # 3) Plain house number or ambiguous patterns → return tidied input unchanged
    return s



def _unify_similar_bases(bases: list[str], base_counts: Counter) -> dict[str, str]:
    """
    Map variant_base -> canonical_base using 70% similarity.
    Canonical = most frequent, then longest.
    """
    def _len_letters(s): return len(_letters_only(s))
    uniques = sorted(set(bases), key=lambda x: (-base_counts.get(x, 0), -_len_letters(x), x))
    alias, visited = {}, set()

    for base in uniques:
        if base in visited:
            continue
        group = [base]
        for other in uniques:
            if other in visited or other == base:
                continue
            if _bases_similar_70(base, other):
                group.append(other)
                visited.add(other)
        visited.add(base)

        canonical = max(group, key=lambda x: (base_counts.get(x, 0), _len_letters(x)))
        for g in group:
            alias[g] = canonical

        if len(group) > 1:
            try:
                merged = [g for g in group if g != canonical]
                if merged:
                    log_correction("Street Base Merge",
                                   f"Canonical '{canonical}' ← {', '.join(sorted(merged))}")
            except Exception:
                pass

    return alias

# =========================
# 🔧 FAST PATCH: Stages 3.3–3.5
# - pre_correct_street_spellings (3.3)
# - standardize_similar_streets (3.4)
# - resolve_conflicting_suburbs_by_proximity (3.5)
# Uses RapidFuzz when available. Minimal logging to speed up I/O.
# =========================

# ---- RapidFuzz (fallback to difflib) ----
try:
    from rapidfuzz import fuzz as _rf_fuzz, process as rf_process
    def _rf_score(a: str, b: str) -> int:
        return max(int(_rf_fuzz.token_set_ratio(a, b)), int(_rf_fuzz.ratio(a, b)))
    _HAS_RF = True
except Exception:
    import difflib as _difflib
    def _rf_score(a: str, b: str) -> int:
        return int(_difflib.SequenceMatcher(None, a, b).ratio() * 100)
    _HAS_RF = False


def _append_note(msg_base, extra):
    msg_base = (msg_base or "").strip()
    extra = (extra or "").strip()
    if not msg_base:
        return extra
    if extra.lower() in msg_base.lower():
        return msg_base
    return f"{msg_base} / {extra}"

def _read_csv_rows(path):
    import csv, os
    if not os.path.exists(path):
        return [], []
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        rows = list(csv.DictReader(f))
        fieldnames = list((rows[0].keys() if rows else []))
    return rows, fieldnames

def _write_csv_rows(path, rows, fieldnames):
    import csv
    # sanitize headers and keep stable order
    fns = [c for c in (fieldnames or []) if isinstance(c, str) and c.strip()]
    # add required columns if missing
    for col in ["Status", "Number", "Notes", "Final Status"]:
        if col not in fns:
            fns.append(col)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fns, extrasaction="ignore", restval="")
        w.writeheader()
        w.writerows(rows)

def _transform_new_street(row, note_msg):
    row["Status"] = "Custom3"
    row["Number"] = ""
    row["Notes"] = _append_note(row.get("Notes", ""), note_msg)
    return row

def postprocess_new_streets(clean_file="output_clean.csv",
                            fail_file="output_fail.csv",
                            missing_file="missing_addresses.csv",
                            include_missing_into_clean=True):
    """
    Apply New Streets changes to clean + fail rows and (optionally) ingest
    missing_addresses.csv → into clean (Pass), then rewrite clean/fail files.
    """
    import os

    note_msg = 'Please refer to "New Streets" for more information'

    # --- Clean ---
    clean_rows, clean_fns = _read_csv_rows(clean_file)
    if clean_rows:
        for r in clean_rows:
            _transform_new_street(r, note_msg)
    _write_csv_rows(clean_file, clean_rows, clean_fns)
    ok_c = bool(clean_rows)

    # --- Fail ---
    fail_rows, fail_fns = _read_csv_rows(fail_file)
    if fail_rows:
        for r in fail_rows:
            _transform_new_street(r, note_msg)
    _write_csv_rows(fail_file, fail_rows, fail_fns)
    ok_f = bool(fail_rows)

    # --- Missing → Clean (Pass) ---
    ok_m = False
    if include_missing_into_clean and os.path.exists(missing_file):
        missing_rows, missing_fns = _read_csv_rows(missing_file)
        # If there are any missing rows, transform & promote to clean:
        if missing_rows:
            # Normalize schemas: union of clean + missing headers (preserve order by preferring clean first)
            union_fns = list(dict.fromkeys((clean_fns or []) + (missing_fns or [])))
            new_missing = []
            for r in missing_rows:
                r = _transform_new_street(r, note_msg)
                # "send to pass" → clear Final Status so they count as Clean
                r["Final Status"] = ""
                new_missing.append(r)

            # Append promoted missings to existing clean rows
            clean_rows = (clean_rows or []) + new_missing
            _write_csv_rows(clean_file, clean_rows, union_fns)
            ok_m = True

    print(f"✅ New Streets post-process → clean: {ok_c} | fail: {ok_f} | promoted_missing: {ok_m}")




# >>> PATCH: add write_missing_addresses_csv_and_check
def write_missing_addresses_csv_and_check(input_file, clean_file, fail_file, out_file):
    """
    Compare input_nws.csv against the union of output_clean.csv + output_fail.csv
    and write any addresses that disappeared to `out_file`.

    • Multiset-aware: if an address appears N times in input but only M times in outputs,
      it records (N-M) missing instances.
    • Canonicalizes address keys so minor formatting isn’t treated as different:
      - flips "UnitX/<house>" to "<house>/UnitX" for comparison
      - expands common street suffix abbreviations once (Rd -> Road, etc.)
      - fixes common suffix typos (Hts -> Heights, Cresent -> Crescent, etc.)
      - normalizes suburb with macrons when available; treats exact "Auckland" as blank
    • Skips rows where Type == "Other" (these are not geocoded by the pipeline).
    """
    import csv, re
    from collections import Counter

    # ---- Safe hooks to existing helpers (fallbacks if not defined) ----
    _expand_once = globals().get("expand_street_suffix_once", lambda s: s)
    _fix_typos   = globals().get("correct_suffix_typos",   lambda s: s)
    _flip_unit   = globals().get("flip_unit_prefix_in_number", lambda s: s)
    _norm_suburb_ascii = globals().get("normalize_suburb_ascii", lambda s: (s or "").strip().title())
    _macron_map = globals().get("macron_suburb_map", {})

    def _to_str(x):
        if x is None: return ""
        s = str(x).strip()
        return s

    def _canon_number(n):
        s = _to_str(n)
        s = re.sub(r"\s*-\s*", "-", s)  # tidy ranges
        # Normalize "UnitX/<house>" → "<house>/UnitX"
        s = _flip_unit(s)
        # Normalize "unit" case and any spaces around slash
        s = re.sub(r"(?i)^\s*(\d+[A-Za-z]?(?:-\d+[A-Za-z]?)?)\s*/\s*unit\s*([A-Za-z0-9]+)\s*$",
                   r"\1/Unit\2", s)
        return s

    def _canon_street(st):
        s = _to_str(st)
        # one-time suffix expand, then typo fix, then Title Case and space collapse
        s = _expand_once(s)
        s = _fix_typos(s)
        s = " ".join(s.split()).title()
        return s

    def _canon_suburb(sb):
        s = _to_str(sb)
        if s.lower() == "auckland":
            return ""  # treat as blank
        # Prefer your macron-aware normaliser if available
        s = _norm_suburb_ascii(s)
        # Ensure Title Case and macron mapping if provided
        s = _macron_map.get(s.title(), s.title())
        return s

    def _addr_key(number, street, suburb):
        n = _canon_number(number)
        st = _canon_street(street)
        sb = _canon_suburb(suburb)
        return f"{n}|{st}|{sb}"

    def _load_rows(path):
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                return list(csv.DictReader(f))
        except FileNotFoundError:
            return []
        except Exception:
            return []

    # ---- Load files ----
    input_rows = _load_rows(input_file)
    clean_rows = _load_rows(clean_file)
    fail_rows  = _load_rows(fail_file)

    # ---- Build multiset of OUTPUT address keys ----
    out_counts = Counter()
    for r in clean_rows + fail_rows:
        num = _to_str(r.get("Number"))
        st  = _to_str(r.get("Street"))
        sb  = _to_str(r.get("Suburb"))
        if num and st:
            out_counts[_addr_key(num, st, sb)] += 1

    # ---- Walk INPUT rows in-order and find missing instances ----
    missing_rows = []
    for r in input_rows:
        # Skip Type == "Other" — the pipeline never geocodes these
        type_norm = _to_str(r.get("Type")).lower()
        if type_norm == "other":
            continue

        num = _to_str(r.get("Number"))
        st  = _to_str(r.get("Street"))
        sb  = _to_str(r.get("Suburb"))
        if not (num and st):
            # no address — keep original behaviour of not counting these
            continue

        k = _addr_key(num, st, sb)
        if out_counts[k] > 0:
            out_counts[k] -= 1  # consume one instance
        else:
            # This instance is missing → keep the original row as-is in the report
            missing_rows.append(r)

    # ---- Write report ----
    # Use the input header order when possible
    fieldnames = list(input_rows[0].keys()) if input_rows else [
        "Number","Street","Suburb","PostalCode","Status","Latitude","Longitude"
    ]
    # Ensure consistent set
    fieldnames = [c for c in fieldnames if isinstance(c, str) and c.strip()]
    fieldnames = list(dict.fromkeys(fieldnames))  # de-dup while preserving order

    with open(out_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore", restval="")
        writer.writeheader()
        for r in missing_rows:
            writer.writerow(r)

    # Console + optional log message
    msg = f"Missing address check: {len(missing_rows)} row(s) not found in outputs → wrote '{out_file}'."
    print("🔎 " + msg)
    if "log_correction" in globals():
        try:
            log_correction("Missing Address Check", msg)
        except Exception:
            pass
# >>> PATCH END

import csv, re

# --- helpers for canonical comparison (ignore suburb) ---
_UNIT_PREFIX_RX = re.compile(
    r'^\s*Unit\s*([A-Za-z0-9]+)\s*/\s*([0-9]+[A-Za-z]?(?:-[0-9]+[A-Za-z]?)?)\s*$',
    re.IGNORECASE
)
_UNIT_SUFFIX_RX = re.compile(
    r'^\s*([0-9]+[A-Za-z]?(?:-[0-9]+[A-Za-z]?)?)\s*/\s*Unit\s*([A-Za-z0-9]+)\s*$',
    re.IGNORECASE
)


def _canon_number_for_compare(num: str) -> str:
    """
    Map UnitA/1 and 1/UnitA to the same token: '1|UA'.
    Keeps ranges (e.g. 12-14) and letter suffixes on the house number.
    """
    s = (num or "").strip()
    if not s:
        return ""
    m = _UNIT_PREFIX_RX.match(s)
    if m:
        unit = m.group(1).upper()
        house = re.sub(r'\s*-\s*', '-', m.group(2))
        return f"{house}|U{unit}"
    m = _UNIT_SUFFIX_RX.match(s)
    if m:
        house = re.sub(r'\s*-\s*', '-', m.group(1))
        unit = m.group(2).upper()
        return f"{house}|U{unit}"
    # plain house number (normalize dash spacing)
    house = re.sub(r'\s*-\s*', '-', s)
    return house.upper() if house.isalpha() else house


def _canon_street_for_compare(st: str) -> str:
    """
    Normalize street for comparison:
      - Title case
      - expand one trailing suffix (Rd→Road, etc.)
      - fix common typos (Hght→Heights, Cresent→Crescent, etc.)
      - collapse spaces
    """
    s = (st or "").strip().title()
    s = expand_street_suffix_once(s)
    s = correct_suffix_typos(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def write_missing_addresses_csv_and_check(input_file, clean_file, fail_file, out_file):
    """
    Write rows from input_file that are NOT present in (clean_file ∪ fail_file),
    comparing ONLY (Number, Street) after canonicalization.
    Suburb differences will NOT cause a row to be flagged as missing.
    """

    def _read_rows(path):
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                return list(csv.DictReader(f))
        except FileNotFoundError:
            return []

    inp_rows = _read_rows(input_file)
    clean_rows = _read_rows(clean_file)
    fail_rows = _read_rows(fail_file)

    # Build a set of present keys from outputs (clean + fail), ignoring suburb
    present_keys = set()
    for r in (clean_rows + fail_rows):
        num = _canon_number_for_compare((r.get("Number") or "").strip())
        st = _canon_street_for_compare((r.get("Street") or "").strip())
        if num and st:
            present_keys.add((num, st))

    # Collect input rows whose (Number, Street) pair does NOT exist in outputs
    missing = []
    for r in inp_rows:
        num = _canon_number_for_compare((r.get("Number") or "").strip())
        st = _canon_street_for_compare((r.get("Street") or "").strip())
        if num and st:
            if (num, st) not in present_keys:
                missing.append(r)
        else:
            # If Number or Street is blank, treat it as missing (unchanged behavior)
            missing.append(r)

    # Write missing rows to out_file (preserving input headers if possible)
    if inp_rows:
        headers = list(inp_rows[0].keys())
    elif clean_rows:
        headers = list(clean_rows[0].keys())
    elif fail_rows:
        headers = list(fail_rows[0].keys())
    else:
        headers = ["Number", "Street", "Suburb", "PostalCode", "Status", "Latitude", "Longitude"]

    with open(out_file, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore", restval="")
        w.writeheader()
        w.writerows(missing)


# ---- quiet logging switch (avoid disk I/O unless important) ----
RESULT_ONLY_LOGS = True  # set False to see detailed audit logs again

def _log_quiet(event, details="", street=None, important=False):
    # only write to file if it's marked important OR global switch is off
    if RESULT_ONLY_LOGS and not important:
        return
    try:
        log_correction(event, details, street=street)
    except Exception:
        pass

# ---- similarity helpers (keep thresholds consistent with your design) ----
def _letters_only_fast(s: str) -> str:
    # cheaper than regex per call
    s = (s or "").lower()
    return "".join(ch for ch in s if "a" <= ch <= "z")

def _bases_similar(a: str, b: str, threshold: int) -> bool:
    a1, b1 = _letters_only_fast(a), _letters_only_fast(b)
    if not a1 or not b1:
        return False
    return _rf_score(a1, b1) >= threshold

def _unify_similar_bases_fast(
    bases: list[str],
    base_counts,
    sim_threshold: int = 86,     # ↑ from 80 → 86 by default
    max_len_delta: int = 2       # block merges if len diff > 2
) -> dict[str, str]:
    """
    Map variant_base -> canonical_base using similarity.
    Guards to avoid false merges like Eaglen → Eaglemont:
      • higher default threshold (86)
      • max length delta (±2)
      • block long-tail prefixy merges (≥4-char common prefix then ≥3-char tail)
      • skip PROTECTED_STREETS bases
    Callers can lower/raise `sim_threshold` as needed (e.g., 70 for 3.3).
    """
    def _letters_only_fast(s: str) -> str:
        # use existing util if present
        try:
            return globals()['_letters_only_fast'](s)
        except Exception:
            import re
            return re.sub(r'[^A-Za-z]', '', s or '')

    def _common_prefix_len(a: str, b: str) -> int:
        n = min(len(a), len(b))
        i = 0
        while i < n and a[i] == b[i]:
            i += 1
        return i

    def _blocks_long_tail_extension(a: str, b: str) -> bool:
        sa = _letters_only_fast(a).lower()
        sb = _letters_only_fast(b).lower()
        cpl = _common_prefix_len(sa, sb)
        tail_a = len(sa) - cpl
        tail_b = len(sb) - cpl
        # If they share a solid prefix (≥4) and one side adds a ≥3-char tail, block.
        return cpl >= 4 and (tail_a >= 3 or tail_b >= 3)

    # Build protected base set from PROTECTED_STREETS (if defined)
    protected_bases = set()
    try:
        if 'PROTECTED_STREETS' in globals():
            for s in PROTECTED_STREETS:
                base_disp, _ = _norm_base_key(s)  # your helper: returns (display_base, key)
                protected_bases.add(base_disp)
    except Exception:
        pass

    # prefix buckets to avoid O(n^2) on unrelated names
    buckets: dict[str, list[str]] = {}
    for b in bases:
        k = _letters_only_fast(b)[:4]  # short key
        buckets.setdefault(k, []).append(b)

    alias: dict[str, str] = {}
    visited: set[str] = set()

    for _, group in buckets.items():
        # sort: most common, then longest, then alpha — improves canonical stability
        group_sorted = sorted(
            set(group),
            key=lambda x: (-base_counts.get(x, 0), -len(_letters_only_fast(x)), x)
        )
        for i, base in enumerate(group_sorted):
            if base in visited:
                continue
            visited.add(base)
            ba = _letters_only_fast(base)
            for other in group_sorted[i + 1:]:
                if other in visited:
                    continue
                if base in protected_bases or other in protected_bases:
                    continue

                ob = _letters_only_fast(other)
                # hard length guard
                if abs(len(ba) - len(ob)) > max_len_delta:
                    continue
                # long-tail prefixy guard
                if _blocks_long_tail_extension(base, other):
                    continue

                # similarity check (uses your existing _bases_similar if available)
                try:
                    similar = _bases_similar(base, other, sim_threshold)
                except Exception:
                    # difflib fallback if _bases_similar not available
                    import difflib
                    ratio = difflib.SequenceMatcher(None, base, other).ratio()
                    similar = ratio >= (sim_threshold / 100.0)

                if similar:
                    alias[other] = base
                    visited.add(other)
    return alias



def _parse_geocoded_label(full_addr: str) -> tuple[str, str]:
    """Return (Street, Suburb) parsed from geocoder label."""
    try:
        parts = (full_addr or "").split(",")
        street = (parts[0] or "").strip().title()
        suburb = (parts[1] or "").strip().title() if len(parts) > 1 else ""
        return street, suburb
    except Exception:
        return "", ""


def enforce_final_street_spelling(all_rows):
    """
    Final enforcement of street spelling:
    Ensures all variations of the same base match the dominant spelling in the dataset.
    Runs after Stage 3.5, so geocode failures can't leave bad spellings in output.
    """
    from collections import defaultdict, Counter

    clusters = defaultdict(list)

    # Group by base (suffixless)
    for idx, r in enumerate(all_rows):
        st = (r.get("Street") or "").strip()
        if not st:
            continue
        base_disp, base_key = _norm_base_key(st)
        clusters[base_key].append(idx)

    # Apply dominant spelling for each base cluster
    for base_key, idxs in clusters.items():
        street_counts = Counter(
            (all_rows[i].get("Street") or "").strip().title()
            for i in idxs if (all_rows[i].get("Street") or "").strip()
        )
        if not street_counts:
            continue

        dominant_street = street_counts.most_common(1)[0][0]

        for i in idxs:
            cur_st = (all_rows[i].get("Street") or "").strip().title()
            if cur_st != dominant_street:
                _log_quiet(
                    "Final-Enforce: Street",
                    f"{cur_st} → {dominant_street}",
                    street=dominant_street,
                    important=False
                )
                all_rows[i]["Street"] = dominant_street

    return all_rows



# ---- Stage 3.3: Pre-correct street spellings (faster & quieter) ----
def pre_correct_street_spellings(all_rows, verbose=False):
    from tqdm import tqdm as _tqdm
    from collections import Counter, defaultdict
    import re

    changed = 0

    # --- Pre-normalise / typo fixes BEFORE base key extraction ---
    for r in all_rows:
        st = (r.get("Street") or "").strip()
        if not st:
            continue
        fixed = st
        fixed = re.sub(r"ikd", "ickd", fixed, flags=re.IGNORECASE)  # Carrikdawson -> Carrickdawson
        fixed = re.sub(r"\s+", " ", fixed)  # collapse spaces
        fixed = fix_known_text_glitches(fixed)
        if fixed != st:
            _log_quiet("Pre-correct: Street OCR", f"{st} → {fixed}", street=fixed, important=False)
            r["Street"] = fixed
            changed += 1

    # Build raw bases with progress bar
    raw_bases, idx_to_base = [], {}
    for idx, r in _tqdm(enumerate(all_rows), total=len(all_rows),
                        desc="🔄 Stage 1: Checking/Correcting Streets...", unit="row"):
        st = (r.get("Street") or "").strip()
        if not st:
            continue
        base_disp, _ = _norm_base_key(st)
        raw_bases.append(base_disp)
        idx_to_base[idx] = base_disp

    base_counts = Counter(raw_bases)

    # --- Bucketed fuzzy match (≥70%) ---
    alias_70 = {}
    buckets = {}
    for b in set(raw_bases):
        k = _letters_only_fast(b)[:4]
        buckets.setdefault(k, []).append(b)
    for group in buckets.values():
        group_sorted = sorted(group, key=lambda x: (-base_counts.get(x,0), -len(_letters_only_fast(x)), x))
        for i, base in enumerate(group_sorted):
            for other in group_sorted[i+1:]:
                if _bases_similar(base, other, 80):
                    canonical = max((base, other), key=lambda x: (base_counts.get(x,0), len(_letters_only_fast(x))))
                    alias_70[(other if canonical == base else base)] = canonical

    # --- Global fallback fuzzy pass for rare bases ---
    rare_bases = [b for b, c in base_counts.items() if c < 3]
    for base in rare_bases:
        for other in set(raw_bases):
            if base != other and _bases_similar(base, other, 80):
                canonical = max((base, other), key=lambda x: (base_counts.get(x,0), len(_letters_only_fast(x))))
                alias_70[base] = canonical
                break

    # --- Apply canonical replacements ---
    clusters = defaultdict(list)
    for idx, r in enumerate(all_rows):
        if idx not in idx_to_base:
            continue
        base_disp, _ = _norm_base_key(r.get("Street") or "")
        can_base = alias_70.get(base_disp, base_disp)
        clusters[can_base].append(idx)

    for base, idxs in clusters.items():
        # Majority suburb in cluster
        sub_counts = Counter(
            canon_suburb((all_rows[i].get("Suburb") or "").strip())
            for i in idxs if (all_rows[i].get("Suburb") or "").strip()
        )
        majority_suburb = sub_counts.most_common(1)[0][0] if sub_counts else ""

        # Choose canonical spelling from majority suburb or most frequent overall
        street_counts = Counter(
            (all_rows[i].get("Street") or "").strip().title()
            for i in idxs if (all_rows[i].get("Street") or "").strip()
        )
        majority_street = street_counts.most_common(1)[0][0] if street_counts else base

        for i in idxs:
            cur_st = (all_rows[i].get("Street") or "").strip().title()
            new_st = majority_street
            if new_st and cur_st != new_st:
                _log_quiet("Pre-correct: Street", f"{cur_st} → {new_st}", street=new_st, important=False)
                all_rows[i]["Street"] = new_st
                changed += 1

    return all_rows, changed


def unit_word_variant(addr: str) -> str:
    """Convert 'UnitB/246 Bucklands Beach Rd, Suburb' to '246 Bucklands Beach Road, Unit B, Suburb'."""
    m = ADDRESS_PARSE_RX.match(addr.strip())
    if not m:
        return addr

    number, street, suburb = [x.strip() for x in m.groups()]
    um = UNIT_RX.match(number)
    if not um:
        return addr

    unit, base = um.groups()
    street = correct_suffix_typos(street).title()
    suburb = suburb.title()

    return f"{base} {street}, Unit {unit.upper()}, {suburb}, Auckland"


def _nearby_support_count(lat, lon, known_coords, radius_m=1000):
    if not known_coords:
        return 0
    try:
        return sum(1 for (a,b) in known_coords if haversine_distance(lat, lon, a, b) <= radius_m)
    except Exception:
        return 0

# --- House/Unit number normalizers (used by addr_key, LINZ lookups, etc.) ---
import re

# Use the global UNIT_RX if it exists; otherwise define a local fallback.
try:
    UNIT_RX
except NameError:
    UNIT_RX = re.compile(r'^Unit([A-Z0-9]+)/(\d+)$', re.IGNORECASE)

_RANGE_RX  = re.compile(r'^\s*(\d+[A-Za-z]?)[\s-]+(\d+[A-Za-z]?)\s*$')
_SIMPLE_RX = re.compile(r'^\s*(\d+)([A-Za-z]?)\s*$')
_SLASH_RX  = re.compile(r'^\s*(\d+[A-Za-z]?)\s*/\s*(\d+[A-Za-z]?)\s*$')

def normalize_number(number_val: str) -> str:
    """
    Normalizes NZ unit/house numbers consistently.
    - Converts month codes (Jan–Dec) to Unit1–Unit12 based on correct month index.
    - Handles letter suffixes (37B → UnitB/37).
    - Cleans separators (~, _, -, etc.) into '/'.
    - Ensures Unit prefix, uppercased.
    """
    number = number_val.strip()
    number = re.sub(r"\s+", "", number)  # collapse spaces

    # Month abbreviation mapping (Jan = 1 ... Dec = 12)
    month_map = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5,
        'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10,
        'nov': 11, 'dec': 12
    }

    # Match patterns like "1-Nov", "2-Oct", "Nov-41", or just "Nov"
    m = re.match(r'^(\d*)[-_/]*([A-Za-z]{3})(?:[-_/]*(\d+))?$', number, re.IGNORECASE)
    if m:
        unit_part, month_abbr, trailing_num = m.groups()
        month_num = month_map.get(month_abbr.lower(), 1)

        # If unit number exists (like "1-Nov"), that becomes the unit prefix
        if unit_part:
            return f"Unit{unit_part}/{month_num}"
        # If it's just "Nov-41", month becomes the unit, trailing is the number
        elif trailing_num:
            return f"Unit{month_num}/{trailing_num}"
        # If it's just "Nov"
        else:
            return f"Unit{month_num}"

    # Letter suffix (e.g., 37B → UnitB/37)
    m = re.match(r'^(\d+)([A-Za-z])$', number)
    if m:
        return f"Unit{m.group(2).upper()}/{m.group(1)}"

    # Replace odd separators with '/'
    number = re.sub(r'[~_\-,.\\:;!\=\+\"\'\(\)]', '/', number)

    # Prepend 'Unit' if there’s a slash but no Unit prefix
    if '/' in number and not number.lower().startswith('unit'):
        parts = number.split('/', 1)
        number = f"Unit{parts[0]}/{parts[1]}"

    # Normalize casing
    if number.lower().startswith("unit"):
        prefix = "Unit"
        remainder = ''.join(ch.upper() if ch.isalpha() else ch for ch in number[4:])
        number = prefix + remainder
    else:
        number = ''.join(ch.upper() if ch.isalpha() else ch for ch in number)

    return number


def merge_number_with_street(number_val, street_val):
    """
    Combines and normalizes NZ unit/house numbers with streets:
    - Converts 39A → UnitA/39
    - If both Number and Street begin with the same digit (e.g., "3" + "3 Macleans Rd"),
      strip the street's duplicate number.
    - Fixes street typos like "Bucklandsbeach" → "Bucklands Beach".
    """
    num_clean = re.sub(r"\s+", "", number_val.strip())

    # Lettered numbers: 39A → UnitA/39
    m = re.match(r'^(\d+)([A-Za-z])$', num_clean)
    if m:
        num_clean = f"Unit{m.group(2).upper()}/{m.group(1)}"

    # If street starts with the same number, strip it
    m2 = re.match(r"^\s*(\d+)\s+(.*)$", street_val.strip())
    if m2:
        street_num, street_name = m2.groups()
        if street_num == re.sub(r'\D', '', num_clean):  # compare digits only
            street_val = street_name

    # Normalize "Bucklandsbeach" type issues
    street_val = re.sub(r"bucklands\s*beach", "Bucklands Beach", street_val, flags=re.IGNORECASE)

    # Expand suffix abbreviations & title case
    parts = street_val.strip().title().split()
    if parts and parts[-1] in street_suffix_map:
        parts[-1] = street_suffix_map[parts[-1]]
    street_val = " ".join(parts)

    return num_clean, street_val


def _apply_status_override(rows, map_home_to_at_home: bool):
    """
    Preserve Status exactly as in the input.
    Only map 'Home' -> 'At Home' when requested.
    """
    if not map_home_to_at_home or not rows:
        return
    for r in rows:
        s = (r.get("Status") or "").strip()
        if s.lower() == "home":
            r["Status"] = "At Home"



def demote_streets_with_out_of_auckland_coords(clean_rows, fail_rows):
        """
        If ANY row on a street has coordinates outside Auckland,
        move ALL rows on that street to Fail (Final Status = 'Fail (Outside Auckland)').

        Returns: new_clean_rows, new_fail_rows, moved_count, affected_streets (set)
        """
        from collections import defaultdict

        # 1) Find streets that have at least one OOB coord
        streets_with_oob = set()
        by_street = defaultdict(list)

        for r in clean_rows:
            st = (r.get("Street") or "").strip().title()
            if not st:
                continue
            by_street[st].append(r)
            la = safe_float(r.get("Latitude"), None)
            lo = safe_float(r.get("Longitude"), None)
            if la is not None and lo is not None:
                if not is_in_auckland(la, lo):
                    streets_with_oob.add(st)

        if not streets_with_oob:
            return clean_rows, fail_rows, 0, set()

        # 2) Demote all rows that belong to any affected street
        new_clean, moved = [], 0
        for r in clean_rows:
            st = (r.get("Street") or "").strip().title()
            if st in streets_with_oob:
                old = (r.get("Final Status") or "").strip()
                r["Final Status"] = "Fail (Outside Auckland)"
                fail_rows.append(r)
                moved += 1
                try:
                    log_correction(
                        "Coverage Demote (Street-Wide)",
                        f"Street '{st}' → moved to fail (prev Final Status: {old or '<blank>'})",
                        street=st
                    )
                except Exception:
                    pass
            else:
                new_clean.append(r)

        return new_clean, fail_rows, moved, streets_with_oob



def clean_and_capitalize_fields(row, valid_suburbs_data=None):
    original_suburb = (row.get("Suburb") or "").strip()
    suburb_name = original_suburb
    suburb_name = fix_known_text_glitches(suburb_name)

    # --- Step 1: Remove RD + number patterns ---
    cleaned = re.sub(r'\bR\.?D\.?\s*\d+\b', '', suburb_name, flags=re.IGNORECASE)

    # --- Step 2: Remove any standalone numbers (postcodes or others) ---
    cleaned = re.sub(r'\b\d+\b', '', cleaned)

    # --- Step 3: Normalize spacing ---
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    # --- Step 4: If cleaned suburb is empty → skip suburb for geocode ---
    if not cleaned:
        if original_suburb:
            log_correction("Removed invalid suburb", f"{original_suburb} → (blank)")
        row["Suburb"] = ""
        row["_skip_suburb_lookup"] = True  # ✅ custom flag for process_single_row()
        return row

    # Hardcoded suburb corrections
    corrections = {
        "bucklands beach": "Bucklands Beach", "east t膩maki heights": "East Tāmaki Heights",
        "east tāmaki heights": "East Tāmaki Heights",
        "east tamaki heights": "East Tāmaki Heights",
        "bucklandsbeach": "Bucklands Beach",
        "bucklands  beach": "Bucklands Beach",
        "half moon bay": "Half Moon Bay",
        "flatbush": "Flat Bush",
        "manukau central": "Manukau Central",
        "mount wellington": "Mount Wellington",
        "onehunga": "Onehunga",
        "sunnyhills": "Sunnyhills"
    }

    lower_suburb = cleaned.lower()
    if lower_suburb in corrections:
        cleaned = corrections[lower_suburb]
    elif valid_suburbs_data:
        match = next((s for s in valid_suburbs_data if s.lower() == lower_suburb), None)
        if match:
            cleaned = match
        else:
            match = safe_fuzzy_match(cleaned, valid_suburbs_data, threshold=90)
            if match:
                cleaned = match

    # Final title-case
    cleaned = cleaned.title()

    # Log change if suburb was altered
    if cleaned != original_suburb:
        log_correction("Suburb corrected", f"{original_suburb} → {cleaned}")

    row["Suburb"] = cleaned
    return row

def _geocode_with_plus_minus_5(anchor_number, street, suburb, anchor_lat=None, anchor_lon=None, radius_m=300):
    """
    Try the given number first, then ±5 numbers (only positive house numbers).
    If anchor coords are provided, require proximity to anchor.
    Returns (addr, lat, lon, postal) or (None, None, None, None) if no acceptable hit.
    """
    def _try_one(n):
        cand = fmt_addr_parts(str(n), street, suburb or "Auckland")
        res = get_lat_long(cand)
        if _is_valid_geocode_tuple(res):
            if anchor_lat is not None and anchor_lon is not None:
                try:
                    d = haversine_distance(float(res[1]), float(res[2]), anchor_lat, anchor_lon)
                    if d <= radius_m:
                        return res
                    return (None, None, None, None)
                except Exception:
                    return (None, None, None, None)
            return res
        return (None, None, None, None)

    # exact first
    n0 = re.sub(r"[^\d]", "", str(anchor_number or ""))
    if n0.isdigit():
        hit = _try_one(int(n0))
        if hit[0]:
            return hit

        # ±5 sweep
        base = int(n0)
        for delta in range(1, 6):
            for cand_n in (base - delta, base + delta):
                if cand_n > 0:
                    hit = _try_one(cand_n)
                    if hit[0]:
                        return hit
    return (None, None, None, None)

from tqdm import tqdm
from collections import defaultdict
import math

# ---- Stage 3.5: Resolve conflicting suburbs by proximity (fast + full features) ----
def resolve_conflicting_suburbs_by_proximity(
    all_rows,
    known_geocodes_by_street,
    radius_m=300,
    k_nearest=3,
    max_samples_per_street=20,
    max_workers=8,
):
    """
    Resolve conflicting suburb labels for the same street using spatial proximity.

    Combines:
      • Early exits (single-label or strong plurality)
      • KD-tree nearest neighbor lookup (SciPy if available; fallback to fast distance)
      • Postal code updates when suburb changes
      • Minimal enrichment (one probe per street, global budget cap)
      • Coord filling via ±5 number probes
      • Caching for repeated (street, suburb) resolutions
      • Parallel execution with progress bar
    """
    from collections import defaultdict, Counter
    import math, re, heapq, random
    from tqdm import tqdm as _tqdm

    # --- Distance helpers ---
    RAD = math.pi / 180.0
    def _fast_dist_m(lat1, lon1, lat2, lon2):
        phi1 = lat1 * RAD; phi2 = lat2 * RAD
        x = (lon2 - lon1) * RAD * math.cos((phi1 + phi2) * 0.5)
        y = (lat2 - lat1) * RAD
        return 6371000.0 * math.sqrt(x*x + y*y)

    # --- Build per-street view ---
    def _get_street_items(rows):
        by_street = defaultdict(list)
        for i, r in enumerate(rows):
            st = (r.get("Street") or "").strip().title()
            if not st: continue
            sb = (r.get("Suburb") or "").strip().title()
            by_street[st].append((i, r, sb))
        return by_street

    # --- Coord extraction ---
    def _street_pts(items):
        pts = []
        for idx, r, sb in items:
            la = safe_float(r.get("Latitude"), None)
            lo = safe_float(r.get("Longitude"), None)
            if la is None or lo is None: continue
            if not is_in_auckland(la, lo): continue
            row_id = r.get("__RowID", idx + 2)
            addr = f"{(r.get('Number') or '').strip()} {(r.get('Street') or '').strip().title()}, {(sb or 'Auckland')}"
            pts.append((la, lo, (sb or "Auckland"), row_id, addr))
        return pts

    def _centroid(pts):
        n = float(len(pts))
        return (sum(p[0] for p in pts)/n, sum(p[1] for p in pts)/n)

    # --- Voting (top-k distances) ---
    def _k_nearest_vote(pts, center, k):
        scored = [(_fast_dist_m(p[0], p[1], center[0], center[1]), p[2]) for p in pts]
        topk = heapq.nsmallest(max(1, k), scored, key=lambda x: x[0])
        top_counts = Counter(lbl for _, lbl in topk)
        all_counts = Counter(lbl for _, lbl in scored)

        buckets = defaultdict(list)
        for d, lbl in scored:
            buckets[lbl].append(d)

        per_label = {
            lbl: {
                "n_all": all_counts[lbl],
                "n_topk": top_counts.get(lbl, 0),
                "min_d": min(arr),
                "avg_d": sum(arr)/len(arr),
            }
            for lbl, arr in buckets.items()
        }
        return top_counts, per_label

    def _pick_canonical(topk_counts, per_label, fallback_label):
        if topk_counts:
            ordered = topk_counts.most_common()
            if len(ordered) == 1 or (len(ordered) > 1 and ordered[0][1] > ordered[1][1]):
                return ordered[0][0]
        if per_label:
            return min(per_label.keys(), key=lambda lbl: per_label[lbl]["avg_d"])
        return fallback_label

    # --- Apply suburb + postal updates ---
    def _apply_suburb_postal(items, canonical_suburb):
        canonical_suburb = (canonical_suburb or "").strip().title()
        canonical_postal = nz_postal_lookup.get(canonical_suburb, "")
        for idx, row, old_sb in items:
            eff_street = (row.get("Street") or "").strip().title()
            if old_sb != canonical_suburb:
                _log_quiet("ConflictResolve: Suburb", f"{old_sb} → {canonical_suburb} (Street '{eff_street}')",
                           street=eff_street, important=False)
                row["Suburb"] = canonical_suburb
            cur_pc = (row.get("PostalCode") or "").strip()
            if canonical_postal and cur_pc != canonical_postal:
                _log_quiet("ConflictResolve: PostalCode", f"{cur_pc} → {canonical_postal} (Street '{eff_street}')",
                           street=eff_street, important=False)
                row["PostalCode"] = canonical_postal
        return canonical_suburb

    # --- One-probe enrichment (when zero coords) ---
    def _try_min_enrich(street, items, budget_left):
        if budget_left <= 0 or len(items) < 2:
            return [], budget_left
        nums = [re.sub(r"\D", "", (r.get("Number") or "")) for _, r, _ in items]
        sample_num = next((n for n in nums if n), "")
        probe_suburb = next((s for *_x, s in items if s), "")
        try:
            enriched = _probe_all_services_for_address(sample_num, street, probe_suburb or "Auckland")
        except Exception:
            enriched = []
        out = []
        for la, lo, lbl, pretty, _addr in enriched[:1]:
            out.append((la, lo, lbl, 0, pretty))
        return out, max(0, budget_left - (1 if out else 0))

    # --- KD-tree index (global) ---
    use_kdtree, tree, pts_global, labels_global = False, None, [], []
    for (st, sb), coords in known_geocodes_by_street.items():
        sample = coords if len(coords) <= max_samples_per_street else random.sample(coords, max_samples_per_street)
        for lat, lon in sample:
            pts_global.append((lat, lon))
            labels_global.append((st, sb))
    if pts_global:
        try:
            from scipy.spatial import cKDTree
            tree = cKDTree(pts_global)
            use_kdtree = True
        except ImportError:
            pass

    # --- Cache for suburb decisions ---
    cache = {}
    PROBE_BUDGET = int(getattr(globals(), "SUBURB_RESOLVE_PROBE_BUDGET", 200))

    # --- Per-street resolution ---
    def resolve_street(street, items):
        nonlocal PROBE_BUDGET

        pts = _street_pts(items)
        labels = [p[2] for p in pts]

        # EARLY EXIT A: single suburb
        if labels and len(set(labels)) == 1:
            _apply_suburb_postal(items, labels[0])
            return

        # EARLY EXIT B: strong plurality
        if labels:
            cnts = Counter(labels)
            total = sum(cnts.values())
            top, c = cnts.most_common(1)[0]
            if c >= max(3, int(0.7 * total)):
                _apply_suburb_postal(items, top)
                return

        # Try enrichment if no coords
        if not pts:
            add, PROBE_BUDGET = _try_min_enrich(street, items, PROBE_BUDGET)
            pts.extend(add)

        if not pts:
            return  # still nothing

        # Decide canonical suburb
        center = _centroid(pts)
        topk_counts, per_label = _k_nearest_vote(pts, center, k_nearest)
        fallback = labels[0] if labels else pts[0][2]
        chosen = _pick_canonical(topk_counts, per_label, fallback)
        canonical_suburb_now = _apply_suburb_postal(items, chosen)

        # Fill coords if missing
        c_lat, c_lon = center
        for idx, row, _old in items:
            la = safe_float(row.get("Latitude"), None)
            lo = safe_float(row.get("Longitude"), None)
            if la is not None and lo is not None:
                continue
            best = _geocode_with_plus_minus_5(
                row.get("Number", ""),
                street,
                canonical_suburb_now,
                anchor_lat=c_lat,
                anchor_lon=c_lon,
                radius_m=radius_m,
            )
            if _is_valid_geocode_tuple(best):
                row["Latitude"] = best[1]
                row["Longitude"] = best[2]
                if is_blank_or_zero(row.get("PostalCode")):
                    cp = nz_postal_lookup.get(canonical_suburb_now, "")
                    if cp:
                        row["PostalCode"] = cp

    # --- Run with parallel executor ---
    by_street = _get_street_items(all_rows)
    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(resolve_street, st, items): st for st, items in by_street.items()}
        for _ in _tqdm(as_completed(futures), total=len(futures),
                       desc="🔄 Resolving Suburb Conflicts....",
                       unit="street", dynamic_ncols=True):
            pass

    return all_rows





def geocode_linz(address, memory_conn=None):
    """
    LINZ local geocode with safer number matching + index-friendly predicates.
    Tries (in order):
      1) Exact number match (fast, index-friendly)
      2) Guarded LIKE fallback for common unit/house patterns
      3) Base street prefix with suffix swaps (Street/Drive/Road/etc.)
      4) NEW: If a suburb was supplied but nothing matched, retry base+number with ANY suburb
      5) Optional in-memory 'Other' DB with the same guards
    Returns: (formatted_address, lat, lon, postal)
    """
    def _base_and_suffix(st):
        st = (st or "").strip().title()
        parts = st.split()
        if not parts:
            return st, ""
        return " ".join(parts[:-1]).strip(), parts[-1].title()

    m = ADDRESS_PARSE_RX.match(address)
    if not m:
        return None, None, None, None

    num, street, suburb = [x.strip() for x in m.groups()]

    try:
        num = normalize_number(num)
        num, street = merge_number_with_street(num, street)
        street = correct_suffix_typos(street).strip().title()
        suburb = suburb.strip().title()
    except Exception:
        street = street.strip().title()
        suburb = suburb.strip().title()

    base, _suffix = _base_and_suffix(street)

    row = None
    try:
        with _db_lock:
            conn = sqlite3.connect(LINZ_DB, check_same_thread=False)
            c = conn.cursor()

            # 1) Exact match
            c.execute("""
                SELECT Street, Suburb, Latitude, Longitude, Postalcode
                  FROM addresses
                 WHERE Street = ? COLLATE NOCASE
                   AND Suburb = ? COLLATE NOCASE
                   AND Number = ?
                 LIMIT 1
            """, (street, suburb, num))
            row = c.fetchone()

            # 2) Guarded LIKE patterns for unit/house formats
            if not row:
                digits = re.sub(r'\D', '', num or "")
                like_patterns = []
                if digits:
                    like_patterns = [f'Unit%/{digits}', f'{digits}/%', f'%/{digits}/%']

                if like_patterns:
                    placeholders = " OR ".join(["Number LIKE ?"] * len(like_patterns))
                    c.execute(f"""
                        SELECT Street, Suburb, Latitude, Longitude, Postalcode
                          FROM addresses
                         WHERE Street = ? COLLATE NOCASE
                           AND Suburb = ? COLLATE NOCASE
                           AND ({placeholders})
                         LIMIT 1
                    """, (street, suburb, *like_patterns))
                    row = c.fetchone()

            # 3) Base-prefix search (suffix-agnostic)
            has_suburb = bool(suburb and suburb.lower() != "auckland")
            if not row and base:
                if has_suburb:
                    c.execute("""
                        SELECT Street, Suburb, Latitude, Longitude, Postalcode
                          FROM addresses
                         WHERE Street LIKE ? ESCAPE '\\' COLLATE NOCASE
                           AND Suburb = ? COLLATE NOCASE
                           AND Number = ?
                         LIMIT 1
                    """, (f"{base} %", suburb, num))
                else:
                    c.execute("""
                        SELECT Street, Suburb, Latitude, Longitude, Postalcode
                          FROM addresses
                         WHERE Street LIKE ? ESCAPE '\\' COLLATE NOCASE
                           AND Number = ?
                         LIMIT 1
                    """, (f"{base} %", num))
                row = c.fetchone()

            # 4) ✅ NEW: suburb-loosen fallback for same base+number
            #    If a suburb was provided but nothing matched, retry with ANY suburb.
            if (not row) and base and has_suburb:
                c.execute("""
                    SELECT Street, Suburb, Latitude, Longitude, Postalcode
                      FROM addresses
                     WHERE Street LIKE ? ESCAPE '\\' COLLATE NOCASE
                       AND Number = ?
                     LIMIT 1
                """, (f"{base} %", num))
                row = c.fetchone()

            conn.close()
    except Exception as e:
        print(f"❌ SQLite access error: {e}")

    if row:
        s, sub, lat, lon, postal = row
        try:
            lat = float(lat); lon = float(lon)
        except Exception:
            return None, None, None, None
        return f"{str(s).strip().title()}, {str(sub).strip().title()}, Auckland", lat, lon, (postal or "")

    # 5) In-memory 'Other' DB (unchanged logic; suburb-loosen already exists there)
    if memory_conn:
        try:
            with _db_lock:
                mc = memory_conn.cursor()

                digits = re.sub(r'\D', '', num or "")
                like_patterns = []
                if digits:
                    like_patterns = [f'Unit%/{digits}', f'{digits}/%', f'%/{digits}/%']

                has_suburb = bool(suburb and suburb.lower() != "auckland")

                # Prefer base-prefix first (suffix-agnostic)
                if base:
                    if has_suburb:
                        mc.execute("""
                            SELECT street, suburb, latitude, longitude, postalcode
                              FROM other_addresses
                             WHERE street LIKE ? ESCAPE '\\' COLLATE NOCASE
                               AND suburb = ? COLLATE NOCASE
                               AND number = ?
                             LIMIT 1
                        """, (f"{base} %", suburb, num))
                    else:
                        mc.execute("""
                            SELECT street, suburb, latitude, longitude, postalcode
                              FROM other_addresses
                             WHERE street LIKE ? ESCAPE '\\' COLLATE NOCASE
                               AND number = ?
                             LIMIT 1
                        """, (f"{base} %", num))
                    row = mc.fetchone()
                else:
                    row = None

                # Guarded LIKE on number
                if (not row) and like_patterns:
                    placeholders = " OR ".join(["number LIKE ?"] * len(like_patterns))
                    if has_suburb:
                        mc.execute(f"""
                            SELECT street, suburb, latitude, longitude, postalcode
                              FROM other_addresses
                             WHERE street LIKE ? ESCAPE '\\' COLLATE NOCASE
                               AND suburb LIKE ? ESCAPE '\\' COLLATE NOCASE
                               AND ({placeholders})
                             LIMIT 1
                        """, (f"%{street}%", f"%{suburb}%", *like_patterns))
                    else:
                        mc.execute(f"""
                            SELECT street, suburb, latitude, longitude, postalcode
                              FROM other_addresses
                             WHERE street LIKE ? ESCAPE '\\' COLLATE NOCASE
                               AND ({placeholders})
                             LIMIT 1
                        """, (f"%{street}%", *like_patterns))
                    row = mc.fetchone()

                # No-digit or exact-number fallback
                if (not row) and not like_patterns:
                    if base:
                        if has_suburb:
                            mc.execute("""
                                SELECT street, suburb, latitude, longitude, postalcode
                                  FROM other_addresses
                                 WHERE street LIKE ? ESCAPE '\\' COLLATE NOCASE
                                   AND suburb = ? COLLATE NOCASE
                                   AND number = ?
                                 LIMIT 1
                            """, (f"{base} %", suburb, num))
                        else:
                            mc.execute("""
                                SELECT street, suburb, latitude, longitude, postalcode
                                  FROM other_addresses
                                 WHERE street LIKE ? ESCAPE '\\' COLLATE NOCASE
                                   AND number = ?
                                 LIMIT 1
                            """, (f"{base} %", num))
                        row = mc.fetchone()

                    if not row:
                        if has_suburb:
                            mc.execute("""
                                SELECT street, suburb, latitude, longitude, postalcode
                                  FROM other_addresses
                                 WHERE street LIKE ? ESCAPE '\\' COLLATE NOCASE
                                   AND suburb LIKE ? ESCAPE '\\' COLLATE NOCASE
                                   AND number = ?
                                 LIMIT 1
                            """, (f"%{street}%", f"%{suburb}%", num))
                        else:
                            mc.execute("""
                                SELECT street, suburb, latitude, longitude, postalcode
                                  FROM other_addresses
                                 WHERE street LIKE ? ESCAPE '\\' COLLATE NOCASE
                                   AND number = ?
                                 LIMIT 1
                            """, (f"%{street}%", num))
                        row = mc.fetchone()

            if row:
                s, sub, lat, lon, postal = row
                lat = float(lat); lon = float(lon)
                return f"{str(s).strip().title()}, {str(sub).strip().title()}, Auckland", lat, lon, (postal or "")
        except Exception as e:
            print(f"⚠️ Memory DB lookup failed: {e}")

    return None, None, None, None




import os
import re
from typing import List, Tuple, Optional

_MARKERS = [
    ("Part 1.py", r"#\s*📌\s*Part\s*1/3\s*Start", r"#\s*📌\s*Part\s*1/3\s*End"),
    ("Part 2.py", r"#\s*📌\s*Part\s*2/3\s*Start", r"#\s*📌\s*Part\s*2/3\s*End"),
    ("Part 3.py", r"#\s*📌\s*Part\s*3/3\s*Start", r"#\s*📌\s*Part\s*3/3\s*End"),
]

def _find_block(lines: List[str], start_rx: re.Pattern, end_rx: re.Pattern) -> Optional[Tuple[int, int]]:
    start_idx = None
    for i, line in enumerate(lines):
        if start_idx is None and start_rx.search(line):
            start_idx = i
            continue
        if start_idx is not None and end_rx.search(line):
            return start_idx, i
    return None

# ADD near export_script_parts()
def _log_export_parts(event, details=""):
    # Route to the global logger with empty Street to keep schema stable
    log_correction(event, details, street="")


def export_script_parts(script_path=None, out_dir="Exported Files",
                        min_lines_per_part=30, min_nonblank_per_part=5):
    """
    Export the script into 4 files using 1/4..4/4 markers only.
    - Does NOT modify the source file.
    - Deletes prior Part*.py in out_dir, then writes Part 1.py..Part 4.py.
    - Skips a part if its marker block is missing/too small.
    """
    import os, re, glob

    PART_PATTERNS = [
        ("Part 1.py",
         re.compile(r"^\s*#\s*📌\s*Part\s*1/4\s*Start\s*$"),
         re.compile(r"^\s*#\s*📌\s*Part\s*1/4\s*End\s*$")),
        ("Part 2.py",
         re.compile(r"^\s*#\s*📌\s*Part\s*2/4\s*Start\s*$"),
         re.compile(r"^\s*#\s*📌\s*Part\s*2/4\s*End\s*$")),
        ("Part 3.py",
         re.compile(r"^\s*#\s*📌\s*Part\s*3/4\s*Start\s*$"),
         re.compile(r"^\s*#\s*📌\s*Part\s*3/4\s*End\s*$")),
        ("Part 4.py",
         re.compile(r"^\s*#\s*📌\s*Part\s*4/4\s*Start\s*$"),
         re.compile(r"^\s*#\s*📌\s*Part\s*4/4\s*End\s*$")),
    ]

    if script_path is None:
        try:
            script_path = __file__
        except NameError:
            script_path = "1.py"

    if not os.path.exists(script_path):
        print(f"❌ Script not found: {script_path}")
        return

    os.makedirs(out_dir, exist_ok=True)

    # Remove old Part*.py in the export folder only
    for p in [os.path.join(out_dir, x) for x in ("Part 1.py","Part 2.py","Part 3.py","Part 4.py")]:
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception as e:
            print(f"⚠️ Could not delete {p}: {e}")

    with open(script_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines(keepends=True)

    def _find_blocks(rx_start, rx_end):
        starts = [i for i, ln in enumerate(lines) if rx_start.match(ln)]
        ends   = [i for i, ln in enumerate(lines) if rx_end.match(ln)]
        pairs = []
        for s in starts:
            following = [e for e in ends if e > s]
            if following:
                pairs.append((s, min(following)))
        return pairs

    made = 0
    for out_name, rx_start, rx_end in PART_PATTERNS:
        blocks = _find_blocks(rx_start, rx_end)
        if not blocks:
            print(f"⚠️ {out_name}: markers not found — skipping.")
            continue
        # choose the largest block if duplicates exist
        s, e = max(blocks, key=lambda p: p[1] - p[0])
        block = lines[s:e+1]
        non_blank = [ln for ln in block if ln.strip()]
        if len(non_blank) < min_nonblank_per_part or len(block) < min_lines_per_part:
            print(f"⚠️ {out_name}: too small ({len(non_blank)} non-blank, {len(block)} total) — skipping.")
            continue

        dst_path = os.path.join(out_dir, out_name)
        with open(dst_path, "w", encoding="utf-8") as out:
            out.writelines(block)
        print(f"✅ Created {dst_path} — {len(block)} lines.")
        made += 1

    if made == 0:
        print("ℹ️ No parts were exported. Ensure 1/4..4/4 markers exist.")





# Part 2/4 End
