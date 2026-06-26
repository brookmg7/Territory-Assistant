# Part 4/4 Start
def resolve_bad_address(number, street_val, suburb_val, all_rows, all_streets, street_index=None, geocode_result=None):
    """
    Fixes broken addresses. Always returns a street if possible.
    Deduplicates geocoding by accepting pre-fetched `geocode_result`.

    Hardened rules:
      • Fuzzy: threshold=88 and first 5 chars must match.
      • NEVER remap when the input street is protected:
          - Full-name in PROTECTED_FULL_STREETS → keep exact.
          - Base in PROTECTED_BASES → don't switch to a different base.
    """
    from collections import Counter

    number     = (number or "").strip()
    street_val = (street_val or "").strip().title()
    suburb_val = (suburb_val or "").strip().title()
    if "auckland" in suburb_val.lower():
        suburb_val = ""

    # Protection flags for the *input* street
    obase_disp, _ = _norm_base_key(street_val)
    prot_full = street_val in PROTECTED_FULL_STREETS
    prot_base = obase_disp in PROTECTED_BASES

    # Use pre-fetched geocode result (from process_csv), but do NOT cross protected boundaries
    if geocode_result:
        addr, lat, lon, postal = geocode_result
        if addr:
            parts    = [p.strip() for p in addr.split(",")]
            g_street = parts[0].title() if parts else ""
            g_suburb = parts[1].title() if len(parts) > 1 else suburb_val

            # Do not adopt a different street if protected
            if prot_full and g_street and g_street != street_val:
                return street_val, g_suburb
            if prot_base and g_street:
                gbase_disp, _ = _norm_base_key(g_street)
                if gbase_disp != obase_disp:
                    return street_val, g_suburb

            return (g_street or street_val), g_suburb

    # Guess suburb if invalid
    all_suburbs = [ (r.get('Suburb') or '').strip().title() for r in all_rows if r.get('Suburb') ]
    guessed_suburb = None
    if not suburb_val or suburb_val.lower() not in [s.lower() for s in all_suburbs]:
        guessed_suburb = Counter(all_suburbs).most_common(1)[0][0] if all_suburbs else ""

    # Fast fuzzy street matching (STRICT) — skip entirely if street is protected
    if street_index and not (prot_full or prot_base):
        fast_match = fast_find_similar_street(street_val, street_index, threshold=88)
        if fast_match and street_val[:5].lower() == fast_match[:5].lower():
            street_val = fast_match

    # Final fallback geocode (only if no pre-fetched result) — respect protections when adopting label
    if not geocode_result or not geocode_result[0]:
        query_suburb = guessed_suburb or suburb_val or "Auckland"
        addr, lat, lon, postal = get_lat_long(f"{number} {street_val}, {query_suburb}")
        if addr:
            parts    = [p.strip() for p in addr.split(",")]
            g_street = parts[0].title() if parts else ""
            g_suburb = parts[1].title() if len(parts) > 1 else query_suburb

            if prot_full and g_street and g_street != street_val:
                return street_val, g_suburb
            if prot_base and g_street:
                gbase_disp, _ = _norm_base_key(g_street)
                if gbase_disp != obase_disp:
                    return street_val, g_suburb

            return (g_street or street_val), g_suburb

    # Always return a street even if suburb can't be resolved
    if street_val:
        return street_val, guessed_suburb or suburb_val or ""

    return "Fail", "Fail"

# ---- Auckland coord guards (drop-in) ----
def _in_akl_bbox(lat: float, lon: float) -> bool:
    """
    Simple rectangular gate for Auckland region.
    Good for cleaning; keep tight to avoid false positives.
    """
    return (-37.30 <= lat <= -36.20) and (174.30 <= lon <= 175.60)

def _maybe_swap_latlon(lat, lon):
    try:
        la = float(lat); lo = float(lon)
    except Exception:
        return lat, lon

    # existing quick rules
    if abs(la) > 90 and abs(lo) <= 90:
        return lo, la
    if 170.0 <= abs(la) <= 180.0 and (-47.0 <= lo <= -34.0):
        return lo, la

    # ✅ new: if swapping places the point inside Auckland, do it
    if is_in_auckland(lo, la) and not is_in_auckland(la, lo):
        return lo, la

    return la, lo


from concurrent.futures import ThreadPoolExecutor, as_completed

def prune_auckland_coords_inplace(row, row_id_fallback=None):
    """
    Remove invalid or out-of-Auckland coordinates from a row.
    Unlike before, this version no longer marks __NeedsRegeo.
    """
    lat = row.get("Latitude")
    lon = row.get("Longitude")

    if not lat or not lon:
        return  # Already blank, nothing to prune

    try:
        lat = float(lat)
        lon = float(lon)
    except Exception:
        # Bad numeric format → clear only
        row["Latitude"] = ""
        row["Longitude"] = ""
        log_correction(
            "Coord Prune",
            f"Non-numeric coords cleared (row {row_id_fallback})",
            street=row.get("Street"),
        )
        return

    if not is_in_auckland(lat, lon):
        row["Latitude"] = ""
        row["Longitude"] = ""
        log_correction(
            "Coord Prune",
            f"Outside Auckland — cleared (row {row_id_fallback})",
            street=row.get("Street"),
        )



def _retry_geocode(row, all_rows=None):
    """Worker function to retry geocoding a single row (tuple/dict-safe result handling)."""
    if all_rows is None:
        all_rows = []

    number = row.get("Number") or row.get("HouseNumber") or ""
    street = row.get("Street") or ""
    suburb = row.get("Suburb") or ""
    addr = f"{number} {street}, {suburb}, Auckland".strip(", ")

    try:
        result = targeted_geocode_retry(row, all_rows, known_geocodes_by_street=None)

        # Support tuple (addr, lat, lon, postal) or dict {'lat':..., 'lon':...}
        lat = lon = None
        if isinstance(result, tuple) and len(result) == 4:
            _addr_lbl, lat, lon, _pc = result
        elif isinstance(result, dict):
            lat, lon = result.get("lat"), result.get("lon")

        if lat is not None and lon is not None:
            if is_in_auckland(float(lat), float(lon)):
                row["Latitude"] = str(lat)
                row["Longitude"] = str(lon)
                row["__NeedsRegeo"] = False
                return ("recovered", f"{addr} → {lat},{lon}")
            else:
                return ("skip", f"{addr} → outside Auckland {lat},{lon}")
        else:
            return ("fail", f"{addr} → no result")
    except Exception as e:
        return ("error", f"{addr} → {e}")



def try_geocoders_with_variants(number, street, suburb):
    """
    Backward compatibility shim for _retry_geocode.
    Just calls targeted_geocode_retry() with a fake row.
    """
    row = {"Number": number, "Street": street, "Suburb": suburb}
    return targeted_geocode_retry(row, all_rows=[], known_geocodes_by_street=None)





def _street_stats(rows):
    """
    Return stats for a list of rows:
      - Number of streets with all coords blank
      - Number of streets with any coords outside Auckland
      - Total number of unique streets
    """
    from collections import defaultdict

    # Group rows by street
    street_buckets = defaultdict(list)
    for r in rows:
        st = (r.get("Street") or "").strip().title()
        if not st:
            continue
        street_buckets[st].append(r)

    blank_count = 0
    oob_count = 0

    for st, bucket in street_buckets.items():
        coords = []
        for r in bucket:
            la = safe_float(r.get("Latitude"), None)
            lo = safe_float(r.get("Longitude"), None)
            if la is not None and lo is not None:
                coords.append((la, lo))

        if not coords:
            blank_count += 1
        else:
            if any(not is_in_auckland(la, lo) for la, lo in coords):
                oob_count += 1

    return blank_count, oob_count, len(street_buckets)



# --- Suburb validation & auto-fill ---


def resolve_suburb(street_val, suburb_val, all_rows, all_streets, number_val: str = ""):
    """
    Resolve a correct suburb for a given street/suburb combo.

    Improvements:
      • Uses a house number when geocoding (falls back to most-common number for that street in CSV).
      • Adopts the suburb returned by geocoders when available (canonized), not just in CSV-retry paths.
      • Keeps 'Howick' whitelisted.
      • Treats 'Auckland' as blank/unknown and normalizes macrons/variants via macron_suburb_map.
    """
    from collections import Counter
    import re

    def _norm(s): return (s or "").strip()
    def _low(s):  return _norm(s).lower()

    # Quick allow-list
    cand = _low(suburb_val)
    if "howick" in cand:
        return "Howick"

    valid_set_low = {s.lower() for s in valid_suburbs_data}
    is_valid = (cand and cand != "auckland" and cand in valid_set_low)
    if is_valid:
        # Normalize macrons/title-case
        sv = _norm(suburb_val).title()
        if "howick" in sv.lower():
            return "Howick"
        return macron_suburb_map.get(sv, sv)

    # ------ CSV heuristics first ------
    street_l = _low(street_val)

    # (1) Exact same street → most-common suburb
    exact_matches = [ _norm(r.get('Suburb','')) for r in all_rows
                      if _low(r.get('Street','')) == street_l and _norm(r.get('Suburb','')) ]
    if exact_matches:
        top = Counter(exact_matches).most_common(1)[0][0]
        if "howick" in _low(top): return "Howick"
        return macron_suburb_map.get(_norm(top).title(), _norm(top).title())

    # (1.5) Partial street match → most-common suburb
    partial_matches = [ _norm(r.get('Suburb','')) for r in all_rows
                        if street_l in _low(r.get('Street','')) and _norm(r.get('Suburb','')) ]
    if partial_matches:
        top = Counter(partial_matches).most_common(1)[0][0]
        if "howick" in _low(top): return "Howick"
        return macron_suburb_map.get(_norm(top).title(), _norm(top).title())

    # ------ Geocode with a HOUSE NUMBER ------
    # Prefer provided number; else borrow most-common number used with this street in CSV.
    digits = re.sub(r"\D", "", _norm(number_val))
    if not digits:
        nums = [ re.sub(r"\D","", _norm(r.get('Number',''))) for r in all_rows
                 if _low(r.get('Street','')) == street_l and _norm(r.get('Number','')) ]
        nums = [n for n in nums if n]
        if nums:
            digits = Counter(nums).most_common(1)[0][0]

    # Build a numbered candidate; fall back to Auckland when suburb is blank/invalid.
    suburb_for_query = _norm(suburb_val) if _norm(suburb_val) else "Auckland"
    addr_query = fmt_addr_parts(digits, _norm(street_val).title(), suburb_for_query)

    try:
        addr, lat, lon, _pc = get_lat_long(addr_query)
    except Exception:
        addr = None

    if addr:
        # Prefer the suburb from the geocoder label
        parts = [p.strip() for p in addr.split(",")]
        g_suburb = parts[1] if len(parts) > 1 else suburb_val
        if g_suburb:
            if "howick" in g_suburb.lower():
                return "Howick"
            # Canonize geocoded suburb (handles macrons/variants)
            g_final = macron_suburb_map.get(_norm(g_suburb).title(), _norm(g_suburb).title())
            return g_final

    # ------ Fuzzy street-based guess (as last hints before global mode) ------
    if all_streets:
        match = safe_fuzzy_match(_norm(street_val), list(all_streets), threshold=20)
        if match:
            guess_suburbs = [ _norm(r.get('Suburb','')) for r in all_rows
                              if _low(r.get('Street','')) == _low(match) and _norm(r.get('Suburb','')) ]
            if guess_suburbs:
                best = Counter(guess_suburbs).most_common(1)[0][0]
                if "howick" in _low(best): return "Howick"
                return macron_suburb_map.get(_norm(best).title(), _norm(best).title())

    # ------ Global most-common suburb in the CSV ------
    all_suburbs = [ _norm(r.get('Suburb','')) for r in all_rows if _norm(r.get('Suburb','')) ]
    if all_suburbs:
        top = Counter(all_suburbs).most_common(1)[0][0]
        if "howick" in _low(top): return "Howick"
        return macron_suburb_map.get(_norm(top).title(), _norm(top).title())

    # Nothing better
    return ""



