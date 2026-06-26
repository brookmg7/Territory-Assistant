
// Code.gs  (server)
 /** Compute a cache version that changes on each deploy, and in /dev when code changes */
function _computeCacheVersion_() {
  try {
    var url = ScriptApp.getService().getUrl() || '';
    // Deployed web app: URL contains /s/{deploymentId}/...
    var m = url.match(/\/s\/([^ /]+)/);
    if (m) return 'v' + m[1].slice(-6); // stable per deployment

    // Test (latest code) endpoint ends with /dev
    if (/\/dev(\?|$)/.test(url)) {
      try {
        var f = DriveApp.getFileById(ScriptApp.getScriptId());
        var d = f.getLastUpdated(); // bumps on every save/push
        var pad = n => ('0' + n).slice(-2);
        return 'dev' + d.getFullYear() + pad(d.getMonth()+1) + pad(d.getDate()) + pad(d.getHours()) + pad(d.getMinutes());
      } catch (_) {
        return 'dev' + Date.now();
      }
    }
  } catch (_) {}

  // Non-web contexts (triggers/editor): fall back to project last-updated if possible
  try {
    var f2 = DriveApp.getFileById(ScriptApp.getScriptId());
    var d2 = f2.getLastUpdated();
    var pad2 = n => ('0' + n).slice(-2);
    return 'trg' + d2.getFullYear() + pad2(d2.getMonth()+1) + pad2(d2.getDate()) + pad2(d2.getHours()) + pad2(d2.getMinutes());
  } catch (_) {}

  // Last-resort: monthly bucket so keys don’t explode every run
  var now = new Date();
  var pad3 = n => ('0' + n).slice(-2);
  return 'local' + now.getFullYear() + pad3(now.getMonth()+1);
}


/** ================= CONFIG ================= **/
const CONFIG = {
  // If bound to the spreadsheet, leave SPREADSHEET_ID: ''.
  // If standalone, paste the long ID below:
  SPREADSHEET_ID: '1gfo_jQeIuQozxcgTuraUpU1AYvKAhD1WkDqfQooKdsk',

  INPUT_SHEET: 'New Addresses',
  UPDATED_SHEET: 'Updated Addresses',   // <— NEW
  STREETS_SHEET: 'Street Database',
  STREETS_HEADER: 'Streets',
  LOOKUPS_SHEET: 'Lookups',
  LOOKUP_HEADERS: {
  type: 'Type',
  apartmentBusiness: 'Apartment/Business',
  unit: 'Unit',
  number: 'Number',
  language: 'Language',
  notes: 'Notes',
  maps: 'Maps' // <-- NEW
},


  CACHE_TTL_SECS: 10800,      // 3 hours
  CACHE_CHUNK_SIZE: 90000,    // <100KB per CacheService entry
  CACHE_VERSION: _computeCacheVersion_()         // bump to force fresh cache
};


/** ===== Logging & Timing helpers ===== **/
function _nowMs_(){ return new Date().getTime(); }
function _iso_(){ return new Date().toISOString(); }

function _log_(lvl, msg, meta){
  const text = (msg == null) ? '(no message)' : String(msg);
  if (meta !== undefined) {
    try { console[lvl](text + ' ' + JSON.stringify(meta)); }
    catch (_){ console[lvl](text + ' (meta_unserializable)'); }
  } else {
    console[lvl](text);
  }
}

function logInfo(msg, meta){ _log_('info', msg, meta); }
function logWarn(msg, meta){ _log_('warn', msg, meta); }
function logError(msg, meta){ _log_('error', msg, meta); }

/** Time a function and log duration + outcome. Returns fn() result. */

function withTiming(name, fn){
  if (typeof fn !== 'function') {
    logError('withTiming misuse', { name, type: typeof fn });
    throw new TypeError('withTiming(fn) expects a function');
  }
  const t0 = _nowMs_();
  try {
    const res = fn();
    const meta = { ms: _nowMs_() - t0 };
    // If the result has an ok flag, include it
    if (res && typeof res === 'object' && 'ok' in res) meta.ok = !!res.ok;
    logInfo(String(name) + ' ok', meta);
    return res;
  } catch (err) {
    logError(String(name) + ' failed', { ms: _nowMs_() - t0, error: String(err) });
    throw err;
  }
}

/** Always-return wrapper: logs error but returns fallback shape */
function withFallback(name, fn, fallbackVal){
  if (typeof fn !== 'function') {
    logError('withFallback misuse', { name: String(name), type: typeof fn, stack: (new Error()).stack });
    return fallbackVal;
  }
  const t0 = _nowMs_();
  try {
    const res = fn();
    logInfo(String(name) + ' ok', { ms: _nowMs_() - t0 });
    return res;
  } catch (err) {
    logError(String(name) + ' failed', { ms: _nowMs_() - t0, error: String(err) });
    return fallbackVal;
  }
}


/** Correlation ID for this execution */
function _reqId_(){
  if (!globalThis.__RID__) globalThis.__RID__ = Utilities.getUuid().slice(0, 8);
  return globalThis.__RID__;
}
/** Wrap meta with reqId automatically */
function _withReqId_(meta){
  const m = (meta && typeof meta === 'object') ? meta : (meta === undefined ? {} : { meta });
  m.reqId = _reqId_();
  return m;
}
// Patch the log fns to always include reqId
const _origLogInfo = logInfo;
const _origLogWarn = logWarn;
const _origLogError = logError;
logInfo  = (msg, meta) => _origLogInfo(msg,  _withReqId_(meta));
logWarn  = (msg, meta) => _origLogWarn(msg,  _withReqId_(meta));
logError = (msg, meta) => _origLogError(msg, _withReqId_(meta));


