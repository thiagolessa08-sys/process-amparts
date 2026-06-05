"""Interface que todo módulo de processo deve implementar."""
from abc import ABC, abstractmethod
import pandas as pd


class ProcessModule(ABC):
    """Declara o esqueleto visual e calcula métricas a partir do event log."""

    @property
    @abstractmethod
    def key(self) -> str:
        """Identificador único: 'p2p', 'o2c', etc."""
        ...

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def short(self) -> str: ...

    @property
    @abstractmethod
    def color(self) -> str: ...

    @property
    @abstractmethod
    def ideal_path(self) -> list[str]:
        """IDs das atividades do caminho feliz, na ordem correta."""
        ...

    @abstractmethod
    def enrich(self, log: pd.DataFrame) -> dict:
        """Recebe o event log e devolve o payload completo do módulo
        no contrato esperado pelo frontend."""
        ...
