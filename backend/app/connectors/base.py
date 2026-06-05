from abc import ABC, abstractmethod
import pandas as pd


class Connector(ABC):
    """Interface comum de ingestão. Produz um event log padronizado."""

    @abstractmethod
    def load(self) -> pd.DataFrame:
        """Retorna um DataFrame com as colunas do event log padrão."""
        raise NotImplementedError
