"""O `build_eventlog` do AM Parts precisa dar o MESMO resultado vindo do CSV
(tudo texto) e do MySQL (datetime, int, Decimal).

É onde o conector novo pode quebrar em silêncio: um Decimal somado com float
estoura TypeError, e um SORTING que chega como texto ordena lexicograficamente
("10" < "5"), trocando a ordem dos eventos sem erro nenhum.
"""
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from app.connectors import mysql_connector
from app.connectors.mysql_connector import MySQLConnector, _frame
from app.sources.amparts import build_eventlog


_INI_CERT = "-----BEGIN CERTIFICATE-----"
_FIM_CERT = "-----END CERTIFICATE-----"


def _ca_pem() -> str:
    """Um PEM de CA de verdade para os testes de TLS.

    `cryptography` não é dependência do projeto (ver requirements.txt), então
    não dá para gerar um certificado na hora — o bundle do certifi, que vem
    junto do httpx, serve como PEM válido qualquer. Só o primeiro certificado:
    o bundle inteiro passa dos 32 KB que o Windows aceita numa variável de
    ambiente, e o teste inline o coloca no ambiente.
    """
    import certifi
    bundle = Path(certifi.where()).read_text(encoding="utf-8")
    ini, fim = bundle.index(_INI_CERT), bundle.index(_FIM_CERT) + len(_FIM_CERT)
    return bundle[ini:fim] + "\n"

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


def test_connector_nao_configurado_sem_senha(monkeypatch):
    monkeypatch.delenv("PM_DB_PASSWORD", raising=False)
    assert MySQLConnector().configured() is False


def test_connector_usa_defaults_de_producao(monkeypatch):
    for v in ("PM_DB_HOST", "PM_DB_PORT", "PM_DB_USER", "PM_DB_NAME"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("PM_DB_PASSWORD", "p")
    c = MySQLConnector()
    assert c.configured() is True
    assert (c.host, c.port, c.user, c.database) == ("192.3.60.208", 3306, "pm_app", "amparts")


def test_ssl_sem_ca_cifra_mas_nao_autentica(monkeypatch):
    """Comportamento deliberado e documentado — o teste existe para que uma
    mudança acidental para CERT_NONE-com-CA (ou o contrário) apareça."""
    monkeypatch.delenv("PM_DB_CA", raising=False)
    monkeypatch.setattr(mysql_connector, "CA_FILE", tmp_path / "nao-existe.pem")
    import ssl as _ssl
    ctx = MySQLConnector(host="h", user="u", password="p")._ssl_context()
    assert ctx.verify_mode == _ssl.CERT_NONE
    assert ctx.check_hostname is False


def test_ssl_com_ca_valida_cadeia_mas_nao_hostname(monkeypatch, tmp_path):
    """Com CA a cadeia passa a ser verificada; check_hostname continua desligado
    porque o host é um IP sem SAN correspondente no certificado."""
    ca = tmp_path / "ca.pem"
    ca.write_text(_ca_pem(), encoding="utf-8")
    monkeypatch.setenv("PM_DB_CA", str(ca))
    import ssl as _ssl
    ctx = MySQLConnector(password="p")._ssl_context()
    assert ctx.verify_mode == _ssl.CERT_REQUIRED
    assert ctx.check_hostname is False
    assert ctx.get_ca_certs()


def test_ssl_aceita_ca_como_pem_inline(monkeypatch):
    """No Railway o CA chega como conteúdo na variável, não como arquivo."""
    monkeypatch.setenv("PM_DB_CA", _ca_pem())
    ctx = MySQLConnector(password="p")._ssl_context()
    assert ctx.get_ca_certs()


def test_ssl_aceita_pem_com_cabecalho_de_comentario(monkeypatch):
    """PEM exportado pelo openssl vem com Issuer/Subject antes do BEGIN. Se o
    reconhecimento exigir BEGIN na primeira posição, o conteúdo é confundido
    com um caminho de arquivo e a carga quebra no deploy."""
    monkeypatch.setenv("PM_DB_CA", "# Issuer: CN=CA\n# Subject: CN=CA\n" + _ca_pem())
    assert MySQLConnector(password="p")._ssl_context().get_ca_certs()


def test_ssl_caminho_de_ca_inexistente_da_erro_explicito(monkeypatch, tmp_path):
    """Erro de configuração precisa dizer o que houve: sobe em background e só
    aparece como texto em /api/debug/config."""
    monkeypatch.setenv("PM_DB_CA", str(tmp_path / "nao-existe.pem"))
    with pytest.raises(RuntimeError, match="nao-existe.pem"):
        MySQLConnector(password="p")._ssl_context()