def is_blank_or_zero(val):
    s = str(val).strip()
    if not s or s in {"0", "O", "None"}:
        return True
    try:
        return float(s) == 0.0
    except ValueError:
        return False


def build_dominant_suburb_map_from_verified(rows, threshold=0.7):
    from collections import defaultdict, Counter
    street_suburb_counter = defaultdict(Counter)
    for row in rows:
        street = row.get("Street","").strip()
        suburb = row.get("Suburb","").strip()
        status = row.get("Final Status","").strip()
        if street and suburb and status == "Pass":
            street_suburb_counter[street][suburb] += 1
    dominant_map = {}
    for street, counter in street_suburb_counter.items():
        total = sum(counter.values())
        if total:
            top_suburb, top_count = counter.most_common(1)[0]
            if (top_count / total) >= threshold:
                dominant_map[street] = top_suburb
    return dominant_map



def build_global_dominant_suburb_map(rows, threshold=0.6):
    from collections import defaultdict, Counter

    street_suburb_counts = defaultdict(Counter)
    for row in rows:
        street = row.get("Street", "").strip()
        suburb = row.get("Suburb", "").strip()
        if street and suburb:
            street_suburb_counts[street][suburb] += 1

    dominant_map = {}
    for street, counter in street_suburb_counts.items():
        total = sum(counter.values())
        top_suburb, count = counter.most_common(1)[0]
        if total > 0 and (count / total) >= threshold:
            dominant_map[street] = top_suburb.strip().title()
    return dominant_map

# ---------- Known text glitch fixes ----------
import re, unicodedata

_EAST_TAMAKI_RX = re.compile(r'(?i)\bEast\s+T(?:膩|ā)maki\s+Heights\b')

def fix_known_text_glitches(s: str) -> str:
    if not s:
        return s
    # Exactly: East T膩maki Heights / East Tāmaki Heights → East Tamaki Heights
    s2 = _EAST_TAMAKI_RX.sub("East Tamaki Heights", s)
    return s2

# ---------- Notes sanitization Patch ----------

import re, unicodedata

_MONTHS_RX = r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*'
_DATE_RX = re.compile(
    rf'\b(?:\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}}|\d{{4}}-\d{{1,2}}-\d{{1,2}}|{_MONTHS_RX}\s+\d{{1,2}}(?:,\s*\d{{2,4}})?)\b',
    re.IGNORECASE
)

# phrases to delete (case-insensitive, keeps other text)
_NOTE_DROP_PATTERNS = [
    # check/confirm boilerplate
    r'pl[sz]\.?\s*check', r'pl[sz]\.?\s*confirm(?:\s*again)?', r'please\s*check', r'please\s*confirm(?:\s*again)?',
    r'check\s*if\s*chinese', r'pl[sz]\s*check\s*if\s*chinese', r'please\s*check\s*if\s*chinese', r'\bif\s*chinese\b(?:\s*[?.!])?',

    # sources / provenance
    r'found\s+in\s+white[\s\-]*pages?', r'white[\s\-]*pages?',  # "white-pages", "whitepages"
    r'passed\s+on\s+from\s+english', r'\bfrom\s+english\b',

    # letter/tract boilerplate
    r'will\s+need\s+to\s+post\s+a?\s+letter\s+(?:to\s+address)?',
    r'posted\s+a?\s+letter', r'left\s+a?\s+letter',
    r'left\s*tract',

    # door/bell boilerplate
    r'no\s*intercom\s*or\s*bell', r'no\s*(?:door)?\s*bell',

    # misc boilerplate
    r'\binitial\s*call\b', r'\bdone\b', r'\bavailable\b', r'\bnew\b',
    r'\bno\s+access\s+to\s+house\.?\b',   # drop completely
    r'\bPLO\b',                           # drop completely
    r'\benglish\b',                       # per spec: delete 'English'
    r'\bbring\s+letter(?:\s+for\s+second\s+call)?\b', r'\bsecond\s+call\b',
]
_NOTE_DROP_RES = [re.compile(p, re.IGNORECASE) for p in _NOTE_DROP_PATTERNS]

# --- extra phrases to drop (case-insensitive, matches even with punctuation/spaces in between)
_EXTRA_NOTE_DROPS = [
    r'wbl',                               # "WBL"
    r'top\s*garden',                      # "Top Garden"
    r'a\s*man\s*with\s*a\s*chinese',      # "A man with a Chinese"
    r'\b\d+[a-z]?\s*also\s*chinese\b',    # "70a also Chinese", etc.
    r'\bthe\s+house\b',                   # "the house"
    r'intercom',                          # "Intercom" (any mention)
    r'\b\d+\s*houses?\b',                 # "4 houses"
    r'\b[d]\s*is\s*chinese\b',            # "D is Chinese"
    r'under\s*decoration(?:\s*no\s*people\s*live\s*there)?',  # "Under decoration no people live there"
    r'\bno\s*people\s*live\s*there\b',    # standalone variant
    r'\bbig\b\s*(?:[.,])?\s*\bwrite\s*letter\b',              # "Big . Write letter for ..."
    r'\bif\s*still\s*chinese\b',          # "If still Chinese"
]

# Extend both the pattern list and the compiled regexes so they’re removed anywhere in the text
try:
    _NOTE_DROP_PATTERNS += _EXTRA_NOTE_DROPS
    _NOTE_DROP_RES.extend(re.compile(p, re.IGNORECASE) for p in _EXTRA_NOTE_DROPS)
except NameError:
    # If this block appears before _NOTE_DROP_RES is created, just append to patterns;
    # the later compile step will include them.
    _NOTE_DROP_PATTERNS += _EXTRA_NOTE_DROPS

# --- token-level hard drops (delete the whole segment if these appear anywhere)
# keep this conservative to avoid collateral damage; you asked to delete even when found separately
_EXTRA_TOKEN_WORDS = [
    r'\bwbl\b',
    r'\bintercom\b',
    r'\bthe\s+house\b',
    r'\bwrite\s*letter\b',
]

_EXTRA_TOKEN_RES = [re.compile(p, re.IGNORECASE) for p in _EXTRA_TOKEN_WORDS]

def _segment_contains_forced_drop(seg: str) -> bool:
    """Return True if a segment still contains any forced-drop tokens/phrases (delete the segment)."""
    if not seg:
        return False
    for rx in _EXTRA_TOKEN_RES:
        if rx.search(seg):
            return True
    # Also treat the big extra list as hard drops at segment level
    for ptn in _EXTRA_NOTE_DROPS:
        if re.search(ptn, seg, re.IGNORECASE):
            return True
    return False


def _normalize_separators(s: str) -> str:
    # unify commas/semicolons/pipes/slashes as " / ", collapse spaces
    s = re.sub(r'\s*[,;|]\s*', ' / ', s)
    s = re.sub(r'\s*/\s*', ' / ', s)
    s = re.sub(r'\s{2,}', ' ', s)
    return s.strip(' ,;/')

def _dedupe_segments_keep_njm(segments):
    seen = {}
    out = []
    for seg in segments:
        key = re.sub(r'(?i)\s*\(NJM\)\s*', '', seg).strip().lower()
        has_njm = '(njm' in seg.lower() or seg.strip().upper() == 'NJM'
        if key in seen:
            idx, prev_has_njm = seen[key]
            if has_njm and not prev_has_njm:
                out[idx] = seg
                seen[key] = (idx, True)
        else:
            seen[key] = (len(out), has_njm)
            out.append(seg)
    # collapse multiple raw 'NJM' segments
    njm_seen = False
    final = []
    for seg in out:
        if seg.strip().upper() == 'NJM':
            if njm_seen:
                continue
            njm_seen = True
        final.append(seg)
    return final

def _pull_njm_from_parentheses(t: str) -> str:
    # Turn "(NJM)" or "[NJM]" into " / NJM " so we preserve it before stripping parens
    return re.sub(r'[\(\[]\s*NJM\s*[\)\]]', ' / NJM ', t, flags=re.IGNORECASE)

def _strip_all_parentheses_content(t: str) -> str:
    # Remove any remaining (...) or [...] completely (including empty "()")
    t = re.sub(r'\([^()]*\)', ' ', t)
    t = re.sub(r'\[[^\[\]]*\]', ' ', t)
    return t

def _remove_non_ascii(t: str) -> str:
    # Drop any non-ASCII characters (keeps pure English only)
    return re.sub(r'[^\x00-\x7F]+', '', t)

def _strip_short_tail_after_proper_nouns(t: str) -> str:
    """
    Remove short (<=4 letters) lowercase 'tail' immediately after 1–3 Proper Nouns.
    Example: 'Hong Kong ren' -> 'Hong Kong'
    Whitelist keeps meaningful short words like 'dog'/'cat'.
    """
    keep = {'dog', 'cat'}
    def repl(m):
        tail = m.group(2)
        return m.group(0) if tail.lower() in keep else m.group(1)
    return re.sub(r'((?:[A-Z][a-z]+\s+){1,3})([a-z]{1,4})\b', repl, t)

# Grammar/wording fixes applied per segment
_GRAMMAR_FIXES = [
    (re.compile(r'(?i)\bReligion\s+Property\b'), 'Religious Property'),
]

# NEW: strip outer punctuation (full stops, commas, colons, etc.)
def _clean_segment_punct(seg: str) -> str:
    seg = re.sub(r'^[\s,.;:!?\-/_\\|]+', '', seg or '')
    seg = re.sub(r'[\s,.;:!?\-/_\\|]+$', '', seg)
    return re.sub(r'\s{2,}', ' ', seg).strip()

def _apply_grammar_fixes(seg: str) -> str:
    # Expand bare "Locked" (with optional punctuation) → "Locked Gate"
    if re.fullmatch(r'(?i)\s*Locked[ \t]*[.,;:!?\-]*\s*', seg or ''):
        return 'Locked Gate'
    for rx, rep in _GRAMMAR_FIXES:
        seg = rx.sub(rep, seg)
    return seg


def _sentence_case(seg: str) -> str:
    seg = (seg or '').strip()
    if not seg:
        return seg
    if seg.upper() == 'NJM':
        return 'NJM'
    return seg[0].upper() + seg[1:]

def _drop_punct_only(seg: str) -> bool:
    # true if the segment is only punctuation like "," ".", "..." or slashes/dashes
    return bool(re.fullmatch(r'[\s,.\-/_\\|]+', seg or ''))

