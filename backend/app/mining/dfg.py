"""Descoberta do Directly-Follows Graph a partir de um event log padrão.

Agnóstico de domínio: opera apenas sobre case_id / activity / timestamp.
"""
import statistics
import pandas as pd
from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP


def discover_dfg(log: pd.DataFrame) -> dict:
    """Retorna {"nodes": [...], "edges": [...]}.

    nodes: {id, count, avg_dwell_seconds}
    edges: {source, target, count, mean_duration_seconds, bottleneck}

    avg_dwell_seconds = tempo médio que um caso permanece nessa atividade
    antes de avançar para a próxima (0 para a última atividade do caso).

    bottleneck = True quando mean_duration_seconds >= percentil 75 das arestas.
    """
    log = log.sort_values([CASE_ID, TIMESTAMP])

    node_counts = log[ACTIVITY].value_counts()
    edge_counts: dict[tuple[str, str], int] = {}
    edge_durations: dict[tuple[str, str], float] = {}
    node_dwell_total: dict[str, float] = {}
    node_dwell_count: dict[str, int] = {}

    for _, group in log.groupby(CASE_ID, sort=False):
        acts = group[ACTIVITY].tolist()
        times = group[TIMESTAMP].tolist()
        for i in range(len(acts) - 1):
            key = (str(acts[i]), str(acts[i + 1]))
            duration = (times[i + 1] - times[i]).total_seconds()
            edge_counts[key] = edge_counts.get(key, 0) + 1
            edge_durations[key] = edge_durations.get(key, 0.0) + duration
            act = str(acts[i])
            node_dwell_total[act] = node_dwell_total.get(act, 0.0) + duration
            node_dwell_count[act] = node_dwell_count.get(act, 0) + 1

    edges_raw = [
        {
            "source": src,
            "target": tgt,
            "count": cnt,
            "mean_duration_seconds": round(edge_durations[(src, tgt)] / cnt, 2),
        }
        for (src, tgt), cnt in edge_counts.items()
    ]

    # bottleneck = aresta com tempo médio >= p75
    if edges_raw:
        durations = [e["mean_duration_seconds"] for e in edges_raw]
        p75 = sorted(durations)[int(len(durations) * 0.75)]
        for e in edges_raw:
            e["bottleneck"] = e["mean_duration_seconds"] >= p75
    else:
        for e in edges_raw:
            e["bottleneck"] = False

    nodes = [
        {
            "id": str(act),
            "count": int(cnt),
            # divide pelo total de ocorrências: última atividade do caso contribui 0
            "avg_dwell_seconds": round(
                node_dwell_total.get(str(act), 0.0) / int(cnt), 2
            ),
        }
        for act, cnt in node_counts.items()
    ]

    return {"nodes": nodes, "edges": edges_raw}
