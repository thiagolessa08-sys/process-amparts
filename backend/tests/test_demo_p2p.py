import pandas as pd
from app.demo.generate_p2p import build_p2p_log
from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP

HAPPY_PATH = [
    "Criar Requisicao",
    "Criar Pedido de Compra",
    "Aprovar Pedido",
    "Receber Mercadoria",
    "Receber Fatura",
    "Pagar",
]


def test_build_log_has_requested_number_of_cases():
    df = build_p2p_log(n_cases=50, seed=1)
    assert df[CASE_ID].nunique() == 50


def test_required_columns_present():
    df = build_p2p_log(n_cases=10, seed=1)
    assert {CASE_ID, ACTIVITY, TIMESTAMP}.issubset(df.columns)


def test_happy_path_case_follows_full_sequence():
    df = build_p2p_log(n_cases=10, seed=1)
    first_case = df[df[CASE_ID] == df[CASE_ID].iloc[0]]
    activities = first_case.sort_values(TIMESTAMP)[ACTIVITY].tolist()
    assert activities == HAPPY_PATH


def test_is_deterministic_with_seed():
    a = build_p2p_log(n_cases=20, seed=42)
    b = build_p2p_log(n_cases=20, seed=42)
    pd.testing.assert_frame_equal(a, b)
