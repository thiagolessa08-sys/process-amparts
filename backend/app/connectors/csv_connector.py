import pandas as pd
from app.connectors.base import Connector
from app.eventlog import TIMESTAMP, REQUIRED_COLUMNS


class CSVConnector(Connector):
    """Lê um event log de um arquivo CSV no formato padrão."""

    def __init__(self, path: str):
        self.path = path

    def load(self) -> pd.DataFrame:
        df = pd.read_csv(self.path)
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"Colunas obrigatorias ausentes: {missing}")
        df[TIMESTAMP] = pd.to_datetime(df[TIMESTAMP])
        return df