/** Ensure lookups are never empty so the UI stays usable */
function _ensureMinimumLookupsServer_(out) {
  if (!out || typeof out !== 'object') return;
  if (!Array.isArray(out.type) || out.type.length === 0) {
    out.type = ['House', 'Apartment', 'Business', 'Other'];
  }
  if (!Array.isArray(out.apartmentBusiness)) out.apartmentBusiness = [];
  if (!Array.isArray(out.unit)) out.unit = [];
  if (!Array.isArray(out.number)) out.number = [];
  if (!Array.isArray(out.language)) out.language = [];
  if (!Array.isArray(out.notes)) out.notes = [];
  if (!Array.isArray(out.maps)) out.maps = [];

}

/** =============== PUBLIC RPCs (first set) =============== **/
function getLookups() {
  return withFallback('getLookups', () => {
    const byCols = JSON.parse(_cacheGetOrBuild_('lookups_by_columns', _readLookupsByColumnsJSON_)) || {};
    const ensure = (k) => (Array.isArray(byCols[k]) && byCols[k].length) ? byCols[k] : _getLookupList_(k) || [];

    const streets   = JSON.parse(_cacheGetOrBuild_('streets', _readStreetsJSON_)) || [];
    const typesRaw  = ensure('type');
    const unitRaw   = ensure('unit');
    const numberRaw = ensure('number');
    const langRaw   = ensure('language');
    const notesRaw  = ensure('notes');
    const abRaw     = ensure('apartmentBusiness');
    const mapsRaw   = ensure('maps');

    const typePinned = _orderTypesPreferred_(typesRaw, ['House','Apartment','Business','Other']) || [];

    const unitFreq     = _getFreqFromInputCached_('Unit')    || { counts:{}, display:{} };
    const numberFreq   = _getFreqFromInputCached_('Number')  || { counts:{}, display:{} };
    const unitSorted   = _sortByFrequencyThenAlpha_(unitRaw, unitFreq)     || [];
    const numberSorted = _sortByFrequencyThenAlpha_(numberRaw, numberFreq) || [];

    const out = {
      streets,
      type:              typePinned,
      apartmentBusiness: abRaw,
      unit:              unitSorted,
      number:            numberSorted,
      language:          langRaw,
      notes:             notesRaw,
      maps:              mapsRaw 
    };

    _ensureMinimumLookupsServer_(out);

    const sizes = Object.fromEntries(Object.entries(out).map(([k,v]) => [k, (Array.isArray(v)?v:[]).length]));
    logInfo('getLookups sizes', sizes);
    return out;

  }, {
    streets: [],
    type: ['House','Apartment','Business','Other'],
    apartmentBusiness: [],
    unit: [],
    number: [],
    language: [],
    notes: [],
    maps: []
  });
}


// Append a row by matching values to existing headers (case/diacritic tolerant + aliases)
function _appendByHeaders_(sheet, headerValueMap) {
  const lastCol = Math.max(sheet.getLastColumn(), 1);
  const rawHeaders = sheet.getRange(1, 1, 1, lastCol)
    .getDisplayValues()[0]
    .map(h => String(h || '').trim());

  // Trim trailing blank header cells
  let realCols = rawHeaders.length;
  while (realCols > 1 && !rawHeaders[realCols - 1]) realCols--;
  const H = rawHeaders.slice(0, realCols);
  if (!H.length) {
    logWarn('_appendByHeaders_: no headers on sheet', { sheet: sheet.getName() });
    return;
  }

  const norm = s => String(s || '')
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase().replace(/\s+/g, ' ').trim();

  // Helpful short/variant header names seen in the wild
  const ALIASES = {
    'apartment/business': ['apartment / business','apartment','business','apartmentbusiness','apt/business','apt / business'],
    'number':             ['no','num','house number','house #','#','house no','house no.'],
    'street':             ['street, suburb','street , suburb','address','addr','street name'],
    'language':           ['lang'],
    'notes':              ['note'],
    'unit':               ['flat','apt','apartment #','unit #'],
    'longitude':          ['long','lng','lon','x','x coord','x-coordinate'],
    'latitude':           ['lat','y','y coord','y-coordinate'],
    'map':                ['map ref','mapref'] // Updated sheet uses "Map" (singular)
  };

  const Hn = H.map(norm);
  function findIndexForKey(key) {
    const W = norm(key);

    // 1) exact
    let i = Hn.indexOf(W);
    if (i >= 0) return i;

    // 2) header starts with want  (e.g., header "longitude (x)" vs want "longitude")
    i = Hn.findIndex(h => h.startsWith(W));
    if (i >= 0) return i;

    // 3) want starts with header  (e.g., want "longitude" vs header "long")
    i = Hn.findIndex(h => W.startsWith(h));
    if (i >= 0) return i;

    // 4) aliases (retry all three ways for each alias)
    const aliasList = ALIASES[W] || [];
    for (const a of aliasList) {
      const A = norm(a);
      i = Hn.indexOf(A);                      if (i >= 0) return i;
      i = Hn.findIndex(h => h.startsWith(A)); if (i >= 0) return i;
      i = Hn.findIndex(h => A.startsWith(h)); if (i >= 0) return i;
    }
    return -1;
  }

  // Build the row in header order
  const row = new Array(H.length).fill('');
  const missing = [];
  Object.keys(headerValueMap || {}).forEach(k => {
    const idx = findIndexForKey(k);
    if (idx >= 0) {
      row[idx] = headerValueMap[k];
    } else {
      missing.push(k);
    }
  });

  if (missing.length) {
    logWarn('_appendByHeaders_ missing headers', {
      sheet: sheet.getName(),
      missing,
      headers: H
    });
  }

  sheet.getRange(sheet.getLastRow() + 1, 1, 1, row.length).setValues([row]);
}



