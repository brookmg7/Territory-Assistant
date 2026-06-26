# FileSummaries.py
#
# Generates: python_modules.md (compact but ChatGPT-friendly)
#
# Goals:
# - Group linked modules into connected components (imports + bat references)
# - Within each group: "Start Here", "Critical Paths", subsystem buckets, mini dep maps
# - Per-module summaries: role, responsibilities, key internal links (resolved to real files), risk notes
# - Summarize .py and .bat
# - Replace old outputs every run
# - Print a Run Stats block after finishing (as requested)

from __future__ import annotations
import shutil
from pathlib import Path
from typing import Iterable
import ast
import re
from pathlib import Path
from typing import List, Set, Dict, Tuple, Optional, Iterable
from collections import defaultdict, deque, Counter

# ============================
# CONFIG
# ============================
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_FOLDER = SCRIPT_DIR
RECURSIVE = True

# ============================
# OUTPUT LOCATION (PORTABLE)
# ============================

# Save next to this script, in a sibling folder named: "File Summary"
OUTPUT_DIR = SCRIPT_DIR / "File Summary"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SUMMARY_MD = OUTPUT_DIR / "python_modules.md"

# ============================
# EXTRA ROOTS (MQL5)
# ============================

# Scan the MIRRORED "latest" MQL5 Experts folder (kept in OneDrive).
# IMPORTANT: This must NOT reference ONEDRIVE_DST_DIR here because ONEDRIVE_DST_DIR
# is defined later in the file. Keep this as a direct Path to avoid NameError.
# (It intentionally matches ONEDRIVE_DST_DIR below.)
MQL5_SCAN_DIR = Path(r"C:\Users\brook\OneDrive\Desktop\Python_AI Bot\MQL5_Experts_Brook")

# Scan MQL5 files too
MQL5_EXTS = {".mq5", ".mqh", ".mq4"}  # include mq4 if you have legacy




# ============================
# MIRROR LOCATIONS
# ============================

# MT5 Expert source folder (your real source of "latest")
MQL5_SRC_DIR = Path(r"C:\Users\brook\AppData\Roaming\MetaQuotes\Terminal\10CE948A1DFC9A8C27E56E827008EBD4\MQL5\Experts\Brook")

# Where you want a mirrored copy (OneDrive Desktop)
ONEDRIVE_DST_DIR = Path(r"C:\Users\brook\OneDrive\Desktop\Python_AI Bot\MQL5_Experts_Brook")

# Keep scan target in sync (safe here because ONEDRIVE_DST_DIR is now defined)
MQL5_SCAN_DIR = ONEDRIVE_DST_DIR



# Optional full dump (kept off by default)
INCLUDE_FULL_CONTENT_DUMP = False
DUMP_MD = OUTPUT_DIR / "folder_dump.md"


# Safety
MAX_FILE_SIZE_MB = 5
INCLUDE_BINARY = False

# Compactness limits
MAX_DOCSTRING_CHARS = 500
MAX_LIST_ITEMS = 18
MAX_CONSTANTS = 12
MAX_SIDEFX = 4

# Group-level compact maps
MAX_DEPS_SHOWN_PER_NODE = 10
MAX_ENTRYPOINTS_SHOWN = 8
MAX_CRITICAL_PATHS_SHOWN = 6
MAX_CRITICAL_PATH_LEN = 6

# BAT parsing
BAT_MAX_LINES_SCAN = 700
BAT_MAX_SUMMARY_LINES = 32

SUMMARIZE_EXTS = {".py", ".bat", ".yaml", ".yml"}


# Responsibilities tuning (compact, but meaningful)
MAX_RESPONSIBILITIES = 6
RESP_EVIDENCE_PER_TAG = 2


# ============================
# OUTPUT REPLACEMENT (FORCE)
# ============================
def replace_file(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


# ============================
# BASIC FILE HELPERS
# ============================
def is_binary_file(path: Path) -> bool:
    """
    Binary check: returns True if a NUL byte is found in the first chunk.
    IMPORTANT: If the file can't be read (permissions/locking), do NOT label it as binary.
    That would cause misleading SKIPPED(binary) classifications.
    """
    try:
        with open(path, "rb") as f:
            chunk = f.read(2048)
        return b"\0" in chunk
    except Exception:
        return False




def safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"[ERROR READING FILE: {e}]"




def mirror_folder(src_dir: Path, dst_dir: Path, *, delete_extraneous: bool = False) -> None:
    """
    Mirror src_dir -> dst_dir (copy/update).
    If delete_extraneous=True, remove files/dirs in dst that don't exist in src.
    """
    src_dir = src_dir.resolve()
    dst_dir = dst_dir.resolve()
    dst_dir.mkdir(parents=True, exist_ok=True)

    # 1) Copy/update files from src into dst
    for p in src_dir.rglob("*"):
        rel = p.relative_to(src_dir)
        out = dst_dir / rel

        if p.is_dir():
            out.mkdir(parents=True, exist_ok=True)
            continue

        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, out)  # preserves mtime, etc.

    # 2) Optionally delete extras in dst
    if delete_extraneous:
        src_set = {p.relative_to(src_dir) for p in src_dir.rglob("*")}
        for q in sorted(dst_dir.rglob("*"), reverse=True):
            rel = q.relative_to(dst_dir)
            if rel not in src_set:
                if q.is_dir():
                    # remove only if empty (after file removals)
                    try:
                        q.rmdir()
                    except OSError:
                        pass
                else:
                    try:
                        q.unlink()
                    except OSError:
                        pass

def _truncate(s: str, n: int) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[: n - 3].rstrip() + "..."


def _rel(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix()

def _mql5_candidates_in_dir(root: Path) -> List[Path]:
    """
    Collect MQL5 source files under MQL5_SCAN_DIR (mq5/mqh/etc).
    """
    if not root.exists():
        return []

    HARD_EXCLUDE_DIRS = {".git", ".idea", "__pycache__", ".venv", "venv", "node_modules"}
    HARD_EXCLUDE_PARTS_CONTAINS = {"site-packages"}

    it = root.rglob("*") if RECURSIVE else root.glob("*")
    out: List[Path] = []

    for p in it:
        try:
            if not p.is_file():
                continue
            if p.name.startswith("."):
                continue
            if p.suffix.lower() not in MQL5_EXTS:
                continue

            parts = set(p.parts)
            if parts & HARD_EXCLUDE_DIRS:
                continue
            if any(x in p.parts for x in HARD_EXCLUDE_PARTS_CONTAINS):
                continue

            out.append(p)
        except Exception:
            continue

    return sorted(out, key=lambda x: str(x).lower())

_MQL5_INCLUDE_RE = re.compile(r'^\s*#include\s*[<"]([^>"]+)[>"]', re.IGNORECASE | re.MULTILINE)
_MQL5_INPUT_RE = re.compile(r'^\s*(?:input|extern)\s+([A-Za-z_][A-Za-z0-9_]*)\s+([A-Za-z_][A-Za-z0-9_]*)', re.IGNORECASE | re.MULTILINE)
_MQL5_EVENT_RE = re.compile(r'\b(OnInit|OnDeinit|OnTick|OnTimer|OnTrade|OnTradeTransaction|OnCalculate)\b')
_MQL5_REF_FILE_RE = re.compile(r'([A-Za-z0-9_\-./\\]+?\.(?:csv|json|txt|log|md))', re.IGNORECASE)

def parse_mql5_file(path: Path) -> Dict[str, object]:
    text = safe_read_text(path)

    out: Dict[str, object] = {
        "ok": True,
        "error": None,
        "total_lines": len((text or "").splitlines()),
        "includes": [],
        "events": [],
        "inputs": [],
        "referenced_files": [],
        "responsibilities": [],
    }

    try:
        inc = [m.strip() for m in _MQL5_INCLUDE_RE.findall(text or "")]
        out["includes"] = sorted(list(dict.fromkeys(inc)), key=str.lower)

        ev = sorted(list(set(_MQL5_EVENT_RE.findall(text or ""))), key=str.lower)
        out["events"] = ev

        ins = _MQL5_INPUT_RE.findall(text or "")
        # store as "type name"
        inputs = [f"{t} {n}" for (t, n) in ins]
        out["inputs"] = inputs[:MAX_LIST_ITEMS]

        refs = [m.strip().strip('"').strip("'") for m in _MQL5_REF_FILE_RE.findall(text or "")]
        out["referenced_files"] = sorted(list(dict.fromkeys(refs)), key=str.lower)[:MAX_LIST_ITEMS]

        # responsibilities (very compact heuristics)
        low = (text or "").lower()
        resps: List[str] = []
        if "ordersend" in low or "order_send" in low or "trade" in low:
            resps.append("execution/trading")
        if "copyrates" in low or "rates" in low or "iopen" in low or "iclose" in low:
            resps.append("market data")
        if "indicator" in low or "oncalculate" in low:
            resps.append("indicator/analysis")
        if "fileopen" in low or "fileread" in low or "filewrite" in low:
            resps.append("file I/O")
        if "ontimer" in low:
            resps.append("timers/scheduling")
        if not resps:
            resps.append("mql5 module")

        out["responsibilities"] = resps[:MAX_RESPONSIBILITIES]

    except Exception as e:
        out["ok"] = False
        out["error"] = str(e)

    return out

def md_module_summary_mql5(relpath: str, meta: Dict[str, object], includes_resolved: List[str]) -> str:
    ok = bool(meta.get("ok", False))
    err = meta.get("error")

    lines: List[str] = []
    lines.append(f"#### {format_node(relpath)}")

    if not ok:
        lines.append(f"- **Parse:** ❌ FAILED — `{_md_escape(str(err))}`")
        return "\n".join(lines)

    lines.append(f"- **Role:** `MQL5` | **Lines:** `{int(meta.get('total_lines', 0) or 0)}`")

    resps = meta.get("responsibilities", []) or []
    if resps:
        lines.append("- **Responsibilities:** " + ", ".join(f"`{r}`" for r in resps))

    ev = meta.get("events", []) or []
    if ev:
        lines.append("- **Events:** " + ", ".join(f"`{e}`" for e in ev))

    inputs = meta.get("inputs", []) or []
    if inputs:
        lines.append("- **Inputs/extern:** " + ", ".join(f"`{_md_escape(x)}`" for x in inputs[:12]) +
                     ("" if len(inputs) <= 12 else f" (+{len(inputs)-12} more)"))

    raw_includes = meta.get("includes", []) or []
    raw_includes = [str(x) for x in raw_includes] if isinstance(raw_includes, list) else []

    if includes_resolved:
        lines.append(
            "- **Includes (resolved):** " + ", ".join(format_node(x) for x in includes_resolved[:MAX_LIST_ITEMS]) +
            ("" if len(includes_resolved) <= MAX_LIST_ITEMS else f" (+{len(includes_resolved) - MAX_LIST_ITEMS} more)"))

    # Show unresolved/external includes too (stdlib/unknown), capped
    unresolved = []
    if raw_includes:
        resolved_set = set(includes_resolved or [])
        for inc in raw_includes:
            # If the include string didn't resolve to a project node, keep it as unresolved
            if inc and (inc not in resolved_set):
                unresolved.append(inc)

    if unresolved:
        show = unresolved[:MAX_LIST_ITEMS]
        tail = "" if len(unresolved) <= len(show) else f" (+{len(unresolved) - len(show)} more)"
        lines.append("- **Includes (unresolved/external):** " + ", ".join(f"`{_md_escape(x)}`" for x in show) + tail)

    refs = meta.get("referenced_files", []) or []
    if refs:
        lines.append("- **File refs (heuristic):** " + ", ".join(f"`{_md_escape(x)}`" for x in refs[:12]) +
                     ("" if len(refs) <= 12 else f" (+{len(refs)-12} more)"))

    return "\n".join(lines)

def _size_mb(p: Path) -> float:
    try:
        return p.stat().st_size / (1024 * 1024)
    except Exception:
        return 0.0


def _md_escape(s: str) -> str:
    # Minimal escape for markdown list weirdness
    return s.replace("\n", " ").replace("\r", "")


# ============================
# PYTHON ANALYSIS
# ============================
def _module_candidates_in_repo(root: Path) -> List[Path]:
    it = root.rglob("*.py") if RECURSIVE else root.glob("*.py")
    out: List[Path] = []

    # Hard excludes (biggest win: .venv)
    HARD_EXCLUDE_DIRS = {
        ".venv", "venv",
        "__pycache__", ".git", ".idea", ".pytest_cache",
        ".mypy_cache", ".ruff_cache", ".tox",
        "node_modules",
    }
    HARD_EXCLUDE_PARTS_CONTAINS = {"site-packages"}

    for p in it:
        try:
            # Skip hidden files/dirs early
            if p.name.startswith("."):
                continue

            parts = set(p.parts)

            # Exclude .venv entirely (and similar)
            if parts & HARD_EXCLUDE_DIRS:
                continue
            if any(x in p.parts for x in HARD_EXCLUDE_PARTS_CONTAINS):
                continue

            if p.stem == "__init__":
                continue

            out.append(p)
        except Exception:
            # If anything weird happens, skip this path
            continue

    return sorted(out, key=lambda x: _rel(root, x).lower())



def _is_all_caps(name: str) -> bool:
    return bool(name) and name.upper() == name and any(c.isalpha() for c in name)


def _ast_name(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Name):
        return node.id
    return None


def _ast_preview(node: ast.AST) -> str:
    try:
        if isinstance(node, ast.Constant):
            return _truncate(repr(node.value), 80)
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return f"<{node.__class__.__name__.lower()} len≈{len(getattr(node, 'elts', []) or [])}>"
        if isinstance(node, ast.Dict):
            return f"<dict len≈{len(getattr(node, 'keys', []) or [])}>"
        if isinstance(node, ast.Call):
            fn = ""
            if isinstance(node.func, ast.Name):
                fn = node.func.id
            elif isinstance(node.func, ast.Attribute):
                fn = node.func.attr
            return f"<call {fn}(... )>"
        if isinstance(node, ast.Attribute):
            return f"<attr {node.attr}>"
        return f"<{node.__class__.__name__}>"
    except Exception:
        return "<unavailable>"


def _detect_argparse(tree: ast.AST) -> bool:
    class V(ast.NodeVisitor):
        def __init__(self) -> None:
            self.found = False

        def visit_Import(self, node: ast.Import) -> None:
            for a in node.names:
                if a.name == "argparse":
                    self.found = True

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            if (node.module or "") == "argparse":
                self.found = True

        def visit_Call(self, node: ast.Call) -> None:
            if isinstance(node.func, ast.Attribute) and node.func.attr == "ArgumentParser":
                self.found = True
            if isinstance(node.func, ast.Name) and node.func.id == "ArgumentParser":
                self.found = True
            self.generic_visit(node)

    v = V()
    v.visit(tree)
    return v.found


def _detect_main_guard(node: ast.If) -> bool:
    # if __name__ == "__main__":
    try:
        test = node.test
        if isinstance(test, ast.Compare):
            left = test.left
            if isinstance(left, ast.Name) and left.id == "__name__":
                for comp in test.comparators:
                    if isinstance(comp, ast.Constant) and comp.value == "__main__":
                        return True
    except Exception:
        pass
    return False


def _detect_top_level_sidefx(tree: ast.Module) -> List[str]:
    effects: List[str] = []
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom)):
            continue
        if isinstance(n, ast.If):
            continue
        if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call):
            effects.append(f"top-level call: {_ast_preview(n.value)}")
        elif isinstance(n, ast.Assign) and isinstance(n.value, ast.Call):
            effects.append(f"top-level assign from call: {_ast_preview(n.value)}")
        elif isinstance(n, ast.AnnAssign) and isinstance(n.value, ast.Call):
            effects.append(f"top-level ann-assign from call: {_ast_preview(n.value)}")
        if len(effects) >= MAX_SIDEFX:
            break
    return effects