def sanitize_notes_text(s: str) -> str:
    if not s:
        return ""

    t = unicodedata.normalize("NFC", str(s))

    # Replace "no junk mail"/"no circulars" with NJM
    t = re.sub(r'(?i)\bno\s+junk\s*mail(s)?\b', 'NJM', t)
    t = re.sub(r'(?i)\bno\s+circulars?\b', 'NJM', t)

    # dog inside → dog
    t = re.sub(r'(?i)\bdog\s+inside\b', 'dog', t)

    # Pull NJM out of parentheses first, then drop every other (...) / [...]
    t = _pull_njm_from_parentheses(t)
    t = _strip_all_parentheses_content(t)

    # Remove common date forms
    t = _DATE_RX.sub('', t)

    # Map "Locked . NJM" / "Locked, NJM" (any punct/space) → "Locked Gate / NJM"
    t = re.sub(r'(?i)\blocked[\s,.\-;:]*NJM\b', 'Locked Gate / NJM', t)

    # Remove lone question marks and stray backslashes
    t = t.replace('?', ' ').replace('\\', ' ')

    # Delete boilerplate phrases (with lots of “similar” variants)
    for rx in _NOTE_DROP_RES:
        t = rx.sub(' ', t)

    # Remove non-ASCII (keep only English)
    t = _remove_non_ascii(t)

    # Remove short non-English-ish tails after proper nouns (e.g., "Hong Kong ren")
    t = _strip_short_tail_after_proper_nouns(t)

    # Normalize repeated dots/commas and odd sequences
    t = re.sub(r'(?:\s*\.\s*){2,}', ' ', t)   # collapse " . . . " / "..." → space
    t = re.sub(r'\s*,\s*,\s*', ' / ', t)      # ", , " → separator
    t = re.sub(r'(?<!\d)\s*,\s*(?!\d)', ' / ', t)

    # Language-specific trims
    t = re.sub(r'(?i)\bNJM\s+English\s+and\s+(Cantonese)\b', r'NJM \1', t)
    t = re.sub(r'(?i)\b(Cantonese)\s*(?:and|/)\s*English\b', r'\1', t)
    t = re.sub(r'(?i)\bEnglish\s*(?:and|/)\s*(Cantonese)\b', r'\1', t)
    # From Vietnam, can speak Cantonese and English → From Vietnam / Cantonese
    t = re.sub(r'(?i)^From\s+([A-Za-z ]+),?\s*can\s*speak\s*(Cantonese|Mandarin)(?:\s*(?:and|/)\s*English)?\b',
               r'From \1 / \2', t)

    # Normalize separators and split
    t = _normalize_separators(t)
    parts = [p.strip(' /,;') for p in t.split(' / ') if p.strip(' /,;')]

    # Hard delete any segment that still mentions banned phrases/tokens,
    # even if they appear separately or with odd spacing/punctuation.
    parts = [p for p in parts if not _segment_contains_forced_drop(p)]

    # Drop punctuation-only fragments like "," "." "…" "/"
    parts = [p for p in parts if not _drop_punct_only(p)]
    parts = [_clean_segment_punct(p) for p in parts if p.strip()]
    # Dedupe, preferring the NJM variant
    parts = _dedupe_segments_keep_njm(parts)

    # Grammar fixes + sentence case each segment
    cleaned = []
    for p in parts:
        p2 = _apply_grammar_fixes(p)
        p2 = _sentence_case(p2)
        cleaned.append(p2)

    # Final tidy
    out = ' / '.join([p for p in cleaned if p])
    out = _normalize_separators(out)
    return out

def sanitize_notes_in_rows(rows) -> int:
    """In-place cleanup for NotesFromPublisher and Notes. Returns count of changed fields."""
    changed = 0
    for r in rows or []:
        for fld in ("NotesFromPublisher", "Notes"):
            if fld in r and (r[fld] or "").strip():
                before = r[fld]
                after = sanitize_notes_text(before)
                if after != before:
                    r[fld] = after
                    changed += 1
    return changed  # similar phrasings/variants are handled via regexes above


# ---------- Notes sanitization Patch End----------


# --- Main CSV processor (patched) ---


from collections import defaultdict



# --- process_csv

