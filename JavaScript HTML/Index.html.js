<!DOCTYPE html>
<html>
<head>
  <base target="_top">
  <meta charset="utf-8" />
  <!--
    Page <title> is templated from Apps Script (or falls back).
    Keeps the UI generic if appTitle is not provided.
  -->
  <title><?!= (typeof appTitle !== 'undefined' ? appTitle : 'Address Tool') ?></title>

  <!--
    Responsive / cache-control metas.
    - Viewport locks scaling for a mobile-first UI.
    - Cache headers reduce stale asset issues on GAS deployments.
  -->
  <meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no" />
  <meta http-equiv="Cache-Control" content="no-cache, no-store, max-age=0, must-revalidate">
  <meta http-equiv="Pragma" content="no-cache">
  <meta http-equiv="Expires" content="0">

  <!--
    =========================
    ========== CSS ==========
    =========================
    Design goals:
    - Clean, readable default system UI font stack
    - Lightweight, card-based layout
    - Accessible focus states
    - Touch-friendly tap targets
  -->
  <style>
    :root { --gap:12px; --pad:14px; --radius:14px; }
    * { box-sizing: border-box; font-family: system-ui,-apple-system,Segoe UI,Roboto,Arial; }
    body { margin:0; background:#f7f7fb; color:#111; }

    /* Header + title bar */
    header { padding:20px 0 8px; background:#fff; border-bottom:1px solid #eee; text-align:center; }
    h1 { margin:0 auto; max-width:760px; padding:0 16px; font-size:22px; }

    /* Title */
    h1 .title-text {
    font-size: clamp(18px, 2.2vw, 24px);  /* 18 → 24px */
    }

    /* Base: small on mobile */
    .subtitle-tip {
      margin: 6px auto 0;
      max-width: 760px;
      padding: 0 16px;
      text-align: center;
      font-weight: 800;
      font-size: clamp(5px, 1vw, 8px);
      line-height: 1.3;
      color: #111;
    }

    /* Desktop/laptop only: fine pointer + hover present */
    @media (min-width: 992px) and (hover: hover) and (pointer: fine) {
      .subtitle-tip { font-size: 11px; }
    }
    @media (min-width: 1200px) and (hover: hover) and (pointer: fine) {
      .subtitle-tip { font-size: 12px; }
    }








    /* Inline spinner — force wine red everywhere */
    .spinner {
      display: inline-block;
      width: 16px;
      height: 16px;
      border: 2px solid #7B1E3F;   /* wine red */
      border-right-color: transparent;
      border-top-color: transparent;
      border-radius: 50%;
      vertical-align: -2px;
      margin-left: 8px;
      animation: spin 0.75s linear infinite;
    }

    @keyframes spin {
      from { transform: rotate(0deg); }
      to   { transform: rotate(360deg); }
    }

    /* Optional: old WebKit/iOS Safari */
    @-webkit-keyframes spin {
      from { -webkit-transform: rotate(0deg); }
      to   { -webkit-transform: rotate(360deg); }
    }

    /* Optional: respect reduced motion */
    @media (prefers-reduced-motion: reduce) {
      .spinner { animation: none; }
    }


    /* Page layout + form card */
    main { max-width:760px; margin:18px auto 64px; padding:0 16px; }
    form { background:#fff; border:1px solid #eee; border-radius:var(--radius); padding:18px; box-shadow:0 2px 10px rgba(0,0,0,.03); }

    /* Uniform row layout: [X] [Label] [Field] */
    .row { 
      display:grid; 
      /* CHANGED: more compact columns + smaller gaps */
      grid-template-columns: 56px 120px minmax(0, 1fr); /* was 64px 120px ... */
      gap:6px; /* was 10px */
      align-items:center; 
      margin-bottom:10px; 
    }
    /* extra gap so X buttons never visually touch labels */
    .row > .btn-clear { margin-right: 6px; }

    /* Left-align labels (updated) */
    label {
      font-weight:700; font-size:14px; line-height:1.2;
      text-align:left;
      pointer-events:none;
      display:flex; align-items:center;
      justify-content:flex-start;
      height:100%;
    }

    /* Inputs + focus ring for accessibility */
    input, select, button, .combo-input { width:100%; padding:var(--pad); border:1px solid #ddd; border-radius:12px; font-size:16px; background:#fff; }
    input:focus, select:focus, .combo-input:focus { outline:2px solid #6ea8fe; border-color:#6ea8fe; }
    select, select option { color:#111; }

    /* Field container (input area) */
    .field-wrap { display:grid; grid-template-columns: 1fr; align-items:center; gap:12px; }
    .field-wrap .grow { min-width:0; }
    /* Street row: GPS + input */
    .field-wrap--street {
      /* CHANGED: move GPS + input further left by shrinking GPS col + gap */
      grid-template-columns: 56px 1fr; /* was 64px 1fr */
      column-gap:6px; /* was 10px */
    }

    /* ===========================
       Classic Flat Color Buttons
       =========================== */
    .btn {
      font-weight:600;
      border:none;
      padding:12px 16px;
      border-radius:12px;
      text-decoration:none;
      display:inline-block;
      line-height:1;
      cursor:pointer;
      background:#3498db;     /* default (not used directly; color classes override) */
      color:#fff;
      /* CHANGED: slower revert */
      transition: background 0.35s ease, color 0.35s ease, opacity 0.35s ease;
    }
    /* BLACK family (Type, A/B, Language, Notes, Submit, New Addresses) */
    .btn-black,
    .btn-green { background:#000; color:#fff; }
    /* CHANGED: much lighter on press for black-family */
    .btn-black:active,
    .btn-green:active { background:#555; } /* was #333 */

    /* RED→WINE family (Unit, Number, Street X; Clear All; GPS; red X buttons) */
    .btn-red { background:#7B1E3F; color:#fff; }             /* dark wine */
    .btn-red:active { background:#9A2D55; }                  /* lighter wine on press */

    .btn[disabled] { opacity:.6; }
    /* CHANGED: width tightened to match new first column */
    .btn-clear { padding:12px 0; width:56px; text-align:center; color:#fff !important; } /* X buttons: white text */

    /* flash helpers (kept, but no longer used on X buttons) */
    .flash-green { background:#16a34a !important; color:#fff !important; opacity:1 !important; }
    .flash-black { background:#000 !important; color:#fff !important; opacity:1 !important; }
    .flash-lightgreen { background:#86efac !important; color:#064e3b !important; opacity:1 !important; }
    .flash-grey { background:#6b7280 !important; color:#fff !important; opacity:1 !important; }
    .flash-text-black { color:#000 !important; }
    .flash-text-red { color:#7B1E3F !important; }            /* wine text accent */
    .flash-to-red { background:#7B1E3F !important; color:#fff !important; } /* wine flash */

    /* NEW: subtle fades (retained but not required for flat style) */
    .fade-lite-red   { background:#B04C6E !important; }      /* lighter wine for Clear All press */
    .fade-lite-black { background:#333 !important; }         /* lighter black for Submit press */

    /* Non-interactive title badge (visual only) */
    .btn-title {
      padding:12px 18px; font-size:inherit; display:block; width:100%;
      text-align:center; color:#fff; /* title text */
      cursor:default; border-radius:12px;
      background:#7B1E3F; /* wine title pill (was #d92d20) */
      pointer-events: none;
    }
    .not-clickable { pointer-events:none; }

    /* Submit/Clear action row */
    .actions {
      display:flex; align-items:center; justify-content:space-between; gap:8px;
      margin-top:8px;
    }
    .actions .btn { padding:16px 20px; font-size:18px; }
    button[type=submit] { background:#000 !important; color:#fff; border:none; }
    button[type=submit]:active { background:#555 !important; } /* CHANGED: match lighter press */

    /* inline status text (stacked, oldest → newest) */
    .searching-msg{
      min-width:150px;
      min-height:24px;            /* will expand as lines stack */
      text-align:center;
      font-weight:700;
      margin:8px 0 20px;
      display:flex;
      flex-direction:column;       /* ← stack vertically */
      align-items:center;          /* center each row’s content */
      justify-content:flex-start;  /* start at the top */
      row-gap:4px;                 /* space between lines */
    }

    /* each status line */
    .searching-msg > div{
      display:flex;                /* keep label + spinner on one line */
      align-items:center;
      justify-content:center;
      width:100%;
    }

    
    align-items:center; justify-content:center; }

    /* Inline status region (ARIA live) */
    .status { margin-top:10px; font-size:14px; }
    .status.ok { color:#0a7b3e; }
    .status.err { color:#b00020; }


    /* Preview pane for human-readable address string and coords */
    .preview { margin-top:16px; background:#fafafa; border:1px solid #eee; border-radius:12px; padding:12px; }
    .steps { font-size:14px; line-height:1.6; white-space:pre-line; text-align:center; font-family: inherit; }
    .preview .steps + .steps { margin-top:8px; }

    /* Combo-box (typeahead) menus */
    .combo { position:relative; }
    .combo-menu{
      position:absolute; top:calc(100% + 4px); left:0; right:0;
      background:#fff; border:1px solid #ddd; border-radius:12px;
      max-height:420px; overflow:auto; z-index:9999;
      box-shadow:0 8px 20px rgba(0,0,0,.08); display:none;
      -webkit-overflow-scrolling: touch; touch-action: pan-y;
      overscroll-behavior: contain;
    }
    .combo-item { padding:14px 16px; cursor:pointer; user-select:none; -webkit-tap-highlight-color: transparent; }
    .combo-item:hover, .combo-item.active { background:#f2f6ff; }
    .combo-item mark { background:#ffef99; border-radius:4px; padding:0; }

    /* Links to external data views (e.g., sheet) */
    .viewlink { margin-top:48px; text-align:center; }
    .viewlink h3 { margin:0 0 8px; font-size:16px; }
    .viewlink > div { margin-top:14px; }

    /* Utility/Accessibility helpers */
    .sr-only { position:absolute!important; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
    .hidden { display:none !important; }

    /* Toast notification (bottom center) */
    .toast {
      position: fixed; left: 50%; bottom: 24px; transform: translateX(-50%);
      background:#111; color:#fff; padding:12px 16px; border-radius:12px;
      box-shadow:0 10px 30px rgba(0,0,0,.25); z-index: 20000; font-size:14px; display:none; font-weight:600;
      pointer-events: none;
    }
    .toast.ok { background:#1f7a46; }
    .toast.err { background:#b00020; }


    /* --- GPS button --- */
    /* Always wine (idle and busy), flat press to lighter wine */
    #gpsBtn { background:#7B1E3F !important; color:#fff !important; width:56px; padding:12px 0; } /* CHANGED: width 56px */
    #gpsBtn.is-busy { background:#7B1E3F !important; color:#fff !important; }
    #gpsBtn:active { background:#9A2D55 !important; } /* lighter on press */
    #gpsBtn.is-busy[disabled] { opacity:1 !important; }

    /* short-lived shield to prevent click-through after menu selection */
    #tapShield {
      position: fixed; inset: 0; background: transparent; z-index: 20001; display: none; pointer-events: auto;
    }

    /* pressed state for "New Addresses" link — wine pressed */
    .is-pressed { background:#9A2D55 !important; color:#fff !important; opacity:1 !important; }

    /* Optional: catch any lingering inline reds, swap to wine */
    *[style*="#d92d20"] { background:#7B1E3F !important; color:#fff !important; }
    *[style*="#f08a80"] { background:#9A2D55 !important; color:#fff !important; }
    *[style*="#ef5a50"] { background:#B04C6E !important; color:#fff !important; }
  </style>
</head>
<body>
  <!--
    ============================
    ========== HEADER ==========
    ============================
    Title bar with a “pill” visual.
  -->
  <header>
    <h1>
      <div class="btn btn-red btn-title not-clickable">
        <span class="title-text"><?!= (typeof appTitle !== 'undefined' ? appTitle : 'Address Tool') ?></span>
      </div>
    </h1>
    <!-- Tip lines under the main title -->
    <div class="subtitle-tip">Add / Update Addresses</div>
    <div class="subtitle-tip">Enable Location Services for GPS</div>
  </header>


  <!--
    ===========================
    ========== MAIN ===========
    ===========================
    The core address entry form.
  -->
  <main>
    <form id="addrForm" autocomplete="off">
      <!-- Type selector -->
      <div class="row">
        <!-- ensure X button colors per spec -->
        <button type="button" id="clearType" class="btn btn-black btn-clear" aria-label="Clear Type">X</button>
        <label for="Type">Type</label>
        <div class="field-wrap">
          <select id="Type" class="grow" aria-label="Type"></select>
        </div>
      </div>

      <!-- Apartment/Business free text with suggestions -->
      <div class="row">
        <button type="button" id="clearApartmentBusiness" class="btn btn-black btn-clear" aria-label="Clear Apartment or Business">X</button>
        <label for="ApartmentBusiness">Apartment/<br>Business</label>
        <div class="field-wrap">
          <div class="combo grow">
            <input id="ApartmentBusiness" class="combo-input" placeholder="eg. Shop 10" aria-autocomplete="list" />
            <div id="ApartmentBusinessMenu" class="combo-menu" role="listbox"></div>
          </div>
        </div>
      </div>

      <!-- Unit field with suggestions -->
      <div class="row">
        <button type="button" id="clearUnit" class="btn btn-red btn-clear" aria-label="Clear Unit">X</button>
        <label for="Unit">Unit</label>
        <div class="field-wrap">
          <div class="combo grow">
            <input id="Unit" class="combo-input" placeholder="eg. A, B" aria-autocomplete="list" />
            <div id="UnitMenu" class="combo-menu" role="listbox"></div>
          </div>
        </div>
      </div>

      <!-- House Number numeric-only input with typeahead values -->
      <div class="row">
        <button type="button" id="clearNumber" class="btn btn-red btn-clear" aria-label="Clear Number">X</button>
        <label for="HouseNumber">Number</label>
        <div class="field-wrap">
          <div class="combo grow">
            <input
              id="HouseNumber"
              class="combo-input"
              inputmode="numeric"
              pattern="[0-9]*"
              autocomplete="off"
              autocapitalize="off"
              autocorrect="off"
              spellcheck="false"
              enterkeyhint="next"
              placeholder="eg. 1, 10"
              aria-autocomplete="list"
            />
            <div id="HouseNumberMenu" class="combo-menu" role="listbox"></div>
          </div>
        </div>
      </div>

      <!-- Street search + GPS button -->
      <div class="row">
        <button type="button" id="clearStreet" class="btn btn-red btn-clear" aria-label="Clear Street">X</button>
        <label for="Street">Street</label>
        <div class="field-wrap field-wrap--street">
          <button type="button" id="gpsBtn" class="btn">GPS</button>
          <div class="combo grow">
            <input
              id="Street"
              class="combo-input"
              inputmode="search"
              enterkeyhint="next"
              autocomplete="off"
              autocapitalize="off"
              autocorrect="off"
              spellcheck="false"
              placeholder="Search Address Here..."
              aria-autocomplete="list"
            />
            <div id="StreetMenu" class="combo-menu" role="listbox"></div>
          </div>
        </div>
      </div>

      <!-- Optional language notes -->
      <div class="row">
        <button type="button" id="clearLanguage" class="btn btn-black btn-clear" aria-label="Clear Language">X</button>
        <label for="Language">Language</label>
        <div class="field-wrap">
          <div class="combo grow">
            <input id="Language" class="combo-input" placeholder="eg. Cantonese" aria-autocomplete="list" />
            <div id="LanguageMenu" class="combo-menu" role="listbox"></div>
          </div>
        </div>
      </div>

      <!-- General Notes -->
      <div class="row">
        <button type="button" id="clearNotes" class="btn btn-black btn-clear" aria-label="Clear Notes">X</button>
        <label for="Notes">Notes</label>
        <div class="field-wrap">
          <div class="combo grow">
            <input id="Notes" class="combo-input" placeholder='eg. Check if Chinese, Panda Restaurant' aria-autocomplete="list" />
            <div id="NotesMenu" class="combo-menu" role="listbox"></div>
          </div>
        </div>
      </div>

      <!-- Map (conditional; shows only when Notes contains "wrong" or "updated") -->
      <div class="row hidden" id="rowMap">
        <button type="button" id="clearMap" class="btn btn-black btn-clear" aria-label="Clear Map">X</button>
        <label for="MapChoice">Map</label>
        <div class="field-wrap">
          <div class="combo grow">
            <input id="MapChoice" class="combo-input" placeholder="Select your current map" aria-autocomplete="list" />
            <div id="MapMenu" class="combo-menu" role="listbox"></div>
          </div>
        </div>
      </div>




      <!-- Inline status (Searching… / Saving…) ABOVE the buttons -->
      <div id="gpsSearchingMsg" class="searching-msg" aria-live="polite"></div>

      <!-- Form action buttons -->
      <div class="actions">
        <button type="button" id="clearBtn" class="btn btn-red">Clear All</button>
        <button type="submit" id="submitBtn" class="btn btn-green">Submit</button>
      </div>

      <!-- Live status and previews -->
      <div id="status" class="status" aria-live="polite"></div>
      <div class="preview">
        <div id="steps" class="steps"></div>
        <div id="coordsLine" class="steps"></div>
      </div>

      <!-- Hidden fields (populated from geocoding) -->
      <input type="hidden" id="Longitude" name="Longitude" />
      <input type="hidden" id="Latitude"  name="Latitude" />
    </form>

    <!-- Global save overlay + toast -->
    
    <div id="toast" class="toast" role="status" aria-live="polite"></div>

    <!-- Direct link to where submitted addresses are stored (Google Sheet) -->
    <div class="viewlink">
      <h3>You Can View Submitted Addresses Here:</h3>
      <div>
        <a
          id="newAddressBtn"
          class="btn btn-green"
          target="_blank"
          href="https://docs.google.com/spreadsheets/d/1gfo_jQeIuQozxcgTuraUpU1AYvKAhD1WkDqfQooKdsk/edit?usp=sharing"
        >
          New Addresses
        </a>
      </div>
    </div>
  </main>

  <!-- anti click-through shield -->
  <div id="tapShield"></div>

  <!--

==================================
    ========== APPLICATION JS =========
    ==================================
    Heavily commented for clarity. No behavior changed—only explanations added.
  -->
  <script>
  /* ========= Crash guard ========= */
  window.addEventListener('error', function (e) {
    if (!e || e.isTrusted === false) return;
    try {
      var msg = (e && e.error && e.error.message) || (e && e.message) || String(e);
      console.error('Script error:', (e && e.error) || e);
      if (location.hostname === 'script.google.com') alert('Script error: ' + msg);
    } catch(_) {}
  });

  /* ========= Safe Number alias ========= */
  const JSNumber = (typeof window !== 'undefined' &&
                   typeof window.Number === 'function' &&
                   window.Number.name === 'Number')
      ? window.Number
      : (1).constructor;

  /* === Geocoding performance caps (Options 1 & 2) === */
  const GEO_COORDS_FRESH_MS       = 120000; // 2 minutes: coords considered "fresh"
  const GEO_SUBMIT_GEOCODE_CAP_MS = 1500;   // max extra geocode time allowed on submit
  const GEO_NEARBY_BUDGET_MS      = 1500;   // total budget for nearby-number probes

  /* tiny helper */
  const wait = (ms) => new Promise(r => setTimeout(r, ms));
  const withBudget = (p, ms) => Promise.race([ p, wait(ms).then(() => null) ]);
 

  /* ========= Build an auto-bumping session cache key ========= */
  const BUILD_TAG  = <?!= JSON.stringify(typeof buildTag  !== "undefined" ? buildTag  : "v0") ?>;
  const WEBAPP_URL = <?!= JSON.stringify(typeof webAppUrl !== "undefined" ? webAppUrl : "") ?>;
  const DEPLOY_TAG  = (() => {
    try {
      if (!WEBAPP_URL) return 'local';
      if (/\/dev(\?|$)/.test(WEBAPP_URL)) return 'dev';
      const m = WEBAPP_URL.match(/\/s\/([^/]+)/);
      return m ? m[1].slice(-6) : 'unk';
    } catch(_) { return 'unk'; }
  })();
  const SESSION_CACHE_KEY = `lookups_${BUILD_TAG}_${DEPLOY_TAG}`;
  window.SESSION_CACHE_KEY = SESSION_CACHE_KEY; 

  /* ========= Small helpers / UI status ========= */
  const $ = s => document.querySelector(s);
  function safeNormalize(str){ try { return String(str||'').normalize('NFD'); } catch(_) { return String(str||''); } }
  const deD = s => safeNormalize(s).replace(/[\u0300-\u036f]/g,'').toLowerCase();

  // Only show coord status when both Street & Number are present
  function hasStreetAndNumber() {
  return !!(getInputTrimmed('HouseNumber') && getInputTrimmed('Street'));
  }


  function showStatus(msg, ok=false){
    const el = document.getElementById('status');
    if(!el) return;
    el.textContent = msg || '';
    el.className = 'status ' + (ok ? 'ok' : 'err');
  }
  function toast(msg, { type='', ms=2200 } = {}) {
    var el = document.getElementById('toast'); if (!el) return;
    el.className = 'toast ' + (type||'');
    el.textContent = msg || '';
    el.style.display = 'block';
    clearTimeout(el._t);
    el._t = setTimeout(function(){ el.style.display='none'; }, ms);
  }
  function hideToastNow(){
    var el = document.getElementById('toast'); if (!el) return;
    el.style.display = 'none';
    if (el._t) { clearTimeout(el._t); el._t = null; }
  }

  function searchingMsgHTML() {
  return 'Acquiring GPS Location <span class="spinner" aria-hidden="true"></span>';
  }

  function savingMsgHTML() {
  return 'Saving Address <span class="spinner" aria-hidden="true"></span>';
  }

  function submittingMsgHTML() {
  return 'Submitting <span class="spinner" aria-hidden="true"></span>';
  }

  function showSaving() {
  /* overlay disabled */
  }

/* ===============================
   Stacked inline status system
   =============================== */
const COORDS_MSG = 'Acquiring GPS Coordinates';

// Oldest → newest; { id, label, spinner, ts, ttlMs? }
let STATUS_STACK = [];

const _now = () => Date.now();
const _keyFromLabel = (s) => String(s || '').trim().toLowerCase().replace(/\s+/g, '_');

function renderStatusStack() {
  const el = document.getElementById('gpsSearchingMsg');
  if (!el) return;
  if (!STATUS_STACK.length) { el.textContent = ''; return; }
  STATUS_STACK.sort((a, b) => a.ts - b.ts);
  el.innerHTML = STATUS_STACK.map(s => {
    const spin = s.spinner ? ' <span class="spinner" aria-hidden="true"></span>' : '';
    return `<div>${s.label}${spin}</div>`;
  }).join('');
}

function pushStatus(id, label, { spinner = true, dedupe = true, ttlMs = null } = {}) {
  id = id || _keyFromLabel(label);
  const exists = dedupe ? STATUS_STACK.find(s => s.id === id) : null;

  if (exists) {
    exists.label = label;
    exists.spinner = !!spinner;
    if (ttlMs) { removeStatus(id, { noRender: true }); STATUS_STACK.push({ id, label, spinner: !!spinner, ts: exists.ts, ttlMs }); }
  } else {
    STATUS_STACK.push({ id, label, spinner: !!spinner, ts: _now(), ttlMs });
  }
  renderStatusStack();
  if (ttlMs) setTimeout(() => removeStatus(id), ttlMs);
}

function removeStatus(id, { noRender = false } = {}) {
  const i = STATUS_STACK.findIndex(s => s.id === id);
  if (i >= 0) { STATUS_STACK.splice(i, 1); if (!noRender) renderStatusStack(); }
}

function clearAllStatuses() { STATUS_STACK = []; renderStatusStack(); }

// ==== Shims to preserve your existing function names ====
function startGettingCoords() { pushStatus('coords', COORDS_MSG, { spinner: true }); }
function stopGettingCoords()  { removeStatus('coords'); }
function isGettingCoords()    { return !!STATUS_STACK.find(s => s.id === 'coords'); }

function setSecondaryStatus(label /* , opts */) {
  const id = _keyFromLabel(label);
  pushStatus(id, label, { spinner: true });
}

function clearSecondaryStatus() {
  STATUS_STACK = STATUS_STACK.filter(s => s.id === 'coords');
  renderStatusStack();
}

function coordsAvailable() {
  return !!(LAST_COORDS && Number.isFinite(LAST_COORDS.lon) && Number.isFinite(LAST_COORDS.lat));
}

function ensureAcquiringBanner() {
  if (hasStreetAndNumber() && !coordsAvailable() && !STATUS_STACK.find(s => s.id === 'coords')) {
    pushStatus('coords', COORDS_MSG, { spinner: true });
  }
}




function buildAddrKey(number, streetInput){
  const num = String(number||'').trim();
  const parts = splitStreetSuburb(streetInput);
  const s = __normalizeStreet__(parts.street);
  const sub = deD(parts.suburb);
  return `${num}|${s}|${sub}`;
}

let isSubmitting = false;
let LAST_COORDS = null;
let FORM_SUBMIT_BOUND = false;
let STATIC_HANDLERS_BOUND = false;

let GEOCODE_REQ_SEQ = 0;          // incremented per geocode attempt
let LAST_GEOCODE_START_KEY = null;
let CONFIRMED_ADDR_KEY = null;


/* Locks */
let CONFIRM_SUMMARY_LOCK = false;
let THANKYOU_PROMPT_LOCK = false;
function resetSubmitLocks() {
  CONFIRM_SUMMARY_LOCK = false;
  THANKYOU_PROMPT_LOCK = false;
}



  /* ===== One-popup guard (prevents stacked native dialogs) ===== */
  let POPUP_LOCK = false;
  function confirmGuarded(message) {
    if (POPUP_LOCK) return false;
    POPUP_LOCK = true;
    try {
      return window.confirm(message);
    } finally {
      POPUP_LOCK = false;
    }
  }



  /* ===== Suggestion suppression window (GPS fill → pause menus for N ms) ===== */
  let SUPPRESS_SUGGESTIONS_UNTIL = 0;
  function isSuggestionSuppressed(){ return Date.now() < SUPPRESS_SUGGESTIONS_UNTIL; }
  function suppressSuggestionsFor(ms){
    ms = JSNumber.isFinite(ms) ? ms : 2000;
    SUPPRESS_SUGGESTIONS_UNTIL = Date.now() + ms;

    // Keep menus fully locked during the suppression window
    MENUS_LOCKED = true;
    clearTimeout(MENUS_LOCK_TIMER);
    try { lockMenusAfterGPS(); closeAllMenus(); } catch (_){}

    MENUS_LOCK_TIMER = setTimeout(function(){
      MENUS_LOCKED = false;
      try { unlockMenusAll(); } catch (_){}
    }, ms);
  }

  // NEW: strong suppression flag — blocks menus until the user types again
  let SUPPRESS_UNTIL_USER_TYPES = false;

  /* ========= Draft helpers ========= */
  function getInputTrimmed(id) {
    var el = document.getElementById(id);
    return (el && typeof el.value === 'string') ? el.value.trim() : '';
  }
  function collect() {
    return {
      Type: getInputTrimmed('Type'),
      ApartmentBusiness: getInputTrimmed('ApartmentBusiness'),
      Unit: getInputTrimmed('Unit'),
      Number: getInputTrimmed('HouseNumber'), // still named "Number" in the payload
      Street: getInputTrimmed('Street'),
      Language: getInputTrimmed('Language'),
      Notes: getInputTrimmed('Notes'),
      Map: getInputTrimmed('MapChoice')  // <-- NEW
    };
  }
  function formatAddress(d) {
    const ab = d.ApartmentBusiness ? d.ApartmentBusiness + ', ' : '';
    const unit = d.Unit ? `Unit ${d.Unit}, ` : '';
    const numStreet = (d.Number ? d.Number + ' ' : '') + (d.Street || '');
    return (ab + unit + numStreet).trim();
  }
  function updatePreview(){ const el=$('#steps'); if(el) el.textContent = formatAddress(collect()); }
  function setSubmitEnabled(on){ const s=$('#submitBtn'), c=$('#clearBtn'); if(s) s.disabled=!on; if(c) c.disabled=!on; }

  // Save draft to localStorage (with compatibility key)
  function persistDraft(){
    try {
      const d = collect();
      // --- write both keys for compatibility ---
      d.HouseNumber = d.Number;
      localStorage.setItem('addr_draft', JSON.stringify(d));
    } catch {}
  }

  // Restore draft (with migration for old key)
  function restoreDraft(){
    try {
      const d = JSON.parse(localStorage.getItem('addr_draft') || '{}');

      // --- MIGRATION for old drafts ---
      if (d && typeof d.Number === 'string' && !d.HouseNumber) {
        const el = document.getElementById('HouseNumber');
        if (el) el.value = d.Number;
      }

      // --- Existing draft restore loop ---
      for (const k in d) {
        if (!Object.prototype.hasOwnProperty.call(d, k)) continue;
        const id = (k === 'Number') ? 'HouseNumber' : (k === 'Map' ? 'MapChoice' : k);

        const el = document.getElementById(id);
        if (el) el.value = d[k] || '';
      }
    } catch {}
  }

  /* ========= Menus & Coordinates helpers ========= */
  function closeAllMenus(){ document.querySelectorAll('.combo-menu').forEach(m=>{ m.style.display='none'; m.removeAttribute('data-open'); }); }

  function updateCoordsPreview(){
    const el = document.getElementById('coordsLine');
    if (!el) return;
    if (LAST_COORDS && JSNumber.isFinite(LAST_COORDS.lon) && JSNumber.isFinite(LAST_COORDS.lat)) {
      el.textContent = `Longitude: ${(+LAST_COORDS.lon).toFixed(6)}\nLatitude: ${(+LAST_COORDS.lat).toFixed(6)}`;
    } else el.textContent = '';
  }
  function setCoords(lon, lat){
    LAST_COORDS = { lon: JSNumber(lon), lat: JSNumber(lat), _ts: Date.now() };
    const lonEl = document.getElementById('Longitude');
    const latEl = document.getElementById('Latitude');
    if (lonEl) lonEl.value = JSNumber.isFinite(LAST_COORDS.lon) ? String(LAST_COORDS.lon) : '';
    if (latEl) latEl.value = JSNumber.isFinite(LAST_COORDS.lat) ? String(LAST_COORDS.lat) : '';
    updateCoordsPreview();
  }

  function clearCoords(){
    LAST_COORDS=null; updateCoordsPreview();
    const lonEl = document.getElementById('Longitude');
    const latEl = document.getElementById('Latitude');
    if (lonEl) lonEl.value = '';
    if (latEl) latEl.value = '';
  }

  /* ========= Field clears ========= */
  function clearField(id) {
    const el = document.getElementById(id);
    if (!el) return;
    if (el.tagName === 'SELECT') {
      el.value = '';
      if (el.value !== '') el.selectedIndex = 0;
    } else {
      el.value = '';
    }
    if (id === 'Street' || id === 'HouseNumber') stopGettingCoords();

    if (id === 'Street' || id === 'HouseNumber' || id === 'Unit') {
      var t = document.getElementById(id);
      if (t) { t.removeAttribute('data-suppress-open'); t.removeAttribute('data-gps-locked'); }
    }
    closeAllMenus();
    updatePreview();
    persistDraft();
    scheduleRestoreCombos(1000);
    triggerGeocodeForCurrent();

    // NEW: if Notes was cleared via the X button (or any programmatic clear), hide Map row
    if (id === 'Notes') toggleMapField();
  }

  function allFieldsEmpty(){
  const ids = ['Type','ApartmentBusiness','Unit','HouseNumber','Street','Language','Notes','MapChoice'];

  for (const id of ids) {
    const el = document.getElementById(id);
    if (el && String(el.value || '').trim()) return false;
  }
  return true;
}



function clearAllConfirmed() {
  // no prompt if everything is empty
  if (!allFieldsEmpty()) {
    if (!confirmGuarded('Clear all fields?')) return;
  }
  const form = document.getElementById('addrForm');
  if (form) form.reset();

  // clear any stale locks/flags on all combo inputs (incl. Map)
  MENU_IDS.forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.removeAttribute('data-suppress-open');
      el.removeAttribute('data-gps-locked');
    }
  });

  closeAllMenus();
  updatePreview();
  showStatus('');
  try { localStorage.removeItem('addr_draft'); } catch {}
  clearCoords();

  // ensure Map row hides after Notes is cleared by form.reset()
  toggleMapField();

  scheduleRestoreCombos(1000);
}




  /* ========= Combo widget (typeahead) ========= */
  const OPEN_MENUS = new Set();
  const COMBOS = new Map();

  // NEW: single source of truth for all menu’d fields
  const MENU_IDS = ['Street','HouseNumber','Unit','ApartmentBusiness','Language','Notes','MapChoice'];


  // Prevent menus from opening while GPS flow is running, etc.
  let MENUS_LOCKED = false;
  let MENUS_LOCK_TIMER = null;

  // Global safety: any user **pointer** action clears menu locks/flags — keyboard typing should NOT close menus
(function () {
  const unlock = (ev) => {
    // ignore keyboard events to prevent random menu closing while typing
    if (ev && (ev.type === 'keydown' || ev.type === 'keyup')) return;

    try { MENUS_LOCKED = false; clearTimeout(MENUS_LOCK_TIMER); } catch (_) {}
    try {
      MENU_IDS.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
          el.removeAttribute('data-suppress-open');
          el.removeAttribute('data-gps-locked');
        }
      });

      const t = ev && ev.target;
      const insideCombo = t && t.closest && t.closest('.combo');
      const insideClickish = ev && ['click','touchstart','pointerdown','pointerup'].includes(ev.type);
      if (!(insideCombo && insideClickish)) {
        // Only close on pointer/click outside combos; never for keyboard
        if (insideClickish) {
          document.querySelectorAll('.combo-menu').forEach(m => {
            m.style.display='none'; m.removeAttribute('data-open');
          });
        }
      }
    } catch (_) {}
  };

  ['pointerdown','pointerup','click','touchstart'].forEach(evt => {
    window.addEventListener(evt, unlock, { capture: true, passive: true });
  });

  window.addEventListener('load', () => setTimeout(unlock, 0));
  document.addEventListener('visibilitychange', () => { if (!document.hidden) unlock({type:'visibility'}); });
})();


  // ESC always closes menus and clears any stale lock
  document.addEventListener('keydown', function(e){
  if (e.key === 'Escape') {
    MENUS_LOCKED = false;
    clearTimeout(MENUS_LOCK_TIMER);
    document.querySelectorAll('.combo-menu').forEach(m => { m.style.display='none'; m.removeAttribute('data-open'); });
    MENU_IDS.forEach(id => {
      const el = document.getElementById(id);
      if (el){ el.removeAttribute('data-suppress-open'); el.removeAttribute('data-gps-locked'); }
    });
  }
});


  // Debouncer utility + highlighter used by combo lists
  function debounce(fn, ms=120){ let t; const w=(...a)=>{ clearTimeout(t); t=setTimeout(()=>fn.apply(null,a), ms); }; w.cancel=function(){ clearTimeout(t); }; return w; }
  function renderHighlighted(text, query) {
    const esc = (s)=>s.replace(/[&<>"']/g, m=>({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[m]));
    const q = deD(query).trim(); if (!q) return esc(text);
    const normText = deD(text); const idx = normText.indexOf(q); if (idx < 0) return esc(text);
    return `${esc(text.slice(0,idx))}<mark>${esc(text.slice(idx,idx+q.length))}</mark>${esc(text.slice(idx+q.length))}`;
  }

  // short-lived shield to block click-through after menu selection
  function showTapShield(ms){
    var sh = document.getElementById('tapShield'); if (!sh) return;
    sh.style.display = 'block';
    clearTimeout(sh._t);
    sh._t = setTimeout(function(){ sh.style.display='none'; }, JSNumber.isFinite(ms)?ms:300);
  }

  // Core combobox wiring: filter/render/select with keyboard support
  function makeCombo(inputEl, menuEl, getItems, opts = {}) {
    if (!inputEl || !menuEl) return { close:function(){}, openAndHighlight:function(){} };
    const key = inputEl.id || menuEl.id;
    if (key && COMBOS.has(key)) return COMBOS.get(key);

    const maxItems = JSNumber.isFinite(opts.maxItems) ? opts.maxItems : 100;
    const matcher  = (typeof opts.matcher === 'function') ? opts.matcher : null;
    const minChars = JSNumber.isFinite(opts.minChars) ? opts.minChars : 0;
    const openOnFocus = (opts.openOnFocus !== false);

    let open=false, active=-1, suppressNextFilter=false, suppressNextFocus=false;

    const openMenu=function(){
      /* NEW: ensure only one dropdown at a time */
      document.querySelectorAll('.combo-menu[data-open="1"]').forEach(m=>{
        if (m !== menuEl) { m.style.display='none'; m.removeAttribute('data-open'); }
      });
      menuEl.style.display='block'; open=true; OPEN_MENUS.add(menuEl); menuEl.setAttribute('data-open','1');
    };
    const closeMenu=function(){
      menuEl.style.display='none'; open=false; active=-1; OPEN_MENUS.delete(menuEl); menuEl.removeAttribute('data-open');
    };

    function selectValue(txt){
      suppressNextFilter=true; suppressNextFocus=true;
      inputEl.value = txt;
      if (debouncedFilter && typeof debouncedFilter.cancel === 'function') debouncedFilter.cancel();
      inputEl.dispatchEvent(new Event('input',{bubbles:true}));
      inputEl.dispatchEvent(new Event('change',{bubbles:true}));
      closeMenu();
      showTapShield(300); // prevent click-through
      setTimeout(function(){ inputEl.focus(); },0);
    }

    // Render list + highlight matches; auto-close when empty
    function render(list,q){
      list = Array.isArray(list) ? list : [];
      q = q || '';
      menuEl.innerHTML='';
      list.slice(0,maxItems).forEach(function(txt,i){
        const div=document.createElement('div');
        div.className='combo-item'+(i===active?' active':'');
        div.innerHTML=renderHighlighted(txt,q);

        // Desktop: select on pointerdown; Touch: select on pointerup
        div.addEventListener('pointerdown', function(e){ if (e.pointerType === 'mouse') { e.preventDefault(); e.stopPropagation(); selectValue(txt); } });
        div.addEventListener('pointerup', function(e){ e.preventDefault(); e.stopPropagation(); selectValue(txt); });
        div.addEventListener('click', function(e){ e.preventDefault(); e.stopPropagation(); selectValue(txt); });

        menuEl.appendChild(div);
      });
      if (list.length) openMenu(); else closeMenu();
    }

    function defaultFilter(items,q){ const Q=deD(q||''); items = Array.isArray(items)?items:[]; return items.filter(function(x){ return deD(x).includes(Q); }); }

    function doFilter(){
      // Block filtering/opening while suppressed
      if (isSuggestionSuppressed() || SUPPRESS_UNTIL_USER_TYPES) { closeMenu(); return; }

      // Clear any stale locks once suppression has ended
      if (inputEl.hasAttribute('data-suppress-open') || inputEl.hasAttribute('data-gps-locked')) {
        inputEl.removeAttribute('data-suppress-open');
        inputEl.removeAttribute('data-gps-locked');
        MENUS_LOCKED = false;
        clearTimeout(MENUS_LOCK_TIMER);
      }

      if (suppressNextFilter){ suppressNextFilter=false; return; }

      const q = inputEl.value.trim();
      const items = (getItems ? getItems() : []);
      if (!q && minChars > 0) return;
      if (!q) return render(items.slice(0, maxItems), q);

      render(matcher ? matcher(items, q) : defaultFilter(items, q), q);
    }

    const debouncedFilter = debounce(doFilter, 90);

    inputEl.addEventListener('input', function(e){
      // If suppression is active, only lift it once the user *actually types*
      if (SUPPRESS_UNTIL_USER_TYPES && e && e.isTrusted === true) {
        SUPPRESS_UNTIL_USER_TYPES = false;
      }

      if (inputEl.getAttribute('data-suppress-open') === '1') {
        if (!isSuggestionSuppressed()) {
          inputEl.removeAttribute('data-suppress-open');
          inputEl.removeAttribute('data-gps-locked');
        }
      }
      debouncedFilter(); updatePreview(); persistDraft();
      triggerGeocodeForCurrent();
    });

    inputEl.addEventListener('focus', function(){
      // NEW: when focusing a different field, close other menus immediately
      document.querySelectorAll('.combo-menu[data-open="1"]').forEach(m=>{
        if (m !== menuEl) { m.style.display='none'; m.removeAttribute('data-open'); }
      });

      if (!isSuggestionSuppressed()) {
        inputEl.removeAttribute('data-suppress-open');
        inputEl.removeAttribute('data-gps-locked');
        MENUS_LOCKED = false;
        clearTimeout(MENUS_LOCK_TIMER);
        if (openOnFocus && !SUPPRESS_UNTIL_USER_TYPES) doFilter();
      }
    });

    inputEl.addEventListener('click', function(){
      if (isSuggestionSuppressed() || SUPPRESS_UNTIL_USER_TYPES) return;
      // NEW: clicking into a different field closes previous open menu
      document.querySelectorAll('.combo-menu[data-open="1"]').forEach(m=>{
        if (m !== menuEl) { m.style.display='none'; m.removeAttribute('data-open'); }
      });

      inputEl.removeAttribute('data-suppress-open');
      inputEl.removeAttribute('data-gps-locked');
      MENUS_LOCKED = false;
      clearTimeout(MENUS_LOCK_TIMER);
      doFilter();
    });

    // Keyboard navigation in menu
    inputEl.addEventListener('keydown', function(e){
      const n=menuEl.children.length;
      if(e.key==='Escape'){ 
        // close only this one
        menuEl.style.display='none'; menuEl.removeAttribute('data-open');
        MENUS_LOCKED=false; clearTimeout(MENUS_LOCK_TIMER); 
        return; 
      }
      if(!n || menuEl.style.display==='none') return;
      if(e.key==='ArrowDown'){ active=Math.min(active+1,n-1); e.preventDefault(); }
      if(e.key==='ArrowUp'){ active=Math.max(active-1,0); e.preventDefault(); }
      if(e.key==='Enter'){
        e.preventDefault();
        const t = menuEl.children[active];
        if (t) t.click();
      }
      Array.prototype.forEach.call(menuEl.children, function(el,i){ el.classList.toggle('active',i===active); });
      if(active>=0) menuEl.children[active].scrollIntoView({ block: 'nearest' });
    });

    const api = { close: closeMenu, openAndHighlight: function(queryText, preferExact, altPrefix) {
      inputEl.removeAttribute('data-suppress-open');
      inputEl.removeAttribute('data-gps-locked');
      MENUS_LOCKED = false;
      clearTimeout(MENUS_LOCK_TIMER);

      inputEl.value = queryText;
      if (debouncedFilter && typeof debouncedFilter.cancel === 'function') debouncedFilter.cancel();
      if (!SUPPRESS_UNTIL_USER_TYPES) doFilter();
      let items = Array.prototype.slice.call(menuEl.children);
      if (!items.length && altPrefix) {
        inputEl.value = altPrefix;
        if (debouncedFilter && typeof debouncedFilter.cancel === 'function') debouncedFilter.cancel();
        if (!SUPPRESS_UNTIL_USER_TYPES) doFilter();
        items = Array.prototype.slice.call(menuEl.children);
      }
      if (!items.length) { return; }
      const norm = s => deD((s||'').trim());
      const wantExact = norm(preferExact || queryText);
      const wantPrefix = norm(altPrefix || '');
      let idx = items.findIndex(el => norm(el.textContent) === wantExact);
      if (idx < 0 && wantPrefix) idx = items.findIndex(el => norm(el.textContent).startsWith(wantPrefix));
      if (idx < 0) idx = 0;
      items.forEach(function(el,i){ el.classList.toggle('active', i===idx); });
      items[idx].scrollIntoView({ block: 'nearest' });
    }};
    if (key) COMBOS.set(key, api);
    return api;
  }

  function shouldActivateMap() {
  const notes = getInputTrimmed('Notes');
  // Visible if Notes contains "wrong" or "update/updated" (any case)
  return /\b(wrong|update(?:d)?)\b/i.test(notes);
}

function toggleMapField() {
  const row = document.getElementById('rowMap');
  if (!row) return;
  const active = shouldActivateMap();
  row.classList.toggle('hidden', !active);
  if (!active) clearField('MapChoice'); // clear when hiding
}



  /* ---- ONE global, delegated outside-click closer ---- */
  let GLOBAL_COMBO_CLOSER_BOUND = false;
  function bindGlobalComboCloser(){
    if (GLOBAL_COMBO_CLOSER_BOUND) return;
    const handler = function(ev){
      const t = ev.target;
      const inCombo = t.closest && t.closest('.combo');
      if (inCombo) return;
      document.querySelectorAll('.combo-menu[data-open="1"]').forEach(m=>{
        m.style.display='none'; m.removeAttribute('data-open');
      });
    };
    document.addEventListener('click', handler);
    GLOBAL_COMBO_CLOSER_BOUND = true;
  }

  /* ========= Predictive matchers ========= */
  const EXTRA_AB_WORDS = [
    'Shop','Unit','Flat','Apt','Apartment','Level','Suite','Block',
    'Office',
  ];
  const EXTRA_NOTES_WORDS = [
    'Check If Chinese', 'Back Entrance', 'Speaks Mandarin', 'Shop', 'Unit', 'Flat', 'Apt', 'Apartment', 'Level', 'Suite', 'Block', 'Kiosk', 'Food Court',
    'Front door', 'Left Unit', 'Right Unit', 'Downstairs', 'Locked Gate', 'Big Dog', 'Office', 'Warehouse', 'Clinic', 'Cafe', 'Restaurant', 'Takeaway', 'Bar', 'Salon', 'Pharmacy', 'Please Check If Chinese',
    'Closed Monday', 'Butchery', 'Bakery', 'Dairy', 'Supermarket', 'Library', 'School', 'Mall',
    'Wrong / Missing Coordinates (Updated)', 'Wrong / Missing Unit (Updated)', 'Wrong / Missing Number (Updated)', 'Wrong - Duplicate Address (Updated)', 'Wrong / Missing Street (Updated)', 'Wrong / Missing Suburb (Updated)', 'Wrong - Out Of Area, East Boundary (Updated)', 'Wrong - Missing Address (Updated)', 'Wrong Map - Street Too Far Away (Updated)',
    'Wrong - Cannot Find Address (Updated)', 
    'Wrong Business Name (Updated)', 'Wrong Apartment Number (Updated)', 'Wrong Type - Changed to House (Updated)', 'Wrong Type - Changed to Business (Updated)', 'Wrong Type - Changed to Apartment (Updated)', 'Wrong/Missing Notes (Updated)', 
];


  function predictiveMatcherFactory(extraWords){
    return function(items, q){
      const out = [];
      const seen = new Set();
      const push = function(s){ const t=String(s||'').trim(); if(!t) return; const k=deD(t); if(seen.has(k)) return; seen.add(k); out.push(t); };

      const Q = deD(q).trim();
      const base = Array.isArray(items) ? items : [];

      // Keep original items that contain the query
      for (let i=0;i<base.length;i++){ if (deD(base[i]).includes(Q)) push(base[i]); }

      // Build a small dictionary from existing items + provided extra words
      const dict = new Set(extraWords || []);
      for (let i=0;i<base.length;i++){
        const it = String(base[i]);
        const parts = it.split(/[^A-Za-z0-9]+/);
        for (let j=0;j<parts.length;j++){ const w=parts[j]; if (w && w.length >= 2) dict.add(w); }
      }

      // Autocomplete the last token using dictionary
      const tokens = String(q).split(/\s+/);
      const last = tokens[tokens.length-1] || '';
      const pref = deD(last);
      if (pref){
        const cands = Array.from(dict).filter(function(w){ return deD(w).startsWith(pref); }).slice(0, 50);
        for (let i=0;i<cands.length;i++){
          const w = cands[i];
          const phrase = tokens.slice(0,-1).concat([w]).join(' ').replace(/\s+/g,' ').trim();
          push(phrase);
          push(w);
        }
      }

      // Prioritize prefix matches near the end
      for (let i=0;i<base.length;i++){ if (deD(base[i]).startsWith(Q)) push(base[i]); }

      return out.slice(0, 100);
    };
  }

  /* ========= Lookups + fixed/defaults ========= */
  const TYPE_FIXED = ['House','Apartment','Business','Other'];

  /* UPDATED: Units — interleave A..Z with 1..26, then 27..300 */
  (function () {
    const letters = Array.from({ length: 26 }, (_, i) => String.fromCharCode(65 + i)); // A..Z
    const nums    = Array.from({ length: 300 }, (_, i) => String(i + 1));              // 1..300

    const interleaved = [];
    const N = Math.min(letters.length, 26); // interleave A..Z with 1..26
    for (let i = 0; i < N; i++) interleaved.push(letters[i], String(i + 1));

    const restNums = nums.slice(N); // 27..300

    window.__DEFAULT_UNITS_EXPANDED__ = [...interleaved, ...restNums];
  })();
  const DEFAULT_UNITS = window.__DEFAULT_UNITS_EXPANDED__;

  const DEFAULT_NUMBERS = Array.from({ length: 20 }, (_, i) => String(i + 1));


  /* UPDATED: Languages incl. Chinese dialects + popular languages */
  const DEFAULT_LANGS = [
    'Cantonese','Chinese','Mandarin','English','French','Japanese','Spanish','Hindi','Arabic','Vietnamese','Korean','Thai','Tagalog',
    'Hokkien','Taiwanese Hokkien','Teochew','Chaoshan','Hakka','Shanghainese','Wu Chinese','Fuzhou','Foochow','Min Nan','Toisanese',
    'Malay','Indonesian','Burmese','Khmer','Nepali','Urdu','Bengali','Punjabi','Gujarati','Tamil','Telugu','Marathi','Sinhala',
    'Portuguese','German','Italian','Russian','Ukrainian','Polish','Dutch','Turkish','Persian','Hebrew','Somali','Swahili','Maori','Samoan','Tongan','Fijian'
  ];

  const DEFAULT_NOTE_PHRASES = ['Back Unit','Side Unit','Front Unit','Rear Unit','Upstairs','Downstairs','Left Unit','Right Unit','Back Entrance','Locked Gate','Big Dog'];

  const state = { streets:[], type:[], apartmentBusiness:[], unit:[], number:[], language:[], notes:[], maps:[] };
  let streetsIndex = [];
  const SUBURB_BY_NORM = new Map();

  function splitStreetSuburb(val){
    const parts = String(val||'').split(',');
       const street=(parts[0]||'').trim(); const suburb=(parts.slice(1).join(',')||'').trim();
    return { street, suburb, nStreet: deD(street), nSuburb: deD(suburb) };
  }

function parseMapKey(s) {
  const m = String(s).match(/^\s*(\d+(?:-\d+)*)\s*([A-Za-z].*)?$/);
  if (!m) return { nums: [], tail: String(s).trim().toUpperCase(), raw: s };
  return {
    nums: m[1].split('-').map(n => parseInt(n, 10)),
    tail: (m[2] || '').trim().toUpperCase(),
    raw: s
  };
}

function cmpMap(a, b) {
  const A = parseMapKey(a), B = parseMapKey(b);

  // compare numeric segments: 1-3 < 1-3-1 < 2-1 ...
  const len = Math.min(A.nums.length, B.nums.length);
  for (let i = 0; i < len; i++) {
    if (A.nums[i] !== B.nums[i]) return A.nums[i] - B.nums[i];
  }
  if (A.nums.length !== B.nums.length) return A.nums.length - B.nums.length;

  // then compare trailing letters (alphabetical)
  if (A.tail && B.tail) {
    const t = A.tail.localeCompare(B.tail, undefined, { sensitivity: 'base', numeric: true });
    if (t) return t;
  } else if (A.tail) return 1;
  else if (B.tail) return -1;

  // final fallback (stable-ish)
  return String(a).localeCompare(String(b), undefined, { sensitivity: 'base', numeric: true });
}



  // Ensure minimal UX even without server lookups
  function ensureMinimumLookups() {
    state.type = TYPE_FIXED.slice();

    const uniqMerge = (defs, arr) => {
      const seen = new Set(), out = [];
      [...(defs||[]), ...(arr||[])].forEach(v=>{
        const s = String(v||'').trim(); if(!s) return;
        const k = s.toLowerCase(); if (seen.has(k)) return;
        seen.add(k); out.push(s);
      });
      return out;
    };
    state.unit      = uniqMerge(DEFAULT_UNITS,    state.unit);
    state.number    = uniqMerge(DEFAULT_NUMBERS,  state.number);
    state.language  = uniqMerge(DEFAULT_LANGS,    state.language);
    state.notes     = uniqMerge([...EXTRA_NOTES_WORDS, ...DEFAULT_NOTE_PHRASES], state.notes);
    state.maps = (state.maps || []).slice().sort(cmpMap);

    if (!Array.isArray(state.apartmentBusiness)) state.apartmentBusiness = [];
    if (!Array.isArray(state.maps)) state.maps = [];

  }

  // Populate the <select> for Type
  function fillTypeOptions(){
    const sel=$('#Type');
    if(!sel) return;
    const opts = TYPE_FIXED;
    sel.innerHTML='<option value="">— Select —</option>'+opts.map(function(t){return `<option>${t}</option>`;}).join('');
  }

  // Build a normalized index for fast street/suburb matching
  function safeRebuildStreetIndex() {
    try {
      streetsIndex=(state.streets||[]).map(function(s){ const o=splitStreetSuburb(s); return {raw:s, nStreet:o.nStreet, nSuburb:o.nSuburb}; });
    } catch(e) {
      streetsIndex = [];
      console.error('streetsIndex rebuild failed', e);
    }
  }

  // Smart matcher prioritizing exact/prefix street, else suburb, then substring
  function streetMatcher(_unused, q){
    const Q=deD(q);
    if(!streetsIndex.length) return [];
    const byPrefix=function(pref){ return streetsIndex.filter(function(o){ return o.nStreet.startsWith(pref); }).map(function(o){ return o.raw; }); };
    let pref=Q, result=byPrefix(pref);
    while(result.length===0 && pref.length>1){ pref=pref.slice(0,-1); result=byPrefix(pref); }
    if(result.length===0 && Q.length>=1) result=streetsIndex.filter(function(o){ return o.nSuburb.startsWith(Q); }).map(function(o){ return o.raw; });
    const seen=new Set(result);
    streetsIndex.forEach(function(o){ if(!seen.has(o.raw) && (o.nStreet.includes(' '+Q)||o.nStreet.includes('-'+Q))){ result.push(o.raw); seen.add(o.raw);} });
    streetsIndex.forEach(function(o){ if(!seen.has(o.raw) && (o.nStreet.includes(Q)||o.nSuburb.includes(Q))){ result.push(o.raw); seen.add(o.raw);} });
    return result;
  }

  // Build a canonical map from normalized suburb → original casing
  function rebuildSuburbIndex() {
    try{
      SUBURB_BY_NORM.clear();
      for (const s of state.streets || []) {
        const parts = String(s || '').split(',');
        const suburb = (parts.slice(1).join(',') || '').trim();
        if (!suburb) continue;
        const key = deD(suburb);
        if (!SUBURB_BY_NORM.has(key)) SUBURB_BY_NORM.set(key, suburb);
      }
    }catch(e){}
  }
  function getCanonicalSuburb(suburb) { return SUBURB_BY_NORM.get(deD(suburb)) || suburb; }

  // Wire up all combos exactly once
  let COMBOS_INITIALISED = false;
  function hydrateCombos(){
  makeCombo($('#ApartmentBusiness'), $('#ApartmentBusinessMenu'),
            () => state.apartmentBusiness || [],
            { openOnFocus: true, matcher: predictiveMatcherFactory(EXTRA_AB_WORDS) });

  makeCombo($('#Unit'), $('#UnitMenu'),
            () => state.unit || [],
            { openOnFocus: true });

  makeCombo($('#HouseNumber'), $('#HouseNumberMenu'),
            () => state.number || [],
            { openOnFocus: true });

  makeCombo($('#Language'), $('#LanguageMenu'),
            () => state.language || [],
            { openOnFocus: true });

  makeCombo($('#Notes'), $('#NotesMenu'),
            () => state.notes || [],
            { openOnFocus: true, matcher: predictiveMatcherFactory(EXTRA_NOTES_WORDS) });

  makeCombo($('#MapChoice'), $('#MapMenu'),
            () => state.maps || [],
            { openOnFocus: true });

  makeCombo($('#Street'), $('#StreetMenu'),
            () => state.streets || [],
            { maxItems: 100, minChars: 0, matcher: streetMatcher, openOnFocus: true });

  bindGlobalComboCloser();
}

  function hydrateCombosOnce() {
    if (COMBOS_INITIALISED) return;
    hydrateCombos();
    COMBOS_INITIALISED = true;
  }

  /* ========= Lookups loader (with offline fallback) ========= */
  function loadLookups(){
    let cached = null;
    try { cached = sessionStorage.getItem(SESSION_CACHE_KEY); } catch (e) { cached = null; }

    if (cached) {
      try {
        Object.assign(state, JSON.parse(cached));
        ensureMinimumLookups();
        safeRebuildStreetIndex();
        rebuildSuburbIndex();
        fillTypeOptions();
        hydrateCombosOnce();
        selectDefaultTypeHouse();
        return Promise.resolve({ ok:true, cached:true });
      } catch (e) {
        try { sessionStorage.removeItem(SESSION_CACHE_KEY); } catch (_){}
      }
    }

    const hasRunner = !!(window.google && google.script && google.script.run);
    if (!hasRunner) {
      showStatus('Running in preview/offline mode — lookups unavailable, but the UI is active.', false);
      ensureMinimumLookups();
      safeRebuildStreetIndex();
      rebuildSuburbIndex();
      fillTypeOptions();
      hydrateCombosOnce();
      selectDefaultTypeHouse();
      return Promise.resolve({ ok:true, offline:true });
    }

    return new Promise((resolve) => {
      google.script.run
        .withSuccessHandler(function(res){
          try{
            Object.assign(state, res || {});
            try { sessionStorage.setItem(SESSION_CACHE_KEY, JSON.stringify(state)); } catch (_){}
            ensureMinimumLookups();
            safeRebuildStreetIndex();
            rebuildSuburbIndex();
            fillTypeOptions();
            hydrateCombosOnce();
            selectDefaultTypeHouse();
            resolve({ ok:true });
          } catch(e){
            showStatus('Lookup parsing error. UI loaded without suggestions.', false);
            ensureMinimumLookups();
            safeRebuildStreetIndex();
            rebuildSuburbIndex();
            fillTypeOptions();
            hydrateCombosOnce();
            selectDefaultTypeHouse();
            resolve({ ok:false, err:e });
          }
        })
        .withFailureHandler(function(err){
          showStatus('Could not load lookup lists (using empty lists).', false);
          ensureMinimumLookups();
          safeRebuildStreetIndex();
          rebuildSuburbIndex();
          fillTypeOptions();
          hydrateCombosOnce();
          selectDefaultTypeHouse();
          resolve({ ok:false, err:err });
        })
        .getLookups();

    });
  }

  /* ========= Networking helpers ========= */
  function fetchWithTimeout(url, ms, headers){
    ms = JSNumber.isFinite(ms) ? ms : 7000;
    headers = headers || {};
    const supportsAbort = typeof AbortController !== 'undefined';
    const ctrl = supportsAbort ? new AbortController() : null;
    const timer = setTimeout(function(){ try { if (ctrl && ctrl.abort) ctrl.abort(); } catch(e) {} }, ms);
    const opts = { headers: Object.assign({ 'Accept':'application/json' }, headers) };
    if (supportsAbort) opts.signal = ctrl.signal;
    return fetch(url, opts).then(
      function(res){ clearTimeout(timer); return res; },
      function(err){ clearTimeout(timer); throw err; }
    );
  }

  /* ========= FORWARD geocoding ========= */
  function ensureAucklandSuffix(text){
    const t = String(text||'');
    return /auckland/i.test(t) ? t : (t.replace(/\s+,/g, ',').trim() + ', Auckland, NZ');
  }
  async function geocodeNominatimForward(q){
    const url = 'https://nominatim.openstreetmap.org/search?format=jsonv2&addressdetails=1&limit=1&q=' + encodeURIComponent(q);
    const res = await fetchWithTimeout(url, 4000);
    if (!res.ok) throw new Error('Nominatim search failed');
    const j = await res.json();
    const hit = (Array.isArray(j) && j[0]) || null;
    if (!hit || !hit.lon || !hit.lat) return null;
    return { lon: +hit.lon, lat: +hit.lat, src:'nominatim' };
  }
  async function geocodePhotonForward(q){
    const url = 'https://photon.komoot.io/api/?limit=1&lang=en&q=' + encodeURIComponent(q);
    const res = await fetchWithTimeout(url, 4000);
    if (!res.ok) throw new Error('Photon search failed');
    const j = await res.json();
    const feat = j && j.features && j.features[0];
    const coords = feat && feat.geometry && feat.geometry.coordinates;
    if (!coords || coords.length < 2) return null;
    return { lon: +coords[0], lat: +coords[1], src:'photon' };
  }
  function raceProviders(q){
    return new Promise((resolve)=>{
      let settled = false, pending = 2;
      const done = (val)=>{ if (!settled && val) { settled = true; resolve(val); } else if (--pending === 0) resolve(null); };
      geocodeNominatimForward(q).then(done).catch(()=>done(null));
      geocodePhotonForward(q).then(done).catch(()=>done(null));
    });
  }
  function buildNearbyNumberList(n){
    const base = parseInt(n, 10);
    if (!JSNumber.isFinite(base)) return [];
    const out = [base];
    for (let d=1; d<=5; d++){
      out.push(base + d);
      if (base - d >= 1) out.push(base - d);
    }
    return out;
  }


// --- Normalize street names (diacritic/case-insensitive; expand common suffixes) ---
function __normalizeStreet__(s) {
  let x = deD(String(s||'')).toLowerCase();
  x = x.replace(/[.,]/g, ' ');
  // expand common NZ/US/UK abbreviations
  x = x
    .replace(/\bave?\b/g, 'avenue')
    .replace(/\bav\b/g, 'avenue')
    .replace(/\brd\b/g, 'road')
    .replace(/\bst\b/g, 'street')
    .replace(/\bdr\b/g, 'drive')
    .replace(/\bct\b/g, 'court')
    .replace(/\bpl\b/g, 'place')
    .replace(/\bln\b/g, 'lane')
    .replace(/\btce?\b/g, 'terrace')
    .replace(/\bter\b/g, 'terrace')
    .replace(/\bcres\b/g, 'crescent')
    .replace(/\bhwy\b/g, 'highway')
    .replace(/\bpde\b/g, 'parade')
    .replace(/\bmt\b/g, 'mount');
  x = x.replace(/\s+/g, ' ').trim();
  return x;
}
function __sameStreet__(a, b) {
  return __normalizeStreet__(a) === __normalizeStreet__(b);
}
function __digits__(s){ const m = String(s||'').match(/\d+/); return m ? m[0] : ''; }

function __parseIntSafe__(s){
  const m = String(s || '').match(/\d+/);
  return m ? parseInt(m[0], 10) : NaN;
}

function __numbersWithinRange__(entered, got, range){
  const wn = __parseIntSafe__(entered);
  const gn = __parseIntSafe__(got);
  if (!Number.isFinite(wn) || !Number.isFinite(gn)) return false;
  if ((wn % 2) !== (gn % 2)) return false; // different side of street → reject
  return Math.abs(wn - gn) <= (Number.isFinite(range) ? range : 0);
}


/* Accept only when reverse has SAME number or is within ±5 of the entered number. */
function __numbersMatch__(want, got){
  return __numbersWithinRange__(want, got, 0);
}

// Distance between entered and reverse housenumber (parity-aware).
// Returns 0 for exact match, positive integer for same-parity distance,
// or Infinity if parity differs / not parseable.
function __numberDistance__(entered, got) {
  const wn = __parseIntSafe__(entered);
  const gn = __parseIntSafe__(got);
  if (!Number.isFinite(wn) || !Number.isFinite(gn)) return Infinity;
  if ((wn % 2) !== (gn % 2)) return Infinity;
  return Math.abs(wn - gn);
}

// Evaluate a single forward candidate by reverse-verifying it.
// Returns { okStreet, dist, exact, hit } where hit={lon,lat,src}
async function __evaluateCandidate__(number, streetInput, candidate) {
  if (!candidate || !JSNumber.isFinite(candidate.lon) || !JSNumber.isFinite(candidate.lat)) {
    return { okStreet:false, dist:Infinity, exact:false, hit:null };
  }
  let rev = null;
  try { rev = await reverseRace(candidate.lat, candidate.lon); } catch(_) {}
  if (!rev || !rev.street) return { okStreet:false, dist:Infinity, exact:false, hit:null };

  const parts = splitStreetSuburb(streetInput);
  const streetOK = __sameStreet__(rev.street, parts.street);
  if (!streetOK) return { okStreet:false, dist:Infinity, exact:false, hit:null };

  const dist = __numberDistance__(number, rev.housenumber);
  return { okStreet:true, dist, exact:(dist === 0), hit:candidate };
}

// Gather both forward hits (Nominatim & Photon) without short-circuiting.
async function __forwardCandidates__(q) {
  const [a, b] = await Promise.allSettled([
    geocodeNominatimForward(q),
    geocodePhotonForward(q)
  ]);
  const hits = [];
  if (a.status === 'fulfilled' && a.value) hits.push(a.value);
  if (b.status === 'fulfilled' && b.value) hits.push(b.value);
  return hits;
}

// NEW: Best-of-both forward → reverse verify, with "closest" selection.
// opts: { omitSuburb: bool }
async function __bestForwardThenVerify__(number, streetInput, opts = {}) {
  const { omitSuburb = false } = opts;
  const parts = splitStreetSuburb(streetInput);
  const q = omitSuburb ? `${number} ${parts.street}` : `${number} ${streetInput}`;
  const query = ensureAucklandSuffix(q);

  const candidates = await __forwardCandidates__(query);
  if (!candidates.length) return null;

  // Evaluate all candidates
  const evals = [];
  for (let i = 0; i < candidates.length; i++) {
    try {
      const e = await __evaluateCandidate__(number, streetInput, candidates[i]);
      evals.push(e);
    } catch (_) {
      evals.push({ okStreet:false, dist:Infinity, exact:false, hit:null });
    }
  }

  // Prefer any exact match on same street
  const exacts = evals.filter(e => e.okStreet && e.exact);
  if (exacts.length) return exacts[0].hit;

  // Otherwise choose closest number on same street (smallest finite dist)
  const closests = evals
    .filter(e => e.okStreet && Number.isFinite(e.dist))
    .sort((a, b) => a.dist - b.dist);

  // IMPORTANT: We still enforce "exact only" acceptance per your rules.
  // So if we only found "closest but not exact", we return null here,
  // letting the caller fall back to omitSuburb/nearby-number probes.
  return null;
}


// Forward → Reverse verification for a single query.
// opts: { omitSuburb: bool, requireNumberMatch: bool }
async function __forwardThenVerify__(number, streetInput, opts = {}) {
  const { omitSuburb = false, requireNumberMatch = true } = opts;
  const parts = splitStreetSuburb(streetInput);
  const q = omitSuburb
    ? `${number} ${parts.street}`
    : `${number} ${streetInput}`;
  const hit = await raceProviders(ensureAucklandSuffix(q));
  if (!hit || !JSNumber.isFinite(hit.lon) || !JSNumber.isFinite(hit.lat)) return null;

  // Reverse check
  let rev = null;
  try { rev = await reverseRace(hit.lat, hit.lon); } catch(_) {}
  if (!rev || !rev.street) return null;

  const streetOK = __sameStreet__(rev.street, parts.street);
  // STRICT: require reverse housenumber to exist and be same or within ±5 of entered
  const numberOK = __numbersMatch__(number, rev.housenumber);

  if (!streetOK) return null;
  if (!numberOK) return null;   // ignore requireNumberMatch flag; we always enforce

  return hit; // verified
} // ←←← CLOSES the function



// Try nearby numbers (±1..5) within a strict time budget.
// Street must match; number match is enforced by __forwardThenVerify__ (same or ±5 of the entered).
async function __tryNearbyVerified__(number, streetInput, budgetMs = GEO_NEARBY_BUDGET_MS) {
  const base = parseInt(number, 10);
  if (!JSNumber.isFinite(base)) return null;

  const deadline = Date.now() + (JSNumber.isFinite(budgetMs) ? budgetMs : GEO_NEARBY_BUDGET_MS);
  const parts = splitStreetSuburb(streetInput);
  const timeLeft = () => Date.now() <= deadline;

  const probe = async (n) => {
    if (!timeLeft()) return null;
    const msLeft = Math.max(0, deadline - Date.now());
    return withBudget(
      __forwardThenVerify__(n, parts.street, { omitSuburb: true /* number match enforced inside */ }),
      msLeft
    );
  };

  // Tight pass: ±1..5
  for (let d = 1; d <= 5; d++) {
    let hit = await probe(base + d);
    if (hit) return hit;

    if (base - d >= 1) {
      hit = await probe(base - d);
      if (hit) return hit;
    }

    if (!timeLeft()) break;
  }
  return null;
  }





async function findCoordsForInputs(){
  const number = getInputTrimmed('HouseNumber');
  const streetInput = getInputTrimmed('Street');
  const currentKey = buildAddrKey(number, streetInput);

  // If address is incomplete → clear state & stop the inline line
  if (!number || !streetInput) {
    CONFIRMED_ADDR_KEY = null;
    LAST_GEOCODE_START_KEY = null;          // NEW: reset, so we can show again next time it’s filled
    clearCoords();
    stopGettingCoords();
    return;
  }

  // NEW: only show “Getting Coordinates” when Number/Street CHANGED
  if (LAST_GEOCODE_START_KEY !== currentKey) {
    startGettingCoords();
    LAST_GEOCODE_START_KEY = currentKey;
  }

  const myReq = ++GEOCODE_REQ_SEQ;

  // 1) As-entered (street + suburb)
  let hit = await __bestForwardThenVerify__(number, streetInput, { omitSuburb:false });

  // 2) If mismatch, retry without suburb
  if (!hit) {
    hit = await __bestForwardThenVerify__(number, streetInput, { omitSuburb:true });
  }

  // 3) If still mismatch, try nearby numbers within strict budget
  if (!hit) {
    hit = await __tryNearbyVerified__(number, streetInput, GEO_NEARBY_BUDGET_MS);
  }

  if (myReq !== GEOCODE_REQ_SEQ) return;

  if (hit && JSNumber.isFinite(hit.lon) && JSNumber.isFinite(hit.lat)) {
    setCoords(hit.lon, hit.lat);
    CONFIRMED_ADDR_KEY = currentKey;
    stopGettingCoords();                    // hide line after success
  } else {
    if (CONFIRMED_ADDR_KEY !== currentKey) clearCoords();
    stopGettingCoords();                    // hide line after attempt
  }
}


  // Throttle forward geocoding while user types
  const triggerGeocodeForCurrent = (function () {
    const deb = function (fn, ms) { ms = JSNumber.isFinite(ms) ? ms : 450; let t; return function(){ clearTimeout(t); t=setTimeout(fn, ms); }; };
    return deb(findCoordsForInputs, 500);
  })();

  /* ========= GPS helpers & logic ========= */
function lockMenusAfterGPS() {
  MENU_IDS.forEach(id => {
    const inp = document.getElementById(id);
    if (inp) {
      inp.setAttribute('data-suppress-open', '1');
      inp.setAttribute('data-gps-locked', '1');
    }
  });
}
function unlockMenusFor(id) {
  const inp = document.getElementById(id);
  if (inp) {
    inp.removeAttribute('data-suppress-open');
    inp.removeAttribute('data-gps-locked');
  }
}
function unlockMenusAll() { MENU_IDS.forEach(unlockMenusFor); }

function scheduleRestoreCombos(delay){
  delay = JSNumber.isFinite(delay) ? delay : 1000;
  clearTimeout(scheduleRestoreCombos._t);
  scheduleRestoreCombos._t = setTimeout(function(){
    try { unlockMenusAll(); } catch(_){}
    try { hydrateCombosOnce(); } catch(_){}
    MENUS_LOCKED = false;
  }, delay);
}


  // Basic geolocation (single read) with timeout
  function getGeoPosition(timeoutMs) {
    timeoutMs = JSNumber.isFinite(timeoutMs) ? timeoutMs : 8000;
    return new Promise((resolve, reject) => {
      if (!('geolocation' in navigator)) return reject(new Error('Geolocation not supported'));
      navigator.geolocation.getCurrentPosition(
        pos => resolve(pos),
        err => reject(err),
        { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 15000 }
      );
    });
  }

  // Watch for a few seconds to get a better accuracy fix, or fallback
  function getBestPosition(maxWaitMs, targetAccM) {
    maxWaitMs = JSNumber.isFinite(maxWaitMs) ? maxWaitMs : 8000;
    targetAccM = JSNumber.isFinite(targetAccM) ? targetAccM : 25;
    return new Promise((resolve, reject) => {
      if (!('geolocation' in navigator)) return reject(new Error('Geolocation not supported'));
      let best = null, done = false;
      const timer = setTimeout(() => {
        done = true;
        if (watchId != null) navigator.geolocation.clearWatch(watchId);
        best ? resolve(best) : reject(new Error('Timeout'));
      }, maxWaitMs);
      const watchId = navigator.geolocation.watchPosition(
        pos => {
          if (done) return;
          if (!best || (pos.coords.accuracy || 1e9) < (best.coords.accuracy || 1e9)) best = pos;
          if ((pos.coords.accuracy || 1e9) <= targetAccM) {
            done = true;
            clearTimeout(timer);
            navigator.geolocation.clearWatch(watchId);
            resolve(best);
          }

        },
        err => { if (done) return; done = true; clearTimeout(timer); if (watchId!=null) navigator.geolocation.clearWatch(watchId); reject(err); },
        { enableHighAccuracy: true, maximumAge: 0, timeout: maxWaitMs }
      );
    });
  }

  // Helpers to interpret provider-specific address payloads
  function bestSuburbFromProps(p) {
    return p.suburb || p.district || p.neighbourhood || p.locality || p.city_district || p.quarter ||
           p.city || p.town || p.village || p.county || '';
  }
  function isAucklandFromProps(p) {
    const AK='auckland'; const n=s=>deD(s||'');
    return [p.city, p.town, p.village, p.county, p.state, p.region, p.city_district].some(v => n(v).includes(AK));
  }
  function propsStreet(p){ return p.road || p.street || p.name || p.pedestrian || p.path || ''; }
  function propsHousenumber(p){ return (p.housenumber || '').toString(); }
  function extractUnitFromProps(p) {
    const cands = [ p && (p.unit || p['addr:unit'] || p.apartment || p.flats || p['addr:flats'] || p.level || p.housename || p.name) ].filter(Boolean);
    for (let i=0;i<cands.length;i++) {
      const raw = cands[i];
      const s = String(raw || '');
      const m = s.match(/\b(?:unit|apt|apartment|flat|level)\s*([A-Za-z0-9\-]+)\b/i);
      if (m) return m[1];
    }
    return '';
  }
  function normalizeNumberForInput(hn) {
    const m = String(hn || '').match(/\d+/);
    return m ? m[0] : '';
  }

  /* ========= Reverse Geocoding Providers ========= */
  async function reversePhoton(lat, lon) {
    const url = 'https://photon.komoot.io/reverse?lon=' + encodeURIComponent(lon) +
            '&lat=' + encodeURIComponent(lat) + '&lang=en';

    const res = await fetchWithTimeout(url, 4000);
    if (!res.ok) throw new Error('Photon reverse failed');
    const j = await res.json();
    const feat = (j && j.features && j.features[0]) || null;
    if (!feat) return null;
    const p = feat.properties || {};
    if (!propsStreet(p)) return null;
    const suburb = bestSuburbFromProps(p);
    if (!isAucklandFromProps(p)) return null;
    return {
      street: propsStreet(p),
      housenumber: propsHousenumber(p),
      unit: extractUnitFromProps(p),
      suburb
    };
  }

  async function reverseNominatim(lat, lon) {
    const url = 'https://nominatim.openstreetmap.org/reverse'
              + '?lat=' + encodeURIComponent(lat)
              + '&lon=' + encodeURIComponent(lon)
              + '&format=jsonv2&addressdetails=1';

    const res = await fetchWithTimeout(url, 4000);
    if (!res.ok) throw new Error('Nominatim reverse failed');
    const j = await res.json();
    const a = (j && j.address) || {};
    const p = {
      road: a.road || a.pedestrian || a.path || a.cycleway || a.footway || a.residential || '',
      housenumber: a.house_number || '',
      city: a.city || a.town || a.village || '',
      county: a.county || '',
      state: a.state || a.region || '',
      city_district: a.city_district || a.suburb || a.neighbourhood || '',
      suburb: a.suburb || a.city_district || a.neighbourhood || ''
    };
    if (!propsStreet(p)) return null;
    if (!isAucklandFromProps(p)) return null;
    return {
      street: propsStreet(p),
      housenumber: propsHousenumber(p),
      unit: '',
      suburb: bestSuburbFromProps(p)
    };
  }

  /* Race reverse geocoders and take the first valid winner */
  function reverseRace(lat, lon){
    return new Promise((resolve) => {
      let settled = false, pending = 2;
      const done = (val) => { if (!settled && val) { settled = true; resolve(val); } else if (--pending === 0) resolve(null); };
      reversePhoton(lat, lon).then(done).catch(()=>done(null));
      reverseNominatim(lat, lon).then(done).catch(()=>done(null));
    });
  }

  // Server-assisted reverse geocode fallback (Apps Script), if available
  async function reverseServer(lat, lon){
    return new Promise((resolve)=>{
      const runnerOK = !!(window.google && google.script && google.script.run);
      if (!runnerOK) return resolve(null);
      google.script.run
        .withSuccessHandler(function(res){
          if (res && res.ok) {
            resolve({ street: res.street || '', housenumber: '', unit:'', suburb: res.suburb || '' });
          } else resolve(null);
        })
        .withFailureHandler(function(){ resolve(null); })
        .reverseGeocodeStreet(lat, lon, 'nominatim');
    });
  }

  // Try to normalize/canonicalize street string against known list
  async function trySnapStreet(street, suburb){
    return new Promise(function(resolve){
      const runnerOK = !!(window.google && google.script && google.script.run);
      if (!runnerOK) return resolve('');
      google.script.run
        .withSuccessHandler(function(res){ resolve(res||''); })
        .withFailureHandler(function(){ resolve(''); })
        .matchKnownStreet(street, suburb);
    });
  }

  // Helpers to set values into inputs while (optionally) suppressing menu openings
  function fillStreetValue(text, opts) {
    opts = opts || {};
    const el = document.getElementById('Street');
    if (!el) return;
    if (opts.suppressMenu) {
      el.setAttribute('data-suppress-open', '1');
      SUPPRESS_UNTIL_USER_TYPES = true;           // NEW: keep menus closed until user types
    }
    el.value = text;
    if (!MENUS_LOCKED) closeAllMenus();
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    updatePreview();
    persistDraft();
  }
  function fillInputValue(id, value, opts) {
    opts = opts || {};
    const el = document.getElementById(id);
    if (!el) return;
    if (opts.suppressMenu) {
      el.setAttribute('data-suppress-open', '1');
      SUPPRESS_UNTIL_USER_TYPES = true;           // NEW
    }
    el.value = value || '';
    if (!MENUS_LOCKED) closeAllMenus();
    el.dispatchEvent(new Event('input',  { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    updatePreview();
    persistDraft();
  }


  /* ========= GPS click handler =========
     Always red; text toggles GPS→ON while active; reverts after status clears
  */
  async function onGpsClick() {
    const btn = document.getElementById('gpsBtn');
    if (!btn) return;

    const msgEl = document.getElementById('gpsSearchingMsg');

    const revertToOriginalIfMsgCleared = () => {
      if (!msgEl) return;
      // if Searching Location message is no longer shown, revert text to GPS
      const txt = (msgEl.textContent || '');
      if (!/Acquiring\s*GPS/i.test(txt) && !/Submitting/i.test(txt) && !/Saving\s*Address/i.test(txt)) {
        btn.textContent = 'GPS';
      }
    };

    const unlockNow = () => {
      const remaining = Math.max(0, SUPPRESS_SUGGESTIONS_UNTIL - Date.now());

      clearTimeout(MENUS_LOCK_TIMER);
      MENUS_LOCKED = false;

      // Back to idle (still red)
      btn.disabled = false;
      btn.classList.remove('is-busy');

      // Restore combos after any remaining suppression time
      scheduleRestoreCombos(remaining);

      // Safety: ensure fields aren’t stuck locked
      unlockMenusAll();
    };

    // Lock menus immediately during GPS operation
    MENUS_LOCKED = true;
    clearTimeout(MENUS_LOCK_TIMER);
    MENUS_LOCK_TIMER = setTimeout(()=>{ MENUS_LOCKED=false; unlockMenusAll(); }, 6000); // superseded later by suppression window

    lockMenusAfterGPS();
    closeAllMenus();

    // Show inline "Searching…" text
    startGettingCoords();

    // BUSY
    btn.classList.add('is-busy');
    btn.disabled = true;
    const originalLabel = 'GPS';
    btn.textContent = 'ON';

    try {
      let pos;
      try { pos = await getBestPosition(8000, 25); }
      catch (_) { pos = await getGeoPosition(10000); }

      const coords = { lat: pos.coords.latitude, lon: pos.coords.longitude };
      const acc = Math.round(pos.coords.accuracy || 0);
      btn.title = 'GPS accuracy: ' + String.fromCharCode(177) + ' ' + acc + ' m';

      // Reverse geocode via racing Photon vs Nominatim, then fallback to server
      let resolved = null;
      try { resolved = await reverseRace(coords.lat, coords.lon); } catch(_){}
      if (!resolved) try { resolved = await reverseServer(coords.lat, coords.lon); } catch(_){}

      // After GPS fills fields, suppress all suggestions/menus
      suppressSuggestionsFor(2000);
      SUPPRESS_UNTIL_USER_TYPES = true; // keep closed until *user types*

      if (resolved) {
        // Snap/canonicalize
        const snapped = await trySnapStreet(resolved.street, resolved.suburb);
        const canon = getCanonicalSuburb(resolved.suburb);
        const suburbForDisplay = snapped ? resolved.suburb : (canon || resolved.suburb || '');
        const finalStreetText = snapped || (suburbForDisplay
          ? (resolved.street + ', ' + suburbForDisplay)
          : resolved.street);

        // Fill inferred unit/number if available
        let unit = resolved.unit || '';
        let numberRaw = resolved.housenumber || '';
        let number = normalizeNumberForInput(numberRaw);

        if (number) fillInputValue('HouseNumber', number, { suppressMenu: true });
        if (unit)   fillInputValue('Unit',   unit,   { suppressMenu: true });
        fillStreetValue(finalStreetText, { suppressMenu: true });

        // If looks like a standalone house (no unit) → set Type to House
        if (!unit) {
          const sel = document.getElementById('Type');
          if (sel) {
            const current = (sel.value || '').trim().toLowerCase();
            if (current !== 'house') {
              const opt = Array.from(sel.options).find(o => (o.value||o.text||'').trim().toLowerCase() === 'house');
              if (opt) sel.value = opt.value || opt.text;
            }
          }
        }

        // Get precise lon/lat using forward geocoding (runs during suppression)
        // Skip re-geocoding if we already have fresh coords; otherwise cap time spent.
        const fresh = LAST_COORDS && (Date.now() - (LAST_COORDS._ts || 0) < GEO_COORDS_FRESH_MS);
        if (!fresh) {
          await Promise.race([ findCoordsForInputs(), wait(GEO_SUBMIT_GEOCODE_CAP_MS) ]);
        }



      } else {
        pushStatus('not_found', 'Street Not Found…', { spinner: false, ttlMs: 2000 });

      }

      } catch (e) {
        const code = (e && e.code) || 0; // 1=PERMISSION_DENIED, 2=POSITION_UNAVAILABLE, 3=TIMEOUT
        const inIframe = (function(){ try { return window.self !== window.top; } catch(_){ return true; } })();

        if (code === 1 && inIframe) {
          showStatus('GPS blocked by container. Ask the site owner to allow “geolocation” on the embed, or open in a new tab.', false);
          toast('GPS blocked by the embed (no permission).', { type: 'err', ms: 3500 });
        } else if (code === 1) {
          showStatus('Location permission denied. Please allow Location in your browser.', false);
        } else if (code === 2) {
          showStatus('Location unavailable. Try moving near a window or check connection.', false);
        } else if (code === 3) {
          showStatus('Location timed out. Try again.', false);
        } else {
          showStatus('GPS lookup failed.', false);
        }

        if (msgEl) msgEl.textContent = '';
        btn.textContent = originalLabel; // revert on error
        } finally {
          // Back to idle (red) and restore menus
          unlockNow();

          // ✅ Always restore the button label
          btn.textContent = originalLabel;  // <- ensures "GPS" returns after success or failure


          
            ensureAcquiringBanner();
          
        }
      } // <-- end of onGpsClick()



  // Convenience: default Type to "House" if nothing selected
  function selectDefaultTypeHouse() {
    const sel = document.getElementById('Type');
    if (!sel || sel.value) return;
    const match = Array.from(sel.options).find(o =>
      (o.value || o.text || '').trim().toLowerCase() === 'house'
    );
    if (match) sel.value = match.value || match.text;
  }

  /* ========= Confirmation summary (new format) ========= */
  function buildConfirmSummary(d, d2) {
    // EXACT requested layout
    // Header line + each item on its own line
    const lines = [];
    lines.push('Please confirm summary:\n_______________________');

    if (d.ApartmentBusiness) lines.push(d.ApartmentBusiness);

    // Unit + Number + Street (Street already contains suburb suffix)
    const unitBit = d.Unit ? `Unit ${d.Unit}, ` : '';
    const line2 = `${unitBit}${d.Number ? d.Number + ' ' : ''}${d.Street || ''}`.trim();
    if (line2) lines.push(`${line2}`);

    if (d.Type) lines.push(d.Type);
    if (d.Language) lines.push(d.Language);

    if (d.Notes) lines.push(`Notes: "${d.Notes}"`);

    // NEW: show selected map when Map field is active/filled
    if (d.Map) lines.push(`Map: ${d.Map}`);

    // Longitude / Latitude lines (show labels, include values if present)
    const lon = d2 && d2.Longitude ? `Longitude: ${d2.Longitude}` : 'Longitude:';
    const lat = d2 && d2.Latitude  ? `Latitude: ${d2.Latitude}`   : 'Latitude:';
    lines.push(lon);
    lines.push(lat);

    return lines.join('\n');
  }

      /* ========= Event bindings (static) ========= */
  function bindStaticHandlers() {
    // One-time guard for all static bindings
    if (STATIC_HANDLERS_BOUND) return;
    STATIC_HANDLERS_BOUND = true;

    const hook = function(id, fn){ const el=document.getElementById(id); if(el) el.addEventListener('click', fn); };

    // Individual clears
    hook('clearType',               ()=>{ clearField('Type'); });
    hook('clearApartmentBusiness',  ()=>{ clearField('ApartmentBusiness'); });
    hook('clearUnit',               ()=>{ clearField('Unit'); });
    hook('clearNumber',             ()=>{ clearField('HouseNumber'); });
    hook('clearStreet',             ()=>{ clearField('Street'); });
    hook('clearLanguage',           ()=>{ clearField('Language'); });
    hook('clearMap',                ()=>{ clearField('MapChoice'); });

    // Notes confirm only when there is content
    
    hook('clearNotes', () => {
      const el = document.getElementById('Notes');
      if (el && String(el.value || '').trim()) {
        if (confirmGuarded('Delete Notes?')) clearField('Notes');
      } else {
        clearField('Notes');
      }
    });


    // Clear All → lighter red + reliable revert
    const clearBtnEl = document.getElementById('clearBtn');
    if (clearBtnEl){
      const removeFlash = () => clearBtnEl.classList.remove('fade-lite-red');
      clearBtnEl.addEventListener('pointerdown', () => {
        clearBtnEl.classList.add('fade-lite-red');
      });
      clearBtnEl.addEventListener('pointerup', removeFlash);
      clearBtnEl.addEventListener('mouseleave', removeFlash);
      clearBtnEl.addEventListener('touchend', removeFlash, {passive:true});
      clearBtnEl.addEventListener('touchcancel', removeFlash, {passive:true});
      clearBtnEl.addEventListener('click', (e)=>{ 
        setTimeout(removeFlash, 350);
        clearAllConfirmed(); 
      });
    }

    // Any click anywhere => clear stale menu lock (does not force-close menus)
    document.addEventListener('click', function(){
      MENUS_LOCKED = false;
      clearTimeout(MENUS_LOCK_TIMER);
    });


// Number field
const numEl = $('#HouseNumber');
if (numEl) {
  numEl.addEventListener('input', e => {
    const cleaned = e.target.value.replace(/[^\d]/g, '');
    if (cleaned !== e.target.value) e.target.value = cleaned;

    // Address changed → only show inline status when Street & Number exist
    CONFIRMED_ADDR_KEY = null;
    if (hasStreetAndNumber()) {
      startGettingCoords();
    } else {
      stopGettingCoords();
    }
    clearCoords();

    scheduleRestoreCombos(1000);
  });
  numEl.addEventListener('input', triggerGeocodeForCurrent);
  numEl.addEventListener('click',  () => scheduleRestoreCombos(0));
  numEl.addEventListener('focus',  () => scheduleRestoreCombos(0));
}

// Street field
const streetEl = $('#Street');
if (streetEl) {
  streetEl.addEventListener('input', () => {
    // Address changed → only show inline status when Street & Number exist
    CONFIRMED_ADDR_KEY = null;
    if (hasStreetAndNumber()) {
      startGettingCoords();
    } else {
      stopGettingCoords();
    }
    clearCoords();

    triggerGeocodeForCurrent();
    scheduleRestoreCombos(1000);
  });
  streetEl.addEventListener('change', triggerGeocodeForCurrent);
  streetEl.addEventListener('click',  () => scheduleRestoreCombos(0));
  streetEl.addEventListener('focus',  () => scheduleRestoreCombos(0));
}

// Unit field — also show the line if Street & Number are already filled
const unitEl = document.getElementById('Unit');
if (unitEl) {
  unitEl.addEventListener('input', () => {
    if (hasStreetAndNumber()) {
      // ensure a fresh “start” even if the addr key didn't change
      CONFIRMED_ADDR_KEY = null;
      LAST_GEOCODE_START_KEY = null;
      startGettingCoords();
      triggerGeocodeForCurrent();
    } else {
      stopGettingCoords();
    }
  });
}



    // Other text fields
    ['Unit','ApartmentBusiness','Language','Notes','MapChoice'].forEach(id=>{
      const el=document.getElementById(id);
      if(el){
        el.addEventListener('input', ()=>scheduleRestoreCombos(1000));
        el.addEventListener('click', ()=>scheduleRestoreCombos(0));
        el.addEventListener('focus', ()=>scheduleRestoreCombos(0));
      }
    });

    // Toggle Map visibility whenever Notes changes
    const notesEl = document.getElementById('Notes');
    if (notesEl) {
      notesEl.addEventListener('input', toggleMapField);  
      notesEl.addEventListener('change', toggleMapField);
    }

    // "New Addresses" button pressed feedback
    const newBtn = document.getElementById('newAddressBtn');
    if (newBtn){
      const pressOn = ()=> newBtn.classList.add('is-pressed');
      const pressOff = ()=> newBtn.classList.remove('is-pressed');
      newBtn.addEventListener('mousedown', pressOn);
      newBtn.addEventListener('mouseup', pressOff);
      newBtn.addEventListener('mouseleave', pressOff);
      newBtn.addEventListener('touchstart', pressOn, {passive:true});
      newBtn.addEventListener('touchend', pressOff);
      newBtn.addEventListener('touchcancel', pressOff);

      newBtn.addEventListener('click', function(){
        newBtn.classList.add('flash-to-red');
        setTimeout(()=>newBtn.classList.remove('flash-to-red'), 3000);
      });
    }

    // GPS
    const gpsBtn = document.getElementById('gpsBtn');
    if (gpsBtn) gpsBtn.addEventListener('click', onGpsClick);

    // Type change
    const typeEl = $('#Type');
    if(typeEl) typeEl.addEventListener('change', ()=>scheduleRestoreCombos(1000));

    // ===== FORM SUBMIT HANDLER (bind once) =====
    if (FORM_SUBMIT_BOUND) return;   // extra guard
    const form = document.getElementById('addrForm');
    if(form){
      // Prevent Enter from selecting while a combo menu is open
      form.addEventListener('keydown', (e) => {
        const openMenuEl = document.querySelector('.combo-menu[data-open="1"]');
        if (openMenuEl && e.key === 'Enter') e.preventDefault();
      });

      form.addEventListener('submit', async (e) => {
  e.preventDefault();

  const submitBtn = document.getElementById('submitBtn');
  const msgEl = document.getElementById('gpsSearchingMsg');

  // Show "Submitting" right away
  
  setSecondaryStatus('Submitting');
  


  if (submitBtn){
    submitBtn.classList.add('fade-lite-black');
    setTimeout(()=>submitBtn.classList.remove('fade-lite-black'), 700);
    submitBtn.disabled = true;                 // stop repeat clicks before confirm
  }
  if (isSubmitting) return;                    // already mid-submit → ignore

  const d = collect();
  // Validate required fields
  const missing = [];
  if (!d.Number) missing.push('Please Enter Number Field');
  if (!d.Street) missing.push('Please Enter Street Field');

  if (missing.length) {
    // clear any inline/secondary status we showed earlier
    clearSecondaryStatus();
    if (msgEl) msgEl.textContent = '';
    if (submitBtn) submitBtn.disabled = false;

    alert(missing.join('\n')); // one or both lines
    return;
  }


  
  const fresh = LAST_COORDS && (Date.now() - (LAST_COORDS._ts || 0) < GEO_COORDS_FRESH_MS);
  if (!fresh) {
    await Promise.race([ findCoordsForInputs(), wait(GEO_SUBMIT_GEOCODE_CAP_MS) ]);
  }

  // Extra checks when Map field is active
  const mapActive = shouldActivateMap();

  if (mapActive) {
    const missing = [];
    if (!d.Number) missing.push('Number');
    if (!d.Street) missing.push('Street');
    if (!/\b(wrong|update(?:d)?)\b/i.test(d.Notes)) {
      missing.push('Notes (must include "wrong" or "update")');
    }
    if (!d.Map) missing.push('Map');

    if (missing.length) {
      if (missing.length === 1 && missing[0] === 'Map') {
        alert("Please Select Current Map");
      } else {
        alert('Please fill in: ' + missing.join(', ') + '.');
      }
      // clear "Submitting" and re-enable
      if (msgEl) msgEl.textContent = '';
      if (submitBtn) submitBtn.disabled = false;
      return; // stop submit
    }
  }

  const d2 = Object.assign({}, d, {
    Longitude: (LAST_COORDS && LAST_COORDS.lon != null) ? String(LAST_COORDS.lon) : '',
    Latitude:  (LAST_COORDS && LAST_COORDS.lat != null) ? String(LAST_COORDS.lat) : ''
  });

  // Confirmation summary — shown once per attempt
  const summary = buildConfirmSummary(d, d2);
  if (!CONFIRM_SUMMARY_LOCK) {
    CONFIRM_SUMMARY_LOCK = true;
  }
  const __userConfirmed = confirmGuarded(summary);
if (!__userConfirmed) {
  // Let the next attempt show the prompt again
  CONFIRM_SUMMARY_LOCK = false;

  // Remove any inline/secondary status like “Submitting” or “Saving Address”
  clearSecondaryStatus();          // <— NEW: guarantees no residual status text

  // Also clear the inline area in case we wrote directly to it
  if (msgEl) msgEl.textContent = '';

  // Re-enable submit and bail
  if (submitBtn) submitBtn.disabled = false;
  return;
}


  isSubmitting = true;
  setSubmitEnabled(false);
  closeAllMenus();

  // After confirmation — always show "Saving Address …", overriding anything
  // setSecondaryStatus('Saving Address', { force: true });


  suppressSuggestionsFor(5000);

  const runnerOK = !!(window.google && google.script && google.script.run);

  // --- OFFLINE SUBMIT BRANCH ---
  if (!runnerOK) {
    await new Promise(r=>setTimeout(r, 350));
    if (msgEl) msgEl.textContent = '';
    clearSecondaryStatus();          // NEW
    await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
    const streetLabel = (d && d.Street ? d.Street : 'the same street');

    let again = false;
    if (!THANKYOU_PROMPT_LOCK) {
      THANKYOU_PROMPT_LOCK = true;
      again = confirmGuarded(`Thank you, your address has been successfully submitted.\nWould you like to add another number from ${streetLabel}?`);
    }

    if (again) {
      ['ApartmentBusiness','Unit','HouseNumber','Language','Notes'].forEach(clearField);
      updatePreview(); persistDraft();
      toggleMapField(); // hide Map if Notes was cleared / keywords removed
    } else {
      const form = document.getElementById('addrForm');
      form.reset(); unlockMenusAll(); try { localStorage.removeItem('addr_draft'); } catch {}
      clearCoords(); closeAllMenus(); updatePreview();
      toggleMapField(); // ensure Map hidden after full reset
    }

    // End-of-flow cleanup
    resetSubmitLocks();
    isSubmitting = false; setSubmitEnabled(true);
    return;
  }

  // Real submission via Apps Script
  google.script.run
    .withSuccessHandler(async (res) => {
      if (msgEl) msgEl.textContent = '';
      clearSecondaryStatus();          // NEW
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));

      if (res && res.ok) {
        const streetLabel = (d && d.Street ? d.Street : 'the same street');

        let again = false;
        if (!THANKYOU_PROMPT_LOCK) {
          THANKYOU_PROMPT_LOCK = true;
          again = confirm(`Thank you, your address has been successfully submitted.\nWould you like to add another number from ${streetLabel}?`);
        }

        if (again) {
          ['ApartmentBusiness','Unit','HouseNumber','Language','Notes'].forEach(clearField);
          updatePreview(); 
          persistDraft();
          toggleMapField(); // hide Map if Notes was cleared / keywords removed
        } else {
          const form = document.getElementById('addrForm');
          form.reset(); 
          unlockMenusAll(); 
          try { localStorage.removeItem('addr_draft'); } catch {}
          clearCoords(); 
          closeAllMenus(); 
          updatePreview();
          toggleMapField(); // ensure Map hidden after full reset
        }

        // End-of-flow: reset locks for the next submission cycle
        resetSubmitLocks();

      } else {
        // Non-OK response: show message and let the user try again
        showStatus((res && res.message) ? res.message : 'Failed to save.');
        clearSecondaryStatus();          // NEW
        resetSubmitLocks();
      }

      isSubmitting = false; 
      setSubmitEnabled(true);
    })
    .submitAddress(d2);
});
    FORM_SUBMIT_BOUND = true;
    } // end if(form)
  } // end bindStaticHandlers



 /* ========= Reset lookups + rehydrate ========= */
async function resetCachesAndHydrate() {
  const runnerOK = !!(window.google && google.script && google.script.run);
  if (!runnerOK) { toast('Offline: cannot contact server', { type: 'err' }); return; }

  google.script.run
    .withSuccessHandler((res) => {
      if (res && res.ok && res.payload) {
        let oldState = null;
        try { oldState = JSON.parse(sessionStorage.getItem(SESSION_CACHE_KEY)); } catch(_) {}

        try { sessionStorage.setItem(SESSION_CACHE_KEY, JSON.stringify(res.payload)); } catch(_) {}
        Object.assign(state, res.payload);
        ensureMinimumLookups();
        safeRebuildStreetIndex();
        rebuildSuburbIndex();
        fillTypeOptions();
        hydrateCombosOnce();
        selectDefaultTypeHouse();

        if (!oldState || JSON.stringify(oldState) !== JSON.stringify(res.payload)) {
          window.showToastRefreshed?.();
        }

        console.log('resetUI complete', res);
      } else {
        toast((res && res.message) || 'Reset failed', { type: 'err' });
      }
    })
    .withFailureHandler((err) => {
      toast('Reset failed', { type: 'err', ms: 3500 });
      console.error('resetUI error:', err);
    })
    .resetUI();
}



  /* ========= App bootstrap (init) ========= */
  function init() {
    // Idempotent guard (safe to call multiple times)
    if (window.__INIT_DONE__) {
      try { MENUS_LOCKED = false; clearTimeout(MENUS_LOCK_TIMER); unlockMenusAll(); closeAllMenus(); } catch (_){}
      return;
    }
    window.__INIT_DONE__ = true;

    // Title text override if needed
    try {
      const tEl = document.querySelector('.title-text');
      if (tEl && /\bAdd New Addresses\b/i.test((tEl.textContent||'').trim())) tEl.textContent = 'New Addresses / Update';
      if (/\bAdd New Addresses\b/i.test(document.title)) document.title = 'New Addresses';
    } catch (_) {}


    // Force-unlock any stale menu locks/flags from previous flows (e.g., GPS)
    try {
      MENUS_LOCKED = false; clearTimeout(MENUS_LOCK_TIMER);
      MENU_IDS.forEach(id => {
        const el = document.getElementById(id);
        if (el) { el.removeAttribute('data-suppress-open'); el.removeAttribute('data-gps-locked'); }
      });
      closeAllMenus();
    } catch (_){}

    // Baseline UI + handlers
    ensureMinimumLookups();
    fillTypeOptions();
    hydrateCombosOnce();
    selectDefaultTypeHouse();
    bindStaticHandlers();

    // Load lookups (never allow a failure to break the UI)
    loadLookups()
      .then(() => { /* ok */ })
      .catch((_e) => {
        try { sessionStorage.removeItem(SESSION_CACHE_KEY); } catch (_){}
        try { hydrateCombosOnce(); } catch (_){}
      });

    // Draft + preview
    try { restoreDraft(); } catch (_){}
    toggleMapField(); // <-- NEW
    updatePreview();

    setSubmitEnabled(true);
    triggerGeocodeForCurrent();

    // Post-init: belt-and-braces unlock on next frames
    requestAnimationFrame(() => {
      try { MENUS_LOCKED = false; unlockMenusAll(); } catch (_){}
    });
    setTimeout(() => {
      try { MENUS_LOCKED = false; unlockMenusAll(); closeAllMenus(); } catch (_){}
    }, 300);
  }

  // Run init as soon as DOM is ready; guard for bfcache/pagehide to avoid stuck UI
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }



/* ======= Auto-refresh Lookups Patch (FULL) ======= */


if (!window.__LOOKUP_REFRESH_PATCH_BOUND__) {
  window.__LOOKUP_REFRESH_PATCH_BOUND__ = true;

  let refreshMsgTimer = null;
  let __inflightToken = 0; // increments per request

  // Use the app's cache key if it exists; otherwise a safe fallback.
  const SESSION_CACHE_KEY_PATCH =
    (typeof window.SESSION_CACHE_KEY !== 'undefined' && window.SESSION_CACHE_KEY)
      ? window.SESSION_CACHE_KEY
      : 'lookups_v0_local';

  /* ---------------------------------------------
   *  GPS busy guard: never refresh while GPS is active
   * --------------------------------------------- */
  function gpsIsBusy() {
    const btn = document.getElementById('gpsBtn');
    const msg = (document.getElementById('gpsSearchingMsg')?.textContent || '').toLowerCase();
    return !!(btn && (btn.disabled || btn.classList.contains('is-busy'))) ||
           /searching\s*location/.test(msg);
  }

  /* ---------------------------------------------
   *  Stable, order-insensitive deep stringify
   * --------------------------------------------- */
  function __sortDeep__(v) {
    if (Array.isArray(v)) {
      return v.map(__sortDeep__).sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b)));
    }
    if (v && typeof v === 'object') {
      const out = {};
      Object.keys(v).sort().forEach(k => { out[k] = __sortDeep__(v[k]); });
      return out;
    }
    return v;
  }
  function __stableStringify__(v) { return JSON.stringify(__sortDeep__(v)); }

 /* ---------------------------------------------
 *  Inline "Syncing..." helper (spinner only)
 * --------------------------------------------- */


function showToastRefreshed() {
  if (gpsIsBusy()) return;
  // 3s auto-clear stacked “Syncing”
  pushStatus('syncing', 'Syncing', { spinner: true, ttlMs: 3000 });
}


  /* ---------------------------------------------
   *  Read cached payload (safe)
   * --------------------------------------------- */
  function readCachedState() {
    try {
      const raw = sessionStorage.getItem(SESSION_CACHE_KEY_PATCH);
      if (!raw) return null;
      return JSON.parse(raw);
    } catch { return null; }
  }

  /* ---------------------------------------------
   *  Apply payload to UI (uses main script globals)
   * --------------------------------------------- */
  function applyPayloadToUI(payload) {
    // Uses globals from your main script: state, ensureMinimumLookups, etc.
    Object.assign(state, payload || {});
    ensureMinimumLookups();
    safeRebuildStreetIndex();
    rebuildSuburbIndex();
    fillTypeOptions();
    hydrateCombosOnce();
    selectDefaultTypeHouse();
  }

  /* ---------------------------------------------
   *  Refresh lookups & update UI (announce only if changed)
   *  — gated to never run during GPS busy
   * --------------------------------------------- */
  async function refreshLookupsOnce() {
    // ⛔ Don’t refresh during GPS — try again shortly
    if (gpsIsBusy()) { setTimeout(refreshLookupsOnce, 1500); return; }

    const runnerOK = !!(window.google && google.script && google.script.run);
    if (!runnerOK) { toast('Offline: cannot contact server', { type: 'err' }); return; }

    const myToken = ++__inflightToken; // token for this request

    google.script.run
      .withSuccessHandler((res) => {
        if (myToken !== __inflightToken) return; // discard stale responses

        // If GPS became busy while we were fetching, defer apply and bump token
        if (gpsIsBusy()) { setTimeout(() => { __inflightToken++; refreshLookupsOnce(); }, 1500); return; }

        if (res && res.ok && res.payload) {
          const oldState = readCachedState();
          const changed = !oldState || (__stableStringify__(oldState) !== __stableStringify__(res.payload));

          applyPayloadToUI(res.payload);

          if (changed) {
            try { sessionStorage.setItem(SESSION_CACHE_KEY_PATCH, JSON.stringify(res.payload)); } catch {}
            window.showToastRefreshed?.();
          }

          console.log('refreshLookupsOnce complete', res);
        } else {
          toast((res && res.message) || 'Reset failed', { type: 'err' });
        }
      })
      .withFailureHandler((err) => {
        if (myToken !== __inflightToken) return;
        toast('Reset failed', { type: 'err', ms: 3500 });
        console.error('refreshLookupsOnce error:', err);
      })
      .resetUI(); // server returns { ok: true, payload: ... }
  }

  /* ---------------------------------------------
   *  Guard: don’t rewrite the GPS message while busy
   * --------------------------------------------- */
  (function guardToastAgainstGPS() {
  const gpsMsgEl = document.getElementById("gpsSearchingMsg");
  if (!gpsMsgEl) return;
  const observer = new MutationObserver(() => { /* no-op under stacked status */ });
  observer.observe(gpsMsgEl, { childList: true, characterData: true, subtree: true });
})();


  /* ---------------------------------------------
   *  Init wrapper (single-bind, no double wrap)
   *  — runs one safe refresh after init, but only if GPS isn’t busy
   * --------------------------------------------- */
  (function patchInitOnce () {
    if (window.__LOOKUP_PATCH_INIT_BOUND__) return;
    window.__LOOKUP_PATCH_INIT_BOUND__ = true;

    const __originalInit = window.init;

    function afterInit() {
      // Belt & braces: ensure styles are reset if message node is reused
      const msgEl = document.getElementById("gpsSearchingMsg");
      if (msgEl) { msgEl.style.color = ""; msgEl.style.fontWeight = ""; }

      console.log("🔄 Refresh after init...");
      if (gpsIsBusy()) setTimeout(refreshLookupsOnce, 1500);
      else refreshLookupsOnce();
    }

    // Wrap for any future direct calls to init()
    window.init = function patchedInit() {
      if (typeof __originalInit === "function") __originalInit();
      afterInit();
    };

    // Ensure we also run on the *first* page load even if an older listener was bound
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", afterInit, { once: true });
    } else {
      setTimeout(afterInit, 0);
    }
  })();

}

// ========================
// End Auto-refresh Patch ✓
// ========================


  // Re-init when returning from bfcache (back/forward)
  window.addEventListener('pageshow', (e) => {
    if (e && e.persisted) init();
  });

  // [TWEAK] Clear locks/timers/menus on pagehide (Safari/Android)
  window.addEventListener('pagehide', () => {
    try { MENUS_LOCKED = false; clearTimeout(MENUS_LOCK_TIMER); } catch(_) {}
    try { closeAllMenus(); } catch(_) {}
  });

  // ===========================
  // ===== Server bridge stubs =
  // ===========================
  function getLookupsHydrated() { return getLookups(); }
  function resetUI() {
    try { refreshAllCaches(); } catch (_){}
    return { ok: true, payload: getLookups() };
  }
  function reverseGeocodeStreet(lat, lon, provider) { return { ok: false }; }
  function matchKnownStreet(street, suburb) { return ''; }

  // ===========================
  // ===== Emergency repair  ===
  // ===========================
  window.repairUI = function () {
  try {
    MENU_IDS.forEach(id => {
      const el = document.getElementById(id);
      if (el) { el.removeAttribute('data-suppress-open'); el.removeAttribute('data-gps-locked'); }
    });
    document.querySelectorAll('.combo-menu').forEach(m => { m.style.display='none'; m.removeAttribute('data-open'); });
    if (typeof hydrateCombos === 'function') hydrateCombos();
    if (typeof bindStaticHandlers === 'function') bindStaticHandlers();
    toast('UI repaired', { type:'ok' });
  } catch (e) {
    alert('Repair failed: ' + (e && e.message ? e.message : e));
  }
};

</script>
</body>
</html>