def _strip_py_comments(src: str) -> str:
    """
    Remove COMMENT tokens only. Keep string literals so path scanners work.
    """
    try:
        import io, tokenize
        out_parts: List[str] = []
        last_row, last_col = 1, 0

        tokgen = tokenize.generate_tokens(io.StringIO(src).readline)
        for tok_type, tok_str, (srow, scol), (erow, ecol), _ in tokgen:
            if srow > last_row:
                out_parts.append("\n" * (srow - last_row))
                last_col = 0
                last_row = srow
            if scol > last_col:
                out_parts.append(" " * (scol - last_col))

            if tok_type == tokenize.COMMENT:
                out_parts.append(" " * max(0, len(tok_str)))
            else:
                out_parts.append(tok_str)

            last_row, last_col = erow, ecol

        return "".join(out_parts)
    except Exception:
        return src


def infer_role(file_name: str, has_main: bool, has_argparse: bool, defs: List[str], classes: List[str], constants: List[Tuple[str, str]]) -> str:
    n = file_name.lower()

    if "test" in n or n.startswith("test_") or n.endswith("_test.py"):
        return "TEST"

    if has_main or has_argparse or n.startswith("run") or "runner" in n or "supervisor" in n or "bootstrap" in n:
        return "ENTRYPOINT"

    if "config" in n or "settings" in n or (len(constants) >= 6 and len(defs) <= 2 and len(classes) == 0):
        return "CONFIG"

    if "util" in n or "helper" in n or "common" in n:
        return "UTILITY"

    if "export" in n or "writer" in n or "report" in n or "dump" in n:
        return "EXPORT"

    if "journal" in n or "log" in n or "trace" in n or "audit" in n:
        return "JOURNAL"

    if "broker" in n or "order" in n or "execution" in n:
        return "BROKER/EXEC"

    if "market" in n or "data" in n:
        return "DATA"

    if "analy" in n or "setup" in n or "strategy" in n or "ict" in n:
        return "ANALYSIS"

    if len(classes) >= 2 or (len(classes) >= 1 and len(defs) >= 4):
        return "LIB"

    return "MODULE"


def infer_responsibilities(defs: List[str], classes: List[str], imports: List[str], file_name: str) -> Tuple[List[str], Dict[str, List[str]]]:
    # Tag, label, keywords
    TAGS: List[Tuple[str, str, List[str]]] = [
        ("runtime", "runtime/orchestration/loops", ["bootstrap", "supervisor", "runner", "loop", "main", "pipeline"]),
        ("broker", "broker/execution/orders", ["mt5", "metatrader", "broker", "order", "trade", "positions", "fills", "execution"]),
        ("data", "market data (OHLC/bars/feeds)", ["marketdata", "ohlc", "candle", "bars", "rates", "prices", "feed", "snapshot"]),
        ("analysis", "analysis/scoring/setups", ["analy", "score", "rank", "setup", "ict", "choch", "bos", "liquidity", "displacement", "pd_zone"]),
        ("journal", "journaling/audit/logging", ["journal", "event", "log", "audit", "schema", "replay", "trace", "fingerprint"]),
        ("export", "exports/reports (csv/json/md/txt)", ["export", "writer", "csv", "json", "md", "markdown", "report", "dump"]),
        ("config", "config/env/constants", ["config", "settings", "env", "flag", "mode", "constants"]),
        ("risk", "risk/position sizing/rr/gates", ["risk", "rr", "stop", "takeprofit", "tp", "sl", "size", "lot", "gate"]),
        ("time", "time/session/scheduling", ["session", "timezone", "utc", "timestamp", "time", "schedule", "bucket"]),
        ("io", "filesystem/path I/O", ["path", "file", "folder", "read", "write", "open", "dump"]),
        ("tests", "tests/harness/verification", ["test", "assert", "fixture", "mock", "harness", "verify"]),
    ]

    evidence: Dict[str, List[str]] = defaultdict(list)
    sources = [("def", d) for d in defs] + [("class", c) for c in classes] + [("import", i) for i in imports] + [("file", file_name)]

    for tag, _, kws in TAGS:
        for _, s in sources:
            sl = s.lower()
            for kw in kws:
                if kw in sl:
                    evidence[tag].append(s)
                    break
            if len(evidence[tag]) >= RESP_EVIDENCE_PER_TAG:
                break

    tag_to_label = {t: lbl for t, lbl, _ in TAGS}
    tags_found = [t for t in tag_to_label.keys() if evidence.get(t)]
    labels = [tag_to_label[t] for t in tags_found][:MAX_RESPONSIBILITIES]

    if not labels:
        labels = ["general"]

    # compact evidence
    for k in list(evidence.keys()):
        evidence[k] = evidence[k][:RESP_EVIDENCE_PER_TAG]

    return labels, dict(evidence)


