import pandas as pd
from app.mining.stats import compute_statistics
from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP


def _log():
    return pd.DataFrame(
        {
            CASE_ID: [1, 1, 2, 2],
            ACTIVITY: ["A", "B", "A", "B"],
            TIMESTAMP: pd.to_datetime(
                [
                    "2026-03-01 09:00",  # caso 1 dura 3600s
                    "2026-03-01 10:00",
                    "2026-03-02 09:00",  # caso 2 dura 7200s
                    "2026-03-02 11:00",
                ]
            ),
        }
    )


def test_counts():
    s = compute_statistics(_log())
    assert s["num_cases"] == 2
    assert s["num_events"] == 4
    assert s["num_variants"] == 1


def test_throughput_mean_and_median():
    s = compute_statistics(_log())
    # media de 3600 e 7200 = 5400
    assert s["mean_throughput_seconds"] == 5400.0
    assert s["median_throughput_seconds"] == 5400.0