// Handle form submission (strict Type validation; writes Longitude/Latitude)
function submitAddress(payload) {
  return withTiming('submitAddress', () => {
    if (!payload || typeof payload !== 'object') {
      logWarn('submitAddress bad payload', { type: typeof payload });
      return { ok: false, message: 'Invalid submission (no payload).' };
    }

    const get = (K) => {
      const direct = _safe(payload[K]);
      if (direct) return direct;
      if (K === 'Number') return _safe(payload.HouseNumber);
      return _safe(payload[String(K).toLowerCase()]);
    };

    const num    = get('Number');
    const street = get('Street');
    if (!num || !street) {
      logWarn('submitAddress missing fields', { num: !!num, street: !!street });
      return { ok: false, message: 'Please enter both Number and Street.' };
    }

    // Type validation (if present)
    const typeVal = get('Type');
    const allowedTypes = _getLookupList_('type');
    if (typeVal && allowedTypes.length && !allowedTypes.includes(typeVal)) {
      logWarn('submitAddress invalid type', { typeVal });
      return { ok: false, message: 'Invalid Type. Please select a value from the dropdown.' };
    }

    // === Update/Correction flow detection ===
    const notes = get('Notes') || '';
    // accept "wrong", "update", or "updated"
    const isUpdateNote = /\b(wrong|update(?:d)?)\b/i.test(notes);
    const hasMap       = !!get('Map');

    // If user indicates an update but forgot Map, enforce Map
    if (isUpdateNote && !hasMap) {
      logWarn('submitAddress update missing Map');
      return { ok:false, message:'Please select a Map for updates (“wrong” or “update”).' };
    }

    // Choose destination sheet
    const destSheetName = (isUpdateNote && hasMap) ? CONFIG.UPDATED_SHEET : CONFIG.INPUT_SHEET;

    const ss = _openSpreadsheet_();
    const sh = _getOrCreateSheet_(ss, destSheetName);

    // Ensure headers exist on the chosen sheet
    const HEADERS_NEW = ['Type','Apartment/Business','Unit','Number','Street','Language','Notes','Longitude','Latitude'];            // no Map
    const HEADERS_UPD = ['Type','Apartment/Business','Unit','Number','Street','Language','Notes','Map','Longitude','Latitude'];     // with Map
    if (sh.getLastRow() === 0) {
      sh.appendRow(destSheetName === CONFIG.UPDATED_SHEET ? HEADERS_UPD : HEADERS_NEW);
    }

    const lock = LockService.getScriptLock();
    if (!lock.tryLock(30000)) {
      logWarn('submitAddress lock busy');
      return { ok:false, message:'Busy, please try again.' };
    }

    try {
      // Build values by header name so columns always line up
      const base = {
        'Type':               typeVal,
        'Apartment/Business': get('ApartmentBusiness'),
        'Unit':               get('Unit'),
        'Number':             num,
        'Street':             street,
        'Language':           get('Language'),
        'Notes':              notes,
        'Longitude':          get('Longitude'),
        'Latitude':           get('Latitude')
    };
    if (destSheetName === CONFIG.UPDATED_SHEET) base['Map'] = get('Map');

    _appendByHeaders_(sh, base);

    logInfo('submitAddress saved', { type: typeVal, number: num, dest: destSheetName, update: isUpdateNote });
    return { ok: true, message: 'Saved' };
  } catch (e) {
    logError('submitAddress error', { error: String(e) });
    return { ok: false, message: 'Error: ' + e };
  } finally {
    lock.releaseLock();
  }
});
}


function verifyHeaders() {
  const ss = _openSpreadsheet_();
  const shNew = _getOrCreateSheet_(ss, CONFIG.INPUT_SHEET);
  const shUpd = _getOrCreateSheet_(ss, CONFIG.UPDATED_SHEET);

  const HEADERS_NEW = ['Type','Apartment/Business','Unit','Number','Street','Language','Notes','Longitude','Latitude'];
  const HEADERS_UPD = ['Type','Apartment/Business','Unit','Number','Street','Language','Notes','Map','Longitude','Latitude'];

  function ensure(sh, want){
    if (sh.getLastRow() === 0) { sh.appendRow(want); return 'created'; }
    const got = sh.getRange(1,1,1,Math.max(sh.getLastColumn(), want.length))
                  .getDisplayValues()[0]
                  .slice(0, want.length);
    if (JSON.stringify(got) !== JSON.stringify(want)) {
      sh.getRange(1,1,1,want.length).setValues([want]);
      return 'patched';
    }
    return 'ok';
  }

  return { new: ensure(shNew, HEADERS_NEW), updated: ensure(shUpd, HEADERS_UPD) };
}


/** =============== FREQUENCY + INPUT READERS =============== **/
function _readInputColumn_(headerText) {
  const ss = _openSpreadsheet_();
  const sh = ss.getSheetByName(CONFIG.INPUT_SHEET);
  if (!sh) return [];
  const lastRow = sh.getLastRow(), lastCol = sh.getLastColumn();
  if (lastRow < 2) return [];
  const heads = sh.getRange(1,1,1,lastCol).getValues()[0].map(h => String(h).trim());
  const norm = (s)=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  let col = heads.findIndex(h => norm(h) === norm(headerText)) + 1;
  if (!col) col = heads.findIndex(h => norm(h).startsWith(norm(headerText))) + 1;
  if (!col) return [];
  return sh.getRange(2, col, lastRow-1, 1).getValues()
           .map(r => _safe(r[0]))
           .filter(Boolean);
}

function _freqFromValues_(values) {
  const counts = Object.create(null);
  const display = Object.create(null);
  const norm = (s)=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  for (const raw of values || []) {
    const v = _safe(raw);
    if (!v) continue;
    const k = norm(v);
    counts[k] = (counts[k]||0) + 1;
    if (!display[k]) display[k] = v;
  }
  return { counts, display };
}

function _buildFreqJSON_(headerText) {
  const values = _readInputColumn_(headerText);
  const freq = _freqFromValues_(values);
  return JSON.stringify(freq);
}

function _getFreqFromInputCached_(headerText) {
  const cacheKey = 'freq_' + headerText;
  try {
    const json = _cacheGetOrBuild_(cacheKey, () => _buildFreqJSON_(headerText));
    const obj = JSON.parse(json);
    if (obj && obj.counts && obj.display) return obj;
    return { counts:{}, display:{} };
  } catch (e) {
    console.error('_getFreqFromInputCached_ error:', headerText, e);
    return { counts:{}, display:{} };
  }
}

