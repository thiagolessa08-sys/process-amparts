"""Mantem qual event log esta ativo. Por padrao, o dataset demo P2P.

Ao receber upload, aponta para o arquivo enviado. Centraliza o acesso
para que os endpoints nao saibam de onde o log vem.
"""
from pathlib import Path

import pandas as pd

from app.connectors.csv_connector import CSVConnector
from app.demo.generate_p2p import write_demo_csv

DEMO_PATH = "data/demo_p2p.csv"

_state = {"path": None}


def get_log() -> pd.DataFrame:
    path = _state["path"] or DEMO_PATH
    if not Path(path).exists():
        write_demo_csv(DEMO_PATH)
        path = DEMO_PATH
    return CSVConnector(path).load()


def set_source(path: str) -> None:
    _state["path"] = path


def reset_to_demo() -> None:
    _state["path"] = None