def parse_python_file(path: Path) -> Dict[str, object]:
    text = safe_read_text(path)

    out: Dict[str, object] = {
        "ok": False,
        "error": None,
        "docstring": "",
        "imports": [],
        "defs": [],
        "classes": [],
        "constants": [],
        "has_main_guard": False,
        "has_argparse": False,
        "top_level_side_effects": [],
        "role": "MODULE",
        "responsibilities": [],
        "responsibility_evidence": {},

        # NEW (IO + touchpoints)
        "total_lines": 0,
        "created_files": [],
        "reads_files": [],
        "network_touchpoints": [],
        "io_label": "internal",   # producer / consumer / boundary / internal
        "csv_contracts": [],      # filenames like foo.csv seen in reads/writes
    }

    out["total_lines"] = len((text or "").splitlines())

    # IMPORTANT: heuristic scanners must NOT see docstrings/comments/regex literals,
    # otherwise this file (and others) will self-match "x.csv", "requests", etc.
    scan_text = _strip_py_comments(text or "")


    # ----------------------------
    # Heuristics (string/regex based)
    # ----------------------------
    def _unique_sorted(xs: List[str]) -> List[str]:
        seen = set()
        out2: List[str] = []
        for x in xs:
            x = (x or "").strip()
            if not x:
                continue
            if x not in seen:
                seen.add(x)
                out2.append(x)
        return sorted(out2, key=str.lower)

    def _extract_literal_paths(src: str, patterns: List[re.Pattern]) -> List[str]:
        hits: List[str] = []
        for pat in patterns:
            for m in pat.finditer(src):
                p = (m.group("path") or "").strip()
                if not p:
                    continue
                # Avoid URLs
                if "://" in p:
                    continue
                hits.append(p)
        return hits

    # Common extensions we care about
    exts = (
        ".csv", ".json", ".jsonl", ".txt", ".log", ".md",
        ".png", ".jpg", ".jpeg", ".webp", ".pdf",
        ".yaml", ".yml",
        ".pkl", ".pickle",
        ".xlsx",
    )

    def _keep_fileish(p: str) -> bool:
        lp = (p or "").strip().lower()
        if not lp:
            return False
        return any(lp.endswith(e) for e in exts)

    # Writes / creates (best-effort, literal paths only)
    write_patterns = [
        # open("x.csv","w") / open("x.csv","a") / open("x.csv","wb")
        re.compile(r"""open\(\s*(['"])(?P<path>.+?)\1\s*,\s*(['"])(?P<mode>[wa][bt]?)\3""", re.IGNORECASE),
        # Path("x.csv").write_text(...) / write_bytes(...)
        re.compile(r"""Path\(\s*(['"])(?P<path>.+?)\1\s*\)\.(?:write_text|write_bytes)\(""", re.IGNORECASE),
        # pandas: df.to_csv("x.csv")
        re.compile(r"""\.to_csv\(\s*(['"])(?P<path>.+?)\1""", re.IGNORECASE),
        re.compile(r"""\.to_excel\(\s*(['"])(?P<path>.+?)\1""", re.IGNORECASE),
        # matplotlib: savefig("x.png")
        re.compile(r"""savefig\(\s*(['"])(?P<path>.+?)\1""", re.IGNORECASE),
        # json.dump(..., open("x.json","w")) is covered by open(), but keep a direct hint too
        re.compile(r"""json\.dump\(.+?,\s*open\(\s*(['"])(?P<path>.+?)\1\s*,\s*['"]w""", re.IGNORECASE),
    ]

    # Reads (literal paths only)
    read_patterns = [
        # open("x.csv","r") / open("x.csv","rb")
        re.compile(r"""open\(\s*(['"])(?P<path>.+?)\1\s*,\s*(['"])(?P<mode>r[bt]?)\3""", re.IGNORECASE),
        # pandas.read_csv("x.csv")
        re.compile(r"""read_csv\(\s*(['"])(?P<path>.+?)\1""", re.IGNORECASE),
        # read_json/read_excel
        re.compile(r"""read_json\(\s*(['"])(?P<path>.+?)\1""", re.IGNORECASE),
        re.compile(r"""read_excel\(\s*(['"])(?P<path>.+?)\1""", re.IGNORECASE),
        # yaml.safe_load(open("x.yaml","r")) is covered by open(), but include direct Path("x.yaml") too
        re.compile(r"""yaml\.safe_load\(\s*open\(\s*(['"])(?P<path>.+?)\1""", re.IGNORECASE),
        # Path("x.yaml").read_text() / read_bytes()
        re.compile(r"""Path\(\s*(['"])(?P<path>.+?)\1\s*\)\.(?:read_text|read_bytes)\(""", re.IGNORECASE),
    ]

    created = [p for p in _extract_literal_paths(scan_text, write_patterns) if _keep_fileish(p)]
    reads = [p for p in _extract_literal_paths(scan_text, read_patterns) if _keep_fileish(p)]

    out["created_files"] = _unique_sorted(created)
    out["reads_files"] = _unique_sorted(reads)

    # Network/MT5 touchpoints (regex heuristics)
    touch: List[str] = []
    src_l = (scan_text or "").lower()

    # MT5 / broker libs
    # IMPORTANT: avoid false positives from identifiers like "mt5_patterns"
    # Only treat as MT5 if we see MetaTrader5 text OR actual attribute usage like "mt5.initialize"
    if "metatrader5" in src_l or re.search(r"\bmt5\s*\.", src_l):
        touch.append("MetaTrader5/MT5")

    if re.search(r"\brequests\b", src_l) or "requests." in src_l:
        touch.append("requests (HTTP)")
    if "urllib" in src_l:
        touch.append("urllib (HTTP)")
    if re.search(r"\bsocket\b", src_l) or "socket." in src_l:
        touch.append("socket (TCP/UDP)")
    if "websocket" in src_l or "websockets" in src_l:
        touch.append("websocket")
    if "asyncio" in src_l and ("websocket" in src_l or "socket" in src_l):
        touch.append("async network (asyncio)")

    out["network_touchpoints"] = _unique_sorted(touch)

    # Auto-label: producer / consumer / boundary / internal
    is_producer = bool(out["created_files"])
    is_consumer = bool(out["reads_files"])
    is_boundary = bool(out["network_touchpoints"])

    # Priority label: boundary > producer/consumer combos
    if is_boundary:
        out["io_label"] = "boundary"
    elif is_producer and is_consumer:
        out["io_label"] = "producer+consumer"
    elif is_producer:
        out["io_label"] = "producer"
    elif is_consumer:
        out["io_label"] = "consumer"
    else:
        out["io_label"] = "internal"

    # CSV contracts (shared “contract” surfaces for ChatGPT)
    csvs: List[str] = []
    for p in (out["created_files"] or []) + (out["reads_files"] or []):
        if str(p).lower().endswith(".csv"):
            csvs.append(str(p))
    out["csv_contracts"] = _unique_sorted(csvs)

    # ----------------------------
    # AST parsing (existing behavior)
    # ----------------------------
    try:
        tree = ast.parse(text, filename=str(path))
    except Exception as e:
        out["error"] = f"AST parse failed: {e}"
        return out

    out["ok"] = True
    out["docstring"] = ast.get_docstring(tree) or ""
    out["has_argparse"] = _detect_argparse(tree)
    out["top_level_side_effects"] = _detect_top_level_sidefx(tree)

    imports: List[str] = []
    defs: List[str] = []
    classes: List[str] = []
    constants: List[Tuple[str, str]] = []
    has_main = False

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)

        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level and mod:
                mod = "." * node.level + mod
            elif node.level and not mod:
                mod = "." * node.level
            imports.append(mod if mod else "(unknown)")

        elif isinstance(node, ast.FunctionDef):
            defs.append(node.name)

        elif isinstance(node, ast.AsyncFunctionDef):
            defs.append(f"async {node.name}")

        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)

        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                name = _ast_name(tgt)
                if name and _is_all_caps(name):
                    constants.append((name, _ast_preview(node.value)))

        elif isinstance(node, ast.AnnAssign):
            name = _ast_name(node.target)
            if name and _is_all_caps(name) and node.value is not None:
                constants.append((name, _ast_preview(node.value)))

        elif isinstance(node, ast.If):
            if _detect_main_guard(node):
                has_main = True

    out["imports"] = imports
    out["defs"] = defs
    out["classes"] = classes
    out["constants"] = constants
    out["has_main_guard"] = has_main

    out["role"] = infer_role(path.name, has_main, bool(out["has_argparse"]), defs, classes, constants)

    resp, ev = infer_responsibilities(defs, classes, imports, path.name)
    out["responsibilities"] = resp
    out["responsibility_evidence"] = ev

    return out




# ============================
# INTERNAL LINK RESOLUTION
# ============================
def stem_to_relpaths(py_files: List[Path], root: Path) -> Dict[str, List[str]]:
    m: Dict[str, List[str]] = defaultdict(list)
    for p in py_files:
        m[p.stem].append(_rel(root, p))
    # stable order
    for k in list(m.keys()):
        m[k] = sorted(m[k], key=str.lower)
    return m

def infer_internal_stems(imports: List[str], internal_stems: Set[str]) -> List[str]:
    """
    Infer internal module stems from import strings.

    Previous behavior split *all* path segments and could produce false edges.
    New behavior:
      - Only considers the final module segment (most accurate for repo-level mapping)
      - Handles relative imports like ".foo" or "..bar.baz" by stripping leading dots
    """
    hits: Set[str] = set()

    for imp in imports or []:
        if not imp or imp == "(unknown)":
            continue

        s = str(imp).strip()
        if not s:
            continue

        # Normalize relative-ish imports: "..pkg.mod" -> "pkg.mod"
        s = s.lstrip(".")
        if not s:
            continue

        # Only the last segment is a sensible module candidate
        candidate = s.split(".")[-1].strip()
        if candidate and candidate in internal_stems:
            hits.add(candidate)

    return sorted(hits, key=str.lower)


def _ast_uses_mt5(tree: ast.AST) -> bool:
    class V(ast.NodeVisitor):
        def __init__(self) -> None:
            self.found = False

        def visit_Import(self, node: ast.Import) -> None:
            for a in node.names:
                if a.name.lower() == "metatrader5":
                    self.found = True

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            if (node.module or "").lower() == "metatrader5":
                self.found = True

        def visit_Attribute(self, node: ast.Attribute) -> None:
            # catches mt5.initialize / mt5.copy_rates etc.
            if isinstance(node.value, ast.Name) and node.value.id == "mt5":
                self.found = True
            self.generic_visit(node)

    v = V()
    v.visit(tree)
    return v.found


def resolve_stems_to_files(stems: List[str], stem_map: Dict[str, List[str]]) -> List[str]:
    out: List[str] = []
    for s in stems:
        candidates = stem_map.get(s, [])
        if not candidates:
            continue
        # If multiple files share the stem, list them all (still compact)
        out.extend(candidates)
    # unique, stable
    seen = set()
    uniq = []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


# ============================
# BAT ANALYSIS
# ============================
_BAT_COMMENT_RE = re.compile(r"^\s*(?:rem\b|::)", re.IGNORECASE)
_BAT_SET_RE = re.compile(r"^\s*set\s+([^=\s]+)\s*=\s*(.*)$", re.IGNORECASE)
_BAT_CALL_RE = re.compile(r"^\s*call\s+(.+)$", re.IGNORECASE)
_BAT_PY_RE = re.compile(r"\bpython(?:\.\w+)?\b", re.IGNORECASE)
_REF_FILE_RE = re.compile(r"([A-Za-z0-9_\-./\\]+?\.(?:py|bat))", re.IGNORECASE)


def parse_bat_file(path: Path) -> Dict[str, object]:
    text = safe_read_text(path)
    lines = text.splitlines()
    scan = lines[:BAT_MAX_LINES_SCAN]

    header_comments: List[str] = []
    set_vars: List[str] = []
    calls: List[str] = []
    python_invocations: List[str] = []
    referenced_files: Set[str] = set()
    tools: Set[str] = set()

    ok = True
    err = None

    # Command keywords we want to detect as "tools"
    tool_cmds = [
        "cd", "pushd", "popd",
        "copy", "xcopy", "robocopy",
        "del", "erase",
        "rmdir", "rd", "mkdir",
        "git", "pip",
        "powershell", "curl", "start",
        "setlocal", "endlocal",
    ]

    try:
        for raw in scan:
            s = raw.strip()
            if not s:
                continue

            if _BAT_COMMENT_RE.match(s):
                if len(header_comments) < 8:
                    header_comments.append(s.lstrip(":").strip())
                continue

            m = _BAT_SET_RE.match(raw)
            if m:
                var = m.group(1).strip()
                val = m.group(2).strip()
                set_vars.append(f"{var}={_truncate(val, 120)}")

            m = _BAT_CALL_RE.match(raw)
            if m:
                calls.append(_truncate(m.group(1).strip(), 200))

            # Only count python *executions*, not "set PY=python"
            raw_exec = raw.lstrip()
            if raw_exec.startswith("@"):
                raw_exec = raw_exec[1:].lstrip()

            if re.search(r"^\s*(?:call\s+)?(?:\"?[^\"]*python(?:\.\w+)?\"?|\%PY\%)\b", raw_exec, re.IGNORECASE):
                python_invocations.append(_truncate(raw.strip(), 240))

            for match in _REF_FILE_RE.findall(raw):
                referenced_files.add(match.strip().strip('"').strip("'"))

            # Robust tool detection: allow common "@cmd" prefix
            # (e.g. "@setlocal", "@pushd", "@mkdir")
            raw2 = raw.lstrip()
            if raw2.startswith("@"):
                raw2 = raw2[1:].lstrip()

            for cmd in tool_cmds:
                if re.match(rf"^\s*{re.escape(cmd)}\b", raw2, re.IGNORECASE):
                    tools.add(cmd)

    except Exception as e:
        ok = False
        err = str(e)

    responsibilities: List[str] = []
    joined = " ".join(scan).lower()
    if "python" in joined:
        responsibilities.append("runs python scripts")
    if "set " in joined:
        responsibilities.append("sets env/runtime flags")
    if any(k in joined for k in ["copy ", "xcopy ", "robocopy "]):
        responsibilities.append("copies/moves files")
    if any(k in joined for k in ["del ", "erase ", "rd ", "rmdir "]):
        responsibilities.append("cleans/removes files")
    if "git " in joined:
        responsibilities.append("uses git")
    if not responsibilities:
        responsibilities.append("batch orchestration")

    responsibilities = responsibilities[:MAX_RESPONSIBILITIES]

    return {
        "ok": ok,
        "error": err,
        "header_comments": header_comments,
        "set_vars": set_vars[:MAX_LIST_ITEMS],
        "calls": calls[:MAX_LIST_ITEMS],
        "python_invocations": python_invocations[:MAX_LIST_ITEMS],
        "tools": sorted(tools)[:MAX_LIST_ITEMS],
        "referenced_files": sorted(referenced_files)[:MAX_LIST_ITEMS],
        "lines_scanned": min(len(lines), BAT_MAX_LINES_SCAN),
        "total_lines": len(lines),
        "responsibilities": responsibilities,
    }



# ============================
# YAML ANALYSIS
# ============================

_YAML_KEY_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*:\s*(.*)\s*$")
_YAML_REF_FILE_RE = re.compile(r"([A-Za-z0-9_\-./\\]+?\.(?:py|bat|ya?ml|json|md|csv|txt))", re.IGNORECASE)


