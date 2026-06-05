import pandas as pd
import pytest
from app.connectors.csv_connector import CSVConnector
from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP


def _write_csv(tmp_path):
    csv = tmp_path / "log.csv"
    csv.write_text(
        "case_id,activity,timestamp\n"
        "1,Criar Requisicao,2026-03-01 09:00:00\n"
        "1,Aprovar Pedido,2026-03-02 10:00:00\n"
        "2,Criar Requisicao,2026-03-01 11:00:00\n",
        encoding="utf-8",
    )
    return csv


def test_load_returns_dataframe_with_required_columns(tmp_path):
    csv = _write_csv(tmp_path)
    df = CSVConnector(str(csv)).load()
    assert isinstance(df, pd.DataFrame)
    assert {CASE_ID, ACTIVITY, TIMESTAMP}.issubset(df.columns)
    assert len(df) == 3


def test_load_parses_timestamp_as_datetime(tmp_path):
    csv = _write_csv(tmp_path)
    df = CSVConnector(str(csv)).load()
    assert pd.api.types.is_datetime64_any_dtype(df[TIMESTAMP])


def test_load_raises_when_required_column_missing(tmp_path):
    csv = tmp_path / "bad.csv"
    csv.write_text("case_id,activity\n1,Criar\n", encoding="utf-8")
    with pytest.raises(ValueError, match="timestamp"):
        CSVConnector(str(csv)).load()
