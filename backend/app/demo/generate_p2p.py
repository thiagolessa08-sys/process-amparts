"""Gera um event log demo de P2P com variantes estruturais e atributos financeiros.

Variantes (estruturais):
- happy:    caminho feliz completo (~70%)
- no_gr:    sem "Receber Mercadoria" (~12%)
- maverick: sem "Aprovar Pedido" (compra fora do processo) (~10%)
- rework:   "Aprovar Pedido" repetido (retrabalho de aprovação) (~8%)

Atributos por caso (mesmos em todos os eventos do caso):
  fornecedor, valor, documento, data_vencimento, comprador, categoria
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

FORNECEDORES = [
    "Tecnomec Industria", "Vega Componentes", "Alianca Logistica",
    "Polimix Quimica", "Brasmetal S.A.", "Norte Suprimentos",
]

CATEGORIAS = [
    "Materia-prima", "Servicos de TI", "Logistica",
    "Material de escritorio", "Manutencao", "Consultoria",
]

COMPRADORES = ["Marina Alves", "Carlos Nunes", "Renata Lima", "Paulo Souza", "Ana Lima"]


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
        path = _path_for(rng)

        # atributos do caso (fixos para todos os eventos)
        fornecedor = rng.choice(FORNECEDORES)
        valor = round(rng.uniform(5_000, 500_000), 2)
        documento = f"NF {rng.randint(10000, 99999)}"
        comprador = rng.choice(COMPRADORES)
        categoria = rng.choice(CATEGORIAS)
        # prazo de pagamento: 10, 15 ou 30 dias após recebimento da fatura
        prazo_dias = rng.choice([10, 15, 30])

        # data_vencimento será calculada a partir do timestamp do evento "Receber Fatura"
        # guardamos o prazo para calcular depois
        fatura_ts = None

        for activity in path:
            if activity == "Receber Fatura":
                fatura_ts = t

            rows.append({
                CASE_ID: case_id,
                ACTIVITY: activity,
                TIMESTAMP: t,
                RESOURCE: rng.choice(RESOURCES),
                "fornecedor": fornecedor,
                "valor": valor,
                "documento": documento,
                "comprador": comprador,
                "categoria": categoria,
                "prazo_dias": prazo_dias,
            })
            t = t + pd.Timedelta(hours=rng.randint(2, 48))

        # preencher data_vencimento nos eventos do caso
        vencimento = (fatura_ts + pd.Timedelta(days=prazo_dias)) if fatura_ts else None
        for row in rows[-(len(path)):]:
            row["data_vencimento"] = vencimento

    return pd.DataFrame(rows)


def write_demo_csv(path: str = "data/demo_p2p.csv", n_cases: int = 2000) -> str:
    df = build_p2p_log(n_cases=n_cases)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path


if __name__ == "__main__":
    out = write_demo_csv()
    print(f"Dataset demo gerado em {out}")