def process_csv(input_file, output_clean, output_fail, expected_headers,
                verify_geocode=False,
                preserve_input_status=False,
                map_home_to_at_home=False,
                geocode_scope: str = "all"):   # ← NEW: "all" or "missing"
    """
    Verbose/instrumented version with STAGE markers:

    STAGE 0: Globals / Setup
    STAGE 1: Load CSV + Header Validation
      1.1 Sanitize Row Types
      1.2 Lift Suburb From Street (embedded tails)
      1.3 Early street clean: remove suburb after suffix + expand suffix
    STAGE 2: Load Canon Suffix Map (previous outputs)
    STAGE 3: Attach Row IDs
    STAGE 4: Build Quick Lookups
    STAGE 5: Detect Majority Suburb
    STAGE 6: 3.3 Pre-correct street spellings
    STAGE 7: 3.4 Standardise similar streets
    STAGE 8: 3.5 Resolve conflicting suburbs by proximity (pre-geocode)
    STAGE 9: 3.6 Final street spelling enforcement (+ final normalise sweep)
    STAGE 10: Build Address Query Set
    STAGE 11: Batch Geocode (LINZ → Photon/Nominatim/geocode.xyz)
    STAGE 12: Build Known Coords (for row processing)
    STAGE 13: Post-Geocode Row Processing
    STAGE 14: Post-Geocode Suburb Resolve + Cleanup
    STAGE 15: Cross-buffer Unify (clean + fail)
    STAGE 16: Retry Fail Candidates (re-geocode)
    STAGE 17: Reclassify Eligible Fails → Clean
    STAGE 18: Final Cross-buffer Unify (post-retry/reclassify)
    STAGE 19: Write Outputs + Summary
    """

    import traceback
    from collections import Counter, defaultdict as _dd
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from tqdm import tqdm as _tqdm

    # ---------- Helpers for logging stage progress ----------
    def _dbg(msg): print(f"[DEBUG] {msg}")
    def _stage_ok(name): print(f"✅ Stage OK: {name}")
    def _stage_start(name):
        print(f"\n=== ▶ {name} ===")
        if 'cancel_flag' in globals():
            print(f"   cancel_flag = {cancel_flag.is_set()}")
    def _cancelled(name):
        print(f"⚠️  Cancelled right after: {name}")
        return
    def _counts_snapshot(rows, label="rows"):
        try:
            n = len(rows)
            streets = len({(r.get('Street') or '').strip().title() for r in rows if r.get('Street')})
            subs = len({(r.get('Suburb') or '').strip().title() for r in rows if r.get('Suburb')})
            print(f"   {label}: {n} | unique streets: {streets} | unique suburbs: {subs}")
        except Exception:
            pass

    # =======================================================
    # STAGE 0: Globals / Setup
    # USES: _ensure_globals(), build_other_linz_memory_db()
    # =======================================================
    _stage_start("Globals/Setup")
    try:
        _ensure_globals()
        enable_hotpath_caches()
        global memory_conn
        memory_conn = build_other_linz_memory_db()
        _stage_ok("Globals/Setup")
    except Exception as e:
        print("❌ Setup error:", e)
        print(traceback.format_exc())
        return

    # =======================================================
    # STAGE 1: Load CSV + Header Validation
    # USES: csv.DictReader
    # -------------------------------------------------------
    # 1.1 Sanitize Row Types
    # 1.2 Lift Suburb From Street (embedded tails)
    # 1.3 Early street clean (strip suburb after suffix; expand)
    # =======================================================
    _stage_start("Load CSV + Header Validation")
    try:
        with open(input_file, "r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.DictReader(f)
            # --- sanitize headers up front ---
            headers = [h for h in (reader.fieldnames or []) if isinstance(h, str) and h.strip()]
            reader.fieldnames = headers  # ✅ remove None/blank headers before row dicts are built
            if not headers:
                print("❌ CSV appears to have no valid headers.")
                return
            if expected_headers:
                missing = [h for h in expected_headers if h not in headers]
                if missing:
                    print(f"⚠️ Missing expected column(s): {missing}")
            all_rows = list(reader)
        _counts_snapshot(all_rows, "loaded rows")
        _stage_ok("Load CSV + Header Validation")
    except FileNotFoundError:
        print(f"❌ Input file not found: {input_file}")
        return
    except Exception as e:
        print("❌ CSV load error:", e)
        print(traceback.format_exc())
        return

    _stage_start("Sanitize Row Types")
    try:
        import math
        def _to_str(v):
            if v is None:
                return ""
            if isinstance(v, float):
                if math.isnan(v):
                    return ""
                if v.is_integer():
                    return str(int(v))  # 2113.0 → "2113"
                return str(v)
            return str(v)

        for r in all_rows:
            for k, v in list(r.items()):
                # 🚫 Never touch free-form text columns
                if k in PRESERVE_FREEFORM_FIELDS:
                    continue
                r[k] = _to_str(v)
        _stage_ok("Sanitize Row Types")
    except Exception as e:
        print("❌ Sanitize error:", e)

    _stage_start("Lift Suburb From Street (embedded tails)")
    try:
        # Build case-insensitive suburb set + canonical map
        canon_map = {}
        cand_set = set()
        source_suburbs = (valid_suburbs_data if 'valid_suburbs_data' in globals() else [])
        for s in source_suburbs:
            if not s:
                continue
            canon = macron_suburb_map.get(s, s) if 'macron_suburb_map' in globals() else s
            canon_map[s.lower()] = canon
            cand_set.add(s.lower())

        # Keep the original Status around if we need to preserve it later
        for r in all_rows:
            r.setdefault("__OrigStatus", (r.get("Status") or ""))

        # Also add ASCII-folded variants
        def _ascii_fold(s: str) -> str:
            import unicodedata, re
            s = unicodedata.normalize("NFKD", s or "")
            s = "".join(ch for ch in s if not unicodedata.combining(ch))
            s = re.sub(r"[^A-Za-z0-9\s]", " ", s)
            return re.sub(r"\s+", " ", s).strip().lower()

        for s in list(cand_set):
            canon = canon_map.get(s, s.title())
            folded = _ascii_fold(s)
            if folded and folded not in cand_set:
                cand_set.add(folded)
                canon_map[folded] = canon

        ordered_cands = sorted(cand_set, key=len, reverse=True)  # longest first

        import re
        def _maybe_lift(row):
            """
            If street ends with a known suburb token (with/without comma, optional 'Auckland' tail),
            move that token into Suburb. Only lifts when Suburb is blank/invalid.
            """
            st = (row.get("Street") or "").strip()
            sb = (row.get("Suburb") or "").strip()
            if not st:
                return

            sb_low = sb.lower()
            has_valid_suburb = (sb_low in canon_map) or (
                sb and macron_suburb_map.get(sb.title(), sb.title())
                in (canon_map.get(sb_low, sb.title()) if 'macron_suburb_map' in globals() else sb)
            )
            if has_valid_suburb and sb_low != "auckland":
                return

            st_norm = re.sub(r"\s+", " ", st.replace(",", " ")).strip().lower()
            st_norm = re.sub(r"(,\s*)?auckland\s*$", "", st_norm).strip()

            hit = None
            for cand in ordered_cands:
                if not cand:
                    continue
                if re.search(rf"(?:\s|^){re.escape(cand)}$", st_norm, flags=re.IGNORECASE):
                    hit = cand
                    break

            if not hit:
                return

            new_suburb = canon_map.get(hit, hit.title())
            if "howick" in new_suburb.lower():
                new_suburb = "Howick"  # policy

            pattern = rf"(?i)[,\s]*{re.escape(hit)}(?:[,\s]+auckland)?\s*$"
            new_street = re.sub(pattern, "", st).rstrip(", ").rstrip()

            if new_street != st or (not sb or sb_low == "auckland"):
                try:
                    _log_quiet("Lift Suburb",
                               f"Street: '{st}' → '{new_street}' | Suburb: '{sb}' → '{new_suburb}'",
                               street=new_street or st, important=False)
                except Exception:
                    pass
                row["Street"] = new_street or st
                row["Suburb"] = new_suburb

        # Run the lift + early suffix/suburb clean together, row by row
        for r in all_rows:
            r = ensure_row_text_types(r)  # safe strings
            _maybe_lift(r)               # 1.2 lift
            # 1.3 early street clean (remove trailing suburb after a suffix, expand suffix, fix spaces)
            st = (r.get("Street") or "").strip()
            if st:
                st_clean = clean_street_suffix_and_suburb(st)
                if st_clean != st:
                    r["Street"] = st_clean
                    _log_quiet("Suffix-tail strip (early)", f"{st} → {st_clean}", street=st_clean, important=False)

        _stage_ok("Lift Suburb From Street (embedded tails)")
    except Exception as e:
        print("ℹ️ Lift-suburb step skipped:", e)

    # =======================================================
    # STAGE 2: Load Canon Suffix Map (from previous outputs)
    # USES: build_canon_suffix_map_from_outputs()
    # =======================================================
    _stage_start("Load Canon Suffix Map (from previous output)")
    try:
        build_canon_suffix_map_from_outputs(paths=("output_clean.csv",))
        _stage_ok("Load Canon Suffix Map (from previous output)")
    except Exception as e:
        print("ℹ️ Canon suffix load skipped:", e)

    # =======================================================
    # STAGE 3: Attach Row IDs (no coord pruning)
    # =======================================================
    _stage_start("Attach Row IDs")
    try:
        bad_rows = [i for i, r in enumerate(all_rows) if not isinstance(r, dict)]
        if bad_rows:
            print(f"❌ Found {len(bad_rows)} invalid row(s): {bad_rows[:3]}")
            return

        for i, r in enumerate(all_rows, start=2):
            r["__RowID"] = i
            # NEW: remember original street to compare later
            r.setdefault("__OrigStreet", (r.get("Street") or "").strip().title())

        _stage_ok("Attach Row IDs")
    except Exception as e:
        print("❌ Row ID step error:", e)
        print(traceback.format_exc())
        return

    # =======================================================
    # STAGE 4: Build Quick Lookups
    # =======================================================
    _stage_start("Build Quick Lookups")
    try:
        all_streets = set()
        input_street_lookup = {}
        for idx, row in enumerate(all_rows):
            street = (row.get("Street", "") or "").strip().title()
            suburb = (row.get("Suburb", "") or "").strip().title()
            type_  = (row.get("Type",   "") or "").strip().title()
            if street:
                all_streets.add(street)
                input_street_lookup[street] = {"row": idx + 2, "suburb": suburb, "type": type_}
        print(f"   unique streets in input: {len(all_streets)}")
        _stage_ok("Build Quick Lookups")
    except Exception as e:
        print("❌ Quick lookup error:", e)
        print(traceback.format_exc())
        return

    # =======================================================
    # STAGE 5: Detect Majority Suburb
    # USES: canon_suburb(), NEARBY_SUBURBS, log_correction()
    # =======================================================
    _stage_start("Detect Majority Suburb")
    majority_suburb = ""
    try:
        counts = Counter(
            (r.get("Suburb") or "").strip().title()
            for r in all_rows if (r.get("Suburb") or "").strip()
        )
        majority_suburb = counts.most_common(1)[0][0] if counts else ""
        majority_suburb = canon_suburb(majority_suburb)
        if majority_suburb not in NEARBY_SUBURBS:
            log_correction("Nearby Policy Disabled", f"Unrecognized majority '{majority_suburb or '<none>'}'")
            majority_suburb = ""
        log_correction("Majority Suburb", f"Detected: {majority_suburb or '<none>'}")
        print(f"   majority_suburb = {majority_suburb or '<none>'}")
        _stage_ok("Detect Majority Suburb")
    except Exception as e:
        print("❌ Majority suburb error:", e)
        print(traceback.format_exc())
        majority_suburb = ""

    if cancel_flag.is_set():
        return _cancelled("Detect Majority Suburb")

    # =======================================================
    # STAGE 6: 3.3 Pre-correct street spellings
    # USES: pre_correct_street_spellings()
    # =======================================================
    _stage_start("3.3 Pre-correct street spellings")
    try:
        with step_timer("Pre-correct street spellings"):
            all_rows, _fixed = pre_correct_street_spellings(
                all_rows, verbose=bool(globals().get("VERBOSE_PRE", False))
            )
        print(f"   changed fields: {_fixed}")
        _counts_snapshot(all_rows, "after 3.3")
        _stage_ok("3.3 Pre-correct street spellings")
    except Exception as e:
        print("❌ 3.3 error:", e)
        print(traceback.format_exc())
    if cancel_flag.is_set():
        return _cancelled("3.3 Pre-correct street spellings")

    # =======================================================
    # STAGE 7: 3.4 Standardise similar streets
    # USES: standardize_similar_streets(), build_global_dominant_suburb_map()
    # =======================================================
    _stage_start("3.4 Standardise similar streets")
    try:
        with step_timer("Standardise similar streets"):
            all_rows, _changed = standardize_similar_streets(
                all_rows, majority_suburb, verbose=bool(globals().get("VERBOSE_PRE", False))
            )
        all_streets = set((r.get('Street') or '').strip().title() for r in all_rows if r.get('Street'))
        _ = build_global_dominant_suburb_map(all_rows)  # recompute map
        print(f"   field changes: {_changed}")
        _counts_snapshot(all_rows, "after 3.4")
        _stage_ok("3.4 Standardise similar streets")
    except Exception as e:
        print("❌ 3.4 error:", e)
        print(traceback.format_exc())
    if cancel_flag.is_set():
        return _cancelled("3.4 Standardise similar streets")

    # =======================================================
    # STAGE 8: 3.5 Resolve conflicting suburbs by proximity (pre-geocode)
    # USES: resolve_conflicting_suburbs_by_proximity(), safe_float()
    # =======================================================
    _stage_start("3.5 Resolve conflicting suburbs by proximity (pre-geocode)")
    try:
        known_coords_early = _dd(list)
        for r in all_rows:
            st = (r.get("Street", "") or "").strip().title()
            sb = (r.get("Suburb", "") or "").strip().title()
            la = safe_float(r.get("Latitude"), None)
            lo = safe_float(r.get("Longitude"), None)
            if st and sb and la is not None and lo is not None:
                known_coords_early[(st, sb)].append((la, lo))

        print(f"   streets with coords before 3.5: {len(known_coords_early)}")
        with step_timer("Resolve conflicting suburbs by proximity"):
            resolve_conflicting_suburbs_by_proximity(
                all_rows,
                known_geocodes_by_street=known_coords_early,
                radius_m=300
            )
        print("   ✔ finished resolve_conflicting_suburbs_by_proximity()")
        _counts_snapshot(all_rows, "after 3.5")
        _stage_ok("3.5 Resolve conflicting suburbs by proximity (pre-geocode)")
    except Exception as e:
        print("❌ 3.5 error:", e)
        print(traceback.format_exc())

    print(f"🔎 Post-3.5 cancel_flag = {cancel_flag.is_set()}")
    if cancel_flag.is_set():
        return _cancelled("3.5 Resolve conflicting suburbs by proximity (pre-geocode)")

    # =======================================================
    # STAGE 9: 3.6 Final street spelling enforcement
    #   9.a Final street/suburb normalisation sweep first
    # USES: final_normalize_rows(), enforce_final_street_spelling()
    # =======================================================
    _stage_start("3.6 Final street spelling enforcement")
    try:
        with step_timer("Final street/suburb normalisation"):
            all_rows, n_changed = final_normalize_rows(all_rows, valid_suburbs_data, enforce_title=True)
            print(f"   normalised (street/suburb): {n_changed} change(s)")

        with step_timer("Final street spelling enforcement"):
            all_rows = enforce_final_street_spelling(all_rows)

        _counts_snapshot(all_rows, "after 3.6")
        _stage_ok("3.6 Final street spelling enforcement")
    except Exception as e:
        print("❌ 3.6 error:", e)
        print(traceback.format_exc())
    if cancel_flag.is_set():
        return _cancelled("3.6 Final street spelling enforcement")

    # =======================================================
    # INITIALIZATION: Build LINZ memory cache
    # =======================================================
    memory_conn = build_other_linz_memory_db()

    # One-time cleanup: drop polluted coords from cache
    try:
        purge_non_auckland_from_memory(memory_conn)
    except Exception:
        log_correction("LINZ Memory Purge", "Cleanup failed (ignored)")

    # =======================================================
    # STAGE 10: Build Address Query Set
    # =======================================================
    _stage_start("Build Address Query Set")
    try:
        address_queries = {}
        missing_only = (str(geocode_scope).lower() == "missing")

        def _is_missing_coords(row):
            la = (row.get("Latitude") or "").strip()
            lo = (row.get("Longitude") or "").strip()
            if la == "" or lo == "":
                return True
            try:
                return float(la) == 0.0 or float(lo) == 0.0
            except Exception:
                return True  # treat non-numeric as missing

        for r in all_rows:
            if not isinstance(r, dict):
                continue
            if (r.get('Type', '') or '').strip().lower() == 'other':
                continue

            number = (r.get('Number') or '').strip()
            street = (r.get('Street') or '').strip()
            suburb = ((r.get('Suburb') or '').strip() or 'Auckland')
            if not (number and street):
                continue

            # Scope gate: only enqueue if coords are missing/empty when geocode_scope == "missing"
            if missing_only and not _is_missing_coords(r):
                continue

            k = addr_key(number, street, suburb)
            address_queries[k] = True

        print(f"   to geocode ({'missing only' if missing_only else 'all'}): {len(address_queries)}")
        if not address_queries:
            print("ℹ️ No addresses need batch geocoding in this scope.")
        _stage_ok("Build Address Query Set")
    except Exception as e:
        print("❌ Address list build error:", e)
        print(traceback.format_exc())
        return

    if cancel_flag.is_set():
        return _cancelled("Build Address Query Set")

    # =======================================================
    # STAGE 11: Batch Geocode  (+ prune/replace patch)
    # =======================================================
    _stage_start("Batch Geocode")
    try:
        address_list = list(address_queries.keys())
        if not address_list:
            print("   (scope produced 0 addresses) — skipping batch geocoding.")
            geocode_results = {}  # make sure downstream has a dict
            _stage_ok("Batch Geocode (skipped)")
        else:
            log_correction("Preparing Addresses", f"Preparing {len(address_list)} Addresses For Geocoding")

        # 11.0 Fetch initial results
        # scale concurrency to the batch size
        addr_n = len(address_list)
        max_workers = 12 if addr_n < 200 else 30 if addr_n < 2000 else 60

        geocode_results = run_async_coro(
            batch_geocode,
            addresses=address_list,
            verify=verify_geocode,
            max_workers=max_workers
        )

        print(f"   geocode results (raw): {len(geocode_results)}")
        log_correction("Batch Geocoding Completed", f"{len(geocode_results)} address results retrieved")

        # 11.1 Sanity pass: swap-if-needed, prune out-of-Auckland, then targeted replacement
        #     We keep all dict keys, but replace bad tuples with a fixed one or a blank tuple.
        cleaned_results = {}
        swapped_fix = 0
        pruned = 0
        replaced = 0
        still_bad = 0

        for akey in address_list:
            tpl = geocode_results.get(akey)

            # Normalize to a 4-tuple
            if not (isinstance(tpl, tuple) and len(tpl) == 4):
                cleaned_results[akey] = ("", "", "", "")
                pruned += 1
                continue

            label, lat, lon, postal = tpl

            # Try to coerce to floats; if not, mark for replacement
            lat_ok = lon_ok = True
            try:
                la = float(lat) if lat not in (None, "") else None
                lo = float(lon) if lon not in (None, "") else None
                if la is None or lo is None:
                    lat_ok = lon_ok = False
            except Exception:
                lat_ok = lon_ok = False

            # If both numeric, check for obvious swap and fix
            if lat_ok and lon_ok:
                la2, lo2 = _maybe_swap_latlon(la, lo)
                if (la2, lo2) != (la, lo):
                    swapped_fix += 1
                    la, lo = la2, lo2

            # Accept if we now have numeric and inside Auckland
            if (lat_ok and lon_ok) and is_in_auckland(la, lo):
                cleaned_results[akey] = (label, la, lo, postal or "")
                continue

            # 11.2 Replacement attempt: re-geocode this exact address string
            #     akey is already the canonical "Number Street, Suburb, Auckland"
            try:
                repl = get_lat_long(akey)
            except Exception:
                repl = None

            if isinstance(repl, tuple) and len(repl) == 4:
                r_label, r_lat, r_lon, r_postal = repl
                try:
                    r_la = float(r_lat);
                    r_lo = float(r_lon)
                except Exception:
                    r_la = r_lo = None

                if (r_la is not None and r_lo is not None) and is_in_auckland(r_la, r_lo):
                    cleaned_results[akey] = (r_label, r_la, r_lo, r_postal or "")
                    replaced += 1
                    continue

            # Couldn’t fix → blank it so downstream won’t trust it
            cleaned_results[akey] = ("", "", "", "")
            pruned += 1
            still_bad += 1

        geocode_results = cleaned_results

        # 11.3 Summary + OK
        print(f"   swapped fixed: {swapped_fix}")
        print(f"   pruned outside/invalid: {pruned} (replaced: {replaced}, still bad: {still_bad})")
        _stage_ok("Batch Geocode")

        # Optional detailed log lines
        if swapped_fix:
            log_correction("Geocode Swap Fix", f"Auto-corrected {swapped_fix} swapped lat/lon pair(s)")
        if pruned:
            log_correction("Geocode Prune",
                           f"Pruned {pruned} outside/invalid result(s) — {replaced} replaced immediately")

    except Exception as e:
        print("❌ Batch geocode error:", e)
        print(traceback.format_exc())
        return

    if cancel_flag.is_set():
        return _cancelled("Batch Geocode")


    # =======================================================
    # STAGE 12: Build Known Coords (for row processing)
    # =======================================================
    _stage_start("Build Known Coords (for row processing)")
    try:
        known_coords = _dd(list)
        for r in all_rows:
            street = (r.get("Street") or "").strip().title()
            suburb = (r.get("Suburb") or "").strip().title()
            lat = r.get("Latitude", "")
            lon = r.get("Longitude", "")
            if street and suburb and not is_blank_or_zero(lat) and not is_blank_or_zero(lon):
                try:
                    known_coords[(street, suburb)].append((float(lat), float(lon)))
                except Exception:
                    continue
        print(f"   known street/suburb coord buckets: {len(known_coords)}")
        _stage_ok("Build Known Coords (for row processing)")
    except Exception as e:
        print("❌ Known coords build error:", e)
        print(traceback.format_exc())
        return
    if cancel_flag.is_set():
        return _cancelled("Build Known Coords (for row processing)")

    # =======================================================
    # STAGE 13: Post-Geocode Row Processing
    # =======================================================
    _stage_start("Post-Geocode Row Processing")
    clean_rows, fail_rows = [], []
    try:
        # Compute once (instead of per-row)
        dom_verified_map = build_dominant_suburb_map_from_verified(all_rows, threshold=0.7)
        header_keys = list(all_rows[0].keys())

        def _call_row(row):
            if cancel_flag.is_set():
                return {"status": "cancelled", "row": row}
            try:
                row = ensure_row_text_types(row)
                return process_single_row(
                    row,
                    geocode_results,
                    all_rows,
                    all_streets,
                    seen_addresses,
                    header_keys,
                    verify_geocode,
                    dom_verified_map,  # ← precomputed once
                    known_geocodes_by_street=known_coords,
                    nearby_policy_enabled=False,
                    majority_suburb=majority_suburb,
                )
            except TypeError:
                # existing fallback
                return process_single_row(
                    row,
                    geocode_results,
                    all_rows,
                    all_streets,
                    seen_addresses,
                    header_keys,
                    verify_geocode,
                    dom_verified_map,  # ← precomputed once
                    known_geocodes_by_street=known_coords
                )

        seen_addresses = set()
        processed_input_streets = set()
        processed_street_lock = threading.Lock()

        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=40) as executor:
            future_map = {executor.submit(_call_row, row): row for row in all_rows}
            for fut in _tqdm(as_completed(future_map), total=len(future_map),
                             desc="🔄 Stage 4: Post-Geocode Processing....", unit="row"):
                if cancel_flag.is_set():
                    return _cancelled("Post-Geocode Row Processing (during futures)")
                orig_row = future_map[fut]
                try:
                    result = fut.result()
                    row = fix_lat_lon_if_swapped(result["row"])
                    street_t = (row.get("Street") or "").strip().title()
                    if street_t:
                        with processed_street_lock:
                            processed_input_streets.add(street_t)
                    if result["status"] == "clean":
                        clean_rows.append(row)
                    else:
                        if not (row.get("Final Status") or "").strip():
                            row["Final Status"] = "Fail"
                        fail_rows.append(row)
                except Exception as e:
                    log_correction("Row Processing Error", f"{e}", street=(orig_row.get("Street", "") or ""))
                    orig_row = dict(orig_row)
                    if not (orig_row.get("Final Status") or "").strip():
                        orig_row["Final Status"] = "Fail"
                    fail_rows.append(orig_row)
        print(f"   clean buffer: {len(clean_rows)} | fail buffer: {len(fail_rows)}")
        _stage_ok("Post-Geocode Row Processing")
    except Exception as e:
        print("❌ Post-geocode processing error:", e)
        print(traceback.format_exc())
        return

    # =======================================================
    # STAGE 14: Post-Geocode Suburb Resolve + Cleanup
    # USES: resolve_conflicting_suburbs_by_proximity(), log_field_change()
    # =======================================================
    _stage_start("Post-Geocode Suburb Resolve + Cleanup")
    try:
        known_coords_after = _dd(list)
        for r in clean_rows:
            st = (r.get("Street", "") or "").strip().title()
            sb = (r.get("Suburb", "") or "").strip().title()
            la = safe_float(r.get("Latitude"), None)
            lo = safe_float(r.get("Longitude"), None)
            if st and sb and la is not None and lo is not None:
                known_coords_after[(st, sb)].append((la, lo))

        with step_timer("Resolve conflicting suburbs by proximity (post-geocode)"):
            resolve_conflicting_suburbs_by_proximity(
                clean_rows,
                known_geocodes_by_street=known_coords_after,
                radius_m=300,
                k_nearest=3
            )

            removed_count = 0
            for r in clean_rows:
                old_sb = (r.get("Suburb") or "").strip()
                if old_sb.lower() == "auckland":
                    street_for_log = (r.get("Street") or "").strip().title()
                    row_id = r.get("__RowID")
                    log_field_change(
                        "Final Cleanup", row_id, "Suburb",
                        old_sb, "", "Removed exact 'Auckland' in Suburb",
                        street=street_for_log
                    )
                    r["Suburb"] = ""
                    removed_count += 1
            if removed_count:
                log_correction("Final Cleanup Summary", f"Removed exact 'Auckland' from {removed_count} row(s)")
        print("   post-geocode resolve done")
        _stage_ok("Post-Geocode Suburb Resolve + Cleanup")
    except Exception as e:
        print("❌ Post-geocode suburb resolve error:", e)
        print(traceback.format_exc())
    if cancel_flag.is_set():
        return _cancelled("Post-Geocode Suburb Resolve + Cleanup")




    # =======================================================
    # STAGE 15: Cross-buffer Unify (clean + fail)
    # USES: _unify_crossfiles_postgeocode()
    # =======================================================
    _stage_start("Cross-buffer Unify (clean + fail)")
    try:
        clean_rows, fail_rows = _unify_crossfiles_postgeocode(clean_rows, fail_rows)
        print(f"   after cross-buffer unify → clean: {len(clean_rows)} | fail: {len(fail_rows)}")
        _stage_ok("Cross-buffer Unify (clean + fail)")
    except Exception as e:
        print("❌ Cross-buffer unify error:", e)
        print(traceback.format_exc())
    if cancel_flag.is_set():
        return _cancelled("Cross-buffer Unify (clean + fail)")

    # =======================================================
    # STAGE 16: Retry Fail Candidates
    # USES: run_async_coro(batch_geocode), is_in_auckland(), macron_suburb_map
    # =======================================================
    _stage_start("Retry Fail Candidates")
    try:
        retry_candidates = []
        for r in fail_rows:
            fs = (r.get("Final Status") or "").strip().lower()
            st = (r.get("Status") or "").strip().lower()
            if fs != "fail": continue
            if st in {"duplicate", "donotcall"}: continue
            if st == "custom1" and fs == "fail": continue
            number = (r.get("Number") or "").strip()
            street = (r.get("Street") or "").strip()
            suburb = (r.get("Suburb") or "").strip()
            if number and street and suburb:
                retry_candidates.append(fmt_addr_parts(number, street, suburb))
        print(f"   retry candidates: {len(retry_candidates)}")

        if retry_candidates:
            retry_results = run_async_coro(
                batch_geocode,
                addresses=list(set(retry_candidates)),
                verify=False,
                max_workers=20
            )
            promoted = 0
            new_fail_rows = []
            for r in fail_rows:
                k = fmt_addr_parts((r.get("Number") or "").strip(),
                                   (r.get("Street") or "").strip(),
                                   (r.get("Suburb") or "").strip())
                hit = retry_results.get(k)
                if hit and isinstance(hit, tuple) and len(hit) == 4:
                    full, lat, lon, postal = hit
                    if lat and lon and is_in_auckland(float(lat), float(lon)):
                        parts = [p.strip() for p in (full or "").split(",")]
                        g_suburb = parts[1].title() if len(parts) > 1 else (r.get("Suburb") or "").strip().title()
                        r["Latitude"] = f"{float(lat):.8f}"
                        r["Longitude"] = f"{float(lon):.8f}"

                        # ✅ Guard postal using nz_postal_lookup
                        if postal:
                            expected = nz_postal_lookup.get(g_suburb, "")
                            if expected and postal != expected:
                                postal = expected

                        if postal and not (r.get("PostalCode") or "").strip():
                            r["PostalCode"] = postal

                        if g_suburb:
                            r["Suburb"] = macron_suburb_map.get(g_suburb, g_suburb)
                        r["Final Status"] = ""
                        clean_rows.append(r)
                        promoted += 1
                        continue

                new_fail_rows.append(r)
            fail_rows = new_fail_rows
            print(f"   promoted from retry: {promoted}")
        _stage_ok("Retry Fail Candidates")
    except Exception as e:
        print("❌ Retry block error:", e)
        print(traceback.format_exc())
    if cancel_flag.is_set():
        return _cancelled("Retry Fail Candidates")

    # =======================================================
    # STAGE 17: Reclassify Eligible Fails → Clean
    # =======================================================
    _stage_start("Reclassify Eligible Fails To Clean")
    try:
        def _bare(s):
            return (s or "").strip().lower().replace(" ", "")

        # Treat these Status values as eligible for Clean (Pass), including DoNotCall
        eligible_statuses = {"home", "nothome", "available", "newfrompublisher", "donotcall"}

        # Only these Final Statuses must remain in Fail
        protected_final = {"duplicate", "notchinese"}  # ← removed "donotcall"

        moved = 0
        keep_fail = []
        for r in fail_rows:
            s_norm = _bare(r.get("Status"))
            fs_norm = _bare(r.get("Final Status"))
            if (s_norm in eligible_statuses) and (fs_norm not in protected_final):
                # Do NOT change Status; just clear Final Status to mark as Clean
                if r.get("Final Status"):
                    log_correction("Reclassify To Clean",
                                   f"Status='{r.get('Status')}', Final Status='{r.get('Final Status')}' → clean",
                                   street=(r.get("Street") or ""))
                r["Final Status"] = ""  # Clean (Pass)
                clean_rows.append(r)
                moved += 1
            else:
                keep_fail.append(r)
        fail_rows = keep_fail
        print(f"   reclassified from fail → clean: {moved}")
        _stage_ok("Reclassify Eligible Fails To Clean")
    except Exception as e:
        print("❌ Reclassify step error:", e)

    # =======================================================
    # STAGE 18: Final Cross-buffer Unify (post-retry/reclassify)
    # USES: unify_street_suburb_across_outputs()
    # =======================================================
    _stage_start("Final Cross-buffer Unify (post-retry/reclassify)")
    try:
        clean_rows, fail_rows, _ = unify_street_suburb_across_outputs(
            clean_rows, fail_rows, radius_m=800, k_nearest=5
        )
        print(f"   final unify → clean: {len(clean_rows)} | fail: {len(fail_rows)}")
        _stage_ok("Final Cross-buffer Unify (post-retry/reclassify)")
    except Exception as e:
        print("❌ Final cross-buffer unify error:", e)
        print(traceback.format_exc())
    if cancel_flag.is_set():
        return _cancelled("Final Cross-buffer Unify (post-retry/reclassify)")

    # =======================================================
    # STAGE 19: Write Outputs + Summary
    # =======================================================
    _stage_start("Write Outputs")
    try:
        def _num_key(n: str) -> int:
            # Sort by the *house* number even if value is "Unit3/219" or "219/Unit3" or "12-14"
            s = (n or "").strip()
            m = re.match(r"\s*(?:Unit[A-Za-z0-9]+\s*/\s*)?(\d+)", s, re.IGNORECASE)
            try:
                return int(m.group(1)) if m else 0
            except Exception:
                return 0

        # --- Enforce protected streets just before logging/writing ---
        def _enforce_protected_streets(rows):
            fixed = 0
            for r in rows or []:
                orig = (r.get("__OrigStreet") or "").strip().title()
                final = (r.get("Street") or "").strip().title()
                if not orig or not final:
                    continue

                # Full-name protection
                if _is_protected_full(orig) and final != orig:
                    r["Street"] = orig
                    fixed += 1
                    log_correction("Protected Street Undo", f"Reverted '{final}' → '{orig}'", street=orig)
                    continue

                # Base-level protection (e.g., Eaglen vs Eaglemont)
                obase = _protected_base(orig)
                if obase:
                    fbase, _ = _norm_base_key(final)
                    if fbase != obase:
                        r["Street"] = orig
                        fixed += 1
                        log_correction("Protected Base Undo", f"Reverted '{final}' → '{orig}'", street=orig)
            return fixed

        # Apply to both buffers before we log any changes
        _ = _enforce_protected_streets(clean_rows)
        _ = _enforce_protected_streets(fail_rows)

        # --- NEW: log any street-name changes from original → final
        try:
            changes = 0
            for r in (clean_rows + fail_rows):
                orig = (r.get("__OrigStreet") or "").strip().title()
                final = (r.get("Street") or "").strip().title()
                if orig and final and orig != final:
                    # Example: "Eaglen Place - Eaglemont Drive"
                    log_correction("Street Name Changed", f"{orig} - {final}", street=final)
                    changes += 1
            if changes:
                log_correction("Street Name Changed Summary", f"Logged {changes} street rename(s)")
        except Exception as e:
            log_correction("Street Change Logging Error", f"{e}")

        def _strip_internal_fields(rows, keep_keys=("__OrigStatus",)):
            if not rows:
                return
            keep = set(keep_keys or ())
            for r in rows:
                if not isinstance(r, dict):
                    continue
                to_remove = []
                for k in list(r.keys()):
                    if not isinstance(k, str):
                        to_remove.append(k)
                        continue
                    if k.startswith("_") and k not in keep:
                        to_remove.append(k)
                for k in to_remove:
                    r.pop(k, None)

        # Ensure we have the full schema
        fieldnames = list(all_rows[0].keys())
        for col in [
            "TerritoryID", "TerritoryNumber", "CategoryCode", "Category",
            "TerritoryAddressID", "ApartmentNumber", "Number", "Street",
            "Suburb", "PostalCode", "State", "Name", "Phone", "Type", "Status",
            "NotHomeAttempt", "Date1", "Date2", "Date3", "Date4", "Date5",
            "Language", "Latitude", "Longitude", "Notes", "NotesFromPublisher",
            "Final Status"
        ]:
            if col not in fieldnames:
                fieldnames.append(col)

        # Fail rows must carry an explicit Final Status
        for r in fail_rows:
            if not (r.get("Final Status") or "").strip():
                r["Final Status"] = "Fail"

        # --- Apply manual overrides BEFORE sorting ---
        _stage_start("Apply Manual Overrides")
        try:
            clean_rows = apply_manual_overrides(clean_rows)
            fail_rows = apply_manual_overrides(fail_rows)
            _stage_ok("Apply Manual Overrides")
        except Exception as e:
            print("❌ Manual overrides error:", e)
            print(traceback.format_exc())
        if cancel_flag.is_set():
            return _cancelled("Apply Manual Overrides")

        # --- Build sorted_* AFTER overrides ---
        def _status_bucket(s: str) -> int:
            s = (s or "").strip().lower()
            if s in {"duplicate"}: return 0
            if s in {"not chinese", "notchinese", "custom1"}: return 1
            if s in {"do not call", "donotcall"}: return 2
            if s in {"fail"}: return 3
            return 4

        sorted_clean = sorted(
            clean_rows,
            key=lambda r: (
                (r.get("Street") or "").strip().lower(),
                (r.get("Suburb") or "").strip().lower(),
                _num_key(r.get("Number", ""))
            )
        )

        sorted_fail = sorted(
            fail_rows,
            key=lambda r: (
                _status_bucket(r.get("Final Status")),
                (r.get("Street") or "").strip().lower(),
                (r.get("Suburb") or "").strip().lower(),
                _num_key(r.get("Number", ""))
            )
        )

        # ---------- Coverage checks ----------
        blank_count = 0
        oob_count = 0
        blank_rows = []
        oob_rows = []

        for r in (sorted_clean + sorted_fail):
            la = safe_float(r.get("Latitude"), None)
            lo = safe_float(r.get("Longitude"), None)
            num = (r.get("Number") or "").strip()
            st = (r.get("Street") or "").strip().title()
            sb = (r.get("Suburb") or "").strip().title()
            addr_label = f"{num} {st}, {sb}".strip(", ")

            if la is None or lo is None or str(la).strip() == "" or str(lo).strip() == "":
                blank_count += 1
                blank_rows.append(addr_label)
            else:
                if not is_in_auckland(la, lo):
                    oob_count += 1
                    oob_rows.append(f"{addr_label} → {la},{lo}")

        if blank_count > 0 or oob_count > 0:
            print("\n📍 Coordinate Coverage Check")
            if blank_count > 0:
                print(f"   • Rows with blank coords: {blank_count}")
                for b in blank_rows:
                    print(f"      - {b}")
                    log_correction("Coverage Blank Coord", f"{b}", street=b)
            if oob_count > 0:
                print(f"   • Rows Outside Auckland:  {oob_count}")
                for o in oob_rows:
                    print(f"      - {o}")
                    log_correction("Coverage OOB Coord", f"{o}", street=o.split("→")[0].strip())

        # Per-row OOB demotion
        moved_rows = 0
        keep_clean = []
        for r in sorted_clean:
            la = safe_float(r.get("Latitude"), None)
            lo = safe_float(r.get("Longitude"), None)
            if la is not None and lo is not None and not is_in_auckland(la, lo):
                r["Final Status"] = "Geocode Outside Auckland/NZ"
                sorted_fail.append(r)
                moved_rows += 1
            else:
                keep_clean.append(r)
        sorted_clean = keep_clean
        if moved_rows:
            log_correction("Coverage Demote (per-row)", f"Moved {moved_rows} OOB row(s) to fail")

        # Street-wide demotion for any OOB coords (always run)
        sorted_clean, sorted_fail, moved, affected = demote_streets_with_out_of_auckland_coords(
            sorted_clean, sorted_fail
        )
        if moved:
            log_correction(
                "Coverage Demote Summary",
                f"Moved {moved} row(s) to fail across {len(affected)} street(s)"
            )

        # --- Final counts after demotions ---
        clean_count = len(sorted_clean)
        fail_count = len(sorted_fail)

        # >>> INSERT HERE, *before* building sorted_clean/sorted_fail <<<
        clean_rows, fail_rows = enforce_real_duplicates(clean_rows, fail_rows)

        # now build the sorted buffers as you already do:
        sorted_clean = sorted(
            clean_rows,
            key=lambda r: (
                (r.get("Street") or "").strip().lower(),
                (r.get("Suburb") or "").strip().lower(),
                _num_key(r.get("Number", ""))
            )
        )
        sorted_fail = sorted(
            fail_rows,
            key=lambda r: (
                _status_bucket(r.get("Final Status")),
                (r.get("Street") or "").strip().lower(),
                (r.get("Suburb") or "").strip().lower(),
                _num_key(r.get("Number", ""))
            )
        )



        # Optional geocode source summary
        if 'geocode_sources_used' in globals() and geocode_sources_used:
            print("📊 Geocode Source Summary:")
            for source, count in geocode_sources_used.items():
                print(f"   - {source}: {count}")

        # Group corrections without touching the live log
        try:
            group_corrections_log_by_street(
                src="corrections_log.csv",
                dst="corrections_log_grouped.csv"
            )
        except Exception as e:
            log_correction("Corrections Grouping Error", f"Could not write grouped corrections log: {e}")

        # Sanitize fieldnames: strings only, non-empty, de-dupe
        fieldnames = [c for c in fieldnames if isinstance(c, str) and c.strip()]
        fieldnames = list(dict.fromkeys(fieldnames))


        # If the caller asked to preserve input Status (options 5/6), DO NOT override it.
        # Only map `Home` → `At Home` when requested.
        # >>> GLOBAL DEDUPE (decide 'Duplicate' at the end, using FINAL names)
        clean_rows, fail_rows = assign_duplicates_globally(clean_rows, fail_rows)

        # … keep everything up to/including dedupe …

        # >>> NEW: append any input rows that never made it into either buffer as Missing
        present_ids = set()
        for r in (clean_rows + fail_rows):
            rid = r.get("__RowID")
            if rid:
                present_ids.add(rid)

        missing_added = 0
        for r in all_rows:
            rid = r.get("__RowID")
            if rid and rid not in present_ids:
                m = dict(r)  # shallow copy so we don't mutate all_rows
                m["Final Status"] = "Missing"
                fail_rows.append(m)
                missing_added += 1

        if missing_added:
            log_correction("Missing Rows → Fail",
                           f"Appended {missing_added} missing row(s) to output_fail.csv with Final Status='Missing'")

        # ✅ Restore original Status FIRST
        if preserve_input_status:
            def _restore_status(rows):
                for r in rows or []:
                    orig = (r.get("__OrigStatus") or r.get("Status") or "").strip()
                    if map_home_to_at_home and orig.lower() == "home":
                        r["Status"] = "At Home"
                    else:
                        r["Status"] = orig

            _restore_status(clean_rows)
            _restore_status(fail_rows)

        # ✅ Now it’s safe to drop internal fields
        _strip_internal_fields(clean_rows)
        _strip_internal_fields(fail_rows)

        # ⚠️ IMPORTANT: rebuild the sorted buffers AFTER the dedupe + status restore
        def _num_key(n: str) -> int:
            s = (n or "").strip()
            m = re.match(r"\s*(?:Unit[A-Za-z0-9]+\s*/\s*)?(\d+)", s, re.IGNORECASE)
            try:
                return int(m.group(1)) if m else 0
            except Exception:
                return 0

        def _status_bucket(s: str) -> int:
            s = (s or "").strip().lower()
            if s in {"duplicate"}: return 0
            if s in {"not chinese", "notchinese", "custom1"}: return 1
            if s in {"do not call", "donotcall"}: return 2
            if s in {"fail"}: return 3
            return 4

        sorted_clean = sorted(
            clean_rows,
            key=lambda r: (
                (r.get("Street") or "").strip().lower(),
                (r.get("Suburb") or "").strip().lower(),
                _num_key(r.get("Number", ""))
            )
        )
        sorted_fail = sorted(
            fail_rows,
            key=lambda r: (
                _status_bucket(r.get("Final Status")),
                (r.get("Street") or "").strip().lower(),
                (r.get("Suburb") or "").strip().lower(),
                _num_key(r.get("Number", ""))
            )
        )

        # --- Quick postcode sanity cleanup (remove obviously foreign or invalid) ---
        for r in (sorted_clean + sorted_fail):
            pc = (r.get("PostalCode") or "").strip()
            if pc:
                try:
                    # NZ postcodes are 4 digits, typically 0xxx–9xxx
                    if not pc.isdigit() or int(pc) > 9999 or len(pc) != 4:
                        r["PostalCode"] = ""
                except Exception:
                    r["PostalCode"] = ""

        # --- ENFORCE ONE POSTCODE PER SUBURB (final guard) ---
        _stage_start("Enforce Postcodes By Suburb (final)")
        try:
            ch_c = enforce_postcode_by_suburb_inplace(sorted_clean)
            ch_f = enforce_postcode_by_suburb_inplace(sorted_fail)
            print(f"   postcode fixes → clean: {ch_c} | fail: {ch_f}")
            _stage_ok("Enforce Postcodes By Suburb (final)")
        except Exception as e:
            print("ℹ️ Postcode enforce step skipped:", e)

        # --- FLIP UNITS LAST (right before writing) & ensure coords unchanged ---
        _stage_start("Flip Unit Prefixes for Output (final)")
        try:
            def _snap_coords(rows):
                return [(r.get("Latitude", ""), r.get("Longitude", "")) for r in rows]

            clean_coords_before = _snap_coords(sorted_clean)
            fail_coords_before = _snap_coords(sorted_fail)

            flips_clean = flip_units_for_rows(sorted_clean)  # only mutates Number
            flips_fail = flip_units_for_rows(sorted_fail)

            # Guard: make sure flipping didn't alter coords
            def _assert_coords_same(before, rows, label):
                after = [(r.get("Latitude", ""), r.get("Longitude", "")) for r in rows]
                if after != before:
                    # Hard stop so bad side effects can never slip into outputs
                    raise RuntimeError(f"{label}: coordinates changed after unit flip")

            _assert_coords_same(clean_coords_before, sorted_clean, "Clean")
            _assert_coords_same(fail_coords_before, sorted_fail, "Fail")

            print(f"   flipped unit prefixes → clean: {flips_clean} | fail: {flips_fail}")
            _stage_ok("Flip Unit Prefixes for Output (final)")
        except Exception as e:
            print("ℹ️ Flip-unit step skipped:", e)

        # --- Merge NotesFromPublisher -> Notes for outputs ---
        _stage_start("Move NotesFromPublisher → Notes")
        try:
            merged_c = merge_publisher_notes_into_notes(sorted_clean)
            merged_f = merge_publisher_notes_into_notes(sorted_fail)
            print(f"   merged rows → clean: {merged_c} | fail: {merged_f}")
            _stage_ok("Move NotesFromPublisher → Notes")
        except Exception as e:
            print("ℹ️ Notes merge step skipped:", e)

        _stage_start("Sanitize Notes (per spec)")
        try:
            changed_c = sanitize_notes_in_rows(sorted_clean)
            changed_f = sanitize_notes_in_rows(sorted_fail)
            print(f"   sanitized notes → clean: {changed_c} field(s) | fail: {changed_f} field(s)")
            _stage_ok("Sanitize Notes (per spec)")
        except Exception as e:
            print("ℹ️ Notes sanitize step skipped:", e)


        # --- FINAL WRITE (nothing after this mutates rows) ---
        with open(output_clean, 'w', newline='', encoding='utf-8') as cleanfile, \
                open(output_fail, 'w', newline='', encoding='utf-8') as failfile:
            wc = csv.DictWriter(cleanfile, fieldnames=fieldnames, extrasaction="ignore", restval="")
            wf = csv.DictWriter(failfile, fieldnames=fieldnames, extrasaction="ignore", restval="")
            wc.writeheader();
            wf.writeheader()
            wc.writerows(sorted_clean)
            wf.writerows(sorted_fail)

        # --- FINAL POST-RUN CHECKS ---

        # 1) Generate missing_addresses.csv and capture its count for the summary
        missing_count = 0
        try:
            missing_count = write_missing_addresses_report(
                input_path=input_file,  # original Input CSV
                clean_path=output_clean,
                fail_path=output_fail,
                out_path="missing_addresses.csv"
            )
        except Exception as e:
            print(f"⚠️ Missing-address check failed: {e}")

        # (keep your split logic here if you like)

        # --- Extended summary (now uses missing_count) ---
        total_imported = len(all_rows)
        total_processed = clean_count + fail_count
        skipped_rows = total_imported - total_processed
        duplicates = sum(1 for r in all_rows if (r.get("Final Status") or "").strip().lower() == "duplicate")
        custom1 = sum(1 for r in all_rows if (r.get("Status") or "").strip().lower() == "custom1")
        donotcall = sum(1 for r in all_rows if (r.get("Status") or "").strip().lower() == "donotcall")

        def _fs(row):
            return (row.get("Final Status") or "").strip().lower()

        geocode_fail_cnt = sum(
            1 for r in sorted_fail
            if _fs(r) in {"geocode fail", "geocode outside auckland/nz"}
        )
        fail_status_cnt = sum(1 for r in sorted_fail if _fs(r) == "fail")
        # removed: missing_cnt from sorted_fail

        print("\n CSV Cleaning Summary")
        print("========================\n")
        print(f"✅ Total Imported Rows:  {total_imported}")
        print(f"✅ Total Processed:      {total_processed}")
        print(f"❌ Skipped Rows:         {skipped_rows}\n")
        print(f"✅ Cleaned Successfully: {clean_count}\n")
        print(f"❌ Total Failed:         {fail_count}")
        print(f" - Duplicate:            {duplicates}")
        print(f" - Not Chinese:          {custom1}")
        print(f" - Do Not Call:          {donotcall}")
        print(f" - Geocode Fail:         {geocode_fail_cnt}")
        print(f" - Fail:                 {fail_status_cnt}")
        print(f" - Missing:              {missing_count}\n")
        print("========================\n")

        _stage_ok("Write Outputs (final)")



    except Exception as e:

        print("❌ Write outputs error:", e)

        print(traceback.format_exc())

        return

    # If the user cancelled, stop here (no post-run checks)

    if cancel_flag.is_set():
        return _cancelled("Write Outputs")

    # --- FINAL POST-RUN CHECKS ---

    try:

        write_missing_addresses_report(

            input_path=input_file,  # original Input.nws.csv

            clean_path=output_clean,

            fail_path=output_fail,

            out_path="missing_addresses.csv"

        )

    except Exception as e:

        print(f"⚠️ Missing-address check failed: {e}")

    try:

        # Use the same headers as the input CSV for splitting

        with open(input_file, "r", encoding="utf-8-sig", errors="replace") as f:

            input_headers = list(csv.DictReader(f).fieldnames or [])

        split_output_clean_if_large(

            src=output_clean,

            dst_prefix="output_clean",

            max_rows=300,

            header=input_headers

        )

    except Exception as e:

        print(f"⚠️ Split check failed: {e}")


