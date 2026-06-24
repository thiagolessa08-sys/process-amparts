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

    # mapa nome-cru -> id-canônico (sobrescrito pelos módulos)
    activity_map: dict = {}

    # nome-cru da atividade que define a "data do pedido" para o filtro de
    # período. Se None, o filtro usa o 1º evento do caso (case start).
    order_activity: str | None = None

    def raw_activities(self, canonical: str) -> list[str]:
        """Nomes crus do event log que correspondem a um id canônico."""
        raws = [raw for raw, canon in self.activity_map.items() if canon == canonical]
        return raws or [canonical]

    @abstractmethod
    def enrich(self, log: pd.DataFrame) -> dict:
        """Recebe o event log e devolve o payload completo do módulo
        no contrato esperado pelo frontend."""
        ...