def parse_yaml_file(path: Path) -> Dict[str, object]:
    """
    Lightweight YAML summarizer (no external deps).
    Extracts:
      - top-level keys (indent == 0)
      - a sample of "key: value" lines
      - referenced filenames (best-effort)
      - line counts
    """
    text = safe_read_text(path)
    lines = text.splitlines()

    top_keys: List[str] = []
    sample_pairs: List[str] = []
    referenced_files: Set[str] = set()

    ok = True
    err = None

    # Cap scan time on massive YAML, but keep enough to be useful
    scan_cap = 400 if len(lines) > 2000 else 2000

    try:
        for raw in lines[:scan_cap]:
            s = raw.rstrip("\n")
            if not s.strip():
                continue
            if s.lstrip().startswith("#"):
                continue

            for match in _YAML_REF_FILE_RE.findall(s):
                referenced_files.add(match.strip().strip('"').strip("'"))

            # capture top-level keys only (no indent)
            if s and not s.startswith(" ") and not s.startswith("\t"):
                m = _YAML_KEY_RE.match(s)
                if m:
                    k = m.group(1).strip()
                    v = m.group(2).strip()
                    if k and k not in top_keys and len(top_keys) < MAX_LIST_ITEMS:
                        top_keys.append(k)
                    if len(sample_pairs) < 12:
                        sample_pairs.append(f"{k}: {_truncate(v, 120)}")

    except Exception as e:
        ok = False
        err = str(e)

    responsibilities: List[str] = []
    low = path.name.lower()
    joined = "\n".join(lines[:200]).lower()

    if "profiles" in joined or "stages" in joined or "rrule" in joined:
        responsibilities.append("config/pipeline definition")
    if "env" in joined or "${" in joined or "%{" in joined:
        responsibilities.append("env templating/variables")
    if "schema" in joined:
        responsibilities.append("schema/config structure")
    if any(x in low for x in ("config", "settings", "pipeline", "stages", "tests")):
        responsibilities.append("config file")
    if not responsibilities:
        responsibilities.append("yaml configuration")

    responsibilities = responsibilities[:MAX_RESPONSIBILITIES]

    return {
        "ok": ok,
        "error": err,
        "top_keys": top_keys,
        "sample_pairs": sample_pairs,
        "referenced_files": sorted(referenced_files)[:MAX_LIST_ITEMS],
        "total_lines": len(lines),
        "responsibilities": responsibilities,
    }



def md_module_summary_yaml(relpath: str, meta: Dict[str, object]) -> str:
    ok = bool(meta.get("ok", False))
    err = meta.get("error")

    lines: List[str] = []
    lines.append(f"### {format_node(relpath)}")

    if not ok:
        lines.append(f"- **Parse:** ❌ FAILED — `{_md_escape(str(err))}`")
        return "\n".join(lines)

    top_keys: List[str] = meta.get("top_keys", []) or []
    refs: List[str] = meta.get("referenced_files", []) or []
    total_lines = int(meta.get("total_lines", 0) or 0)

    lines.append(f"- **Role:** `YAML` | **Lines:** `{total_lines}`")

    if top_keys:
        lines.append("- **Top keys:** " + ", ".join(f"`{k}`" for k in top_keys[:12]) + ("" if len(top_keys) <= 12 else f" (+{len(top_keys)-12} more)"))
    else:
        lines.append("- **Top keys:** `[none detected]`")

    if refs:
        lines.append("- **References:** " + ", ".join(f"`{r}`" for r in refs[:12]) + ("" if len(refs) <= 12 else f" (+{len(refs)-12} more)"))

    return "\n".join(lines)


def _resolve_any_ref(tok: str, all_nodes: Set[str], basename_index: Optional[Dict[str, List[str]]] = None) -> Optional[str]:
    """
    Resolve a token that references a repo file to an actual node in all_nodes.

    - Direct match wins (after normalization)
    - Otherwise try basename match using a precomputed index when provided
    - If multiple files share a basename, prefer a "closest" match by:
        1) exact normalized token suffix match
        2) shortest path length
        3) lexicographic
    """
    t = (tok or "").replace("\\", "/").strip().lstrip("./")
    if not t:
        return None

    # Direct match
    if t in all_nodes:
        return t

    base = t.split("/")[-1]
    if not base:
        return None

    # If no index passed, fall back to scanning (kept for back-compat)
    if basename_index is None:
        for n in all_nodes:
            if n.split("/")[-1] == base:
                return n
        return None

    cands = basename_index.get(base, [])
    if not cands:
        return None

    # Prefer candidate whose path ends with the normalized token (stronger signal)
    suffix_matches = [c for c in cands if c.endswith("/" + t) or c == t or c.endswith(t)]
    if suffix_matches:
        suffix_matches.sort(key=lambda x: (len(x), x.lower()))
        return suffix_matches[0]

    # Otherwise choose shortest (usually more "top-level") and stable order
    cands_sorted = sorted(cands, key=lambda x: (len(x), x.lower()))
    return cands_sorted[0]


# ============================
# GRAPH / GROUPING
# ============================
def _resolve_bat_ref(tok: str, all_nodes: Set[str]) -> Optional[str]:
    # normalize and try direct match; then basename match
    t = tok.replace("\\", "/").strip().lstrip("./")
    if t in all_nodes:
        return t
    base = t.split("/")[-1]
    # if base exists as a node basename
    for n in all_nodes:
        if n.split("/")[-1] == base:
            return n
    return None



def connected_components(graph: Dict[str, Set[str]]) -> List[List[str]]:
    seen: Set[str] = set()
    comps: List[List[str]] = []

    for node in sorted(graph.keys()):
        if node in seen:
            continue
        q = deque([node])
        seen.add(node)
        comp: List[str] = []
        while q:
            cur = q.popleft()
            comp.append(cur)
            for nxt in graph.get(cur, set()):
                if nxt not in seen:
                    seen.add(nxt)
                    q.append(nxt)
        comp = sorted(comp, key=str.lower)
        comps.append(comp)

    comps.sort(key=lambda c: (-len(c), c[0].lower()))
    return comps


# ============================
# REPORT HELPERS (COMPACT + CLEAR)
# ============================
def format_node(n: str) -> str:
    return f"`{n}`"


def is_entrypoint_py(relpath: str, py_meta: Dict[str, Dict[str, object]]) -> bool:
    meta = py_meta.get(relpath)
    if not meta or not meta.get("ok"):
        return False

    role = str(meta.get("role", ""))
    if role == "TEST":
        return False

    if role == "ENTRYPOINT":
        return True

    # heuristic by filename (but avoid tests)
    low = relpath.lower()
    base = low.split("/")[-1]

    if base.startswith("run") or "bootstrap" in base or "supervisor" in base or "runner" in base:
        return True

    return False



def group_bucket_for_py(relpath: str, py_meta: Dict[str, Dict[str, object]]) -> str:
    meta = py_meta.get(relpath, {})
    role = str(meta.get("role", "MODULE"))
    resps = meta.get("responsibilities", []) or []

    # priority buckets
    if role == "ENTRYPOINT":
        return "Runtime / Entrypoints"
    if role in ("BROKER/EXEC",):
        return "Broker / Execution"
    if role == "JOURNAL":
        return "Journal / Audit"
    if role == "EXPORT":
        return "Exports / Reporting"
    if role == "CONFIG":
        return "Config / Constants"
    if role == "TEST":
        return "Tests / Harness"
    # responsibility-based
    joined = " ".join(resps).lower()
    if "broker" in joined:
        return "Broker / Execution"
    if "journal" in joined or "audit" in joined or "logging" in joined:
        return "Journal / Audit"
    if "exports" in joined or "reports" in joined:
        return "Exports / Reporting"
    if "market data" in joined:
        return "Market Data"
    if "analysis" in joined or "scoring" in joined or "setups" in joined:
        return "Strategy / Analysis"
    if "risk" in joined:
        return "Risk / Gates"
    if "time/session" in joined or "scheduling" in joined:
        return "Time / Sessions"
    if "filesystem" in joined or "path" in joined:
        return "Filesystem / I/O"
    return "Core / Other"


def group_bucket_for_bat(relpath: str, bat_meta: Optional[Dict[str, Dict[str, object]]] = None) -> str:
    """
    Compatibility signature: some run() versions call group_bucket_for_bat(node, bat_meta).

    We keep it simple and stable:
      - default bucket = BAT / Orchestration
      - optionally refine bucket based on parsed responsibilities/tools if available
    """
    if not bat_meta:
        return "BAT / Orchestration"

    meta = bat_meta.get(relpath, {}) if isinstance(bat_meta, dict) else {}
    resps = meta.get("responsibilities", []) or []
    tools = meta.get("tools", []) or []
    joined = (" ".join([str(x) for x in resps]) + " " + " ".join([str(x) for x in tools])).lower()

    # Light refinement (still compact)
    if "cleans/removes" in joined or "del" in joined or "erase" in joined or "rd" in joined or "rmdir" in joined:
        return "BAT / Cleanup"
    if "copies/moves" in joined or "copy" in joined or "xcopy" in joined or "robocopy" in joined:
        return "BAT / File Ops"
    if "runs python" in joined or "python" in joined:
        return "BAT / Launchers"

    return "BAT / Orchestration"



def collapsed_dep_map_lines(group_nodes: List[str], directed: Dict[str, Set[str]]) -> List[str]:
    nodes_set = set(group_nodes)
    lines: List[str] = []
    for src in group_nodes:
        dsts = sorted([d for d in directed.get(src, set()) if d in nodes_set], key=str.lower)
        if not dsts:
            continue
        shown = dsts[:MAX_DEPS_SHOWN_PER_NODE]
        tail = "" if len(dsts) <= len(shown) else f", +{len(dsts) - len(shown)} more"
        lines.append(f"- {format_node(src)} → {{ " + ", ".join(format_node(d) for d in shown) + f"{tail} }}")
    return lines


def bucket_dependency_map(group_nodes: List[str], directed: Dict[str, Set[str]], bucket_of: Dict[str, str]) -> List[str]:
    # Aggregate edges between buckets
    edges: Dict[Tuple[str, str], int] = defaultdict(int)
    nodes_set = set(group_nodes)
    for src in group_nodes:
        bsrc = bucket_of.get(src, "Core / Other")
        for dst in directed.get(src, set()):
            if dst not in nodes_set:
                continue
            bdst = bucket_of.get(dst, "Core / Other")
            if bsrc == bdst:
                continue
            edges[(bsrc, bdst)] += 1

    if not edges:
        return ["- [no cross-subsystem edges detected]"]

    # show top edges
    items = sorted(edges.items(), key=lambda kv: (-kv[1], kv[0][0].lower(), kv[0][1].lower()))
    lines: List[str] = []
    for (a, b), w in items[:12]:
        lines.append(f"- **{a}** → **{b}** (edges≈{w})")
    return lines


def find_critical_paths(entrypoints: List[str], group_nodes: List[str], directed: Dict[str, Set[str]]) -> List[str]:
    # BFS from each entrypoint, pick "interesting" targets by indegree within group.
    nodes_set = set(group_nodes)
    indeg: Dict[str, int] = defaultdict(int)
    for src in group_nodes:
        for dst in directed.get(src, set()):
            if dst in nodes_set:
                indeg[dst] += 1

    # candidate targets: top indegree nodes
    targets = [n for n, _ in sorted(indeg.items(), key=lambda kv: (-kv[1], kv[0].lower()))]
    targets = targets[: min(18, len(targets))]

    # BFS pathfinder (shortest)
    def shortest_path(start: str, goal: str) -> Optional[List[str]]:
        if start == goal:
            return [start]
        q = deque([start])
        prev: Dict[str, Optional[str]] = {start: None}
        while q:
            cur = q.popleft()
            for nxt in directed.get(cur, set()):
                if nxt not in nodes_set:
                    continue
                if nxt not in prev:
                    prev[nxt] = cur
                    if nxt == goal:
                        # reconstruct
                        path = [nxt]
                        p = cur
                        while p is not None:
                            path.append(p)
                            p = prev[p]
                        path.reverse()
                        return path
                    q.append(nxt)
        return None

    paths: List[str] = []
    used_pairs: Set[Tuple[str, str]] = set()

    for ep in entrypoints:
        for t in targets:
            if len(paths) >= MAX_CRITICAL_PATHS_SHOWN:
                break
            if (ep, t) in used_pairs:
                continue
            p = shortest_path(ep, t)
            if not p:
                continue
            if len(p) > MAX_CRITICAL_PATH_LEN:
                continue
            used_pairs.add((ep, t))
            pretty = " → ".join(format_node(x) for x in p)
            paths.append(f"- {pretty}")
        if len(paths) >= MAX_CRITICAL_PATHS_SHOWN:
            break

    if not paths:
        return ["- [no short critical paths detected]"]

    return paths



