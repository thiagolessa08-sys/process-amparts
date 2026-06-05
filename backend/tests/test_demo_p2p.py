import pandas as pd
from app.demo.generate_p2p import build_p2p_log, HAPPY_PATH
from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP


def _sequences(df):
    df = df.sort_values([CASE_ID, TIMESTAMP])
    return df.groupby(CASE_ID, sort=False)[ACTIVITY].apply(lambda s: tuple(s))


def test_build_log_has_requested_number_of_cases():
    df = build_p2p_log(n_cases=200, seed=1)
    assert df[CASE_ID].nunique() == 200


def test_required_columns_present():
    df = build_p2p_log(n_cases=10, seed=1)
    assert {CASE_ID, ACTIVITY, TIMESTAMP}.issubset(df.columns)


def test_happy_path_is_the_most_common_variant():
    df = build_p2p_log(n_cases=500, seed=1)
    counts = _sequences(df).value_counts()
    assert counts.index[0] == tuple(HAPPY_PATH)
    # caminho feliz deve ser maioria, mas nao 100%
    assert 0.5 < counts.iloc[0] / counts.sum() < 0.95


def test_has_multiple_variants():
    df = build_p2p_log(n_cases=500, seed=1)
    assert _sequences(df).nunique() >= 3


def test_maverick_variant_skips_approval():
    # existe pelo menos um caso que paga sem "Aprovar Pedido"
    df = build_p2p_log(n_cases=500, seed=1)
    seqs = _sequences(df)
    assert any("Aprovar Pedido" not in s and "Pagar" in s for s in seqs)


def test_is_deterministic_with_seed():
    a = build_p2p_log(n_cases=100, seed=42)
    b = build_p2p_log(n_cases=100, seed=42)
    pd.testing.assert_frame_equal(a, b)
