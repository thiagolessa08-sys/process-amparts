"""O `build_eventlog` do AM Parts precisa dar o MESMO resultado vindo do CSV
(tudo texto) e do MySQL (datetime, int, Decimal).

É onde o conector novo pode quebrar em silêncio: um Decimal somado com float
estoura TypeError, e um SORTING que chega como texto ordena lexicograficamente
("10" < "5"), trocando a ordem dos eventos sem erro nenhum.
"""
from datetime import datetime
from decimal import Decimal

import pandas as pd

from app.connectors.mysql_connector import MySQLConnector, _frame
from app.sources.amparts import build_eventlog

ATIVIDADES = [
    # case, atividade,             eventtime,             sorting
    ("A|1", "CRIOU ORCAMENTO", "2026-03-01 09:00:00", 10),
    ("A|1", "CRIOU PEDIDO", "2026-03-02 10:00:00", 20),
    ("A|1", "PAGAMENTO", "2026-03-03 11:00:00", 50),
    ("B|1", "CRIOU ORCAMENTO", "2026-03-04 08:00:00", 10),
]
CASOS = [
    # case, orcamento, orc_item, pedido, ped_qtde, ped_total, fat_total, cancelado
    ("A|1", "900", "1", "800", 3, "1500.50", "1500.50", 0),
    ("B|1", "901", "1", None, 1, "250.00", "0.00", 1),
]

_ACT_COLS = ["CASE_KEY", "ACTIVITY_EN", "EVENTTIME", "SORTING", "USUARIO", "VENDEDOR",
             "ORCAMENTO", "ORC_ITEM", "PEDIDO", "PED_ITEM", "OS", "SAIDA", "CLIENTE",
             "PRODUTO", "PROD_NOME", "CONCESSIONARIA", "SOURCE_ACTIVITY"]
_CASE_COLS = ["CASE_KEY", "ORCAMENTO", "ORC_ITEM", "PEDIDO", "PED_ITEM", "OS", "SAIDA",
              "CLIENTE", "CONCESSIONARIA", "PROD_NOME", "DATA_ORCAMENTO", "DATA_PEDIDO",
              "ORC_VALOR", "PED_QTDE", "PED_TOTAL", "FAT_TOTAL", "FOI_CANCELADO"]


def _acts(como_banco: bool) -> pd.DataFrame:
    linhas = []
    for case, act, ts, sort in ATIVIDADES:
        linhas.append({
            "CASE_KEY": case, "ACTIVITY_EN": act,
            "EVENTTIME": datetime.fromisoformat(ts) if como_banco else ts,
            "SORTING": sort if como_banco else str(sort),
            "USUARIO": "u1", "VENDEDOR": "v1", "ORCAMENTO": "900", "ORC_ITEM": "1",
            "PEDIDO": "800", "PED_ITEM": "1", "OS": None, "SAIDA": None,
            "CLIENTE": "c1", "PRODUTO": "p1", "PROD_NOME": "Peca",
            "CONCESSIONARIA": "conc", "SOURCE_ACTIVITY": "PEDIDO",
        })
    return pd.DataFrame(linhas, columns=_ACT_COLS)


def _cases(como_banco: bool) -> pd.DataFrame:
    linhas = []
    for case, orc, item, ped, qtde, total, fat, canc in CASOS:
        linhas.append({
            "CASE_KEY": case, "ORCAMENTO": orc, "ORC_ITEM": item, "PEDIDO": ped,
            "PED_ITEM": "1", "OS": None, "SAIDA": None, "CLIENTE": "c1",
            "CONCESSIONARIA": "conc", "PROD_NOME": "Peca",
            "DATA_ORCAMENTO": datetime(2026, 3, 1) if como_banco else "2026-03-01",
            "DATA_PEDIDO": datetime(2026, 3, 2) if como_banco else "2026-03-02",
            "ORC_VALOR": Decimal(total) if como_banco else total,
            "PED_QTDE": qtde if como_banco else str(qtde),
            "PED_TOTAL": Decimal(total) if como_banco else total,
            "FAT_TOTAL": Decimal(fat) if como_banco else fat,
            "FOI_CANCELADO": canc if como_banco else str(canc),
        })
    return pd.DataFrame(linhas, columns=_CASE_COLS)


def test_csv_e_banco_produzem_o_mesmo_eventlog():
    do_csv = build_eventlog(_acts(False), _cases(False))
    do_banco = build_eventlog(_acts(True), _cases(True))

    assert len(do_csv) == len(do_banco) == 4
    for col in ("case_id", "activity"):
        assert list(do_csv[col]) == list(do_banco[col])
    assert list(do_csv["timestamp"]) == list(do_banco["timestamp"])
    assert list(do_csv["sort"]) == list(do_banco["sort"])


def test_valores_por_caso_batem_entre_as_duas_fontes():
    do_csv = build_eventlog(_acts(False), _cases(False))
    do_banco = build_eventlog(_acts(True), _cases(True))
    for col in ("valor", "fat_total", "orc_total", "qtde_un"):
        assert do_csv[col].sum() == do_banco[col].sum(), col


def test_sorting_do_banco_ordena_numericamente():
    """SORTING como texto ordenaria '10' < '20' < '50' por acaso; o caso real que
    quebra é 5 vs 10 vs 50 — '10' viria antes de '5'."""
    acts = _acts(True)
    acts.loc[acts["ACTIVITY_EN"] == "PAGAMENTO", "SORTING"] = 5
    log = build_eventlog(acts, _cases(True))
    caso_a = log[log["case_id"] == "A|1"]
    assert list(caso_a["activity"]) == ["PAGAMENTO", "CRIOU ORCAMENTO", "CRIOU PEDIDO"]


def test_frame_converte_decimal_para_float():
    df = _frame([(Decimal("10.5"), "texto"), (Decimal("2.25"), "outro")], ["v", "t"])
    assert df["v"].dtype == float
    assert df["v"].sum() == 12.75
    assert df["t"].dtype == object


def test_frame_preserva_none_em_coluna_decimal():
    df = _frame([(None,), (Decimal("3"),)], ["v"])
    assert df["v"].isna().sum() == 1


def test_connector_nao_configurado_sem_variaveis(monkeypatch):
    for v in ("AMPARTS_DB_HOST", "AMPARTS_DB_USER", "AMPARTS_DB_PASSWORD"):
        monkeypatch.delenv(v, raising=False)
    assert MySQLConnector().configured() is False


def test_connector_configurado_com_variaveis(monkeypatch):
    monkeypatch.setenv("AMPARTS_DB_HOST", "10.0.0.1")
    monkeypatch.setenv("AMPARTS_DB_USER", "u")
    monkeypatch.setenv("AMPARTS_DB_PASSWORD", "p")
    c = MySQLConnector()
    assert c.configured() is True
    assert c.port == 3306
    assert c.database == "amparts"


def test_ssl_sem_ca_cifra_mas_nao_autentica(monkeypatch):
    """Comportamento deliberado e documentado — o teste existe para que uma
    mudança acidental para CERT_NONE-com-CA (ou o contrário) apareça."""
    monkeypatch.delenv("AMPARTS_DB_SSL_CA", raising=False)
    import ssl as _ssl
    ctx = MySQLConnector(host="h", user="u", password="p")._ssl_context()
    assert ctx.verify_mode == _ssl.CERT_NONE
    assert ctx.check_hostname is False