def split_cleaned_by_suburb_and_include_failed(clean_file, fail_file):
    out_dir = "New_Addresses_By_Suburb"

    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)

    # Split by suburb

    if os.path.exists(clean_file):
        with open(clean_file, 'r', encoding='utf-8') as infile:
            reader = csv.DictReader(infile)
            fieldnames = reader.fieldnames  # <-- cache once

            for row in tqdm(reader, desc="📂 Splitting By Suburb", unit="row"):
                suburb = row.get("Suburb", "").strip()
                suburb = "Other" if not suburb else suburb.replace(" ", "_")
                suburb_file = os.path.join(out_dir, f"{suburb}.csv")
                write_header = not os.path.exists(suburb_file)
                with open(suburb_file, 'a', newline='', encoding='utf-8') as sf:
                    writer = csv.DictWriter(sf, fieldnames=fieldnames)
                    if write_header:
                        writer.writeheader()
                    writer.writerow(row)


    # Include failed output
    if os.path.exists(fail_file):
        shutil.copy(fail_file, os.path.join(out_dir, "Failed_Output.csv"))

    if cancel_flag.is_set():
        print("⚠️ 'q' Pressed — Cancelling Process...")
        print("⚠️ Cancelled During File Splitting.")
        return None

    # Sort and display output files
    all_files = [f for f in os.listdir(out_dir) if f.strip()]
    normal_files = sorted(f for f in all_files if f not in {"Other.csv", "Failed_Output.csv"})
    special_files = [f for f in ["Other.csv", "Failed_Output.csv"] if f in all_files]
    final_files = normal_files + special_files

    print("\n✅ Cleaned Addresses Split Into Suburbs Inside 'New_Addresses_By_Suburb' Folder")
    print(f"📁 {len(final_files)} file(s) created:\n")
    for f in final_files:
        print(f"    📑 {f}")



