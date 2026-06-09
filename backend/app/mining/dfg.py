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

    bottleneck = True quando a aresta tem duração média > média + 1 desvio padrão
    de todas as arestas (z-score ≥ 1). Indica gargalo estatisticamente relevante.
    """
    log = log.sort_values([CASE_ID, TIMESTAMP])

    node_counts = log[ACTIVITY].value_counts()

    # transições diretamente-seguem (vetorizado): linha i -> linha i+1 do mesmo caso
    same = log[CASE_ID].to_numpy() == log[CASE_ID].shift(-1).to_numpy()
    trans = pd.DataFrame({
        "src": log[ACTIVITY].astype(str).to_numpy(),
        "tgt": log[ACTIVITY].shift(-1).astype(str).to_numpy(),
        "dur": (log[TIMESTAMP].shift(-1) - log[TIMESTAMP]).dt.total_seconds().to_numpy(),
    })[same]

    eg = trans.groupby(["src", "tgt"], sort=False)["dur"]
    e_count, e_sum = eg.size(), eg.sum()
    edges_raw = [
        {
            "source": src,
            "target": tgt,
            "count":  int(cnt),
            "mean_duration_seconds": round(float(e_sum[(src, tgt)]) / int(cnt), 2),
        }
        for (src, tgt), cnt in e_count.items()
    ]

    # dwell por nó = soma das durações de saída / total de ocorrências do nó
    node_dwell_total = trans.groupby("src")["dur"].sum()

    # bottleneck: z-score ≥ 1 (mean + 1 stdev) para 3+ arestas;
    # para 2 arestas, a mais lenta é gargalo; para 1, nenhuma.
    durations = [e["mean_duration_seconds"] for e in edges_raw]
    if len(durations) >= 3:
        mean_d    = statistics.mean(durations)
        stdev_d   = statistics.stdev(durations)
        threshold = mean_d + 1.0 * stdev_d
        for e in edges_raw:
            e["bottleneck"] = e["mean_duration_seconds"] > threshold
    elif len(durations) == 2:
        max_d = max(durations)
        for e in edges_raw:
            e["bottleneck"] = e["mean_duration_seconds"] == max_d
    else:
        for e in edges_raw:
            e["bottleneck"] = False

    nodes = [
        {
            "id":    str(act),
            "count": int(cnt),
            "avg_dwell_seconds": round(
                float(node_dwell_total.get(str(act), 0.0)) / int(cnt), 2
            ),
        }
        for act, cnt in node_counts.items()
    ]

    return {"nodes": nodes, "edges": edges_raw}
