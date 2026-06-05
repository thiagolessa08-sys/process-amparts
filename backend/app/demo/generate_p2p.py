"""Gera um event log demo de P2P com variantes estruturais.

Variantes (estruturais) nesta fatia:
- happy:    caminho feliz completo (~70%)
- no_gr:    sem "Receber Mercadoria" (~12%)
- maverick: sem "Aprovar Pedido" (compra fora do processo) (~10%)
- rework:   "Aprovar Pedido" repetido (retrabalho de aprovacao) (~8%)

Os problemas baseados em atributos (pagamento duplicado, desconto perdido)
entram na Fatia 3 junto com os KPIs.
"""
import random
from pathlib import Path

import pandas as pd

from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP, RESOURCE

HAPPY_PATH = [
    "Criar Requisicao",
    "Criar Pedido de Compra",
    "Aprovar Pedido",
    "Receber Mercadoria",
    "Receber Fatura",
    "Pagar",
]

RESOURCES = ["Joao Silva", "Maria Souza", "Sistema", "Ana Lima"]


def _path_for(rng: random.Random) -> list[str]:
    r = rng.random()
    if r < 0.70:
        return list(HAPPY_PATH)
    if r < 0.82:
        return [a for a in HAPPY_PATH if a != "Receber Mercadoria"]
    if r < 0.92:
        return [a for a in HAPPY_PATH if a != "Aprovar Pedido"]
    # rework: duplica "Aprovar Pedido"
    path = []
    for a in HAPPY_PATH:
        path.append(a)
        if a == "Aprovar Pedido":
            path.append("Aprovar Pedido")
    return path


def build_p2p_log(n_cases: int = 2000, seed: int = 7) -> pd.DataFrame:
    rng = random.Random(seed)
    rows = []
    base = pd.Timestamp("2026-01-01 08:00:00")
    for case_idx in range(1, n_cases + 1):
        case_id = 4500000 + case_idx
        t = base + pd.Timedelta(days=rng.randint(0, 120))
        for activity in _path_for(rng):
            rows.append(
                {
                    CASE_ID: case_id,
                    ACTIVITY: activity,
                    TIMESTAMP: t,
                    RESOURCE: rng.choice(RESOURCES),
                }
            )
            t = t + pd.Timedelta(hours=rng.randint(2, 48))
    return pd.DataFrame(rows)


def write_demo_csv(path: str = "data/demo_p2p.csv", n_cases: int = 2000) -> str:
    df = build_p2p_log(n_cases=n_cases)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path


if __name__ == "__main__":
    out = write_demo_csv()
    print(f"Dataset demo gerado em {out}")