# --- Output housekeeping helpers (fix for ensure_delete_outputs_interactive) ---
import os, shutil

def _list_existing_outputs():
    """
    Return a list of output files/folders that this tool creates,
    so we can show & delete them before a new run.
    """
    items = []

    # top-level CSVs written by the pipeline
    for name in [
        "output_clean.csv",
        "output_fail.csv",
        "corrections_log.csv",
        "corrections_log_grouped.csv",
    ]:
        if os.path.exists(name):
            items.append(name)

    # export/split folders (delete whole trees)
    for folder in ["Exported Files", "New_Addresses_By_Suburb"]:
        if os.path.isdir(folder):
            # include files in the folder (nice for preview) and the folder itself (for deletion)
            for root, _dirs, files in os.walk(folder):
                for f in files:
                    items.append(os.path.join(root, f))
            items.append(folder)

    return items

class oth:
    @staticmethod
    def remove_files(paths):
        """Best-effort removal of files or folders listed in `paths`."""
        for p in paths:
            try:
                if os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
                elif os.path.exists(p):
                    os.remove(p)
            except Exception as e:
                print(f"⚠️ Could not remove {p}: {e}")




def ensure_delete_outputs_interactive() -> bool:
    existing = _list_existing_outputs()
    if not existing:
        return True
    print("⚠️ Existing Output Files Detected:")
    for p in existing:
        print(f"   • {p}")
    print("Proceeding Will DELETE These Files.")
    confirm = input("Type 'y' to remove them and continue (anything else to cancel): ").strip().lower()
    if confirm != "y":
        print("❌ Cancelled — Outputs Were Not Deleted.")
        return False
    # call module helper
    oth.remove_files(existing)
    still = _list_existing_outputs()
    if still:
        print("❌ Could Not Remove The Following Files:")
        for p in still:
            print(f"   • {p}")
        return False
    print("✅ Files Removed Successfully...")
    return True

