"""Painéis da tela Retrabalho, calculados a partir do event log.

Um caso tem *retrabalho* quando alguma atividade se repete nele (loop):
aprovação repetida, pedido alterado e recriado, pagamento duplicado,
reexpedição, etc. Reativo aos filtros aplicados antes do enrich.
"""
from collections import Counter

import pandas as pd

from app.eventlog import CASE_ID, TIMESTAMP


def _case_first(log: pd.DataFrame) -> pd.DataFrame:
    return log.sort_values(TIMESTAMP).groupby(CASE_ID).first()


def rework(log: pd.DataFrame, dim_col: str, label_map: dict, top: int | None = None,
           also_rework_acts=None, allowed_acts=None) -> dict:
    """also_rework_acts: atividades que marcam o caso como retrabalho só por
    estarem presentes, sem precisar repetir (ex.: cancelamentos no O2C).
    allowed_acts: quando definido, somente estas atividades aparecem no resultado
    e somente casos com ao menos uma delas são contados como retrabalho."""
    also = set(also_rework_acts or ())
    first = _case_first(log)
    has = lambda c: c in first.columns  # noqa: E731

    seqs = (log.sort_values([CASE_ID, TIMESTAMP])
               .groupby(CASE_ID, sort=False)["activity"].apply(list))

    rework_cases: set = set()
    act_cases: dict = {}   # atividade -> casos em que contribuiu p/ retrabalho
    act_extra: dict = {}   # atividade -> total de ocorrências de retrabalho
    for cid, acts in seqs.items():
        cnt = Counter(acts)
        flagged = False
        for a, c in cnt.items():
            extra = (c - 1) if c > 1 else 0   # repetições além da 1ª (loop)
            if a in also:
                extra += c                     # presença (ex.: cancelamento) conta cada ocorrência
            if extra > 0:
                act_cases.setdefault(a, set()).add(cid)
                act_extra[a] = act_extra.get(a, 0) + extra
                flagged = True
        if flagged:
            rework_cases.add(cid)

    # filtra atividades para o conjunto autorizado (ex.: só cancelamentos + alterações)
    if allowed_acts is not None:
        allowed = set(allowed_acts)
        act_cases = {a: v for a, v in act_cases.items() if a in allowed}
        act_extra = {a: v for a, v in act_extra.items() if a in allowed}
        rework_cases = set().union(*act_cases.values()) if act_cases else set()

    total = len(seqs)
    valor_by_case = first["valor"] if has("valor") else None

    # ── atividades de retrabalho ─────────────────────────────────────────────
    # itens = nº de itens (casos) distintos afetados pela atividade;
    # valor = soma do valor (R$) desses itens.
    atividades = []
    for a, cases in act_cases.items():
        valor = float(valor_by_case.loc[list(cases)].sum()) if valor_by_case is not None else 0.0
        atividades.append({
            "atividade": label_map.get(a, str(a)),
            "itens": len(cases),
            "valor": round(valor, 2),
            "ocorrencias": int(act_extra[a]),
        })
    atividades.sort(key=lambda r: r["ocorrencias"], reverse=True)

    # ── custo estimado de retrabalho ─────────────────────────────────────────
    # premissa: cada item (caso) cancelado ou alterado custa 30 min × R$ 50/h
    # = R$ 25,00 por item afetado (conta o item uma vez, não por ocorrência)
    REWORK_MIN = 30
    REWORK_HORA = 50.0
    itens_afetados = len(rework_cases)
    custo_retrabalho = round(itens_afetados * (REWORK_MIN / 60) * REWORK_HORA, 2)

    # ── com ou sem retrabalho ────────────────────────────────────────────────
    com = len(rework_cases)
    pct_com = round(100 * com / total, 2) if total else 0.0
    com_sem = [
        {"nome": "Com Retrabalho", "pct": pct_com},
        {"nome": "Sem Retrabalho", "pct": round(100 - pct_com, 2)},
    ]

    # ── retrabalho por cliente/fornecedor ────────────────────────────────────
    por_entidade = []
    if has(dim_col):
        f2 = first.assign(_rwk=first.index.isin(rework_cases))
        for ent, sub in f2.groupby(dim_col):
            n = int(len(sub))
            rw = int(sub["_rwk"].sum())
            por_entidade.append({
                "entidade": str(ent),
                "qtdUnidades": int(sub["itens"].sum()) if has("itens") else 0,
                "itensVenda": n,
                "pctRetrabalho": round(100 * rw / n, 2) if n else 0.0,
            })
        por_entidade.sort(key=lambda r: r["pctRetrabalho"], reverse=True)
        if top is not None:
            por_entidade = por_entidade[:top]

    return {
        "atividades": atividades,
        "comSem": com_sem,
        "porEntidade": por_entidade,
        "pctComRetrabalho": pct_com,
        "custoRetrabalho": custo_retrabalho,
        "itensRetrabalho": itens_afetados,
        "custoPremissa": {"minutos": REWORK_MIN, "valorHora": REWORK_HORA},
    }