function _sortByFrequencyThenAlpha_(values, freqObj) {
  const arr = Array.isArray(values) ? values.slice() : [];
  const counts = (freqObj && freqObj.counts) || {};
  const norm = (s)=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();

  const enriched = arr.map(v => {
    const s = _safe(v);
    const k = norm(s);
    const count = counts[k] || 0;
    const isNum = /^\d+$/.test(s);
    const numVal = isNum ? parseInt(s,10) : NaN;
    return { s, k, count, isNum, numVal };
  });

  enriched.sort((a,b) => {
    if (b.count !== a.count) return b.count - a.count;       // 1) frequency desc
    if (a.isNum !== b.isNum) return a.isNum ? -1 : 1;        // 2) numbers first
    if (a.isNum && b.isNum) return a.numVal - b.numVal;      // 3) numeric asc
    return a.s.toLowerCase().localeCompare(b.s.toLowerCase());// 4) alpha
  });

  return enriched.map(o => o.s);
}


/** =============== CACHE CORE (chunked) =============== **/
function _nsKey_(key){ return `addr_${CONFIG.CACHE_VERSION}_${key}`; }

function _cacheGetOrBuild_(key, builderFn) {
  const cache = CacheService.getScriptCache();
  const manifestKey = _nsKey_(key) + '_manifest';
  const m = cache.get(manifestKey);

  if (!m) {
    logWarn('cache miss (manifest)', { key });
    const json = withTiming('cache.build.' + key, builderFn);
    _cachePutChunked_(key, json);
    return json;
  }

  let chunks = 0;
  try {
    ({ chunks } = JSON.parse(m));
  } catch (e) {
    logError('cache manifest parse error', { key, manifest: m.slice(0,100) });
    const json = withTiming('cache.rebuild.badmanifest.' + key, builderFn);
    _cachePutChunked_(key, json);
    return json;
  }

  const parts = [];
  for (let i = 0; i < chunks; i++) {
    const piece = cache.get(_nsKey_(key) + `_part_${i}`);
    if (piece === null) {
      logWarn('cache chunk missing', { key, chunk: i, chunks });
      const json = withTiming('cache.rebuild.missing.' + key, builderFn);
      _cachePutChunked_(key, json);
      return json;
    }
    parts.push(piece);
  }
  return parts.join('');
}

function _cachePutChunked_(key, json) {
  const cache = CacheService.getScriptCache();
  const CHUNK = CONFIG.CACHE_CHUNK_SIZE;
  const total = Math.ceil(json.length / CHUNK);
  for (let i = 0; i < total; i++) {
    cache.put(_nsKey_(key) + `_part_${i}`, json.slice(i*CHUNK, (i+1)*CHUNK), CONFIG.CACHE_TTL_SECS);
  }
  cache.put(_nsKey_(key) + '_manifest', JSON.stringify({ chunks: total }), CONFIG.CACHE_TTL_SECS);
  logInfo('cache put', { key, bytes: json.length, chunks: total, ttl: CONFIG.CACHE_TTL_SECS });
}


/** =============== READERS =============== **/
function _openSpreadsheet_() {
  if (CONFIG.SPREADSHEET_ID) return SpreadsheetApp.openById(CONFIG.SPREADSHEET_ID);
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  if (!ss) throw new Error('No active spreadsheet. Bind this script to "Add New Addresses" or set CONFIG.SPREADSHEET_ID.');
  return ss;
}
function _getOrCreateSheet_(ss, name){ return ss.getSheetByName(name) || ss.insertSheet(name); }
function _safe(v){ return (v==null?'':String(v)).trim(); }
function _norm(s){ return String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase(); }

function _readColumn_(sheetName, headerText) {
  const ss = _openSpreadsheet_();
  const sh = ss.getSheetByName(sheetName);
  if (!sh) return [];
  const lastRow = sh.getLastRow(), lastCol = sh.getLastColumn();
  if (lastRow < 2) return [];
  const heads = sh.getRange(1,1,1,lastCol).getValues()[0].map(h => String(h).trim());
  let col = heads.findIndex(h => _norm(h) === _norm(headerText)) + 1;
  if (!col) col = heads.findIndex(h => _norm(h).startsWith(_norm(headerText))) + 1; // tolerant match
  if (!col) return [];
  return sh.getRange(2, col, lastRow-1, 1).getValues()
           .map(r => _safe(r[0]))
           .filter(Boolean);
}

function _uniqueSortCaseDiacriticSafe_(arr) {
  const seen = Object.create(null), out = [];
  for (const v of arr) {
    const k = _norm(v);
    if (!seen[k]) { seen[k] = true; out.push(v); }
  }
  out.sort((a,b)=>a.localeCompare(b,'en',{sensitivity:'base'}));
  return out;
}

// --- Tolerant header finder (fix) ---
function _findHeaderCol_Tolerant_(sheet, headerText){
  const lastCol = sheet.getLastColumn() || 1;
  const row = sheet.getRange(1,1,1,lastCol).getDisplayValues()[0].map(x=>String(x||'').trim());
  const want = _norm(headerText);
  let idx = row.findIndex(h => _norm(h) === want);
  if (idx >= 0) return idx + 1;

  // Common variants
  const candidates = ['streets','street','street, suburb','street , suburb','address','addresses'];
  idx = row.findIndex(h => candidates.includes(_norm(h)));
  if (idx >= 0) return idx + 1;

  // Starts with "street"
  idx = row.findIndex(h => _norm(h).startsWith('street'));
  if (idx >= 0) return idx + 1;

  // Fallback: first non-empty column
  idx = row.findIndex(h => _norm(h).length);
  return (idx >= 0) ? (idx + 1) : -1;
}

