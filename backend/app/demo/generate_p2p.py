"""Gera um event log demo de P2P com variantes estruturais e atributos financeiros.

Variantes (~%):
- happy          60%  caminho feliz completo
- no_gr          10%  sem Receber Mercadoria
- maverick        9%  sem Aprovar Pedido (compra fora do processo)
- rework_aprov    7%  Aprovar Pedido repetido
- alterar         8%  Alterar Pedido → volta ao Criar Pedido de Compra
- dup_pay         6%  Pagar aparece duas vezes (pagamento duplicado)

Atributos por caso (fixos em todos os eventos):
  fornecedor, valor, documento, data_vencimento, comprador, categoria, prazo_dias

Pagamento tardio: ~25% dos casos happy/no_gr/alterar pagam após data_vencimento.
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

FORNECEDORES = [
    "Tecnomec Industria", "Vega Componentes", "Alianca Logistica",
    "Polimix Quimica", "Brasmetal S.A.", "Norte Suprimentos",
    "Forte Aco", "Delta Plasticos", "Sigma Eletro", "Andrade Pecas",
    "Uniao Quimica", "Prima Embalagens", "Centro Oeste Insumos", "Atlas Ferragens",
]

# códigos de produto sintéticos (PI = importado, PA = nacional)
PRODUTOS = (
    [f"PI{rng_n:06d}" for rng_n in range(100, 124)] +
    [f"PA{rng_n:06d}" for rng_n in range(100, 124)]
)

CATEGORIAS = [
    "Materia-prima", "Servicos de TI", "Logistica",
    "Material de escritorio", "Manutencao", "Consultoria",
]

COMPRADORES = ["Marina Alves", "Carlos Nunes", "Renata Lima", "Paulo Souza", "Ana Lima"]
RESOURCES   = ["Joao Silva", "Maria Souza", "Sistema", "Ana Lima"]


def _build_path(rng: random.Random) -> tuple[list[str], str]:
    """Retorna (path, variant_type)."""
    r = rng.random()
    if r < 0.60:
        return list(HAPPY_PATH), "happy"
    if r < 0.70:
        return [a for a in HAPPY_PATH if a != "Receber Mercadoria"], "no_gr"
    if r < 0.79:
        return [a for a in HAPPY_PATH if a != "Aprovar Pedido"], "maverick"
    if r < 0.86:
        path = []
        for a in HAPPY_PATH:
            path.append(a)
            if a == "Aprovar Pedido":
                path.append("Aprovar Pedido")
        return path, "rework_aprov"
    if r < 0.94:
        return [
            "Criar Requisicao",
            "Criar Pedido de Compra",
            "Alterar Pedido",
            "Criar Pedido de Compra",
            "Aprovar Pedido",
            "Receber Mercadoria",
            "Receber Fatura",
            "Pagar",
        ], "alterar"
    # dup_pay: paga duas vezes
    return list(HAPPY_PATH) + ["Pagar"], "dup_pay"


def build_p2p_log(n_cases: int = 2000, seed: int = 7) -> pd.DataFrame:
    rng   = random.Random(seed)
    rows  = []
    base  = pd.Timestamp("2024-12-01 08:00:00")  # ~17 meses de histórico

    for case_idx in range(1, n_cases + 1):
        case_id   = 4500000 + case_idx
        path, vtype = _build_path(rng)

        fornecedor   = rng.choice(FORNECEDORES)
        produto      = rng.choice(PRODUTOS)
        cancelado    = rng.random() < 0.12
        valor        = round(rng.uniform(5_000, 500_000), 2)
        itens        = rng.randint(50, 5_000)
        documento    = f"NF {rng.randint(10000, 99999)}"
        comprador    = rng.choice(COMPRADORES)
        categoria    = rng.choice(CATEGORIAS)
        prazo_dias   = rng.choice([10, 15, 30])
        # pagamento tardio em ~25% dos casos onde há fatura
        late_pay = vtype not in ("maverick",) and rng.random() < 0.25

        t          = base + pd.Timedelta(days=rng.randint(0, 510))
        fatura_ts  = None
        path_rows  = []

        for activity in path:
            if activity == "Receber Fatura":
                fatura_ts = t

            # Pagar: se late_pay e há fatura, avança além do prazo
            if activity == "Pagar" and late_pay and fatura_ts is not None:
                # paga entre (prazo + 3) e (prazo + 30) dias após fatura
                extra = rng.randint(3, 30)
                t = fatura_ts + pd.Timedelta(days=prazo_dias + extra)
                late_pay = False  # aplica só no primeiro Pagar

            path_rows.append({
                CASE_ID:        case_id,
                ACTIVITY:       activity,
                TIMESTAMP:      t,
                RESOURCE:       rng.choice(RESOURCES),
                "fornecedor":   fornecedor,
                "produto":      produto,
                "cancelado":    cancelado,
                "valor":        valor,
                "itens":        itens,
                "documento":    documento,
                "comprador":    comprador,
                "categoria":    categoria,
                "prazo_dias":   prazo_dias,
                "data_vencimento": None,   # preenchido abaixo
            })
            t = t + pd.Timedelta(hours=rng.randint(2, 48))

        # preencher data_vencimento nos eventos do caso
        vencimento = (fatura_ts + pd.Timedelta(days=prazo_dias)) if fatura_ts else None
        for row in path_rows:
            row["data_vencimento"] = vencimento

        rows.extend(path_rows)

    return pd.DataFrame(rows)


def write_demo_csv(path: str = "data/demo_p2p.csv", n_cases: int = 2000) -> str:
    df = build_p2p_log(n_cases=n_cases)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path


if __name__ == "__main__":
    out = write_demo_csv()
    print(f"Dataset demo gerado em {out}")
