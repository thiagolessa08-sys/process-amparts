"""Lista de casos para a tela Case Explorer.

Cada caso traz um resumo (nº de atividades, throughput, primeira/última
atividade e timestamps) e a timeline completa de atividades com o intervalo
até a atividade anterior. Reativo aos filtros aplicados antes de chamar.
"""
import pandas as pd

from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP


def build_cases(log: pd.DataFrame) -> list[dict]:
    log = log.copy()
    log[TIMESTAMP] = pd.to_datetime(log[TIMESTAMP])
    log = log.sort_values([CASE_ID, TIMESTAMP])

    out: list[dict] = []
    for cid, g in log.groupby(CASE_ID, sort=False):
        acts = [str(a) for a in g[ACTIVITY].tolist()]
        tss = list(g[TIMESTAMP].tolist())

        timeline = []
        prev = None
        for a, t in zip(acts, tss):
            delta = (t - prev).total_seconds() if prev is not None else None
            timeline.append({"label": a, "ts": t.isoformat(), "deltaSeconds": delta})
            prev = t

        out.append({
            "id": str(cid),
            "nActivities": len(acts),
            "throughputSeconds": (tss[-1] - tss[0]).total_seconds(),
            "firstActivity": acts[0],
            "firstTs": tss[0].isoformat(),
            "lastActivity": acts[-1],
            "lastTs": tss[-1].isoformat(),
            "activities": timeline,
        })
    return out
