"""Descoberta de variantes: cada caminho distinto inicio->fim de um caso."""
import pandas as pd
from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP
from app.mining.conformance import is_conformant


def discover_variants(log: pd.DataFrame, ideal_path: list[str] | None = None) -> list[dict]:
    """Retorna lista de {variant_id, activities, count, percentage,
    avg_duration_seconds, conformant}, ordenada por frequencia decrescente."""
    if log.empty:
        return []

    log = log.sort_values([CASE_ID, TIMESTAMP])
    log = log.assign(**{ACTIVITY: log[ACTIVITY].astype(str)})

    g = log.groupby(CASE_ID, sort=False)
    seq = g[ACTIVITY].agg(tuple)
    dur = (g[TIMESTAMP].last() - g[TIMESTAMP].first()).dt.total_seconds().fillna(0.0)

    df = pd.DataFrame({"seq": seq.to_numpy(), "dur": dur.to_numpy()})
    # sort=False preserva ordem de 1ª aparição; sort estável mantém empates nessa ordem
    agg = (df.groupby("seq", sort=False)
             .agg(count=("dur", "size"), avgdur=("dur", "mean"))
             .sort_values("count", ascending=False, kind="stable"))

    total = int(len(df))
    n = len(agg)
    result, pct_so_far = [], 0.0
    for i, (seq_key, row) in enumerate(agg.iterrows()):
        count = int(row["count"])
        is_last = i == n - 1
        pct = round(100 - pct_so_far, 1) if is_last else round(100 * count / total, 1)
        pct_so_far += round(100 * count / total, 1)
        result.append({
            "variant_id": i + 1,
            "activities": list(seq_key),
            "count": count,
            "percentage": pct,
            "avg_duration_seconds": round(float(row["avgdur"]), 2),
            "conformant": is_conformant(list(seq_key), ideal_path) if ideal_path else True,
        })

    return result