def _bat_candidates_in_repo(root: Path) -> List[Path]:
    """
    Discover .bat files under repo root, excluding virtualenvs / junk folders.
    """
    it = root.rglob("*.bat") if RECURSIVE else root.glob("*.bat")
    out: List[Path] = []

    HARD_EXCLUDE_DIRS = {".venv", "venv", "__pycache__", ".git", ".idea", ".pytest_cache"}
    HARD_EXCLUDE_PARTS_CONTAINS = {"site-packages"}

    for p in it:
        parts = set(p.parts)

        if parts & HARD_EXCLUDE_DIRS:
            continue
        if any(x in p.parts for x in HARD_EXCLUDE_PARTS_CONTAINS):
            continue

        if p.name.startswith("."):
            continue

        out.append(p)

    return sorted(out, key=lambda x: _rel(root, x).lower())

def allow_file(p: Path) -> Tuple[bool, str]:
    try:
        if not p.exists():
            return False, "missing"
        if _size_mb(p) > MAX_FILE_SIZE_MB:
            return False, "too large"
        if not INCLUDE_BINARY and is_binary_file(p):
            return False, "binary"
        return True, ""
    except Exception:
        return False, "error"


def build_directed_graph(
    py_relpaths: List[str],
    bat_relpaths: List[str],
    yaml_relpaths: List[str],
    py_import_edges: Dict[str, Set[str]],
    bat_refs: Dict[str, List[str]],
    yaml_refs: Dict[str, List[str]],
    root: Path,
    extra_nodes: Optional[List[str]] = None,
    extra_refs: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Set[str]]:
    global _GRAPH_CACHE

    undirected: Dict[str, Set[str]] = defaultdict(set)
    directed: Dict[str, Set[str]] = defaultdict(set)

    extra_nodes = extra_nodes or []
    extra_refs = extra_refs or {}

    all_nodes = set(py_relpaths) | set(bat_relpaths) | set(yaml_relpaths) | set(extra_nodes)

    for n in all_nodes:
        undirected.setdefault(n, set())
        directed.setdefault(n, set())

    # Precompute basename index for fast ref resolution
    basename_index: Dict[str, List[str]] = defaultdict(list)
    for n in all_nodes:
        basename_index[n.split("/")[-1]].append(n)
    for k in list(basename_index.keys()):
        basename_index[k] = sorted(basename_index[k], key=str.lower)

    def add_u(a: str, b: str) -> None:
        if a != b:
            undirected[a].add(b)
            undirected[b].add(a)

    def add_d(a: str, b: str) -> None:
        if a != b:
            directed[a].add(b)

    # python edges
    for src, dsts in py_import_edges.items():
        for dst in dsts:
            if src in all_nodes and dst in all_nodes:
                add_u(src, dst)
                add_d(src, dst)

    # bat refs
    for src, toks in bat_refs.items():
        for t in toks:
            resolved = _resolve_any_ref(t, all_nodes, basename_index)
            if resolved:
                add_u(src, resolved)
                add_d(src, resolved)

    # yaml refs
    for src, toks in (yaml_refs or {}).items():
        for t in toks:
            resolved = _resolve_any_ref(t, all_nodes, basename_index)
            if resolved:
                add_u(src, resolved)
                add_d(src, resolved)

    # extra refs (MQL5 includes)
    for src, toks in (extra_refs or {}).items():
        for t in toks:
            resolved = _resolve_any_ref(t, all_nodes, basename_index)
            if resolved:
                add_u(src, resolved)
                add_d(src, resolved)

    _GRAPH_CACHE["undirected"] = undirected
    _GRAPH_CACHE["directed"] = directed
    return directed






def _yaml_candidates_in_repo(root: Path) -> List[Path]:
    """
    Collect .yaml/.yml files, skipping junk dirs (especially .venv).
    Uses RECURSIVE flag to match repo scan behavior.
    """
    def _ok(p: Path) -> bool:
        parts = set(p.parts)
        if parts & {".venv", "venv", "__pycache__", ".git", ".idea", ".pytest_cache"}:
            return False
        if "site-packages" in p.parts:
            return False
        return True

    it = root.rglob("*") if RECURSIVE else root.glob("*")
    out: List[Path] = []
    for p in it:
        if not p.is_file():
            continue
        if p.suffix.lower() not in (".yaml", ".yml"):
            continue
        if not _ok(p):
            continue
        out.append(p)

    out.sort(key=lambda p: _rel(root, p).lower())
    return out

def _basenameish(p: str) -> str:
    try:
        return Path(p).name
    except Exception:
        return p.split("/")[-1].split("\\")[-1]


def build_io_dependency_graph(py_meta: Dict[str, Dict[str, object]]) -> List[str]:
    """
    Tiny IO dependency graph (heuristic):
      Producer -> Consumer : file.csv

    We match by basename to survive relative/absolute differences.
    """
    producers: Dict[str, List[str]] = {}  # filebase -> [module relpaths]
    consumers: Dict[str, List[str]] = {}  # filebase -> [module relpaths]

    for mod, meta in (py_meta or {}).items():
        if not meta or not meta.get("ok"):
            continue
        created = meta.get("created_files", []) or []
        readf = meta.get("reads_files", []) or []   # <-- correct key
        for f in created:
            fb = _basenameish(str(f))
            producers.setdefault(fb, []).append(mod)
        for f in readf:
            fb = _basenameish(str(f))
            consumers.setdefault(fb, []).append(mod)

    edges: List[str] = []
    for fb, ps in producers.items():
        cs = consumers.get(fb, [])
        if not cs:
            continue
        ps2 = list(dict.fromkeys(ps))
        cs2 = list(dict.fromkeys(cs))
        for p in ps2[:6]:
            for c in cs2[:6]:
                edges.append(f"- `{p}` → `{c}` : `{fb}`")
                if len(edges) >= 60:
                    return edges
    return edges



def find_shared_csv_contracts(py_meta: Dict[str, Dict[str, object]]) -> List[str]:
    """
    Flags shared CSV contracts:
      - CSVs with multiple producers, or multiple consumers, or both.
    """
    prod: Dict[str, List[str]] = {}
    cons: Dict[str, List[str]] = {}

    for mod, meta in (py_meta or {}).items():
        if not meta or not meta.get("ok"):
            continue
        for f in (meta.get("created_files", []) or []):
            fb = _basenameish(str(f))
            if fb.lower().endswith(".csv"):
                prod.setdefault(fb, []).append(mod)
        for f in (meta.get("reads_files", []) or []):   # <-- correct key
            fb = _basenameish(str(f))
            if fb.lower().endswith(".csv"):
                cons.setdefault(fb, []).append(mod)

    lines: List[str] = []
    keys = sorted(set(prod) | set(cons), key=lambda s: s.lower())
    for fb in keys:
        ps = list(dict.fromkeys(prod.get(fb, [])))
        cs = list(dict.fromkeys(cons.get(fb, [])))
        if len(ps) + len(cs) <= 1:
            continue
        if len(ps) <= 1 and len(cs) <= 1:
            continue

        ptxt = ", ".join(f"`{x}`" for x in ps[:8]) if ps else "[none]"
        ctxt = ", ".join(f"`{x}`" for x in cs[:8]) if cs else "[none]"
        lines.append(f"- `{fb}` — producers: {ptxt} | consumers: {ctxt}")
        if len(lines) >= 50:
            break
    return lines



def detect_network_touchpoints_from_text(src: str) -> List[str]:
    """
    Best-effort heuristic: detect whether a module touches external IO boundaries:
      - MT5 / MetaTrader5
      - HTTP (requests/httpx/urllib)
      - sockets / websockets
      - (optional) low-level networking libs

    Returns: a sorted list of touchpoint tags, e.g. ["MT5", "HTTP", "SOCKETS"].
    """
    if not src:
        return []

    s = src

    tags: Set[str] = set()

    # --- MT5 / MetaTrader5 ---
    mt5_patterns = [
        r"\bimport\s+MetaTrader5\b",
        r"\bfrom\s+MetaTrader5\s+import\b",
        r"\bMetaTrader5\b",
        r"\bmt5\.(initialize|shutdown|copy_rates|copy_rates_from|copy_rates_from_pos|order_send|orders_get|positions_get|symbol_info|symbol_info_tick)\b",
    ]
    if any(re.search(p, s, re.IGNORECASE) for p in mt5_patterns):
        tags.add("MT5")

    # --- HTTP clients ---
    http_patterns = [
        r"\bimport\s+requests\b",
        r"\bfrom\s+requests\s+import\b",
        r"\brequests\.(get|post|put|delete|patch|head|options)\b",
        r"\brequests\.Session\b",
        r"\bHTTPAdapter\b",
        r"\burllib\.request\b",
        r"\bimport\s+httpx\b",
        r"\bhttpx\.(Client|AsyncClient)\b",
        r"\baiohttp\b",
    ]
    if any(re.search(p, s, re.IGNORECASE) for p in http_patterns):
        tags.add("HTTP")

    # --- sockets / websockets ---
    sock_patterns = [
        r"\bimport\s+socket\b",
        r"\bsocket\.socket\b",
        r"\basyncio\.open_connection\b",
        r"\bwebsocket\b",          # websocket-client, websockets, etc.
        r"\bwebsockets\b",
        r"\bzmq\b",                # ZeroMQ often used for streaming
    ]
    if any(re.search(p, s, re.IGNORECASE) for p in sock_patterns):
        tags.add("SOCKETS")

    # --- optional: retries/timeouts often correlate with network calls ---
    # Keep this conservative: only tag if we already saw HTTP/SOCKETS/MT5
    if tags and re.search(r"\b(timeout|retries|retry|backoff|HTTPError|ConnectionError)\b", s, re.IGNORECASE):
        tags.add("RETRY/TIMEOUT")

    return sorted(tags)

# ============================
# MAIN LOGIC / SPEC LINKING (Flow Logic docs)
# ============================

# ============================
# SPEC DOCS (AUTO: all .md in "File Summary")
# ============================

def list_spec_md_files() -> List[Path]:
    """
    Spec docs = all .md files inside OUTPUT_DIR ("File Summary"),
    excluding the generated report itself (python_modules.md) and optional dump.
    """
    if not OUTPUT_DIR.exists():
        return []

    md_files = sorted(OUTPUT_DIR.glob("*.md"), key=lambda p: p.name.lower())

    # Exclude generated outputs (so we don't treat them as "spec docs")
    exclude = {SUMMARY_MD.name, DUMP_MD.name}
    md_files = [p for p in md_files if p.name not in exclude]

    return md_files


# Global cache built once in run()
_SPEC_CTX: Optional[Dict[str, object]] = None

# Graph cache so run() can reuse undirected connectivity without changing signatures
_GRAPH_CACHE: Dict[str, object] = {}


def _find_first_by_basename(root: Path, basename: str) -> Optional[Path]:
    try:
        # Prefer exact basename match anywhere under repo
        for p in (root.rglob(basename) if RECURSIVE else root.glob(basename)):
            if p.is_file() and p.name == basename:
                return p
    except Exception:
        pass
    return None


def _extract_upper_tokens(text: str) -> Set[str]:
    """
    Pull uppercase / underscore tokens used by the spec (events, enums, statuses).
    Examples: RUN_CLOSE, DECISION_EVENT, NON_CERTIFIED, REPLAY_FINGERPRINT, etc.
    """
    if not text:
        return set()

    # Common stop tokens that are not helpful
    STOP = {
        "THE", "AND", "FOR", "WITH", "THIS", "THAT", "FROM", "INTO", "ONLY",
        "TRUE", "FALSE", "NONE", "NULL", "JSON", "CSV", "HTTP", "HTTPS",
        "BEGIN", "END", "EVENT", "MODE", "PASS", "FAIL", "STAGE",
    }

    # Token patterns: ALLCAPS with underscores/numbers (length guard)
    raw = set(re.findall(r"\b[A-Z][A-Z0-9_]{2,40}\b", text))
    out: Set[str] = set()
    for t in raw:
        if t in STOP:
            continue
        # avoid pure numeric-ish noise
        if not any(c.isalpha() for c in t):
            continue
        # drop ultra-generic prefixes
        if t.startswith("YYYY") or t.startswith("HHMM") or t.startswith("MMDD"):
            continue
        out.add(t)
    return out


