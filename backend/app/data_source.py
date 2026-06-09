"""Mantem qual event log esta ativo por módulo.

Fontes demo (p2p/o2c) são carregadas sob demanda do CSV. Fontes reais caras
(cordeiro) são carregadas UMA vez em background (thread), nunca dentro do request
HTTP — para não estourar memória/timeout no servidor de produção.
"""
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

_state = {"path": None}                      # override manual (upload)
_cache: dict[str, pd.DataFrame] = {}         # logs de fontes reais (caros de carregar)
_cordeiro = {"loading": False, "error": None}
_lock = threading.Lock()


# ── Cordeiro (carga em background) ───────────────────────────────────────────
def _bg_load_cordeiro() -> None:
    try:
        from app.sources.cordeiro import load_cordeiro_eventlog
        _cache["cordeiro"] = load_cordeiro_eventlog()
        _cordeiro["error"] = None
    except Exception as exc:  # noqa: BLE001
        _cordeiro["error"] = str(exc)
        print(f"[cordeiro] falha ao carregar: {exc}")
    finally:
        _cordeiro["loading"] = False


def start_cordeiro_load() -> None:
    """Dispara a carga em background (idempotente)."""
    with _lock:
        if "cordeiro" in _cache or _cordeiro["loading"]:
            return
        _cordeiro["loading"] = True
        _cordeiro["error"] = None
    threading.Thread(target=_bg_load_cordeiro, daemon=True).start()


def cordeiro_status() -> str:
    """ready | loading | error | idle"""
    if "cordeiro" in _cache:
        return "ready"
    if _cordeiro["loading"]:
        return "loading"
    if _cordeiro["error"]:
        return "error"
    return "idle"


def cordeiro_error() -> str | None:
    return _cordeiro["error"]


def refresh(module_key: str) -> None:
    """Descarta o cache de uma fonte real para forçar recarga."""
    _cache.pop(module_key, None)
    if module_key == "cordeiro":
        _cordeiro["error"] = None


# ── API geral ────────────────────────────────────────────────────────────────
def get_log(module_key: str = "p2p") -> pd.DataFrame:
    if _state["path"] is None and module_key == "cordeiro":
        if "cordeiro" in _cache:
            return _cache["cordeiro"]
        # fallback (ex.: testes/CLI): carga síncrona sob demanda
        from app.sources.cordeiro import load_cordeiro_eventlog
        _cache["cordeiro"] = load_cordeiro_eventlog()
        return _cache["cordeiro"]
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