# --- NEW: per-option file collector (files only; never folders)
def _files_created_by_option(option_str: str):
    import os
    files = []

    core = [
        "output_clean.csv",
        "output_fail.csv",
        "corrections_log.csv",
        "corrections_log_grouped.csv",
    ]
    files += [p for p in core if os.path.isfile(p)]

    # Options that create split artifacts
    if option_str in {"3", "4", "7"}:  # ← added "7"
        for d in ["New_Addresses_By_Suburb", "Exported Files"]:
            if os.path.isdir(d):
                for root, _dirs, fns in os.walk(d):
                    for fn in fns:
                        files.append(os.path.join(root, fn))
    return files



# --- NEW: confirm & delete only the related files for a given option
def ensure_delete_option_outputs_interactive(option_str: str) -> bool:
    """
    Show and delete only the files created by a specific menu option.
    Folders are *never* removed; we only list & delete files.
    """
    targets = _files_created_by_option(option_str)
    if not targets:
        print("No existing output files to remove.")
        return True

    print("Existing output files for this option will be DELETED (folders will be kept):")
    for p in targets:
        print(f"   • {p}")

    confirm = input("Type 'y' to delete these files and continue (anything else to cancel): ").strip().lower()
    if confirm != "y":
        print("❌ Cancelled — no files were deleted.")
        return False

    removed = 0
    for p in targets:
        try:
            os.remove(p)   # files only
            removed += 1
        except Exception as e:
            print(f"⚠️ Could not remove {p}: {e}")

    print(f"✅ Removed {removed} file(s).")
    return True


