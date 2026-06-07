"""Painéis da tela Visão Geral, calculados a partir do event log.

Quatro blocos: TOP produtos (por itens), cancelados por mês, TOP clientes
(por valor) e a tabela Pedidos × Nota Fiscal. Reativo aos filtros aplicados
ao log antes do enrich.
"""
import pandas as pd

from app.eventlog import CASE_ID, TIMESTAMP

INVOICE_ACTIVITY = "invoice"


def _case_first(log: pd.DataFrame) -> pd.DataFrame:
    """Atributos de cada caso (primeiro evento), indexado por CASE_ID."""
    return log.sort_values(TIMESTAMP).groupby(CASE_ID).first()


def overview(log: pd.DataFrame, dim_col: str) -> dict:
    first = _case_first(log)
    has = lambda c: c in first.columns  # noqa: E731

    # ── TOP 10 produtos por quantidade de itens ──────────────────────────────
    top_produtos = []
    if has("produto") and has("itens"):
        prod = first.groupby("produto")["itens"].sum().sort_values(ascending=False).head(10)
        top_produtos = [{"produto": str(p), "itens": int(v)} for p, v in prod.items()]

    # ── cancelados por mês (série completa, mesmo meses sem cancelamento) ─────
    cancelados_por_mes = []
    fts = pd.to_datetime(first[TIMESTAMP])
    meses = pd.PeriodIndex(fts.dt.to_period("M"))
    meses_all = sorted({str(m) for m in meses})
    if has("cancelado"):
        canc = first[first["cancelado"].astype(bool)]
        canc_mes = pd.to_datetime(canc[TIMESTAMP]).dt.to_period("M").astype(str).value_counts()
        cancelados_por_mes = [{"mes": m, "count": int(canc_mes.get(m, 0))} for m in meses_all]

    # ── TOP 10 clientes/fornecedores por valor (+ Outros) ────────────────────
    top_clientes = []
    if has(dim_col) and has("valor"):
        byval = first.groupby(dim_col)["valor"].sum().sort_values(ascending=False)
        total = float(byval.sum()) or 1.0
        top = byval.head(10)
        top_clientes = [
            {"nome": str(k), "valor": float(v), "pct": round(100 * v / total, 2)}
            for k, v in top.items()
        ]
        outros = float(byval.iloc[10:].sum())
        if outros > 0:
            top_clientes.append({"nome": "Outros", "valor": outros, "pct": round(100 * outros / total, 2)})

    # ── Pedidos × Nota Fiscal (por entidade, top por valor) ──────────────────
    pedidos_nf = []
    if has(dim_col) and has("valor"):
        inv_cases = set(log[log["activity"] == INVOICE_ACTIVITY][CASE_ID].unique())
        first = first.assign(_faturado=first.index.isin(inv_cases))
        byval = first.groupby(dim_col)["valor"].sum().sort_values(ascending=False)
        for ent in byval.head(10).index:
            sub = first[first[dim_col] == ent]
            fat = sub[sub["_faturado"]]
            pedidos_nf.append({
                "entidade":    str(ent),
                "pedidos":     int(len(sub)),
                "qtdUnid":     int(sub["itens"].sum()) if has("itens") else 0,
                "itensPed":    int(sub["produto"].nunique()) if has("produto") else 0,
                "totalPedido": float(sub["valor"].sum()),
                "faturas":     int(len(fat)),
                "itensFat":    int(fat["produto"].nunique()) if has("produto") else 0,
                "totalFatura": float(fat["valor"].sum()),
            })

    return {
        "topProdutos": top_produtos,
        "canceladosPorMes": cancelados_por_mes,
        "topClientes": top_clientes,
        "pedidosNf": pedidos_nf,
    }
