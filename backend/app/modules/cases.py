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


def _cell(x):
    if x is None or (not isinstance(x, str) and pd.isna(x)):
        return "—"
    s = str(x).strip()
    return s if s and s.lower() != "nan" else "—"


def page_cases(sorted_log: pd.DataFrame, summary: pd.DataFrame,
               q: str | None = None, limit: int = 500, event_attrs=None) -> dict:
    """Filtra por Case Id (substring), pagina e monta a timeline só da página.

    `event_attrs`: lista opcional de {label, col, fmt?} para o painel de detalhe
    do evento ao clicar na atividade. `col` é uma coluna do event log (ou
    'case_id'/'activity'); fmt='date' formata como AAAA-MM-DD.

    Retorna {"cases": [...], "total": <após busca>}.
    """
    ids = summary.index.tolist()
    if q and q.strip():
        ql = q.strip().lower()
        ids = [c for c in ids if ql in c.lower()]
    total = len(ids)

    page_ids = ids[: max(0, limit)]
    sub = sorted_log[sorted_log[CASE_ID].isin(set(page_ids))]

    # painel de detalhe por evento: só os campos cujas colunas existem no log
    specs = [s for s in (event_attrs or [])
             if s["col"] in ("case_id", "activity") or s["col"] in sorted_log.columns]
    has_attrs = bool(specs)

    def _build_attrs(cid, a, r):
        out = {}
        for s in specs:
            col = s["col"]
            if col == "case_id":
                out[s["label"]] = _cell(cid)
            elif col == "activity":
                out[s["label"]] = _cell(a)
            elif s.get("fmt") == "date":
                x = r.get(col)
                out[s["label"]] = (pd.to_datetime(x).strftime("%Y-%m-%d")
                                   if x is not None and not pd.isna(x) else "—")
            else:
                out[s["label"]] = _cell(r.get(col))
        return out

    timelines: dict[str, list] = {}
    for cid, g in sub.groupby(CASE_ID, sort=False):
        tl, prev = [], None
        recs = g.to_dict("records") if has_attrs else None
        acts_list = g[ACTIVITY].astype(str).tolist()
        ts_list = g[TIMESTAMP].tolist()
        for idx, (a, t) in enumerate(zip(acts_list, ts_list)):
            delta = (t - prev).total_seconds() if prev is not None else None
            ev = {"label": a, "ts": t.isoformat(), "deltaSeconds": delta}
            if has_attrs:
                ev["attrs"] = _build_attrs(cid, a, recs[idx])
            tl.append(ev)
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
