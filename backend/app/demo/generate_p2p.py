"""Gera um event log demo de P2P. Nesta fatia, apenas o caminho feliz.

Os casos com problemas (pagamento duplicado, maverick buying, etc.)
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


def build_p2p_log(n_cases: int = 2000, seed: int = 7) -> pd.DataFrame:
    rng = random.Random(seed)
    rows = []
    base = pd.Timestamp("2026-01-01 08:00:00")
    for case_idx in range(1, n_cases + 1):
        case_id = 4500000 + case_idx
        t = base + pd.Timedelta(days=rng.randint(0, 120))
        for activity in HAPPY_PATH:
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
