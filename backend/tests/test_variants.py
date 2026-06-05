import pandas as pd
from app.mining.variants import discover_variants
from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP


def _log():
    return pd.DataFrame(
        {
            CASE_ID: [1, 1, 2, 2, 3, 3],
            ACTIVITY: ["A", "B", "A", "B", "A", "C"],
            TIMESTAMP: pd.to_datetime(
                [
                    "2026-03-01 09:00",
                    "2026-03-01 10:00",
                    "2026-03-02 09:00",
                    "2026-03-02 10:00",
                    "2026-03-03 09:00",
                    "2026-03-03 10:00",
                ]
            ),
        }
    )


def test_returns_variants_ordered_by_frequency():
    result = discover_variants(_log())
    assert result[0]["activities"] == ["A", "B"]
    assert result[0]["count"] == 2
    assert result[1]["activities"] == ["A", "C"]
    assert result[1]["count"] == 1


def test_percentages_sum_to_100():
    result = discover_variants(_log())
    assert round(sum(v["percentage"] for v in result), 1) == 100.0


def test_each_variant_has_sequential_id():
    result = discover_variants(_log())
    assert [v["variant_id"] for v in result] == [1, 2]
