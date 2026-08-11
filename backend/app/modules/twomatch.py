"""2-Way Match: Pedido × Faturamento.

Efetivado/faturado = pedido que passou pela atividade de fatura (invoice).
Séries mensais (por data do pedido) e pedidos pendentes (não faturados) por
cliente/fornecedor. Reativo aos filtros aplicados antes do enrich.
"""
import pandas as pd

from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP

INVOICE_ACTIVITY = "invoice"


def two_match(log: pd.DataFrame, dim_col: str,
              invoice_activity: str = INVOICE_ACTIVITY,
              order_activity: str | None = None) -> dict:
    """Pedido × Faturamento.

    `invoice_activity`: atividade que marca a fatura (efetivado).
    `order_activity`: se informado, a base são apenas os casos que têm essa
    atividade (o pedido) e o mês de referência é a data do pedido — em vez do
    1º evento do caso (que, no O2C, costuma ser o orçamento).
    """
    log = log.copy()
    log[TIMESTAMP] = pd.to_datetime(log[TIMESTAMP])
    first = log.sort_values([CASE_ID, TIMESTAMP]).groupby(CASE_ID, sort=False).first()
    inv_cases = set(log[log[ACTIVITY] == invoice_activity][CASE_ID].unique())

    if order_activity:
        # base = casos com pedido; data de referência = data do pedido
        order_ts = log[log[ACTIVITY] == order_activity].groupby(CASE_ID)[TIMESTAMP].min()
        first = first.loc[first.index.intersection(order_ts.index)].copy()
        first[TIMESTAMP] = first.index.map(order_ts)

    first = first.assign(_fat=first.index.isin(inv_cases))
    first["_mes"] = pd.to_datetime(first[TIMESTAMP]).dt.strftime("%Y-%m")
    has = lambda c: c in first.columns  # noqa: E731

    # ── série mensal ─────────────────────────────────────────────────────────
    monthly = []
    for mes, g in first.groupby("_mes"):
        fat = g[g["_fat"]]
        n = int(len(g))
        monthly.append({
            "mes": mes,
            "pedidoValor": float(g["valor"].sum()) if has("valor") else 0.0,
            "faturadoValor": float(fat["valor"].sum()) if has("valor") else 0.0,
            "pedidoCount": n,
            "faturadoCount": int(len(fat)),
            "pct": round(100 * len(fat) / n, 2) if n else 0.0,
        })
    monthly.sort(key=lambda r: r["mes"])

    # ── pedidos pendentes (não faturados) por entidade ───────────────────────
    pend = first[~first["_fat"]]
    pendentes = []
    if dim_col in pend.columns and len(pend):
        for ent, sub in pend.groupby(dim_col):
            pendentes.append({
                "entidade": str(ent),
                "qtdUnidades": int(sub["itens"].sum()) if has("itens") else 0,
                "itensVenda": int(sub["produto"].nunique()) if has("produto") else 0,
                "pedidos": int(len(sub)),
            })
        pendentes.sort(key=lambda r: r["pedidos"], reverse=True)

    return {"monthly": monthly, "pendentes": pendentes}
