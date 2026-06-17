"""Mantem qual event log esta ativo por módulo.

Fontes demo (p2p/o2c) são carregadas sob demanda do CSV. Fontes reais caras
(cordeiro, vedara) são carregadas UMA vez em background (thread), nunca dentro
do request HTTP — para não estourar memória/timeout no servidor de produção.
"""
import importlib
import threading
from pathlib import Path

import pandas as pd

from app.connectors.csv_connector import CSVConnector
from app.demo.generate_p2p import write_demo_csv as write_p2p
from app.demo.generate_o2c import write_demo_csv as write_o2c

DEMO_PATHS = {
    "p2p": "data/demo_p2p.csv",
    "o2c": "data/demo_o2c.csv",
}
DEMO_WRITERS = {
    "p2p": write_p2p,
    "o2c": write_o2c,
}

# fontes reais (banco via agent): módulo:função do loader
REAL_LOADERS = {
    "cordeiro": ("app.sources.cordeiro", "load_cordeiro_eventlog"),
    "vedara":   ("app.sources.vedara",   "load_vedara_eventlog"),
}

_state = {"path": None}                       # override manual (upload)
_cache: dict[str, pd.DataFrame] = {}          # logs de fontes reais (caros)
_real = {k: {"loading": False, "error": None, "progress": 0} for k in REAL_LOADERS}
_lock = threading.Lock()


def _set_progress(key: str, pct) -> None:
    if key in _real:
        _real[key]["progress"] = max(0, min(100, int(pct)))


# ── fontes reais (carga em background) ───────────────────────────────────────
def _load_real(key: str, progress=None) -> pd.DataFrame:
    mod, fn = REAL_LOADERS[key]
    try:
        return getattr(importlib.import_module(mod), fn)(progress=progress)
    except TypeError:
        # loader antigo sem o parâmetro progress (fallback)
        return getattr(importlib.import_module(mod), fn)()


def _bg_load(key: str) -> None:
    try:
        _cache[key] = _load_real(key, progress=lambda p: _set_progress(key, p))
        _real[key]["error"] = None
        _real[key]["progress"] = 100
    except Exception as exc:  # noqa: BLE001
        _real[key]["error"] = str(exc)
        print(f"[{key}] falha ao carregar: {exc}")
    finally:
        _real[key]["loading"] = False


def start_real_load(key: str) -> None:
    """Dispara a carga em background de uma fonte real (idempotente)."""
    if key not in REAL_LOADERS:
        return
    with _lock:
        if key in _cache or _real[key]["loading"]:
            return
        _real[key]["loading"] = True
        _real[key]["error"] = None
        _real[key]["progress"] = 0
    threading.Thread(target=_bg_load, args=(key,), daemon=True).start()


def real_status(key: str) -> str:
    """ready | loading | error | idle"""
    if key in _cache:
        return "ready"
    if _real.get(key, {}).get("loading"):
        return "loading"
    if _real.get(key, {}).get("error"):
        return "error"
    return "idle"


def real_error(key: str) -> str | None:
    return _real.get(key, {}).get("error")


def real_progress(key: str) -> int:
    return int(_real.get(key, {}).get("progress", 0))


def is_real(key: str) -> bool:
    return key in REAL_LOADERS


# compat: helpers antigos do Cordeiro
def start_cordeiro_load() -> None:
    start_real_load("cordeiro")


def cordeiro_status() -> str:
    return real_status("cordeiro")


def cordeiro_error() -> str | None:
    return real_error("cordeiro")


def refresh(module_key: str) -> None:
    """Descarta o cache de uma fonte real para forçar recarga."""
    _cache.pop(module_key, None)
    if module_key in _real:
        _real[module_key]["error"] = None


# ── API geral ────────────────────────────────────────────────────────────────
def get_log(module_key: str = "p2p") -> pd.DataFrame:
    if _state["path"] is None and module_key in REAL_LOADERS:
        if module_key in _cache:
            return _cache[module_key]
        # fallback (ex.: testes/CLI): carga síncrona sob demanda
        _cache[module_key] = _load_real(module_key)
        return _cache[module_key]
    path = _state["path"]
    if path is None:
        demo = DEMO_PATHS.get(module_key, DEMO_PATHS["p2p"])
        if not Path(demo).exists():
            DEMO_WRITERS[module_key](demo)
        path = demo
    return CSVConnector(path).load()


def set_source(path: str) -> None:
    _state["path"] = path


def reset_to_demo() -> None:
    _state["path"] = None
