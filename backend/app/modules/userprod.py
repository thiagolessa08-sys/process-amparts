"""Produtividade de usuário — métricas por recurso (resource) do event log.

KPIs (usuários ativos/dia, eventos por usuário, casos por usuário, usuários
por caso), série de usuários ativos por dia e dados por usuário para o bubble
chart (eventos e throughput). Reativo aos filtros aplicados antes do enrich.
"""
import pandas as pd

from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP, RESOURCE

_BUCKETS = [
    "00:00 - 02:00", "02:00 - 04:00", "04:00 - 06:00", "06:00 - 08:00",
    "08:00 - 10:00", "10:00 - 12:00", "12:00 - 14:00", "14:00 - 16:00",
    "16:00 - 18:00", "18:00 - 20:00", "20:00 - 22:00", "22:00 - 24:00",
]


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


def user_detail(log: pd.DataFrame, name: str) -> dict:
    """Detalhe (drill) de um usuário: KPIs, série mensal e perfil diário."""
    if RESOURCE not in log.columns or log.empty:
        return {"user": name, "found": False}
    log = log.copy()
    log[TIMESTAMP] = pd.to_datetime(log[TIMESTAMP])
    log = log.sort_values([CASE_ID, TIMESTAMP])
    log["_prev"] = log.groupby(CASE_ID)[RESOURCE].shift(1)
    log["_next"] = log.groupby(CASE_ID)[RESOURCE].shift(-1)

    u = log[log[RESOURCE] == name]
    if u.empty:
        return {"user": name, "found": False}

    days = u[TIMESTAMP].dt.strftime("%Y-%m-%d")
    active_days = int(days.nunique())
    events = int(len(u))
    events_per_day = round(events / active_days) if active_days else 0
    acts_per_day = round(float(u.assign(_d=days).groupby("_d")[ACTIVITY].nunique().mean()))

    cs = u[CASE_ID].unique()
    grp = log[log[CASE_ID].isin(cs)].groupby(CASE_ID)[TIMESTAMP]
    dur_h = (grp.max() - grp.min()).dt.total_seconds() / 3600
    throughput_h = round(float(dur_h.mean()), 1) if len(dur_h) else 0.0
    last_active = u[TIMESTAMP].max().isoformat()

    come = u["_prev"].dropna(); come = come[come != name]
    goes = u["_next"].dropna(); goes = goes[goes != name]
    tc = come.value_counts().head(3)
    tg = goes.value_counts().head(3)
    pc = round(100 * tc.sum() / len(come)) if len(come) else 0
    pg = round(100 * tg.sum() / len(goes)) if len(goes) else 0

    monthly = [
        {"mes": m, "events": int(c)}
        for m, c in u.assign(_m=u[TIMESTAMP].dt.strftime("%Y-%m")).groupby("_m").size().sort_index().items()
    ]

    bi = (u[TIMESTAMP].dt.hour // 2).clip(0, 11)
    counts = bi.value_counts()
    daily = [{"bucket": _BUCKETS[i], "count": int(counts.get(i, 0))} for i in range(12)]

    return {
        "user": name, "found": True,
        "eventsPerDay": events_per_day,
        "activitiesPerDay": acts_per_day,
        "throughputHours": throughput_h,
        "lastActive": last_active,
        "events": events,
        "comeFrom": {"names": [str(x) for x in tc.index], "pct": pc},
        "goesTo": {"names": [str(x) for x in tg.index], "pct": pg},
        "monthly": monthly,
        "dailyProfile": daily,
    }
