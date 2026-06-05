import pandas as pd
from app.mining.variants import discover_variants
from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP

IDEAL = ["A", "B", "C"]


def _log():
    return pd.DataFrame({
        CASE_ID: [1, 1, 1, 2, 2, 3, 3],
        ACTIVITY: ["A", "B", "C", "A", "B", "A", "C"],
        TIMESTAMP: pd.to_datetime([
            "2026-03-01 09:00", "2026-03-01 10:00", "2026-03-01 11:00",
            "2026-03-02 09:00", "2026-03-02 10:00",
            "2026-03-03 09:00", "2026-03-03 10:00",
        ]),
    })


def test_returns_variants_ordered_by_frequency():
    result = discover_variants(_log(), ideal_path=IDEAL)
    assert result[0]["activities"] == ["A", "B", "C"]
    assert result[0]["count"] == 1


def test_percentages_sum_to_100():
    result = discover_variants(_log(), ideal_path=IDEAL)
    assert round(sum(v["percentage"] for v in result), 1) == 100.0


def test_each_variant_has_sequential_id():
    result = discover_variants(_log(), ideal_path=IDEAL)
    ids = [v["variant_id"] for v in result]
    assert ids == list(range(1, len(ids) + 1))


def test_variants_have_avg_duration():
    result = discover_variants(_log(), ideal_path=IDEAL)
    for v in result:
        assert "avg_duration_seconds" in v
        assert v["avg_duration_seconds"] >= 0


def test_conformant_flag_matches_ideal():
    result = discover_variants(_log(), ideal_path=IDEAL)
    by_acts = {tuple(v["activities"]): v for v in result}
    assert by_acts[("A", "B", "C")]["conformant"] is True
    assert by_acts[("A", "B")]["conformant"] is False
    assert by_acts[("A", "C")]["conformant"] is False
