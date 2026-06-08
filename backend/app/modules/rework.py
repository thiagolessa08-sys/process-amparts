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


def rework(log: pd.DataFrame, dim_col: str, label_map: dict) -> dict:
    first = _case_first(log)
    has = lambda c: c in first.columns  # noqa: E731

    seqs = (log.sort_values([CASE_ID, TIMESTAMP])
               .groupby(CASE_ID, sort=False)["activity"].apply(list))

    rework_cases: set = set()
    act_cases: dict = {}   # atividade -> casos em que repetiu
    act_extra: dict = {}   # atividade -> total de ocorrências extras
    for cid, acts in seqs.items():
        cnt = Counter(acts)
        repeated = [a for a, c in cnt.items() if c > 1]
        if repeated:
            rework_cases.add(cid)
        for a in repeated:
            act_cases.setdefault(a, set()).add(cid)
            act_extra[a] = act_extra.get(a, 0) + (cnt[a] - 1)

    total = len(seqs)
    itens_by_case = first["itens"] if has("itens") else None

    # ── atividades de retrabalho ─────────────────────────────────────────────
    atividades = []
    for a, cases in act_cases.items():
        itens = int(itens_by_case.loc[list(cases)].sum()) if itens_by_case is not None else 0
        atividades.append({
            "atividade": label_map.get(a, str(a)),
            "itens": itens,
            "ocorrencias": int(act_extra[a]),
        })
    atividades.sort(key=lambda r: r["ocorrencias"], reverse=True)

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

    return {
        "atividades": atividades,
        "comSem": com_sem,
        "porEntidade": por_entidade,
        "pctComRetrabalho": pct_com,
    }
