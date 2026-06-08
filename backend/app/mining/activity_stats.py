"""Métricas por atividade para o popover de etapa do Explorador.

Para cada atividade: frequência (eventos), casos distintos que a contêm,
e quantos casos começam / terminam nela. Calculado sobre o log já filtrado.
"""
import pandas as pd

from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP


def activity_metrics(log: pd.DataFrame) -> dict:
    total = int(log[CASE_ID].nunique())
    g = log.sort_values([CASE_ID, TIMESTAMP]).groupby(CASE_ID, sort=False)[ACTIVITY]
    firsts = g.first().value_counts()
    lasts = g.last().value_counts()
    cases_with = log.groupby(ACTIVITY)[CASE_ID].nunique()
    freq = log[ACTIVITY].value_counts()

    out: dict = {}
    for act in freq.index:
        a = str(act)
        cw = int(cases_with.get(act, 0))
        out[a] = {
            "freq": int(freq.get(act, 0)),
            "casesWith": cw,
            "casesWithout": total - cw,
            "startCount": int(firsts.get(act, 0)),
            "endCount": int(lasts.get(act, 0)),
            "pct": round(100 * cw / total, 1) if total else 0,
        }
    return out
