"""Mantem qual event log esta ativo por módulo.

Por padrão usa o dataset demo do módulo solicitado.
"""
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

_state = {"path": None}   # override manual (upload)
_cache: dict[str, pd.DataFrame] = {}   # logs de fontes reais (caras de carregar)


def _load_cordeiro() -> pd.DataFrame:
    if "cordeiro" not in _cache:
        from app.sources.cordeiro import load_cordeiro_eventlog
        _cache["cordeiro"] = load_cordeiro_eventlog()
    return _cache["cordeiro"]


def refresh(module_key: str) -> None:
    """Descarta o cache de uma fonte real para forçar recarga."""
    _cache.pop(module_key, None)


def get_log(module_key: str = "p2p") -> pd.DataFrame:
    if _state["path"] is None and module_key == "cordeiro":
        return _load_cordeiro()
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
