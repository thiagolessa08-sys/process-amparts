"""Testes da config editável das queries-base do Cordeiro."""
import pandas as pd
import pytest

from app.sources import cordeiro_queries as cq


@pytest.fixture
def cfg_path(tmp_path, monkeypatch):
    p = tmp_path / "cordeiro_queries.json"
    monkeypatch.setenv("CORDEIRO_QUERY_CONFIG", str(p))
    return p


def test_defaults_when_no_override(cfg_path):
    cfg = cq.get_config()
    assert set(cfg) == set(cq.ORDER)
    assert cfg["cotacoes"]["table"] == cq.DEFAULT_QUERIES["cotacoes"]["table"]
    assert cfg["cotacoes"]["where"] == ""
    assert not cq.is_customized()


def test_save_and_get_override(cfg_path):
    base = cq.get_config()
    base["cotacoes"]["where"] = "QuotationDocCancellationStatus = 'N'"
    base["pedidos"]["table"] = "outro.PEDIDOS"
    saved = cq.save_config(base)
    assert saved["cotacoes"]["where"] == "QuotationDocCancellationStatus = 'N'"
    assert cq.is_customized()

    again = cq.get_config()
    assert again["cotacoes"]["where"] == "QuotationDocCancellationStatus = 'N'"
    assert again["pedidos"]["table"] == "outro.PEDIDOS"
    # campos não tocados seguem no default
    assert again["nfsaida"]["table"] == cq.DEFAULT_QUERIES["nfsaida"]["table"]


def test_reset_removes_override(cfg_path):
    cq.save_config(cq.get_config())
    assert cq.is_customized()
    cq.reset_config()
    assert not cq.is_customized()
    assert cq.get_config()["cotacoes"]["where"] == ""


def test_probe_sql_keyset_and_group():
    s = cq.probe_sql("cotacoes", "t.COT", "A, B", "A > 0")
    assert s.startswith("SELECT TOP 1 ")
    assert "QuotationDocInternalNumber AS kk1" in s
    assert "FROM t.COT WHERE A > 0 ORDER BY" in s

    g = cq.probe_sql("aprovacoes", "t.APR", "X k, Y dtype", "")
    assert "GROUP BY DocumentInternalNumber, DocumentType" in g
    assert "WHERE" not in g


class _FakeConn:
    def __init__(self, columns=None, raise_exc=None):
        self._columns = columns or []
        self._raise = raise_exc

    def configured(self):
        return True

    def query_df(self, sql, limit=1):
        if self._raise:
            raise RuntimeError(self._raise)
        return pd.DataFrame(columns=self._columns)


def test_validate_ok():
    cols = ["kk1", "kk2"] + cq.REQUIRED_COLUMNS["cotacoes"]
    res = cq.validate_source("cotacoes", "t.COT", "x", "", conn=_FakeConn(columns=cols))
    assert res["ok"] is True
    assert res["missing"] == []
    assert res["error"] is None


def test_validate_missing_column():
    cols = cq.REQUIRED_COLUMNS["cotacoes"][:-1]  # falta a última
    res = cq.validate_source("cotacoes", "t.COT", "x", "", conn=_FakeConn(columns=cols))
    assert res["ok"] is False
    assert cq.REQUIRED_COLUMNS["cotacoes"][-1] in res["missing"]


def test_validate_sql_error():
    res = cq.validate_source("pedidos", "t.PED", "x", "", conn=_FakeConn(raise_exc="syntax error"))
    assert res["ok"] is False
    assert "syntax error" in res["error"]


def test_validate_case_insensitive():
    cols = [c.upper() for c in cq.REQUIRED_COLUMNS["nfsaida"]]
    res = cq.validate_source("nfsaida", "t.NF", "x", "", conn=_FakeConn(columns=cols))
    assert res["ok"] is True