# --- Option 7: New Streets (called by Clean_GoogleSheets option 3) -----------
import os
import sys

def option7_clean_split_new_streets(clean_path: str, fail_path: str, kml_dir: str = "KML Boundaries"):
    """
    New World Scheduler — Option 7
    Accepts output_clean/output_fail produced by the Google Sheets 'New Streets' flow
    and runs the usual split/export pipeline. (Rows were already filtered upstream.)
    """
    print("\n====================================================================")
    print("  Option 7 — Clean & Split Into Different Suburbs (New Streets)")
    print("--------------------------------------------------------------------")
    print(f"  Clean CSV : {os.path.abspath(clean_path)}")
    print(f"  Fail  CSV : {os.path.abspath(fail_path)}")
    print(f"  KML Dir   : {os.path.abspath(kml_dir)}")
    print("====================================================================\n")

    try:
        # 0) Validate inputs
        if not os.path.exists(clean_path):
            print(f"❌ Clean file not found: {clean_path}")
            return None
        if not os.path.exists(fail_path):
            print(f"⚠️  Fail file not found (continuing): {fail_path}")

        # 1) Resolve splitter function from this module (or elsewhere if you moved it)
        split_fn = None
        # try current module first
        split_fn = globals().get("split_cleaned_by_polygon_and_include_failed")
        if split_fn is None:
            # optional: if you moved the splitter to another module, import it here:
            # from GeoPackage_Borders import split_cleaned_by_polygon_and_include_failed as split_fn
            pass

        if split_fn is None or not callable(split_fn):
            print("❌ Could not find 'split_cleaned_by_polygon_and_include_failed'. "
                  "Ensure it is defined/imported in Clean_NewWorldScheduler.py.")
            return None

        # 2) Prefer a 'new_streets_only' flag if supported, else fall back
        try:
            result = split_fn(clean_path, fail_path, kml_dir=kml_dir, new_streets_only=True)
            print("✅ Split complete (new_streets_only=True).")
            return result
        except TypeError:
            # older signature without the flag
            result = split_fn(clean_path, fail_path, kml_dir=kml_dir)
            print("ℹ️  Splitter does not support 'new_streets_only'; ran standard split.")
            return result

    except KeyboardInterrupt:
        print("⛔ Interrupted.")
        return None
    except Exception as e:
        print(f"❌ Option 7 failed: {e}")
        return None




# --- Update menu actions to use the new file-only cleaner
def run_clean_normal_after_purge(expected_headers):
    if not ensure_delete_option_outputs_interactive("1"):
        return
    log_correction("Session Start", "Corrections log recreated after deletion or fresh start.")
    process_csv("input_nws.csv", "output_clean.csv", "output_fail.csv", expected_headers, verify_geocode=False,
                geocode_scope="missing")

def run_clean_verify_after_purge(expected_headers):
    if not ensure_delete_option_outputs_interactive("2"):
        return
    log_correction("Session Start", "Corrections log recreated after deletion or fresh start.")
    process_csv("input_nws.csv", "output_clean.csv", "output_fail.csv", expected_headers, verify_geocode=True)

def run_clean_and_split_after_purge():
    if not ensure_delete_option_outputs_interactive("3"):
        return
    log_correction("Session Start", "Corrections log recreated after deletion or fresh start.")
    process_csv(
        "input_nws.csv",
        "output_clean.csv",
        "output_fail.csv",
        expected_headers=["Number","Street","Suburb","PostalCode","Status","Latitude","Longitude"],
        verify_geocode=False,
        geocode_scope="missing")
    split_cleaned_by_polygon_and_include_failed("output_clean.csv", "output_fail.csv", kml_dir="KML Boundaries")

def run_clean_verify_and_split_after_purge():
    """
    Option 4: verify + polygon split.
    This merged version:
      - deletes Option-4 output files (CSV/logs) if present
      - deletes the suburb output folder if present
      - then runs process_csv + polygon split
    """
    # 1) Delete option outputs (output_clean/output_fail/logs/splits) if user agrees
    if not ensure_delete_option_outputs_interactive("4"):
        return

    # 2) Also delete suburb split dir if present (user prompt)
    if not ensure_delete_suburb_dir_interactive():
        return

    try:
        if 'log_correction' in globals():
            log_correction("Session Start", "Corrections log recreated after deletion or fresh start.")
    except Exception:
        pass

    process_csv(
        "input_nws.csv",
        "output_clean.csv",
        "output_fail.csv",
        expected_headers=EXPECTED_HEADERS,
        verify_geocode=True
    )
    split_cleaned_by_polygon_and_include_failed("output_clean.csv", "output_fail.csv", kml_dir="KML Boundaries")



import shutil, os

def ensure_delete_suburb_dir_interactive() -> bool:
    out_dir = "New_Addresses_By_Suburb"
    if not os.path.exists(out_dir):
        return True
    print(f"⚠️ Folder '{out_dir}' already exists. It will be DELETED.")
    confirm = input("Type 'y' to remove it and continue (anything else to cancel): ").strip().lower()
    if confirm != "y":
        print("❌ Cancelled — Folder was not deleted.")
        return False
    try:
        shutil.rmtree(out_dir)
        print("✅ Folder removed.")
        return True
    except Exception as e:
        print(f"❌ Could not remove '{out_dir}': {e}")
        return False


EXPECTED_HEADERS = ["Number","Street","Suburb","PostalCode","Status","Latitude","Longitude"]



def open_menu():
    actions = {
        "1": lambda: run_clean_normal_after_purge(EXPECTED_HEADERS),
        "2": lambda: run_clean_verify_after_purge(EXPECTED_HEADERS),
        "3": run_clean_and_split_after_purge,
        "4": run_clean_verify_and_split_after_purge,
        "5": lambda: run_clean_live_after_purge(EXPECTED_HEADERS),
        "6": lambda: run_clean_verify_live_after_purge(EXPECTED_HEADERS),
        "7": run_clean_verify_and_split_newstreets_after_purge,  # ← NEW
        "0": lambda: None,
    }

    while True:
        print("\n\033[4mNew World Scheduler (input_nws)\033[0m")
        print("1 - ✨ Run CSV File Cleaning")
        print("2 - ✨ Run CSV File Cleaning (Full Geocode Check)")
        print("3 - ✨ Clean & Split Into Different Suburbs")
        print("4 - ✨ Clean & Split Into Different Suburbs (Full Geocode Check)")
        print("5 - ✨ Run CSV File Cleaning (Live Updating)")
        print("6 - ✨ Run CSV File Cleaning (Live Updating + Full Geocode Check)")
        print("7 - ✨ Clean & Split Into Different Suburbs (New Streets - Full Geocode Check)")
        print("\n0 - Back/Exit")

        pick = input("\nChoose (0/1/2/3/4/5/6/7): ").strip()

        if pick not in actions:
            print("❌ Invalid choice.\n")
            continue

        if pick == "0":
            break

        actions[pick]()  # run the selected action




if __name__ == "__main__":
    try:
        open_menu()
    except KeyboardInterrupt:
        print("\n👋 Exiting...")



# Part 4/4 End of script
