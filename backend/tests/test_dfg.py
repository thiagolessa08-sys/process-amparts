import pandas as pd
from app.mining.dfg import discover_dfg
from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP


def _log():
    return pd.DataFrame(
        {
            CASE_ID: [1, 1, 1, 2, 2],
            ACTIVITY: ["A", "B", "C", "A", "B"],
            TIMESTAMP: pd.to_datetime(
                [
                    "2026-03-01 09:00",
                    "2026-03-01 10:00",
                    "2026-03-01 11:00",
                    "2026-03-02 09:00",
                    "2026-03-02 11:00",
                ]
            ),
        }
    )


def test_nodes_have_activities_with_counts():
    result = discover_dfg(_log())
    nodes = {n["id"]: n for n in result["nodes"]}
    assert set(nodes) == {"A", "B", "C"}
    assert nodes["A"]["count"] == 2
    assert nodes["C"]["count"] == 1


def test_edges_have_frequency():
    result = discover_dfg(_log())
    edges = {(e["source"], e["target"]): e for e in result["edges"]}
    # A->B ocorre nos dois casos; B->C apenas no caso 1
    assert edges[("A", "B")]["count"] == 2
    assert edges[("B", "C")]["count"] == 1


def test_edges_have_mean_duration_seconds():
    result = discover_dfg(_log())
    edges = {(e["source"], e["target"]): e for e in result["edges"]}
    # caso1 A->B = 3600s; caso2 A->B = 7200s; media = 5400s
    assert edges[("A", "B")]["mean_duration_seconds"] == 5400.0
