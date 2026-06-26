#!/usr/bin/env python3
"""
GoogleSheets_Log.py

Single-file logger for the GoogleSheets suite.

Goals
- One shared log text file for ALL modules.
- Log function calls/returns/exceptions with module + function identity.
- Easy "decision" breadcrumbs.
- Optional auto-wrap: wrap all functions in a module automatically.

No imports from your other modules (avoids circular imports).
Stdlib only.
"""

from __future__ import annotations

import os
import sys
import time
import inspect
import traceback
import threading
import functools
from pathlib import Path
from typing import Any, Callable, Optional

# --- Spam control (console dedupe) ---
# Only affects console echo; file still records everything.
_NOISY_EVENTS = {
    "MISSING_COORDS_AFTER_PROCESSING",
    "GEOCODE_FAIL",
    "GEOCODE_QUERY_EMPTY",
}

# How long we suppress repeats for the same event signature (seconds)
_NOISY_TTL_SECONDS = 30.0

# Hard cap to prevent memory growth
_NOISY_MAX_KEYS = 50000

# (key -> (last_ts, suppressed_count))
_NOISY_SEEN: dict[tuple, tuple[float, int]] = {}
_NOISY_LOCK = threading.Lock()

# ----------------------------
# Config (can be overridden)
# ----------------------------
DEFAULT_LOG_DIRNAME = "Log"
DEFAULT_LOG_FILENAME = "GoogleSheets_All.txt"

# Truncation so logs don't explode
MAX_REPR = 600          # max chars for args/return repr
MAX_TRACE = 12000       # max chars for traceback
MAX_LINE = 4000         # max chars per single log line

# Thread-safe file writes
_LOCK = threading.Lock()
_RUN_ID: Optional[str] = None

# Global logger state
_LOG_PATH: Optional[Path] = None
_ECHO_CONSOLE: bool = True
_LEVEL: int = 20  # 10=DEBUG 20=INFO 30=WARN 40=ERROR

# Per-thread nesting to show call depth
_TLS = threading.local()
# ----------------------------
# Shared lightweight correction log API (used by modules)
# ----------------------------

# Separate lock for "corrections/events" style logging that modules may call frequently.
# Kept distinct from _LOCK (main file write lock) so callers can share a common guard.
_log_lock = threading.Lock()

def _noisy_signature(msg: str, extra: Optional[dict]) -> tuple:
    """
    Build a stable signature for deduping noisy console spam.
    We intentionally keep it compact and stable.

    We dedupe by:
      - msg code
      - query (if present)
      - Number/Street/Suburb (if present)
    """
    msg = (msg or "").strip()

    def _g(k: str) -> str:
        try:
            if not extra:
                return ""
            v = extra.get(k, "")
            return "" if v is None else str(v).strip()
        except Exception:
            return ""

    # include most helpful identity fields if present
    return (
        msg,
        _g("query"),
        _g("Number"),
        _g("Street"),
        _g("Suburb"),
    )