// Streets: "Street, Suburb" list from Street Database (robust)
function _readStreetsJSON_() {
  const ss = _openSpreadsheet_();
  const sh = ss.getSheetByName(CONFIG.STREETS_SHEET);
  if (!sh) return JSON.stringify([]);
  const colIdx = _findHeaderCol_Tolerant_(sh, CONFIG.STREETS_HEADER);
  if (colIdx === -1) {
    logWarn('Street header not found; returning empty list');
    return JSON.stringify([]);
  }
  const rows = Math.max(sh.getLastRow()-1, 0);
  if (rows <= 0) return JSON.stringify([]);
  const vals = sh.getRange(2, colIdx, rows, 1).getDisplayValues().flat();
  const list = vals.map(s => String(s||'').trim()).filter(Boolean);
  return JSON.stringify(_uniqueSortCaseDiacriticSafe_(list));
}

// Lookups for all inputs (raw read from Lookups sheet)
function _readLookupJSON_(key) {
  const header = CONFIG.LOOKUP_HEADERS[key];
  const col = _readColumn_(CONFIG.LOOKUPS_SHEET, header);
  return JSON.stringify(_uniqueSortCaseDiacriticSafe_(col));
}

// Lookups for all inputs — strictly from the Lookups sheet (no defaults)
function _getLookupList_(key) {
  try {
    const cached = _cacheGetOrBuild_('lookup_' + key, () => _readLookupJSON_(key));
    const arr = JSON.parse(cached);
    return Array.isArray(arr) ? arr : [];
  } catch (e) {
    console.error('_getLookupList_ error for key:', key, e);
    return [];
  }
}

/** read Lookups whole columns A..F (Type..Notes), rows 2..last, cached */
function _readLookupsByColumnsJSON_() {
  const ss = _openSpreadsheet_();
  const sh = ss.getSheetByName(CONFIG.LOOKUPS_SHEET);
  const empty = { type:[], apartmentBusiness:[], unit:[], number:[], language:[], notes:[], maps:[] };
  if (!sh) return JSON.stringify(empty);

  const lastRow = sh.getLastRow();
  if (lastRow < 2) return JSON.stringify(empty);

  const vals = sh.getRange(2, 1, lastRow - 1, 7).getValues(); // A..G
  const col = (i) => vals.map(r => _safe(r[i])).filter(Boolean);
  const uniq = (arr) => _uniqueSortCaseDiacriticSafe_(arr);

  const out = {
    type:              uniq(col(0)), // A
    apartmentBusiness: uniq(col(1)), // B
    unit:              uniq(col(2)), // C
    number:            uniq(col(3)), // D
    language:          uniq(col(4)), // E
    notes:             uniq(col(5)), // F
    maps:              uniq(col(6)), // G  <-- NEW
  };
  return JSON.stringify(out);
}


/** =============== Helpers runnable from editor =============== **/
function setupSheetsOnce() {
  const ss = _openSpreadsheet_();

  const shNew     = _getOrCreateSheet_(ss, CONFIG.INPUT_SHEET);
  if (shNew.getLastRow() === 0) {
    shNew.appendRow(['Type','Apartment/Business','Unit','Number','Street','Language','Notes','Longitude','Latitude']);
  }

  const shStreets = _getOrCreateSheet_(ss, CONFIG.STREETS_SHEET);
  if (shStreets.getLastRow() === 0) {
    shStreets.getRange(1,1).setValue(CONFIG.STREETS_HEADER);
  }

  const shLookups = _getOrCreateSheet_(ss, CONFIG.LOOKUPS_SHEET);
  if (shLookups.getLastRow() === 0) {
    shLookups.getRange(1,1,1,7).setValues([['Type','Apartment/Business','Unit','Number','Language','Notes','Maps']]);
  }

  const shUpd     = _getOrCreateSheet_(ss, CONFIG.UPDATED_SHEET);
  if (shUpd.getLastRow() === 0) {
    shUpd.appendRow(['Type','Apartment/Business','Unit','Number','Street','Language','Notes','Map','Longitude','Latitude']);
  }

  // NEW: ensure headers are exact even if someone edited them later
  const status = verifyHeaders();
  logInfo('setupSheetsOnce.verifyHeaders', status);

  SpreadsheetApp.flush();
  return 'Sheets ready';
}




/** =============== (Optional) server reverse geocode (first version) =============== **/
function reverseGeocodeStreet(lat, lon, provider) {
  const la = Number(lat), lo = Number(lon);
  logInfo('reverseGeocodeStreet.start', { lat: la, lon: lo, provider });

  return withFallback('reverseGeocodeStreet', () => {
    if (!isFinite(la) || !isFinite(lo)) {
      logWarn('reverseGeocodeStreet.invalid_coords', { lat, lon });
      return { ok:false, message:'Invalid coordinates' };
    }

    const want = (String(provider||'').toLowerCase() === 'nominatim') ? 'nominatim' : 'photon';
    const tryNom = () => withTiming('reverse.nominatim', () => _reverseNominatim_(la, lo));
    const tryPho = () => withTiming('reverse.photon',    () => _reversePhoton_(la, lo));
    const hasAddr = (r) => r && (String(r.street||'').trim() || String(r.suburb||'').trim());

    let res   = (want === 'nominatim') ? tryNom() : tryPho();
    let used  = want;

    if (!hasAddr(res)) {
      const alt = (want === 'nominatim') ? tryPho() : tryNom();
      if (hasAddr(alt)) { res = alt; used = (want === 'nominatim') ? 'photon' : 'nominatim'; }
    }

    if (hasAddr(res)) {
      logInfo('reverseGeocodeStreet.result', { provider: used, hasStreet: !!res.street, hasSuburb: !!res.suburb });
      return Object.assign({ ok:true, provider: used }, res);
    } else {
      const msg = res && res.message ? res.message : 'No address found';
      logWarn('reverseGeocodeStreet.result_empty', { provider: used, message: msg });
      return { ok:false, provider: used, message: msg };
    }
  }, { ok:false, message:'Reverse geocode failed' });
}

