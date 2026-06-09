"""Produtividade de usuário — métricas por recurso (resource) do event log.

KPIs (usuários ativos/dia, eventos por usuário, casos por usuário, usuários
por caso), série de usuários ativos por dia e dados por usuário para o bubble
chart (eventos e throughput). Reativo aos filtros aplicados antes do enrich.
"""
import pandas as pd

from app.eventlog import CASE_ID, TIMESTAMP, RESOURCE


def _empty() -> dict:
    return {"activeUsersPerDay": 0, "eventsPerUser": 0, "casesPerUser": 0,
            "usersPerCase": 0, "series": [], "users": []}


def user_productivity(log: pd.DataFrame) -> dict:
    if RESOURCE not in log.columns or log.empty:
        return _empty()
    log = log.copy()
    log[TIMESTAMP] = pd.to_datetime(log[TIMESTAMP])
    log["_day"] = log[TIMESTAMP].dt.strftime("%Y-%m-%d")

    per_day_users = log.groupby("_day")[RESOURCE].nunique()
    per_day_events = log.groupby("_day").size()

    active_avg = round(float(per_day_users.mean()))
    events_per_user = round(float((per_day_events / per_day_users).mean()))
    cases_per_user = round(float(log.groupby(RESOURCE)[CASE_ID].nunique().mean()))
    users_per_case = round(float(log.groupby(CASE_ID)[RESOURCE].nunique().mean()))

    series = [{"date": d, "count": int(c)} for d, c in per_day_users.sort_index().items()]

    grp = log.groupby(CASE_ID)[TIMESTAMP]
    dur = (grp.max() - grp.min()).dt.total_seconds()  # duração por caso (s)

    users = []
    for u, sub in log.groupby(RESOURCE):
        cs = sub[CASE_ID].unique()
        tp = float(dur.loc[cs].mean()) if len(cs) else 0.0
        users.append({
            "user": str(u),
            "events": int(len(sub)),
            "cases": int(len(cs)),
            "throughput": round(tp / 86400, 2),  # em dias
        })
    users.sort(key=lambda r: r["events"], reverse=True)

    return {
        "activeUsersPerDay": int(active_avg),
        "eventsPerUser": int(events_per_user),
        "casesPerUser": int(cases_per_user),
        "usersPerCase": int(users_per_case),
        "series": series,
        "users": users,
    }
