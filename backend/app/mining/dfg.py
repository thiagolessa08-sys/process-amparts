"""Descoberta do Directly-Follows Graph a partir de um event log padrão.

Agnóstico de domínio: opera apenas sobre case_id / activity / timestamp.
"""
import pandas as pd
from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP


def discover_dfg(log: pd.DataFrame) -> dict:
    """Retorna {"nodes": [...], "edges": [...]}.

    nodes: {id, count}
    edges: {source, target, count, mean_duration_seconds}
    """
    log = log.sort_values([CASE_ID, TIMESTAMP])

    node_counts = log[ACTIVITY].value_counts()
    nodes = [
        {"id": str(act), "count": int(cnt)}
        for act, cnt in node_counts.items()
    ]

    edge_counts: dict[tuple[str, str], int] = {}
    edge_durations: dict[tuple[str, str], float] = {}

    for _, group in log.groupby(CASE_ID, sort=False):
        acts = group[ACTIVITY].tolist()
        times = group[TIMESTAMP].tolist()
        for i in range(len(acts) - 1):
            key = (str(acts[i]), str(acts[i + 1]))
            duration = (times[i + 1] - times[i]).total_seconds()
            edge_counts[key] = edge_counts.get(key, 0) + 1
            edge_durations[key] = edge_durations.get(key, 0.0) + duration

    edges = [
        {
            "source": src,
            "target": tgt,
            "count": cnt,
            "mean_duration_seconds": round(edge_durations[(src, tgt)] / cnt, 2),
        }
        for (src, tgt), cnt in edge_counts.items()
    ]

    return {"nodes": nodes, "edges": edges}