function _reverseNominatim_(lat, lon) {
  const url = `https://nominatim.openstreetmap.org/reverse?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}&format=jsonv2&addressdetails=1`;
  try {
    const resp = UrlFetchApp.fetch(url, {
      muteHttpExceptions:true,
      followRedirects:true,
      headers: { 'User-Agent': 'AddNewAddresses/1.0 (+https://yourdomain.example/contact; you@yourdomain.example)' }
    });
    const code = resp.getResponseCode();
    const body = String(resp.getContentText() || '');
    if (code !== 200) {
      logWarn('nominatim.http_non200', { code, bodySnippet: body.slice(0, 300) });
      return { message:`Nominatim HTTP ${code}` };
    }
    let json;
    try { json = JSON.parse(body); }
    catch (e) {
      logError('nominatim.json_parse_error', { error: String(e), bodySnippet: body.slice(0, 300) });
      return { message:'Nominatim JSON parse error' };
    }
    const adr  = json && json.address || {};
    const street = adr.road || adr.pedestrian || adr.cycleway || adr.footway || '';
    const suburb = adr.suburb || adr.neighbourhood || adr.city_district || '';
    const city   = adr.city || adr.town || adr.village || adr.county || '';
    return { street, suburb, city, message:'' };
  } catch (e) {
    logError('nominatim.fetch_error', { error: String(e), url });
    return { message: 'Nominatim fetch error' };
  }
}

function _reversePhoton_(lat, lon) {
  var url = 'https://photon.komoot.io/reverse?lat=' + encodeURIComponent(lat) +
            '&lon=' + encodeURIComponent(lon) + '&limit=6';
  try {
    var resp = UrlFetchApp.fetch(url, {
      muteHttpExceptions: true,
      followRedirects: true,
      headers: { 'User-Agent': 'AddNewAddresses/1.0 (reverse-geocode)' },
      timeout: 10000
    });
    var code = resp.getResponseCode();
    var body = String(resp.getContentText() || '');
    if (code !== 200) {
      logWarn('photon.http_non200', { code: code, bodySnippet: body.slice(0, 300) });
      return { message: 'Photon HTTP ' + code };
    }

    var json = JSON.parse(body || '{}');
    var feat = json && json.features && json.features[0];
    if (!feat || !feat.properties) return { message: 'Photon empty' };

    var p = feat.properties || {};
    var street = p.street || p.name || p.road || '';
    var suburb = p.suburb || p.district || p.city || p.town || p.village || '';
    return {
      street: street || '',
      suburb: suburb || '',
      city: p.city || p.town || '',
      message: ''
    };
  } catch (e) {
    logError('photon.fetch_error', { error: String(e), url: url });
    return { message: 'Photon fetch error' };
  }
}

/** =============== CACHES/TRIGGERS MAINTENANCE =============== **/
function refreshAllCaches() {
  const t0 = _nowMs_();
  const summary = { lookups: {}, freqs: {} };

  try {
    withTiming('cache.build.streets', () => {
      const json = _readStreetsJSON_();
      const arr  = JSON.parse(json) || [];
      _cachePutChunked_('streets', json);
      logInfo('cache.streets.count', { count: arr.length });
      summary.streets = arr.length;
    });

    for (const key of Object.keys(CONFIG.LOOKUP_HEADERS)) {
      withTiming('cache.build.lookup_' + key, () => {
        const json = _readLookupJSON_(key);
        const arr  = JSON.parse(json) || [];
        _cachePutChunked_('lookup_' + key, json);
        logInfo('cache.lookup.count', { key, count: arr.length });
        summary.lookups[key] = arr.length;
      });
    }

    withTiming('cache.build.lookups_by_columns', () => {
      const json = _readLookupsByColumnsJSON_();
      const obj  = JSON.parse(json) || {};
      _cachePutChunked_('lookups_by_columns', json);
      const counts = Object.fromEntries(Object.entries(obj).map(([k,v]) => [k, (Array.isArray(v)?v:[]).length]));
      logInfo('cache.lookups_by_columns.counts', counts);
      summary.byColumns = counts;
    });

    withTiming('cache.build.freq.Unit', () => {
      const json = _buildFreqJSON_('Unit');
      const obj  = JSON.parse(json) || {counts:{},display:{}};
      _cachePutChunked_('freq_Unit', json);
      logInfo('cache.freq.unit.keys', { keys: Object.keys(obj.counts).length });
      summary.freqs.Unit = Object.keys(obj.counts).length;
    });

    withTiming('cache.build.freq.Number', () => {
      const json = _buildFreqJSON_('Number');
      const obj  = JSON.parse(json) || {counts:{},display:{}};
      _cachePutChunked_('freq_Number', json);
      logInfo('cache.freq.number.keys', { keys: Object.keys(obj.counts).length });
      summary.freqs.Number = Object.keys(obj.counts).length;
    });

    logInfo('refreshAllCaches ok', { ms: _nowMs_() - t0, summary });
    return 'OK';
  } catch (err) {
    logError('refreshAllCaches failed', { ms: _nowMs_() - t0, error: String(err), partial: summary });
    return 'OK';
  }
}

function ensure3HourTrigger() {
  const fn = 'refreshAllCaches';
  ScriptApp.getProjectTriggers()
    .filter(t => t.getHandlerFunction() === fn)
    .forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger(fn).timeBased().everyHours(3).create();
  return 'OK';
}

function _orderTypesPreferred_(arr, preferredOrder) {
  const list = Array.isArray(arr) ? arr.slice() : [];
  const pref = Array.isArray(preferredOrder) ? preferredOrder : [];
  const out = [];
  const seen = new Set();
  const key = (s) => String(s || '')
    .normalize('NFD').replace(/[\u0300-\u036f]/g,'')
    .toLowerCase();

  for (const want of pref) {
    const k = key(want);
    const hit = list.find(v => key(v) === k);
    if (hit && !seen.has(k)) { out.push(hit); seen.add(k); }
  }
  for (const v of list) {
    const k = key(v);
    if (!seen.has(k)) { out.push(v); seen.add(k); }
  }
  return out;
}


/** ================= Utilities (2nd set) ================= **/
function _nowMs_2(){ return Date.now(); }
function _iso_2(){ return new Date().toISOString(); }
function _log_2(tag, obj){ try { Logger.log('%s %s', tag, JSON.stringify(obj || {})); } catch(_){} }
function _norm_2(s){ return String(s || '').toLowerCase().replace(/\s+/g,' ').trim(); }

