"""Estatisticas gerais do processo a partir do event log padrao."""
import pandas as pd
from app.eventlog import CASE_ID, TIMESTAMP
from app.mining.variants import discover_variants


def compute_statistics(log: pd.DataFrame) -> dict:
    grp = log.groupby(CASE_ID)[TIMESTAMP]
    durations = (grp.max() - grp.min()).dt.total_seconds()
    return {
        "num_cases": int(log[CASE_ID].nunique()),
        "num_events": int(len(log)),
        "num_variants": len(discover_variants(log)),
        "mean_throughput_seconds": round(float(durations.mean()), 2),
        "median_throughput_seconds": round(float(durations.median()), 2),
    }
