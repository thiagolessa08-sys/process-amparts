"""Lista de casos para a tela Case Explorer.

Cada caso traz um resumo (nº de atividades, throughput, primeira/última
atividade e timestamps) e a timeline completa de atividades com o intervalo
até a atividade anterior. Reativo aos filtros aplicados antes de chamar.

Em escala (Cordeiro ~207k casos) a parte cara é ordenar/resumir o log inteiro.
Por isso ela é separada (`build_case_index`) e cacheada pelo chamador; cada
requisição de busca/página chama só `page_cases`, que filtra a lista de casos
e monta a timeline detalhada APENAS da página devolvida.
"""
import pandas as pd

from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP


def build_case_index(log: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Parte cara (vetorizada): ordena o log e resume cada caso.

    Retorna (sorted_log, summary). `summary` é indexado por case_id em ordem
    estável, com colunas n / first_act / last_act / first_ts / last_ts / throughput.
    """
    log = log.copy()
    log[TIMESTAMP] = pd.to_datetime(log[TIMESTAMP])
    log = log.assign(**{CASE_ID: log[CASE_ID].astype(str)})
    log = log.sort_values([CASE_ID, TIMESTAMP])

    g = log.groupby(CASE_ID, sort=False)
    summary = pd.DataFrame({
        "n": g[ACTIVITY].size(),
        "first_act": g[ACTIVITY].first().astype(str),
        "last_act": g[ACTIVITY].last().astype(str),
        "first_ts": g[TIMESTAMP].first(),
        "last_ts": g[TIMESTAMP].last(),
    })
    summary["throughput"] = (summary["last_ts"] - summary["first_ts"]).dt.total_seconds()
    return log, summary


def page_cases(sorted_log: pd.DataFrame, summary: pd.DataFrame,
               q: str | None = None, limit: int = 500) -> dict:
    """Filtra por Case Id (substring), pagina e monta a timeline só da página.

    Retorna {"cases": [...], "total": <após busca>}.
    """
    ids = summary.index.tolist()
    if q and q.strip():
        ql = q.strip().lower()
        ids = [c for c in ids if ql in c.lower()]
    total = len(ids)

    page_ids = ids[: max(0, limit)]
    sub = sorted_log[sorted_log[CASE_ID].isin(set(page_ids))]

    timelines: dict[str, list] = {}
    for cid, g in sub.groupby(CASE_ID, sort=False):
        tl, prev = [], None
        for a, t in zip(g[ACTIVITY].astype(str).tolist(), g[TIMESTAMP].tolist()):
            delta = (t - prev).total_seconds() if prev is not None else None
            tl.append({"label": a, "ts": t.isoformat(), "deltaSeconds": delta})
            prev = t
        timelines[str(cid)] = tl

    cases = []
    for c in page_ids:
        row = summary.loc[c]
        cases.append({
            "id": c,
            "nActivities": int(row["n"]),
            "throughputSeconds": float(row["throughput"]),
            "firstActivity": row["first_act"],
            "firstTs": row["first_ts"].isoformat(),
            "lastActivity": row["last_act"],
            "lastTs": row["last_ts"].isoformat(),
            "activities": timelines.get(c, []),
        })
    return {"cases": cases, "total": total}


def build_cases(log: pd.DataFrame, q: str | None = None, limit: int = 500) -> dict:
    """Conveniência: índice + página numa chamada (sem cache)."""
    sorted_log, summary = build_case_index(log)
    return page_cases(sorted_log, summary, q=q, limit=limit)