function _ss_(){
  if (CONFIG.SPREADSHEET_ID && CONFIG.SPREADSHEET_ID.trim())
    return SpreadsheetApp.openById(CONFIG.SPREADSHEET_ID.trim());
  return SpreadsheetApp.getActiveSpreadsheet();
}
function _sheet_(name){
  const sh = _ss_().getSheetByName(name);
  if (!sh) throw new Error('Missing sheet: ' + name);
  return sh;
}
function _findHeaderCol_(sheet, headerText){
  // Use tolerant finder to avoid empty streets (fix)
  return _findHeaderCol_Tolerant_(sheet, headerText);
}

/** ================= Cache (chunked JSON, 2nd set) ================= **/
function _cache_(){ return CacheService.getScriptCache(); }
function _ckey_(k){ return CONFIG.CACHE_VERSION + '::' + k; }

function cacheGetJSON(key){
  const cache = _cache_();
  const base = _ckey_(key);
  const head = cache.get(base + '::len');
  if (!head) {
    const single = cache.get(base);
    return single ? JSON.parse(single) : null;
  }
  const len = +head;
  let buf = '';
  for (let i=0;i<len;i++){
    const part = cache.get(base + '::' + i);
    if (!part) return null;
    buf += part;
  }
  return buf ? JSON.parse(buf) : null;
}

function cacheSetJSON(key, obj, ttl){
  const cache = _cache_();
  const base = _ckey_(key);
  const str = JSON.stringify(obj);
  if (str.length <= CONFIG.CACHE_CHUNK_SIZE){
    cache.put(base, str, ttl || CONFIG.CACHE_TTL_SECS);
    cache.remove(base + '::len');
    return;
  }
  const chunks = [];
  for (let i=0; i<str.length; i+=CONFIG.CACHE_CHUNK_SIZE){
    chunks.push(str.slice(i, i + CONFIG.CACHE_CHUNK_SIZE));
  }
  cache.put(base + '::len', String(chunks.length), ttl || CONFIG.CACHE_TTL_SECS);
  chunks.forEach((c, i) => cache.put(base + '::' + i, c, ttl || CONFIG.CACHE_TTL_SECS));
}

/** ================= Data Loaders (2nd set) ================= **/
function getStreetDatabase(){
  const CKEY = 'streets_db';
  const cached = cacheGetJSON(CKEY);
  if (cached) return cached;

  const sh = _sheet_(CONFIG.STREETS_SHEET);
  const col = _findHeaderCol_(sh, CONFIG.STREETS_HEADER); // tolerant
  if (col === -1) {
    _log_2('getStreetDatabase.header_missing', { header: CONFIG.STREETS_HEADER });
    cacheSetJSON(CKEY, [], CONFIG.CACHE_TTL_SECS);
    return [];
  }

  const vals = sh.getRange(2, col, Math.max(sh.getLastRow()-1,0), 1).getDisplayValues().flat();
  const list = vals.map(s => String(s||'').trim()).filter(Boolean);
  cacheSetJSON(CKEY, list, CONFIG.CACHE_TTL_SECS);
  return list;
}

function getLookups_2(){
  const CKEY = 'lookups';
  const cached = cacheGetJSON(CKEY);
  if (cached) return cached;

  const sh = _sheet_(CONFIG.LOOKUPS_SHEET);
  const headerRow = sh.getRange(1,1,1, sh.getLastColumn()).getDisplayValues()[0];
  const idxByKey = {};
  Object.keys(CONFIG.LOOKUP_HEADERS).forEach(k => {
    const want = CONFIG.LOOKUP_HEADERS[k];
    // tolerant header matching
    const idxHard = headerRow.findIndex(h => _norm_2(h) === _norm_2(want));
    const idxSoft = headerRow.findIndex(h => _norm_2(h).startsWith(_norm_2(want)));
    idxByKey[k] = (idxHard >= 0 ? idxHard : idxSoft);
  });

  const rows = Math.max(sh.getLastRow()-1, 0);
  const out = { type:[], apartmentBusiness:[], unit:[], number:[], language:[], notes:[], maps:[] };

  if (rows > 0){
    const data = sh.getRange(2,1, rows, sh.getLastColumn()).getDisplayValues();
    Object.keys(idxByKey).forEach(k => {
      const idx = idxByKey[k];
      if (idx < 0) return;
      const set = new Set();
      for (let r=0;r<data.length;r++){
        const v = String(data[r][idx] || '').trim();
        if (v) set.add(v);
      }
      out[k] = Array.from(set);
    });
  }
  cacheSetJSON(CKEY, out, CONFIG.CACHE_TTL_SECS);
  return out;
}

/** ================= Public: hydration / options (2nd set) ================= **/
function hydrateCombos(){
  const payload = {
    streets: getStreetDatabase(),
    lookups: getLookups_2(),
    cacheVersion: CONFIG.CACHE_VERSION,
    ts: _iso_2()
  };
  _log_2('hydrateCombos', {counts:{streets: payload.streets.length}});
  return payload;
}

function fillTypeOptions(){  // retained for legacy editor testing; client uses its own fill
  const look = getLookups_2();
  return look.type || [];
}

function getState(){
  return { now: _iso_2(), cacheVersion: CONFIG.CACHE_VERSION };
}

/** --- Simple canonical street snap for GPS flow --- **/
function matchKnownStreet(street, suburb) {
  try {
    const list = JSON.parse(_cacheGetOrBuild_('streets', _readStreetsJSON_)) || [];
    const n = s => String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();
    const ns = n(street);
    const nb = n(suburb);
    let best = '';
    for (const raw of list) {
      const parts = String(raw||'').split(',');
      const st = (parts[0]||'').trim();
      const sub = (parts.slice(1).join(',')||'').trim();
      if (!st) continue;
      if (n(st) === ns && (!nb || n(sub) === nb)) return raw;
      if (!best && n(st) === ns) best = raw;
    }
    return best; // '' if nothing
  } catch (e) {
    logWarn('matchKnownStreet error', { error: String(e) });
    return '';
  }
}

