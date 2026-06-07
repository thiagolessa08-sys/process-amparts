"""Gera um event log demo de O2C (Order-to-Cash) com variantes e atributos financeiros.

Variantes (~%):
- happy          60%  caminho feliz completo
- credit_block   11%  Bloqueio de Crédito antes de Separar/Expedir
- reexpedicao     8%  Separar/Expedir + Entregar repetidos (entrega parcial)
- cancelamento    5%  Bloqueio → cancelamento (não chega a entregar)
- fat_antecipado  6%  Faturar antes de Entregar
- late_recv      10%  caminho feliz mas recebe pagamento após prazo (DSO alto)

Atributos por caso:
  cliente, valor, data_prometida, data_entrega, prazo_recebimento, categoria
"""
import random
from pathlib import Path

import pandas as pd

from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP, RESOURCE

HAPPY_PATH = [
    "Criar Pedido",
    "Liberar Credito",
    "Separar Expedir",
    "Entregar",
    "Faturar",
    "Receber Pagamento",
]

CLIENTES = [
    "Atacadao Vale", "Distribuidora Sul", "Mercantil Centro",
    "RedeMix Varejo", "Comercial Norte", "Rede Sul Varejo",
]
CATEGORIAS = [
    "Eletronicos", "Alimentos", "Vestuario",
    "Moveis", "Ferramentas", "Material de Construcao",
]
RESOURCES = ["Carlos Nunes", "Ana Lima", "Sistema", "Renata Lima", "Joao Silva"]


def _build_path(rng: random.Random) -> tuple[list[str], str]:
    r = rng.random()
    if r < 0.60:
        return list(HAPPY_PATH), "happy"
    if r < 0.71:
        # credit block: vai para bloqueio mas depois segue
        return [
            "Criar Pedido",
            "Liberar Credito",
            "Bloqueio de Credito",
            "Separar Expedir",
            "Entregar",
            "Faturar",
            "Receber Pagamento",
        ], "credit_block"
    if r < 0.79:
        # re-expedicao: entrega parcial, repete Separar+Entregar
        return [
            "Criar Pedido",
            "Liberar Credito",
            "Separar Expedir",
            "Entregar",
            "Separar Expedir",
            "Entregar",
            "Faturar",
            "Receber Pagamento",
        ], "reexpedicao"
    if r < 0.84:
        # cancelamento: bloqueio → fim (pedido cancelado)
        return [
            "Criar Pedido",
            "Liberar Credito",
            "Bloqueio de Credito",
        ], "cancelamento"
    if r < 0.90:
        # faturamento antecipado: fatura antes de entregar
        return [
            "Criar Pedido",
            "Liberar Credito",
            "Separar Expedir",
            "Faturar",
            "Entregar",
            "Receber Pagamento",
        ], "fat_antecipado"
    # late_recv: caminho feliz mas recebimento tardio
    return list(HAPPY_PATH), "late_recv"


def build_o2c_log(n_cases: int = 2000, seed: int = 13) -> pd.DataFrame:
    rng  = random.Random(seed)
    rows = []
    base = pd.Timestamp("2026-01-01 08:00:00")

    for case_idx in range(1, n_cases + 1):
        case_id  = 7700000 + case_idx
        path, vtype = _build_path(rng)

        cliente    = rng.choice(CLIENTES)
        valor      = round(rng.uniform(8_000, 600_000), 2)
        itens      = rng.randint(50, 5_000)
        categoria  = rng.choice(CATEGORIAS)
        prazo_rec  = rng.choice([30, 45, 60])  # dias para receber pagamento
        late_recv  = vtype == "late_recv"

        t = base + pd.Timedelta(days=rng.randint(0, 150))
        entrega_ts = None
        fatura_ts  = None
        path_rows  = []

        for activity in path:
            if activity == "Entregar":
                entrega_ts = t
            if activity == "Faturar":
                fatura_ts = t

            # Receber Pagamento tardio: paga após prazo
            if activity == "Receber Pagamento" and late_recv and fatura_ts:
                extra = rng.randint(5, 40)
                t = fatura_ts + pd.Timedelta(days=prazo_rec + extra)
                late_recv = False

            path_rows.append({
                CASE_ID:             case_id,
                ACTIVITY:            activity,
                TIMESTAMP:           t,
                RESOURCE:            rng.choice(RESOURCES),
                "cliente":           cliente,
                "valor":             valor,
                "itens":             itens,
                "categoria":         categoria,
                "prazo_recebimento": prazo_rec,
                "data_prometida":    None,  # preenchido abaixo
                "data_entrega":      None,  # preenchido abaixo
            })
            t = t + pd.Timedelta(hours=rng.randint(2, 72))

        # data_prometida = início do caso + lead time prometido (~5 dias)
        case_start = path_rows[0][TIMESTAMP]
        data_prometida = case_start + pd.Timedelta(days=rng.randint(4, 8))
        for row in path_rows:
            row["data_prometida"] = data_prometida
            row["data_entrega"]   = entrega_ts

        rows.extend(path_rows)

    return pd.DataFrame(rows)


def write_demo_csv(path: str = "data/demo_o2c.csv", n_cases: int = 2000) -> str:
    df = build_o2c_log(n_cases=n_cases)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path


if __name__ == "__main__":
    out = write_demo_csv()
    print(f"Dataset demo O2C gerado em {out}")
