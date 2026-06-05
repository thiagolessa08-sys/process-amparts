import pandas as pd
from app.mining.dfg import discover_dfg
from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP


def _log():
    """Caso 1: A(9h)->B(10h)->C(11h). Caso 2: A(9h)->B(11h)."""
    return pd.DataFrame({
        CASE_ID: [1, 1, 1, 2, 2],
        ACTIVITY: ["A", "B", "C", "A", "B"],
        TIMESTAMP: pd.to_datetime([
            "2026-03-01 09:00", "2026-03-01 10:00", "2026-03-01 11:00",
            "2026-03-02 09:00", "2026-03-02 11:00",
        ]),
    })


def test_nodes_have_avg_dwell_seconds():
    r = discover_dfg(_log())
    nodes = {n["id"]: n for n in r["nodes"]}
    # B tem dwell de: caso1=(C-B=3600s), caso2=nao tem sucessor -> 0; media = (3600+0)/2=1800
    assert "avg_dwell_seconds" in nodes["A"]
    assert nodes["B"]["avg_dwell_seconds"] == 1800.0


def test_edges_have_bottleneck_flag():
    r = discover_dfg(_log())
    edges = {(e["source"], e["target"]): e for e in r["edges"]}
    # A->B: media 5400s (maior); B->C: 3600s. p75 = 5400. A->B eh bottleneck.
    assert "bottleneck" in edges[("A", "B")]
    assert edges[("A", "B")]["bottleneck"] is True
    assert edges[("B", "C")]["bottleneck"] is False