def build_spec_context(root: Path) -> Dict[str, object]:
    """
    Loads ALL markdown files from OUTPUT_DIR ("File Summary") as spec docs.
    Extracts a token set per doc (uppercase tokens) for touchpoint tagging.
    """
    spec_files = list_spec_md_files()  # List[Path]
    tokens_by_doc: Dict[str, Set[str]] = {}
    text_by_doc: Dict[str, str] = {}
    rel_by_doc: Dict[str, str] = {}

    for p in spec_files:
        try:
            txt = safe_read_text(p)
        except Exception:
            txt = ""

        name = p.name
        text_by_doc[name] = txt
        tokens_by_doc[name] = _extract_upper_tokens(txt)

        # path relative to repo root if possible; else absolute
        try:
            rel_by_doc[name] = _rel(root, p)
        except Exception:
            rel_by_doc[name] = str(p)

    # Back-compat: some run() versions expect spec_paths (even if unused).
    spec_paths: Dict[str, Optional[Path]] = {}

    return {
        "spec_files": spec_files,  # List[Path]
        "tokens_by_doc": tokens_by_doc,  # filename -> Set[str]
        "text_by_doc": text_by_doc,  # filename -> str
        "rel_by_doc": rel_by_doc,  # filename -> rel/abs string
        "spec_paths": spec_paths,  # basename -> Path|None (optional/back-compat)
    }


def _ensure_spec_ctx(root: Path) -> Dict[str, object]:
    global _SPEC_CTX
    if _SPEC_CTX is None:
        _SPEC_CTX = build_spec_context(root)
    return _SPEC_CTX


def _module_text_fingerprint(relpath: str, meta: Dict[str, object]) -> str:
    """
    We don't store full file text in meta (by design). Build a compact searchable
    fingerprint from filename + docstring + defs/classes/constants/imports.
    """
    parts: List[str] = []
    parts.append(relpath)
    parts.append(str(meta.get("docstring", "") or ""))
    parts.extend([str(x) for x in (meta.get("imports", []) or [])])
    parts.extend([str(x) for x in (meta.get("defs", []) or [])])
    parts.extend([str(x) for x in (meta.get("classes", []) or [])])
    for k, v in (meta.get("constants", []) or []):
        parts.append(str(k))
        parts.append(str(v))
    # responsibilities are already inferred keywords
    parts.extend([str(x) for x in (meta.get("responsibilities", []) or [])])
    return "\n".join(parts)


def _spec_touchpoints_for_text(text: str, spec_ctx: Dict[str, object]) -> Dict[str, List[str]]:
    """
    Returns: {spec_basename: [matched_tokens...]} limited for compact output.
    """
    tokens_by_doc: Dict[str, Set[str]] = spec_ctx.get("tokens_by_doc", {})  # type: ignore[assignment]
    if not tokens_by_doc:
        return {}

    utext = text.upper()
    out: Dict[str, List[str]] = {}

    for base, toks in tokens_by_doc.items():
        if not toks:
            continue
        hits = [t for t in toks if t in utext]
        if hits:
            # stable + compact
            hits = sorted(hits, key=str.lower)[:8]
            out[base] = hits
    return out


def _main_logic_parts_from_responsibilities(meta: Dict[str, object]) -> List[str]:
    """
    Converts the existing "Key responsibilities" tags into a short "main logic part" label list.
    """
    resps = [str(x) for x in (meta.get("responsibilities", []) or [])]
    joined = " ".join(resps).lower()

    parts: List[str] = []

    # Map your responsibility labels into higher-level "main logic" buckets
    if "runtime/orchestration" in joined or "loops" in joined:
        parts.append("Runtime orchestration")
    if "market data" in joined:
        parts.append("Market data ingestion")
    if "analysis/scoring" in joined or "setups" in joined:
        parts.append("Strategy / setup detection")
    if "broker/execution" in joined or "orders" in joined:
        parts.append("Execution / broker routing")
    if "risk/position sizing" in joined or "rr/gates" in joined:
        parts.append("Risk & gates")
    if "journaling/audit" in joined or "logging" in joined:
        parts.append("Audit journaling")
    if "exports/reports" in joined:
        parts.append("Views / reporting")
    if "tests/harness" in joined or "verification" in joined:
        parts.append("Verification & test harness")
    if "config/env" in joined or "constants" in joined:
        parts.append("Config & policy")

    if not parts:
        parts.append("Core / utility")

    # Stable, unique, compact
    uniq: List[str] = []
    seen: Set[str] = set()
    for p in parts:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq[:6]


def _spec_influence_parts(touchpoints: Dict[str, List[str]]) -> List[str]:
    """
    Generic: returns up to 3 spec doc names that matched.
    """
    if not touchpoints:
        return []
    docs = sorted(touchpoints.keys(), key=str.lower)[:3]
    return [f"Spec: {d}" for d in docs]