// --- Unified hydration used by client ---
function getLookupsHydrated() {
  try {
    var look = getLookups_2();
    var streets = getStreetDatabase();
    function arr(x){ return Array.isArray(x) ? x : []; }
    const out = {
      streets: arr(streets),
      type: arr(look.type),
      apartmentBusiness: arr(look.apartmentBusiness),
      unit: arr(look.unit),
      number: arr(look.number),
      language: arr(look.language),
      notes: arr(look.notes),
      maps: arr(look.maps)
    };
    _ensureMinimumLookupsServer_(out);
    return out;
  } catch (e) {
    try { logError('getLookupsHydrated failed', { error: String(e) }); } catch(_){}
    return {
      streets: [],
      type: ['House','Apartment','Business','Other'],
      apartmentBusiness: [],
      unit: [],
      number: [],
      language: [],
      notes: [],
      maps: []
    };
  }
}

function test_GetLookupsHydrated(){
  var x = getLookupsHydrated();
  Logger.log(JSON.stringify({
    streets: (x.streets||[]).length,
    type: (x.type||[]).slice(0,4),
    unit: (x.unit||[]).length,
    number: (x.number||[]).length
  }, null, 2));
}


/** ========= UI + Cache Reset (server) ========= */
function _purgeAllCaches_() {
  const cache = CacheService.getScriptCache();

  // Cache system #1 (namespaced, chunked): keys controlled via _nsKey_()
  const nsKeys = ['streets', 'lookups_by_columns', 'freq_Unit', 'freq_Number']
    .concat(Object.keys(CONFIG.LOOKUP_HEADERS).map(k => 'lookup_' + k));

  nsKeys.forEach(key => {
    const base = _nsKey_(key);
    try {
      const manifest = cache.get(base + '_manifest');
      if (manifest) {
        var chunks = 0;
        try { chunks = JSON.parse(manifest).chunks || 0; } catch (_){}
        for (var i = 0; i < chunks; i++) cache.remove(base + '_part_' + i);
        cache.remove(base + '_manifest');
      }
      // In case something was written as a single value
      cache.remove(base);
    } catch (_){}
  });

  // Cache system #2 (CONFIG.CACHE_VERSION + '::' + key, optional ::len + parts)
  const vKeys = ['streets_db', 'lookups'];
  vKeys.forEach(key => {
    const base = _ckey_(key);
    try {
      const lenStr = cache.get(base + '::len');
      const n = lenStr ? +lenStr : 0;
      for (var i = 0; i < n; i++) cache.remove(base + '::' + i);
      cache.remove(base + '::len');
      cache.remove(base);
    } catch (_){}
  });
}

/** Call this from client: google.script.run.resetUI()
 *  Returns fresh lookups so the UI can re-hydrate immediately.
 */
function resetUI() {
  return withFallback('resetUI', () => {
    _purgeAllCaches_();       // wipe caches we own
    refreshAllCaches();       // rebuild everything (streets, lookups, freqs)
    const payload = getLookupsHydrated(); // same shape your UI loader expects
    logInfo('resetUI complete', { cacheVersion: CONFIG.CACHE_VERSION });
    return {
      ok: true,
      cacheVersion: CONFIG.CACHE_VERSION,
      when: _iso_(),
      payload: payload
    };
  }, { ok: false, message: 'reset failed' });
}

function resetUIFromEditor() {
  const res = resetUI();
  Logger.log(JSON.stringify(res, null, 2));
  return 'OK';
}

/** =============== WEB APP ENTRY (single version) =============== **/
function doGet(e) {
  // Lightweight health/version probes
  if (e && e.parameter) {
    if (e.parameter.ping) {
      return ContentService.createTextOutput('OK');
    }
    if (e.parameter.v === '1') {
      return ContentService.createTextOutput(JSON.stringify({
        version: CONFIG.CACHE_VERSION,
        when: _iso_()
      })).setMimeType(ContentService.MimeType.JSON);
    }
  }

  // Isolation test toggle: add ?mini=1 (or ?isotest=1 or ?index=mini) to the URL
  const p = (e && e.parameter) || {};
  const toLower = v => String(v || '').toLowerCase();
  const wantMini =
    ('mini' in p && (!p.mini || ['1','true','yes'].includes(toLower(p.mini)))) ||
    ['1','true','yes'].includes(toLower(p.isotest)) ||
    toLower(p.index) === 'mini';
    
  logInfo('doGet.toggle', { wantMini, params: p });
  if (wantMini) {
    logInfo('doGet.IndexMini', { when: _iso_() });
    return withTiming('doGet.IndexMini', () => {
      const t = HtmlService.createTemplateFromFile('IndexMini'); // isolation file
      t.appTitle = 'Address Entry';
      t.buildTag = CONFIG.CACHE_VERSION;
      try { t.webAppUrl = ScriptApp.getService().getUrl() || ''; } catch (_) { t.webAppUrl = ''; }
      return t.evaluate()
        .setTitle(t.appTitle)
        .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
    });
  }

  // Normal UI render
  logInfo('doGet', { when: _iso_() });
  return withTiming('doGet.template', () => {
    const t = HtmlService.createTemplateFromFile('Index'); // main file
    t.appTitle = 'Address Entry';
    t.buildTag = CONFIG.CACHE_VERSION;
    try { t.webAppUrl = ScriptApp.getService().getUrl() || ''; } catch (_) { t.webAppUrl = ''; }
    return t.evaluate()
      .setTitle(t.appTitle)
      .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
  });
}



function submitAddressFromEditor() {
  return submitAddress({
    Type: 'House',
    ApartmentBusiness: '',
    Unit: '',
    Number: '10',
    Street: 'Queen Street, Auckland',
    Language: 'English',
    Notes: 'TEST',
    Longitude: '174.7633',
    Latitude: '-36.8485'
  });
}