def _should_echo_event_to_console(level_num: int, msg: str, extra: Optional[dict]) -> tuple[bool, Optional[str]]:
    """
    Returns (echo?, optional_override_line).

    - For WARN/ERROR we normally echo.
    - For noisy events, we dedupe/rate-limit console echo.
    - File logging is NOT affected.
    """
    # Keep existing policy
    if not _should_print_to_console(level_num, msg):
        return False, None

    # Only dedupe specific noisy codes
    code = (msg or "").strip()
    if code not in _NOISY_EVENTS:
        return True, None

    now = time.time()
    sig = _noisy_signature(code, extra)

    with _NOISY_LOCK:
        # occasional cleanup to avoid unbounded growth
        if len(_NOISY_SEEN) > _NOISY_MAX_KEYS:
            # drop oldest-ish entries quickly
            try:
                items = list(_NOISY_SEEN.items())
                items.sort(key=lambda kv: kv[1][0])  # by last_ts
                for k, _ in items[: max(1, len(items) // 3)]:
                    _NOISY_SEEN.pop(k, None)
            except Exception:
                _NOISY_SEEN.clear()

        prev = _NOISY_SEEN.get(sig)
        if not prev:
            _NOISY_SEEN[sig] = (now, 0)
            return True, None

        last_ts, suppressed = prev
        if (now - last_ts) < _NOISY_TTL_SECONDS:
            # suppress this console echo; bump count
            _NOISY_SEEN[sig] = (last_ts, suppressed + 1)
            return False, None

        # TTL expired: allow one echo again.
        # If we suppressed many, print a short summary BEFORE the new echo.
        summary = None
        if suppressed > 0:
            summary = f"⚠️ {code} (suppressed {suppressed} repeats in last {int(_NOISY_TTL_SECONDS)}s)"
        _NOISY_SEEN[sig] = (now, 0)
        return True, summary

def log_correction(
    event: str,
    details: str = "",
    street: str = "",
    *,
    module: Optional[str] = None,
    fn: Optional[str] = None,
) -> None:
    """
    Centralized lightweight event log.

    IMPORTANT:
    - If module/fn aren't provided, we infer the caller module/function so the log
      correctly attributes the source (not GoogleSheets_Log).
    """
    module, fn = _maybe_infer_module_fn(module, fn)

    extra: dict[str, Any] = {}
    if street:
        extra["street"] = street
    if details:
        extra["details"] = details

    _log(20, "INFO", f"CORRECTION: {event}", module=module, fn=fn, extra=extra)



def _log_quiet(
    event: str,
    details: str = "",
    *,
    important: bool = False,
    street: str = "",
    module: Optional[str] = None,
    fn: Optional[str] = None,
) -> None:
    """
    Centralized quiet logger that modules can delegate to.

    - If important=True, record via log_correction()
    - Else emit DEBUG quiet events (or ignore if level higher)

    IMPORTANT:
    - If module/fn aren't provided, we infer caller module/function.
    """
    module, fn = _maybe_infer_module_fn(module, fn)

    if important:
        log_correction(event, details=details, street=street, module=module, fn=fn)
        return

    extra: dict[str, Any] = {}
    if street:
        extra["street"] = street
    if details:
        extra["details"] = details

    _log(10, "DEBUG", f"QUIET: {event}", module=module, fn=fn, extra=extra)



def _get_depth() -> int:
    d = getattr(_TLS, "depth", 0)
    return int(d or 0)


def _inc_depth() -> None:
    _TLS.depth = _get_depth() + 1


def _dec_depth() -> None:
    _TLS.depth = max(0, _get_depth() - 1)


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _safe_repr(x: Any) -> str:
    try:
        s = repr(x)
    except Exception:
        s = f"<unreprable {type(x).__name__}>"
    if len(s) > MAX_REPR:
        s = s[:MAX_REPR] + "…"
    return s


def _clip(s: str, max_len: int = MAX_LINE) -> str:
    if len(s) > max_len:
        return s[:max_len] + "…"
    return s


def init_logger(
    app_root: Optional[Path] = None,
    log_dir: str = DEFAULT_LOG_DIRNAME,
    filename: str = DEFAULT_LOG_FILENAME,
    echo_console: bool = True,
    level: str = "INFO",
) -> Path:
    """
    Initialize global log path once. Safe to call multiple times.
    If app_root is None, it infers from frozen exe or current file.

    NEW DEFAULT (per Brook):
    - The log file is TRUNCATED on each new program run (so it is "replaced").
    - If you ever want to append instead, set:
          GS_LOG_APPEND=1
    """
    global _LOG_PATH, _ECHO_CONSOLE, _LEVEL, _RUN_ID

    if app_root is None:
        # robust app_root inference (works in .py and PyInstaller)
        if getattr(sys, "frozen", False):
            app_root = Path(sys.executable).resolve().parent
        else:
            # fallback: this module's folder (not cwd)
            app_root = Path(__file__).resolve().parent

    lv = (level or "INFO").upper().strip()
    _LEVEL = {"DEBUG": 10, "INFO": 20, "WARN": 30, "WARNING": 30, "ERROR": 40}.get(lv, 20)

    # Controls console echo policy (we still filter what is printed)
    _ECHO_CONSOLE = bool(echo_console)

    log_folder = (app_root / log_dir)
    log_folder.mkdir(parents=True, exist_ok=True)

    new_path = (log_folder / filename)

    # If already initialized in this process, do nothing (prevents re-init mid-run)
    if _LOG_PATH is not None:
        return _LOG_PATH

    _LOG_PATH = new_path
    _RUN_ID = f"{int(time.time())}-{os.getpid()}"

    # ✅ Default is "replace each run"
    append = os.environ.get("GS_LOG_APPEND", "").strip().lower() in ("1", "true", "yes", "y")

    # Create or replace file (never crash app if this fails)
    with _LOCK:
        try:
            if append:
                # Ensure file exists (append mode)
                _LOG_PATH.open("a", encoding="utf-8", errors="replace").close()
            else:
                # Truncate/recreate every run (replace)
                _LOG_PATH.open("w", encoding="utf-8", errors="replace").close()
        except Exception:
            pass

        # mark init (direct file write; avoids recursion + ordering issues)
        line = (
            f"{_now()} | INFO  | run={_safe_repr(_RUN_ID)} | {__name__}.init_logger | LOGGER_INIT"
            f" | log_path={_safe_repr(str(_LOG_PATH))}, level={_safe_repr(lv)}, echo={_safe_repr(_ECHO_CONSOLE)}, append={_safe_repr(append)}"
        )
        line = _clip(line, MAX_LINE)

        try:
            with _LOG_PATH.open("a", encoding="utf-8", errors="replace") as f:
                f.write(line + "\n")
        except Exception:
            pass

    return _LOG_PATH



def console(
    msg: str,
    *,
    module: Optional[str] = None,
    fn: Optional[str] = None,
    extra: Optional[dict] = None,
) -> None:
    """
    Print a human-facing console line AND log it to the shared log file.

    Use this instead of bare print() anywhere you want full audit parity.
    Console output remains clean; the file records a structured event.

    - Does NOT print timestamps or module names (console stays legacy-style).
    - Always logs at INFO as "CONSOLE:".
    """
    module, fn = _maybe_infer_module_fn(module, fn)

    # 1) Print exactly what the user should see (tqdm-safe)
    try:
        if _ECHO_CONSOLE:
            from tqdm import tqdm as _tqdm  # type: ignore
            _tqdm.write(str(msg))
    except Exception:
        try:
            if _ECHO_CONSOLE:
                print(msg, flush=True)
        except Exception:
            pass

    # 2) Log it (file only; INFO won't echo due to _should_print_to_console)
    try:
        _log(
            20,
            "INFO",
            "CONSOLE: " + str(msg),
            module=module,
            fn=fn,
            extra=extra,
        )
    except Exception:
        pass

def consolef(
    fmt: str,
    *args: Any,
    module: Optional[str] = None,
    fn: Optional[str] = None,
    extra: Optional[dict] = None,
    **kwargs: Any,
) -> None:
    try:
        msg = fmt.format(*args, **kwargs)
    except Exception:
        msg = fmt
    console(msg, module=module, fn=fn, extra=extra)

def get_log_path() -> Optional[Path]:
    return _LOG_PATH

def module_loaded(module_name: str) -> None:
    """
    Log that a module has been imported/loaded.
    Include pid and best-effort file path.
    """
    mod = sys.modules.get(module_name)
    mod_file = getattr(mod, "__file__", None)
    _log(
        20,
        "INFO",
        "MODULE_LOAD",
        module=module_name,
        fn="<module>",
        extra={"pid": os.getpid(), "file": mod_file},
    )


def install_excepthook() -> None:
    """
    Logs any uncaught exception that would normally crash the program.
    Also logs uncaught exceptions in threads (Python 3.8+ via threading.excepthook).

    Call this once (best in GoogleSheets_Menu).
    """
    def _hook(exc_type, exc, tb):
        # Let Ctrl+C behave normally (no scary traceback spam)
        if exc_type is KeyboardInterrupt:
            _log(30, "WARN", "KEYBOARD_INTERRUPT", module="__main__", fn="excepthook")
            sys.__excepthook__(exc_type, exc, tb)
            return

        txt = "".join(traceback.format_exception(exc_type, exc, tb))
        txt = txt[:MAX_TRACE] + ("…" if len(txt) > MAX_TRACE else "")
        _log(40, "ERROR", "UNCAUGHT", module="__main__", fn="excepthook", extra={"traceback": txt})

        # preserve default printing to stderr
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = _hook

    # Thread exceptions (Python 3.8+)
    if hasattr(threading, "excepthook"):
        # Capture the current/default hook BEFORE we override it
        _prev_thread_hook = getattr(threading, "excepthook", None)
        _default_thread_hook = getattr(threading, "__excepthook__", None)

        def _thread_hook(args):
            try:
                txt = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
                txt = txt[:MAX_TRACE] + ("…" if len(txt) > MAX_TRACE else "")
                _log(
                    40,
                    "ERROR",
                    "THREAD_UNCAUGHT",
                    module=getattr(args.thread, "name", "<thread>"),
                    fn="threading.excepthook",
                    extra={"traceback": txt},
                )
            finally:
                # Preserve default behavior (prefer __excepthook__ if available)
                try:
                    if callable(_default_thread_hook):
                        _default_thread_hook(args)  # type: ignore[misc]
                    elif callable(_prev_thread_hook) and _prev_thread_hook is not _thread_hook:
                        _prev_thread_hook(args)
                except Exception:
                    pass

        threading.excepthook = _thread_hook  # type: ignore[assignment]


def _write_line(line: str, *, echo: bool, console_override: Optional[str] = None) -> None:
    """
    Write a single log line to file.

    If echo is True, prints a filtered console line:
    - Uses console_override if provided (legacy style)
    - Else prints the raw line (rare fallback)

    Never raises: logging must not break app behavior.
    """
    global _LOG_PATH

    if _LOG_PATH is None:
        fallback_root = (
            Path(sys.executable).resolve().parent
            if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parent
        )
        try:
            init_logger(app_root=fallback_root)
        except Exception:
            # If even init fails, give up quietly
            return

    if _LOG_PATH is None:
        return

    line = _clip(line, MAX_LINE)

    # File write (guarded)
    try:
        with _LOCK:
            with _LOG_PATH.open("a", encoding="utf-8", errors="replace") as f:
                f.write(line + "\n")
    except Exception:
        # Never crash the program due to logging
        pass

    # Console echo (guarded)
    if _ECHO_CONSOLE and echo:
        out = console_override or line
        try:
            from tqdm import tqdm as _tqdm  # type: ignore
            _tqdm.write(out)
        except Exception:
            try:
                print(out, flush=True)
            except Exception:
                pass


def _copy_wrapper_passthrough_attrs(src: Any, dst: Any) -> None:
    """
    Preserve important decorator-added attributes (especially functools.lru_cache).

    Without this, wrapping a cached function can break:
      - fn.cache_clear()
      - fn.cache_info()
      - fn.cache_parameters() (py3.9+)
    """
    for name in ("cache_clear", "cache_info", "cache_parameters"):
        try:
            if hasattr(src, name):
                setattr(dst, name, getattr(src, name))
        except Exception:
            pass

    # Preserve signature when possible (helps inspect/tools)
    for name in ("__signature__",):
        try:
            if hasattr(src, name):
                setattr(dst, name, getattr(src, name))
        except Exception:
            pass


def _summarize_value(v: Any) -> str:
    try:
        if isinstance(v, (str, int, float, bool, type(None))):
            s = repr(v)
        elif isinstance(v, (list, tuple, set)):
            s = f"<{type(v).__name__} len={len(v)}>"
        elif isinstance(v, dict):
            s = f"<dict len={len(v)}>"
        elif isinstance(v, (bytes, bytearray)):
            s = f"<{type(v).__name__} len={len(v)}>"
        else:
            s = f"<{type(v).__name__}>"
    except Exception:
        s = "<unreprable>"
    return _clip(s, MAX_REPR)

def _summarize_args(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    return {
        "argc": len(args),
        "kwc": len(kwargs),
        "args": [_summarize_value(a) for a in args[:8]] + (["…"] if len(args) > 8 else []),
        "kwargs": {k: _summarize_value(v) for k, v in list(kwargs.items())[:12]},
        **({"kwargs_more": len(kwargs) - 12} if len(kwargs) > 12 else {}),
    }


def _should_print_to_console(level_num: int, msg: str) -> bool:
    """
    Console policy:
    - Do NOT print timestamped "STAGE:" log lines (we print clean stage lines via stage()).
    - DO print WARN/ERROR (timestamped is fine for these).
    """
    if level_num >= 40:  # ERROR+
        return True
    if level_num >= 30:  # WARN
        return True
    return False



def _log(level_num: int, level_name: str, msg: str, module: str, fn: str, extra: Optional[dict] = None) -> None:
    if level_num < _LEVEL:
        return

    depth = _get_depth()
    indent = "  " * depth

    extrastr = ""
    if extra:
        parts = [f"{k}={_safe_repr(v)}" for k, v in sorted(extra.items(), key=lambda kv: kv[0])]
        extrastr = " | " + ", ".join(parts)

    rid = _RUN_ID or "-"

    # File line (structured)
    line = f"{_now()} | {level_name:<5} | run={rid} | {module}.{fn} | {indent}{msg}{extrastr}"

    echo, summary_line = _should_echo_event_to_console(level_num, msg, extra)

    console_override = None
    if echo and level_num >= 30:
        console_override = _console_line(level_name, module, fn, msg, extra)

    # If we have a "suppressed N repeats" summary, emit it once (console + file)
    if summary_line:
        try:
            # summary should be console-visible and also recorded
            _write_line(
                f"{_now()} | WARN  | run={rid} | {module}.{fn} | {indent}{summary_line}",
                echo=True,
                console_override=summary_line,
            )
        except Exception:
            pass

    _write_line(line, echo=echo, console_override=console_override)


def _find_external_caller() -> tuple[Optional[str], Optional[int]]:
    """
    Best-effort: return (filename, lineno) of the first stack frame
    that is NOT inside this logger module.
    """
    try:
        fr = inspect.currentframe()
        # Walk back until we leave this file
        while fr:
            fr = fr.f_back
            if not fr:
                break
            fn = fr.f_code.co_filename
            if fn and os.path.basename(fn) != os.path.basename(__file__):
                return fn, fr.f_lineno
    except Exception:
        pass
    return None, None



def log_debug(msg: str, module: str, fn: str, extra: Optional[dict] = None) -> None:
    _log(10, "DEBUG", msg, module, fn, extra)


def log_info(msg: str, module: str, fn: str, extra: Optional[dict] = None) -> None:
    _log(20, "INFO", msg, module, fn, extra)


def log_warn(msg: str, module: str, fn: str, extra: Optional[dict] = None) -> None:
    _log(30, "WARN", msg, module, fn, extra)


def log_error(msg: str, module: str, fn: str, extra: Optional[dict] = None) -> None:
    _log(40, "ERROR", msg, module, fn, extra)


def decision(msg: str, *, module: str, fn: str, extra: Optional[dict] = None) -> None:
    """
    Use at key branches:
        decision("Using MASTER duplicate path", module=__name__, fn="run_flow", extra={"count": 123})
    """
    _log(20, "INFO", "DECISION: " + msg, module, fn, extra)

def stage(msg: str, *, module: str, fn: str, extra: Optional[dict] = None) -> None:
    """
    Major milestone banner.

    File:
      - Still logs the full structured line with "STAGE:" prefix.

    Console:
      - Prints a clean, human-friendly line WITHOUT timestamps/module names.
      - tqdm-safe so it won't be overwritten by progress bars.
    """
    # Always write to file (but _should_print_to_console prevents timestamped stage lines)
    _log(20, "INFO", "STAGE: " + msg, module, fn, extra)

    # Clean console line (only if echo enabled)
    if not _ECHO_CONSOLE:
        return

    clean = str(msg)

    # tqdm-safe write (doesn't get overwritten by bars)
    try:
        from tqdm import tqdm as _tqdm  # type: ignore
        _tqdm.write(clean)
    except Exception:
        print(clean, flush=True)


def log_exception(prefix: str, *, module: str, fn: str, extra: Optional[dict] = None) -> None:
    """
    Log an exception with traceback into the file, and also echo traceback to console
    in a tqdm-safe way (so you actually SEE it during progress bars).
    """
    tb = traceback.format_exc()
    tb = tb[:MAX_TRACE] + ("…" if len(tb) > MAX_TRACE else "")
    merged = dict(extra or {})
    merged["traceback"] = tb

    # 1) Log the ERROR line + store traceback in file
    log_error(prefix, module=module, fn=fn, extra=merged)

    # 2) Echo traceback block to console (tqdm-safe), because users often need it
    if _ECHO_CONSOLE:
        try:
            from tqdm import tqdm as _tqdm  # type: ignore
            _tqdm.write("---- TRACEBACK START ----")
            for line in tb.splitlines():
                _tqdm.write(line)
            _tqdm.write("---- TRACEBACK END ----")
        except Exception:
            print("---- TRACEBACK START ----", flush=True)
            print(tb, flush=True)
            print("---- TRACEBACK END ----", flush=True)


def _console_line(level_name: str, module: str, fn: str, msg: str, extra: Optional[dict]) -> str:
    """
    Convert a structured log event into a legacy-style console line.
    File logging stays structured elsewhere.
    """
    icon = {"ERROR": "❌", "WARN": "⚠️", "WARNING": "⚠️"}.get(level_name, "ℹ️")

    # Keep console simple: message only
    line = f"{icon} {msg}"

    # If you want a tiny hint of location, uncomment:
    # line = f"{icon} {msg}  ({module}.{fn})"

    # Optionally append a short extra summary for common cases
    if extra:
        # keep it short + stable
        parts = []
        for k, v in sorted(extra.items(), key=lambda kv: kv[0]):
            if k in {"file", "input_file", "dir", "count"}:
                parts.append(f"{k}={v}")
        if parts:
            line += " | " + ", ".join(parts)

    return _clip(line, 1200)

def log_call(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator: logs CALL / RETURN / EXCEPTION with module + function name.

    Cache-safe:
    - If func is @lru_cache wrapped, we preserve cache_clear/cache_info on our wrapper.
    """
    # ✅ If already autowrapped, do nothing (prevents double wrapping)
    try:
        if getattr(func, "__gs_autowrapped__", False):
            return func
    except Exception:
        pass

    mod = getattr(func, "__module__", "?")
    name = getattr(func, "__qualname__", getattr(func, "__name__", "<?>"))

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Only pay for caller+arg summarization when DEBUG is enabled
        if _LEVEL <= 10:
            caller_file, caller_line = _find_external_caller()
            call_summary = _summarize_args(args, kwargs)
            caller = f"{caller_file}:{caller_line}"
        else:
            caller = None
            call_summary = {"argc": len(args), "kwc": len(kwargs)}

        log_debug(
            "CALL",
            module=mod,
            fn=name,
            extra={"call": call_summary, **({"caller": caller} if caller else {})},
        )

        _inc_depth()
        t0 = time.time()
        try:
            out = func(*args, **kwargs)
            dt = round((time.time() - t0) * 1000.0, 2)

            if _LEVEL <= 10:
                out_summary = _summarize_value(out)
            else:
                out_summary = f"<{type(out).__name__}>"

            log_debug("RETURN", module=mod, fn=name, extra={"ms": dt, "out": out_summary})
            return out

        except Exception:
            dt = round((time.time() - t0) * 1000.0, 2)
            tb = traceback.format_exc()
            tb = tb[:MAX_TRACE] + ("…" if len(tb) > MAX_TRACE else "")
            extra = {"ms": dt, "traceback": tb}
            if caller:
                extra["caller"] = caller
            log_error("EXCEPTION", module=mod, fn=name, extra=extra)
            raise

        finally:
            _dec_depth()

    # ✅ Marker to avoid double-wrapping
    try:
        setattr(wrapper, "__gs_autowrapped__", True)
    except Exception:
        pass

    # ✅ Preserve lru_cache API + useful decorator attributes
    _copy_wrapper_passthrough_attrs(func, wrapper)

    return wrapper




def install_atexit_marker() -> None:
    """
    Writes a clean session end marker when the interpreter exits normally.
    Safe to call multiple times.
    """
    if getattr(install_atexit_marker, "_installed", False):
        return

    def _bye():
        try:
            _log(20, "INFO", "SESSION_END", module="__main__", fn="atexit")
        except Exception:
            pass

    import atexit
    atexit.register(_bye)
    install_atexit_marker._installed = True  # type: ignore[attr-defined]

def _infer_caller_module_fn() -> tuple[str, str]:
    """
    Best-effort: return (module_name, function_name) of the first stack frame
    that is NOT inside this logger module.

    Useful when callers don't pass module/fn explicitly.
    """
    try:
        fr = inspect.currentframe()
        # Walk back until we leave this file/module
        while fr:
            fr = fr.f_back
            if not fr:
                break
            mod = fr.f_globals.get("__name__", "")
            if mod and mod != __name__:
                func = fr.f_code.co_name or "<module>"
                return str(mod), str(func)
    except Exception:
        pass
    return "__main__", "<unknown>"


def _maybe_infer_module_fn(module: Optional[str], fn: Optional[str]) -> tuple[str, str]:
    """
    If module/fn are missing, infer them from stack.
    """
    if module and fn:
        return module, fn
    im, ifn = _infer_caller_module_fn()
    return module or im, fn or ifn

def autowrap_module(
    module_name: str,
    *,
    include_private: bool = False,
    only_defined_here: bool = True,
    exclude_names: Optional[set[str]] = None,
) -> None:
    """
    Wrap functions in the given module with @log_call.

    Parameters
    ----------
    include_private:
        If False, skips names starting with "_".
    only_defined_here:
        If True (default), only wraps functions whose obj.__module__ == module_name.
        This prevents wrapping imported callables.
    exclude_names:
        Optional set of function attribute names to skip (e.g. {"listen_for_quit_key"}).

    Call this ONCE near the bottom of a module (after defs).

    Safety:
    - Skips wrapping this logger module itself.

    IMPORTANT BEHAVIOR:
    - We do NOT skip functions just because they have __wrapped__.
      (Decorators like functools.lru_cache set __wrapped__; we still want to wrap them.)
    - We skip only if our own marker __gs_autowrapped__ is present.
    """
    if module_name == __name__:
        return

    mod = sys.modules.get(module_name)
    if not mod:
        return

    excludes = exclude_names or set()

    for attr_name, obj in list(vars(mod).items()):
        # Only wrap plain python functions (skip classes, methods, functools.partial, etc.)
        if not inspect.isfunction(obj):
            continue

        if attr_name in excludes:
            continue

        if only_defined_here and getattr(obj, "__module__", None) != module_name:
            continue

        if (not include_private) and attr_name.startswith("_"):
            continue

        # ✅ Skip ONLY if our wrapper marker is present
        try:
            if getattr(obj, "__gs_autowrapped__", False):
                continue
        except Exception:
            pass

        setattr(mod, attr_name, log_call(obj))



