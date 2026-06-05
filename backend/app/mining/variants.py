"""Descoberta de variantes: cada caminho distinto inicio->fim de um caso."""
import pandas as pd
from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP


def discover_variants(log: pd.DataFrame) -> list[dict]:
    """Retorna lista de {variant_id, activities, count, percentage},
    ordenada por frequencia decrescente."""
    log = log.sort_values([CASE_ID, TIMESTAMP])
    sequences = log.groupby(CASE_ID, sort=False)[ACTIVITY].apply(
        lambda s: tuple(str(a) for a in s)
    )

    counts: dict[tuple, int] = {}
    for seq in sequences:
        counts[seq] = counts.get(seq, 0) + 1

    total = len(sequences)
    ordered = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return [
        {
            "variant_id": i + 1,
            "activities": list(seq),
            "count": count,
            "percentage": round(100 * count / total, 1),
        }
        for i, (seq, count) in enumerate(ordered)
    ]