def infer_main_logic_summary(relpath: str, meta: Dict[str, object], spec_ctx: Dict[str, object]) -> Tuple[str, str]:
    """
    Returns (main_logic_part_line, spec_touchpoints_line) as compact markdown-ready strings.

    NOTE: Spec touchpoints are intentionally collapsed to doc names only (no token lists),
    to keep python_modules.md small but still ChatGPT-usable.
    """
    fp = _module_text_fingerprint(relpath, meta)
    touch = _spec_touchpoints_for_text(fp, spec_ctx)

    # Main logic parts = responsibility bucket + (optional) spec alignment tag(s)
    parts = _main_logic_parts_from_responsibilities(meta)

    # If it touches a spec doc, add a short alignment label (no tokens)
    spec_labels: List[str] = []
    if "A+ SYSTEM 3.7-HWR-VX.md" in touch:
        spec_labels.append("A+ SYSTEM")
    if "Logging_Retention.md" in touch:
        spec_labels.append("Logging_Retention")
    if "Tests.md" in touch:
        spec_labels.append("Tests")

    if spec_labels:
        parts.append("Spec-aligned: " + ", ".join(spec_labels))

    # De-dupe
    seen: Set[str] = set()
    parts2: List[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            parts2.append(p)

    main_logic = ", ".join(parts2[:6])

    # Spec touchpoints = just doc names
    spec_touchpoints = ""
    if spec_labels:
        spec_touchpoints = " | ".join(spec_labels)

    return main_logic, spec_touchpoints


def connected_components_of(directed: Dict[str, Set[str]]) -> List[List[str]]:
    """
    Fallback: treat directed graph as undirected and compute components.
    """
    undirected: Dict[str, Set[str]] = defaultdict(set)
    for a, bs in directed.items():
        undirected.setdefault(a, set())
        for b in bs:
            undirected[a].add(b)
            undirected[b].add(a)
    return connected_components(undirected)

# ============================
# MODULE SUMMARY RENDERING
# ============================
def md_module_summary_py(
    relpath: str,
    meta: Dict[str, object],
    imports_resolved: List[str],
    imported_by_resolved: List[str],
) -> str:
    role = str(meta.get("role", "MODULE"))
    resps: List[str] = meta.get("responsibilities", []) or []
    doc = _truncate(str(meta.get("docstring", "")), MAX_DOCSTRING_CHARS)

    defs: List[str] = meta.get("defs", []) or []
    classes: List[str] = meta.get("classes", []) or []
    constants: List[Tuple[str, str]] = meta.get("constants", []) or []
    has_main = bool(meta.get("has_main_guard", False))
    has_argparse = bool(meta.get("has_argparse", False))
    sidefx: List[str] = meta.get("top_level_side_effects", []) or []
    ok = bool(meta.get("ok", False))
    err = meta.get("error")

    created_files: List[str] = meta.get("created_files", []) or []
    reads_files: List[str] = meta.get("reads_files", []) or []
    touchpoints: List[str] = meta.get("network_touchpoints", []) or []
    io_label = str(meta.get("io_label", "internal"))

    # Hard-coded Change Impact Hints (depends on file name patterns)
    low = (relpath or "").lower()
    impact_hints: List[str] = []

    # core causal chain reminder
    impact_hints.append("If a change affects a CSV field or decision outcome, always check: Analyzer → Decision → Journal → Export (in that order).")

    # filename-based “where else to look”
    if any(k in low for k in ["export", "csv", "writer", "report"]):
        impact_hints.append("Likely touches output contracts (CSV/MD). Also scan ExportUtils + any *Export* modules that write the same CSV.")
    if any(k in low for k in ["journal", "audit", "trace", "event", "log"]):
        impact_hints.append("Likely affects audit truth / replay. Also scan reason-code registry + decision finalizer.")
    if any(k in low for k in ["decision", "final", "verdict", "gate", "block", "risk"]):
        impact_hints.append("Likely affects final outcome gates. Also scan analyzers upstream + exporters downstream.")
    if any(k in low for k in ["analy", "setup", "ict", "score", "rank", "sentiment"]):
        impact_hints.append("Likely affects ranking/scoring fields. Also scan decision finalization + export ordering/filters.")
    if any(k in low for k in ["market", "data", "ohlc", "bars", "feed"]):
        impact_hints.append("Likely affects data freshness/integrity. Also scan caching/staleness logic + any MT5/network adapters.")
    if any(k in low for k in ["mt5", "broker", "execution", "order"]):
        impact_hints.append("Likely touches live execution. Also scan risk gates + journal events for trace completeness.")

    # keep compact, avoid spam
    impact_hints = impact_hints[:6]

    lines: List[str] = []
    lines.append(f"#### {format_node(relpath)}")

    # Status / role
    if ok:
        lines.append(f"- **Role:** `{role}`" + (" • `has __main__`" if has_main else "") + (" • `argparse`" if has_argparse else ""))
    else:
        lines.append(f"- **Role:** `{role}` • **Status:** `FAILED`")
        if err:
            lines.append(f"  - Error: `{_md_escape(str(err))}`")
        return "\n".join(lines)

    # Responsibilities
    if resps:
        lines.append(f"- **Responsibilities:** " + ", ".join(f"`{r}`" for r in resps))
    else:
        lines.append(f"- **Responsibilities:** `[none inferred]`")

    # Internal links
    if imports_resolved:
        show = imports_resolved[:MAX_LIST_ITEMS]
        tail = "" if len(imports_resolved) <= len(show) else f" (+{len(imports_resolved)-len(show)} more)"
        lines.append(f"- **Internal imports:** " + ", ".join(format_node(x) for x in show) + tail)
    else:
        lines.append(f"- **Internal imports:** `[none detected]`")

    if imported_by_resolved:
        show = imported_by_resolved[:MAX_LIST_ITEMS]
        tail = "" if len(imported_by_resolved) <= len(show) else f" (+{len(imported_by_resolved)-len(show)} more)"
        lines.append(f"- **Imported by:** " + ", ".join(format_node(x) for x in show) + tail)
    else:
        lines.append(f"- **Imported by:** `[none detected]`")

    # IO / touchpoints
    lines.append(f"- **IO label:** `{io_label}`")
    if created_files:
        show = created_files[:MAX_LIST_ITEMS]
        tail = "" if len(created_files) <= len(show) else f" (+{len(created_files)-len(show)} more)"
        lines.append(f"- **Creates/writes files (heuristic):** " + ", ".join(f"`{_md_escape(x)}`" for x in show) + tail)
    else:
        lines.append(f"- **Creates/writes files (heuristic):** `[none detected]`")

    if reads_files:
        show = reads_files[:MAX_LIST_ITEMS]
        tail = "" if len(reads_files) <= len(show) else f" (+{len(reads_files)-len(show)} more)"
        lines.append(f"- **Reads files (heuristic):** " + ", ".join(f"`{_md_escape(x)}`" for x in show) + tail)
    else:
        lines.append(f"- **Reads files (heuristic):** `[none detected]`")

    if touchpoints:
        lines.append(f"- **Network/MT5 touchpoints (heuristic):** " + ", ".join(f"`{_md_escape(x)}`" for x in touchpoints))
    else:
        lines.append(f"- **Network/MT5 touchpoints (heuristic):** `[none detected]`")

    # Docstring
    if doc:
        lines.append("")
        lines.append("**Why it exists (docstring/intent):**")
        lines.append("")
        lines.append("```text")
        lines.append(doc)
        lines.append("```")

    # Compact “what’s inside”
    inside_bits: List[str] = []
    if classes:
        inside_bits.append(
            "classes: " + ", ".join(classes[:MAX_LIST_ITEMS]) +
            ("" if len(classes) <= MAX_LIST_ITEMS else f", +{len(classes)-MAX_LIST_ITEMS} more")
        )
    if defs:
        inside_bits.append(
            "funcs: " + ", ".join(defs[:MAX_LIST_ITEMS]) +
            ("" if len(defs) <= MAX_LIST_ITEMS else f", +{len(defs)-MAX_LIST_ITEMS} more")
        )
    if constants:
        cshow = constants[:MAX_CONSTANTS]
        inside_bits.append(
            "consts: " + ", ".join([f"{k}={v}" for (k, v) in cshow]) +
            ("" if len(constants) <= len(cshow) else f", +{len(constants)-len(cshow)} more")
        )
    if inside_bits:
        lines.append(f"- **Inside:** " + " • ".join(inside_bits))

    # Change Impact Hints (hard-coded)
    lines.append("")
    lines.append("**Change Impact Hints (hard-coded):**")
    for h in impact_hints:
        lines.append(f"- {_md_escape(h)}")

    # Risk notes
    risk_notes: List[str] = []
    if sidefx:
        risk_notes.append("⚠️ import-time side effects (heuristic)")
    if role == "ENTRYPOINT":
        risk_notes.append("⚠️ executing may touch external systems")
    if touchpoints:
        risk_notes.append("⚠️ boundary module (network/MT5)")
    if risk_notes:
        lines.append(f"- **Risk notes:** " + "; ".join(risk_notes))
        if sidefx:
            lines.append(f"  - Side effects: " + "; ".join(f"`{s}`" for s in sidefx))

    return "\n".join(lines)






def md_module_summary_bat(relpath: str, meta: Dict[str, object]) -> str:
    ok = bool(meta.get("ok", False))
    err = meta.get("error")

    lines: List[str] = []
    lines.append(f"### {format_node(relpath)}")

    if not ok:
        lines.append(f"- **Parse:** ❌ FAILED — `{_md_escape(str(err))}`")
        return "\n".join(lines)

    resps: List[str] = meta.get("responsibilities", []) or []
    set_vars: List[str] = meta.get("set_vars", []) or []
    py_inv: List[str] = meta.get("python_invocations", []) or []
    refs: List[str] = meta.get("referenced_files", []) or []

    lines.append("- **Role:** `BAT`")
    if resps:
        lines.append("- **Responsibilities:** " + ", ".join(f"`{r}`" for r in resps[:4]))

    if set_vars:
        lines.append("- **Env vars:** " + ", ".join(f"`{v}`" for v in set_vars[:8]) + ("" if len(set_vars) <= 8 else f" (+{len(set_vars)-8} more)"))

    if py_inv:
        lines.append("- **Python calls:** " + ", ".join(f"`{_md_escape(s)}`" for s in py_inv[:4]) + ("" if len(py_inv) <= 4 else f" (+{len(py_inv)-4} more)"))

    if refs:
        lines.append("- **References:** " + ", ".join(f"`{r}`" for r in refs[:10]) + ("" if len(refs) <= 10 else f" (+{len(refs)-10} more)"))

    return "\n".join(lines)





def _brief_desc_py(meta: Dict[str, object]) -> str:
    if not meta or not meta.get("ok"):
        err = meta.get("error") if meta else "unknown"
        return f"SKIPPED/FAILED: {_truncate(_md_escape(str(err)), 90)}"

    role = str(meta.get("role", "MODULE"))
    doc = _truncate(str(meta.get("docstring", "")).strip(), 110)
    resps: List[str] = meta.get("responsibilities", []) or []

    # Prefer docstring if present; else fall back to role + top 1-2 responsibilities
    if doc:
        return doc
    if resps:
        top = ", ".join(resps[:2])
        return f"{role} — {top}"
    return role


def _brief_desc_bat(meta: Dict[str, object]) -> str:
    if not meta or not meta.get("ok"):
        err = meta.get("error") if meta else "unknown"
        return f"SKIPPED/FAILED: {_truncate(_md_escape(str(err)), 90)}"

    header: List[str] = meta.get("header_comments", []) or []
    resps: List[str] = meta.get("responsibilities", []) or []

    # Prefer header comments if present; else responsibilities
    if header:
        joined = " ".join(h.strip() for h in header if h.strip())
        return _truncate(_md_escape(joined), 110)
    if resps:
        return _truncate(", ".join(resps[:3]), 110)
    return "BAT orchestration"


def brief_desc_for_node(
    relpath: str,
    py_meta: Dict[str, Dict[str, object]],
    bat_meta: Dict[str, Dict[str, object]],
    yaml_meta: Dict[str, Dict[str, object]],
) -> str:
    low = relpath.lower()
    if low.endswith(".bat"):
        return _brief_desc_bat(bat_meta.get(relpath, {}))
    if low.endswith(".py"):
        return _brief_desc_py(py_meta.get(relpath, {}))
    if low.endswith(".yaml") or low.endswith(".yml"):
        meta = yaml_meta.get(relpath, {})
        if not meta or not meta.get("ok"):
            err = meta.get("error") if meta else "unknown"
            return f"SKIPPED/FAILED: {_truncate(_md_escape(str(err)), 90)}"
        keys = meta.get("top_keys", []) or []
        if keys:
            return _truncate("YAML keys: " + ", ".join(keys[:6]), 110)
        return "YAML configuration"
    return "file"



# ============================
# MAIN
# ============================
def run() -> None:
    root = ROOT_FOLDER.resolve()

    # Build spec context once (Flow Logic docs)
    _ensure_spec_ctx(root)

    # ------------------------------------------------------------
    # Mirror latest MQL5 files to OneDrive BEFORE scanning
    # (so the summaries reflect the latest terminal source)
    # ------------------------------------------------------------
    did_mirror = False
    try:
        if MQL5_SRC_DIR.exists():
            mirror_folder(
                MQL5_SRC_DIR,
                ONEDRIVE_DST_DIR,
                delete_extraneous=True,   # replace old files
            )
            did_mirror = True
            print(f"[MIRROR] MQL5 -> OneDrive OK: {ONEDRIVE_DST_DIR}")
        else:
            print(f"[MIRROR] SKIP: missing source dir: {MQL5_SRC_DIR}")
    except Exception as e:
        print(f"[MIRROR] FAILED: {e}")

    # ------------------------------------------------------------
    # Print Flow Logic docs presence to console
    # ------------------------------------------------------------
    spec_ctx = _ensure_spec_ctx(root)
    spec_paths = spec_ctx.get("spec_paths", {}) or {}

    print("\n## Flow Logic docs (from 'File Summary' folder)\n")
    spec_ctx = _ensure_spec_ctx(root)
    rel_by_doc = spec_ctx.get("rel_by_doc", {}) or {}

    if not rel_by_doc:
        print("- [no .md files found in 'File Summary']")
    else:
        for name in sorted(rel_by_doc.keys(), key=str.lower):
            print(f"- {name}: {rel_by_doc[name]}")

    # ------------------------------------------------------------
    # Collect files
    # ------------------------------------------------------------
    all_py = _module_candidates_in_repo(root)
    all_bat = _bat_candidates_in_repo(root)
    all_yaml = _yaml_candidates_in_repo(root)
    all_mql5 = _mql5_candidates_in_dir(MQL5_SCAN_DIR)

    # ------------------------------------------------------------
    # Parse MQL5 (from OneDrive MQL5_SCAN_DIR)
    # ------------------------------------------------------------
    mql5_meta: Dict[str, Dict[str, object]] = {}
    mql5_failed: Dict[str, str] = {}
    mql5_ok = 0

    mql5_relpaths: List[str] = []
    mql5_refs: Dict[str, List[str]] = {}  # relpath -> raw include tokens

    for p in all_mql5:
        ok_file, reason = allow_file(p)

        # Make a stable namespace so it never collides with repo files
        relp = _rel(MQL5_SCAN_DIR, p)  # e.g. Experts/Brook/foo.mq5
        relp = f"MQL5/{relp}"  # namespaced node in the graph
        mql5_relpaths.append(relp)

        if not ok_file:
            mql5_failed[relp] = f"SKIPPED ({reason})"
            mql5_meta[relp] = {"ok": False, "error": f"SKIPPED ({reason})"}
            continue

        meta = parse_mql5_file(p)
        mql5_meta[relp] = meta
        if meta.get("ok"):
            mql5_ok += 1
            # raw include tokens (like "Trade/Trade.mqh" or "MyLib.mqh")
            mql5_refs[relp] = [str(x) for x in (meta.get("includes", []) or [])]
        else:
            mql5_failed[relp] = str(meta.get("error"))
            mql5_refs[relp] = []

    # NOTE:
    # A duplicate allow_file() previously lived here, which could confuse behavior.
    # Use the global allow_file() defined above for consistent filtering.
    allow_file_local = allow_file  # backward-compatible alias if you ever referenced it below

    py_found = len(all_py)
    bat_found = len(all_bat)
    yaml_found = len(all_yaml)

    # ------------------------------------------------------------
    # Parse python
    # ------------------------------------------------------------
    py_meta: Dict[str, Dict[str, object]] = {}
    py_failed: Dict[str, str] = {}
    py_ok = 0
    internal_stems = {p.stem for p in all_py}
    stem_map = stem_to_relpaths(all_py, root)

    for p in all_py:
        ok_file, reason = allow_file(p)
        relp = _rel(root, p)
        if not ok_file:
            py_failed[relp] = f"SKIPPED ({reason})"
            py_meta[relp] = {"ok": False, "error": f"SKIPPED ({reason})"}
            continue

        meta = parse_python_file(p)
        py_meta[relp] = meta
        if meta.get("ok"):
            py_ok += 1
        else:
            py_failed[relp] = str(meta.get("error"))

    # ------------------------------------------------------------
    # Parse BAT
    # ------------------------------------------------------------
    bat_meta: Dict[str, Dict[str, object]] = {}
    bat_failed: Dict[str, str] = {}
    bat_ok = 0

    for p in all_bat:
        ok_file, reason = allow_file(p)
        relp = _rel(root, p)
        if not ok_file:
            bat_failed[relp] = f"SKIPPED ({reason})"
            bat_meta[relp] = {"ok": False, "error": f"SKIPPED ({reason})"}
            continue

        meta = parse_bat_file(p)
        bat_meta[relp] = meta
        if meta.get("ok"):
            bat_ok += 1
        else:
            bat_failed[relp] = str(meta.get("error"))

    # ------------------------------------------------------------
    # Parse YAML
    # ------------------------------------------------------------
    yaml_meta: Dict[str, Dict[str, object]] = {}
    yaml_failed: Dict[str, str] = {}
    yaml_ok = 0

    for p in all_yaml:
        ok_file, reason = allow_file(p)
        relp = _rel(root, p)
        if not ok_file:
            yaml_failed[relp] = f"SKIPPED ({reason})"
            yaml_meta[relp] = {"ok": False, "error": f"SKIPPED ({reason})"}
            continue

        meta = parse_yaml_file(p)
        yaml_meta[relp] = meta
        if meta.get("ok"):
            yaml_ok += 1
        else:
            yaml_failed[relp] = str(meta.get("error"))

    # ------------------------------------------------------------
    # Resolve internal python imports to real files
    # ------------------------------------------------------------
    py_import_edges: Dict[str, Set[str]] = defaultdict(set)
    internal_import_files_by_py: Dict[str, List[str]] = {}

    for relp, meta in py_meta.items():
        if not meta.get("ok"):
            continue
        imports = meta.get("imports", []) or []
        stems = infer_internal_stems([str(x) for x in imports], internal_stems)
        resolved = resolve_stems_to_files(stems, stem_map)
        internal_import_files_by_py[relp] = resolved
        for dst in resolved:
            py_import_edges[relp].add(dst)

    # Reverse edges: imported_by
    imported_by: Dict[str, Set[str]] = defaultdict(set)
    for src, dsts in py_import_edges.items():
        for dst in dsts:
            imported_by[dst].add(src)

    # ------------------------------------------------------------
    # Resolve bat references (raw tokens; graph builder resolves them)
    # ------------------------------------------------------------
    bat_refs: Dict[str, List[str]] = {}
    for relp, meta in bat_meta.items():
        if not meta.get("ok"):
            continue
        bat_refs[relp] = [str(x) for x in (meta.get("referenced_files", []) or [])]

    # ------------------------------------------------------------
    # Resolve yaml references (raw tokens; graph builder resolves them)
    # ------------------------------------------------------------
    yaml_refs: Dict[str, List[str]] = {}
    for relp, meta in yaml_meta.items():
        if not meta.get("ok"):
            continue
        yaml_refs[relp] = [str(x) for x in (meta.get("referenced_files", []) or [])]

    # ------------------------------------------------------------
    # Graph: build connected components (existing behavior)
    # ------------------------------------------------------------
    py_relpaths = sorted(py_meta.keys(), key=str.lower)
    bat_relpaths = sorted(bat_meta.keys(), key=str.lower)
    yaml_relpaths = sorted(yaml_meta.keys(), key=str.lower)

    directed = build_directed_graph(
        py_relpaths,
        bat_relpaths,
        yaml_relpaths,
        py_import_edges,
        bat_refs,
        yaml_refs,
        root,
        extra_nodes=mql5_relpaths,
        extra_refs=mql5_refs,
    )

    undirected = _GRAPH_CACHE.get("undirected")
    if isinstance(undirected, dict) and undirected:
        comps = connected_components(undirected)  # correct: components must be undirected
    else:
        comps = connected_components_of(directed)  # fallback

    # ------------------------------------------------------------
    # IO / contract aggregation (NEW)
    # ------------------------------------------------------------
    producers_by_file: Dict[str, List[str]] = defaultdict(list)
    consumers_by_file: Dict[str, List[str]] = defaultdict(list)

    for mod, meta in py_meta.items():
        if not meta.get("ok"):
            continue
        for f in (meta.get("created_files", []) or []):
            producers_by_file[_basenameish(str(f))].append(mod)
        for f in (meta.get("reads_files", []) or []):
            consumers_by_file[_basenameish(str(f))].append(mod)

    def _uniq(xs: List[str]) -> List[str]:
        seen = set()
        out2: List[str] = []
        for x in xs:
            if x not in seen:
                seen.add(x)
                out2.append(x)
        return out2

    # shared CSV contracts: files that appear in >=2 modules (read or write)
    shared_csvs: List[str] = []
    all_files = set(producers_by_file.keys()) | set(consumers_by_file.keys())
    for f in all_files:
        if not str(f).lower().endswith(".csv"):
            continue
        mods = _uniq((producers_by_file.get(f, []) or []) + (consumers_by_file.get(f, []) or []))
        if len(mods) >= 2:
            shared_csvs.append(f)
    shared_csvs = sorted(shared_csvs, key=str.lower)

    # ------------------------------------------------------------
    # Write markdown
    # ------------------------------------------------------------
    replace_file(SUMMARY_MD)

    py_failed_count = len(py_failed)
    bat_failed_count = len(bat_failed)
    yaml_failed_count = len(yaml_failed)

    with SUMMARY_MD.open("w", encoding="utf-8") as out:
        out.write("# Python/BAT Module Map (compact)\n\n")

        # Show whether spec docs were found (tiny, non-noisy)

        out.write("## Flow Logic docs detected (from 'File Summary' folder)\n\n")

        spec_ctx = _ensure_spec_ctx(root)
        rel_by_doc = spec_ctx.get("rel_by_doc", {}) or {}

        if not rel_by_doc:
            out.write("- `[no .md files found in 'File Summary']`\n\n")
        else:
            for name in sorted(rel_by_doc.keys(), key=str.lower):
                out.write(f"- `{name}`: `{_md_escape(rel_by_doc[name])}`\n")
            out.write("\n")

        out.write("---\n\n")

        # NEW: shared CSV contracts + tiny IO dependency graph (global, compact)
        out.write("## Shared CSV contracts + IO dependency graph (heuristic)\n\n")
        out.write("If a change affects a CSV field or decision outcome, always check:\n")
        out.write("- `Analyzer → Decision → Journal → Export` (in that order)\n\n")

        if shared_csvs:
            out.write("### Shared CSV contracts (same file seen in multiple modules)\n\n")
            for f in shared_csvs[:120]:
                mods = _uniq((producers_by_file.get(f, []) or []) + (consumers_by_file.get(f, []) or []))
                mods_show = mods[:12]
                tail = "" if len(mods) <= len(mods_show) else f" (+{len(mods)-len(mods_show)} more)"
                out.write(f"- `{_md_escape(f)}` ← " + ", ".join(format_node(m) for m in mods_show) + tail + "\n")
            if len(shared_csvs) > 120:
                out.write(f"- `. +{len(shared_csvs)-120} more`\n")
            out.write("\n")
        else:
            out.write("### Shared CSV contracts\n\n- None detected\n\n")

        # Tiny IO dependency edges: producer -> consumer for same file
        out.write("### Tiny IO dependency edges (producer → consumer via same file)\n\n")
        edges_written = 0
        for f in sorted(all_files, key=str.lower):
            prods = _uniq(producers_by_file.get(f, []) or [])
            cons = _uniq(consumers_by_file.get(f, []) or [])
            if not prods or not cons:
                continue
            prods_show = prods[:6]
            cons_show = cons[:6]
            out.write(
                f"- `{_md_escape(f)}`: "
                + " • producers: " + ", ".join(format_node(m) for m in prods_show)
                + (" (+more)" if len(prods) > len(prods_show) else "")
                + " → consumers: " + ", ".join(format_node(m) for m in cons_show)
                + (" (+more)" if len(cons) > len(cons_show) else "")
                + "\n"
            )
            edges_written += 1
            if edges_written >= 80:
                out.write("- `. [truncated: too many edges]`\n")
                break
        if edges_written == 0:
            out.write("- None detected\n")
        out.write("\n---\n\n")

        # Existing group output
        for idx, nodes in enumerate(comps, 1):
            out.write(f"## Group {idx} (size={len(nodes)})\n\n")

            # Determine entrypoints
            eps = [n for n in nodes if n.lower().endswith(".py") and is_entrypoint_py(n, py_meta)]
            eps = sorted(eps, key=str.lower)[:MAX_ENTRYPOINTS_SHOWN]

            # Build bucket map for this group
            bucket_of: Dict[str, str] = {}
            for n in nodes:
                low = n.lower()
                if low.endswith(".py"):
                    bucket_of[n] = group_bucket_for_py(n, py_meta)
                elif low.endswith(".bat"):
                    bucket_of[n] = group_bucket_for_bat(n, bat_meta)
                elif low.endswith((".yaml", ".yml")):
                    bucket_of[n] = "Config / YAML"
                else:
                    bucket_of[n] = "Core / Other"

            # Start Here
            out.write("### Start Here\n\n")
            if eps:
                for e in eps:
                    out.write(f"- {format_node(e)}\n")
            else:
                out.write("- [no entrypoints]\n")
            out.write("\n")

            out.write("### Critical paths (heuristic)\n\n")
            if eps:
                for line in find_critical_paths(eps, nodes, directed):
                    out.write(line + "\n")
            else:
                out.write("- [no entrypoints → cannot compute critical paths]\n")
            out.write("\n")

            # Bucket map
            out.write("### Subsystems\n\n")
            by_bucket: Dict[str, List[str]] = defaultdict(list)
            for n in nodes:
                by_bucket[bucket_of.get(n, "Core / Other")].append(n)
            for b in sorted(by_bucket.keys(), key=str.lower):
                out.write(f"- **{b}** ({len(by_bucket[b])})\n")
            out.write("\n")

            # Subsystem dependency map
            out.write("### Subsystem dependency map (collapsed)\n\n")
            for line in bucket_dependency_map(nodes, directed, bucket_of):
                out.write(line + "\n")
            out.write("\n")

            # File-level dep map
            out.write("### File-level dependency map (collapsed)\n\n")
            dep_lines = collapsed_dep_map_lines(nodes, directed)
            if dep_lines:
                for line in dep_lines:
                    out.write(line + "\n")
            else:
                out.write("- [no dependencies]\n")
            out.write("\n")

            # Module summaries
            out.write("### Modules\n\n")

            for n in nodes:
                low = n.lower()

                if low.endswith(".py"):
                    meta = py_meta.get(n, {})
                    imports_resolved = internal_import_files_by_py.get(n, []) or []
                    imported_by_resolved = sorted(list(imported_by.get(n, set())), key=str.lower)

                    out.write(
                        md_module_summary_py(
                            n,
                            meta,
                            imports_resolved=imports_resolved,
                            imported_by_resolved=imported_by_resolved,
                        )
                        + "\n\n"
                    )

                elif low.endswith(".bat"):
                    meta = bat_meta.get(n, {})
                    out.write(md_module_summary_bat(n, meta) + "\n\n")

                elif low.endswith((".yaml", ".yml")):
                    meta = yaml_meta.get(n, {})
                    out.write(md_module_summary_yaml(n, meta) + "\n\n")

                elif low.startswith("mql5/") or low.endswith((".mq5", ".mqh", ".mq4")):
                    meta = mql5_meta.get(n, {})
                    includes_raw = meta.get("includes", []) or []

                    includes_resolved: List[str] = []
                    if isinstance(includes_raw, list):
                        all_nodes = (
                                set(py_relpaths)
                                | set(bat_relpaths)
                                | set(yaml_relpaths)
                                | set(mql5_relpaths)
                        )
                        for tok in includes_raw:
                            r = _resolve_any_ref(str(tok), all_nodes)  # basename resolution is built-in
                            if r:
                                includes_resolved.append(r)

                    out.write(md_module_summary_mql5(n, meta, includes_resolved) + "\n\n")

                else:
                    out.write(f"#### {format_node(n)}\n- [unhandled type]\n\n")

        # Failures list (compact)
        out.write("## Failures / Skips\n\n")
        if not py_failed and not bat_failed and not yaml_failed:
            out.write("- None\n")
        else:
            if py_failed:
                out.write("### Python failures/skips\n\n")
                for k in sorted(py_failed.keys(), key=str.lower)[:200]:
                    out.write(f"- {format_node(k)} — `{_md_escape(py_failed[k])}`\n")
                if len(py_failed) > 200:
                    out.write(f"- `. +{len(py_failed)-200} more`\n")
                out.write("\n")
            if bat_failed:
                out.write("### BAT failures/skips\n\n")
                for k in sorted(bat_failed.keys(), key=str.lower)[:200]:
                    out.write(f"- {format_node(k)} — `{_md_escape(bat_failed[k])}`\n")
                if len(bat_failed) > 200:
                    out.write(f"- `. +{len(bat_failed)-200} more`\n")
                out.write("\n")
            if yaml_failed:
                out.write("### YAML failures/skips\n\n")
                for k in sorted(yaml_failed.keys(), key=str.lower)[:200]:
                    out.write(f"- {format_node(k)} — `{_md_escape(yaml_failed[k])}`\n")
                if len(yaml_failed) > 200:
                    out.write(f"- `. +{len(yaml_failed)-200} more`\n")
                out.write("\n")

        # Run stats (existing behavior)
        out.write("\n---\n\n")
        out.write("## Run Stats\n\n")
        out.write(f"- Python files found: `{py_found}` • parsed ok: `{py_ok}` • failed/skipped: `{py_failed_count}`\n")
        out.write(f"- BAT files found: `{bat_found}` • parsed ok: `{bat_ok}` • failed/skipped: `{bat_failed_count}`\n")
        out.write(f"- YAML files found: `{yaml_found}` • parsed ok: `{yaml_ok}` • failed/skipped: `{yaml_failed_count}`\n")
        try:
            out_path = _rel(root, SUMMARY_MD)
        except Exception:
            out_path = str(SUMMARY_MD)
        out.write(f"- Output: `{_md_escape(out_path)}`\n")

    print(f"\nWrote: {SUMMARY_MD}")

    # ------------------------------------------------------------
    # Mirror latest MQL5 files to OneDrive (REPLACE OLD FILES)
    # ------------------------------------------------------------
    # Mirror now happens at the START of run() so scans reflect latest files.
    # Keep this block for compatibility, but avoid doing it twice.
    if not locals().get("did_mirror", False):
        try:
            if MQL5_SRC_DIR.exists():
                mirror_folder(
                    MQL5_SRC_DIR,
                    ONEDRIVE_DST_DIR,
                    delete_extraneous=True,
                )
                print(f"[MIRROR] MQL5 -> OneDrive OK: {ONEDRIVE_DST_DIR}")
            else:
                print(f"[MIRROR] SKIP: missing source dir: {MQL5_SRC_DIR}")
        except Exception as e:
            print(f"[MIRROR] FAILED: {e}")
    else:
        print(f"[MIRROR] SKIP: already mirrored earlier in run()")


if __name__ == "__main__":
    run()
