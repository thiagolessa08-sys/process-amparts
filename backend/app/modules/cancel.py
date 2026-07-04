"""Análise de cancelamentos: onde no fluxo cancela, valor cancelado / perdido
(pós-fatura), evolução no tempo e top clientes/produtos.

Recebe o event log já filtrado + o conjunto de atividades de cancelamento
(inclui devoluções/estornos, se o módulo definir REVERSAL_ACTS)."""
import pandas as pd

from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP

# etapas do funil, em ordem
_STAGE_ORDER = ["Orçamento", "Pedido", "Fatura", "Pagamento", "Outro"]
# etapas "tardias" = perda real (já faturou/entregou)
_LATE = {"Fatura", "Pagamento"}


def _stage_of(act: str) -> str:
    a = str(act).upper()
    if "PAGAMENTO" in a or "VOUCHER" in a:
        return "Pagamento"
    if "PEDIDO" in a:
        return "Pedido"
    if "ORCAMENTO" in a or "ORÇAMENTO" in a or "REQUIS" in a or "COTA" in a:
        return "Orçamento"
    if "FATURA" in a or "NOTA" in a or "INVOICE" in a or "DEVOL" in a or "RECEB" in a or "ENTRAD" in a:
        return "Fatura"
    return "Outro"


def _empty():
    return {"pctCancel": 0.0, "valorCancelado": 0.0, "valorPerdido": 0.0, "numCancel": 0,
            "casosCancelados": 0, "tempoMedioDias": 0.0, "porEtapa": [], "porMes": [],
            "porTipo": [], "topClientes": [], "topProdutos": []}


def cancel_analysis(log: pd.DataFrame, cancel_set, label_map=None, top: int = 8) -> dict:
    label_map = label_map or {}
    if log is None or log.empty or not cancel_set:
        return _empty()

    df = log.copy()
    df[TIMESTAMP] = pd.to_datetime(df[TIMESTAMP], errors="coerce")
    first = df.sort_values(TIMESTAMP).groupby(CASE_ID).first()
    total_cases = int(len(first))
    valor_case = first["valor"] if "valor" in first.columns else pd.Series(0.0, index=first.index)

    canc = df[df[ACTIVITY].isin(set(cancel_set))].copy()
    if canc.empty:
        return _empty()
    canc["_stage"] = canc[ACTIVITY].map(_stage_of)
    cancelled = canc[CASE_ID].unique()

    def vsum(case_ids):
        return round(float(valor_case.reindex(list(case_ids)).dropna().sum()), 2)

    # ── KPIs ──
    pct = round(100 * len(cancelled) / total_cases, 2) if total_cases else 0.0
    valor_cancelado = vsum(cancelled)
    late_cases = canc[canc["_stage"].isin(_LATE)][CASE_ID].unique()
    valor_perdido = vsum(late_cases)
    num_cancel = int(len(canc))
    start = df.groupby(CASE_ID)[TIMESTAMP].min()
    first_canc = canc.groupby(CASE_ID)[TIMESTAMP].min()
    dias = (first_canc - start.reindex(first_canc.index)).dt.total_seconds() / 86400
    dias = dias[dias >= 0]
    tempo_medio = round(float(dias.mean()), 1) if len(dias) else 0.0

    # ── por etapa (funil) ──
    por_etapa = []
    for st in _STAGE_ORDER:
        cs = canc[canc["_stage"] == st][CASE_ID].unique()
        if len(cs):
            por_etapa.append({"etapa": st, "casos": int(len(cs)), "valor": vsum(cs)})

    # ── por tipo de cancelamento ──
    por_tipo = []
    for a, sub in canc.groupby(ACTIVITY):
        cs = sub[CASE_ID].unique()
        por_tipo.append({"tipo": label_map.get(a, str(a)), "casos": int(len(cs)), "valor": vsum(cs)})
    por_tipo.sort(key=lambda r: r["casos"], reverse=True)

    # ── evolução por mês (do evento de cancelamento) ──
    canc["_mes"] = canc[TIMESTAMP].dt.strftime("%Y-%m")
    pm = canc.dropna(subset=["_mes"]).groupby("_mes")[CASE_ID].size()
    por_mes = [{"mes": m, "qtd": int(n)} for m, n in pm.sort_index().items()]

    # ── top clientes / produtos (dos casos cancelados) ──
    def top_by(col):
        if col not in first.columns:
            return []
        sub = first.reindex(list(cancelled)).dropna(subset=[col])
        sub = sub[sub[col].astype(str) != "—"]
        if sub.empty:
            return []
        grp = sub.groupby(col).agg(casos=(col, "size"),
                                   valor=("valor", "sum") if "valor" in sub.columns else (col, "size"))
        grp = grp.sort_values("casos", ascending=False).head(top)
        return [{"nome": str(name), "casos": int(r["casos"]), "valor": round(float(r.get("valor", 0.0)), 2)}
                for name, r in grp.iterrows()]

    return {
        "pctCancel": pct, "valorCancelado": valor_cancelado, "valorPerdido": valor_perdido,
        "numCancel": num_cancel, "casosCancelados": int(len(cancelled)),
        "tempoMedioDias": tempo_medio, "porEtapa": por_etapa, "porTipo": por_tipo,
        "porMes": por_mes, "topClientes": top_by("cliente"), "topProdutos": top_by("produto"),
    }
