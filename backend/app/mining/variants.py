"""Descoberta de variantes: cada caminho distinto inicio->fim de um caso."""
import pandas as pd
from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP
from app.mining.conformance import is_conformant


def discover_variants(log: pd.DataFrame, ideal_path: list[str] | None = None) -> list[dict]:
    """Retorna lista de {variant_id, activities, count, percentage,
    avg_duration_seconds, conformant}, ordenada por frequencia decrescente."""
    log = log.sort_values([CASE_ID, TIMESTAMP])

    case_sequences: dict = {}
    case_durations: dict = {}

    for case_id, group in log.groupby(CASE_ID, sort=False):
        group = group.sort_values(TIMESTAMP)
        acts = [str(a) for a in group[ACTIVITY].tolist()]
        times = group[TIMESTAMP].tolist()
        duration = (times[-1] - times[0]).total_seconds() if len(times) > 1 else 0.0
        case_sequences[case_id] = acts
        case_durations[case_id] = duration

    seq_cases: dict[tuple, list] = {}
    for case_id, acts in case_sequences.items():
        key = tuple(acts)
        if key not in seq_cases:
            seq_cases[key] = []
        seq_cases[key].append(case_id)

    total = len(case_sequences)
    ordered = sorted(seq_cases.items(), key=lambda kv: len(kv[1]), reverse=True)

    result = []
    pct_so_far = 0.0
    for i, (seq, case_ids) in enumerate(ordered):
        count = len(case_ids)
        durations = [case_durations[cid] for cid in case_ids]
        avg_dur = round(sum(durations) / count, 2) if durations else 0.0
        conformant = is_conformant(list(seq), ideal_path) if ideal_path else True
        is_last = i == len(ordered) - 1
        pct = round(100 - pct_so_far, 1) if is_last else round(100 * count / total, 1)
        pct_so_far += round(100 * count / total, 1)
        result.append({
            "variant_id": i + 1,
            "activities": list(seq),
            "count": count,
            "percentage": pct,
            "avg_duration_seconds": avg_dur,
            "conformant": conformant,
        })

    return result
