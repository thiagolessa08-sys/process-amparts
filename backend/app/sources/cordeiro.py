"""Event log Cordeiro (O2C, SAP) do modelo de process mining pronto no banco
(schema `cordeiro`): SQL_PM_ATIVIDADES (eventos) + SQL_PM_CASES (atributos).

Mesma estrutura de ATIVIDADES do Veddara; a CASES traz valores e datas de
pedido/NF/pagamento próprios do Cordeiro (PED_VALOR, FAT_VALOR, PAG_VALOR…).
"""
import pandas as pd

from ..connectors.agent_connector import AgentConnector

SCHEMA = "cordeiro"
ACT_TABLE = f"{SCHEMA}.SQL_PM_ATIVIDADES"
CASE_TABLE = f"{SCHEMA}.SQL_PM_CASES"

DESDE = "2024-01-01"

# colunas da tela Detalhes (a partir da SQL_PM_CASES)
DETAIL_COLS = [
    {"key": "pedido", "label": "Nr. PED", "fmt": "id"},
    {"key": "data", "label": "Data Pedido", "fmt": "text"},
    {"key": "orcamento", "label": "Nr. ORC", "fmt": "id"},
    {"key": "fatura", "label": "Nr. NF", "fmt": "id"},
    {"key": "dataNf", "label": "Data NF", "fmt": "text"},
    {"key": "cliente", "label": "Cliente", "fmt": "text"},
    {"key": "produto", "label": "Produto", "fmt": "text"},
    {"key": "qtde", "label": "Qtde", "fmt": "int"},
    {"key": "valorPed", "label": "Valor Pedido", "fmt": "money"},
    {"key": "valorFat", "label": "Valor Fatura", "fmt": "money"},
    {"key": "valorPago", "label": "Valor Pago", "fmt": "money"},
    {"key": "dataPag", "label": "Data Pgto", "fmt": "text"},
]

# painel de atributos do evento (Case Explorer) — ATIVIDADES igual ao Veddara
EVENT_ATTRS = [
    {"label": "Activity En", "col": "activity"},
    {"label": "Case Key O2c", "col": "case_id"},
    {"label": "Cliente", "col": "cliente"},
    {"label": "Eventtime", "col": "eventtime_raw", "fmt": "date"},
    {"label": "Fat Item", "col": "fat_item"},
    {"label": "Fatura", "col": "fatura"},
    {"label": "New Value Changed", "col": "new_value_changed"},
    {"label": "Old Value Changed", "col": "old_value_changed"},
    {"label": "Orc Item", "col": "orc_item"},
    {"label": "Orcamento", "col": "orcamento"},
    {"label": "Ped Item", "col": "ped_item"},
    {"label": "Pedido", "col": "pedido"},
    {"label": "Prod Nome", "col": "prod_nome"},
    {"label": "Produto", "col": "produto_cod"},
    {"label": "Sorting", "col": "sort"},
    {"label": "Source Activity", "col": "source_activity"},
    {"label": "Usuario", "col": "resource"},
    {"label": "Vendedor", "col": "vendedor"},
]

_CASES_DETAIL: pd.DataFrame | None = None


def get_cases_detail() -> pd.DataFrame:
    return _CASES_DETAIL if _CASES_DETAIL is not None else pd.DataFrame()


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def _date(s):
    return pd.to_datetime(s, errors="coerce").dt.strftime("%Y-%m-%d")


def load_cordeiro_eventlog(conn: AgentConnector | None = None, progress=None) -> pd.DataFrame:
    progress = progress or (lambda p: None)
    conn = conn or AgentConnector()
    if not conn.configured():
        raise RuntimeError("AGENT_URL/AGENT_API_KEY não configurados")

    total = conn.query_df(
        f"SELECT COUNT(*) AS n FROM {ACT_TABLE} WHERE EVENTTIME >= '{DESDE}'", limit=1)
    total = max(int(total["n"].iloc[0]) if not total.empty else 1, 1)
    progress(3)

    acts = conn.paginate_offset(
        "_CASE_KEY_O2C, ACTIVITY_EN, EVENTTIME, SORTING, USUARIO, VENDEDOR, "
        "CLIENTE, PRODUTO, PROD_NOME, ORCAMENTO, ORC_ITEM, PEDIDO, PED_ITEM, "
        "FATURA, FAT_ITEM, SOURCE_ACTIVITY, OLD_VALUE_CHANGED, NEW_VALUE_CHANGED",
        ACT_TABLE, order="_CASE_KEY_O2C, SORTING, EVENTTIME",
        where=f"EVENTTIME >= '{DESDE}'",
        on_rows=lambda n: progress(3 + 80 * min(n, total) / total))
    progress(84)
    cases = conn.paginate_offset(
        "_CASE_KEY_O2C, PEDIDO, ORCAMENTO, FATURA, CLIENTE, PROD_NOME, "
        "DATA_PEDIDO, DATA_EMISSAO_NF, DATA_PAGAMENTO, PED_QTDE_ITEM, "
        "PED_VALOR, FAT_VALOR, PAG_VALOR",
        CASE_TABLE, order="_CASE_KEY_O2C")
    progress(90)

    global _CASES_DETAIL
    if not cases.empty:
        _CASES_DETAIL = pd.DataFrame({
            "pedido": cases["PEDIDO"],
            "data": _date(cases["DATA_PEDIDO"]),
            "orcamento": cases["ORCAMENTO"],
            "fatura": cases["FATURA"],
            "dataNf": _date(cases["DATA_EMISSAO_NF"]),
            "cliente": cases["CLIENTE"],
            "produto": cases["PROD_NOME"],
            "qtde": _num(cases["PED_QTDE_ITEM"]),
            "valorPed": _num(cases["PED_VALOR"]),
            "valorFat": _num(cases["FAT_VALOR"]),
            "valorPago": _num(cases["PAG_VALOR"]),
            "dataPag": _date(cases["DATA_PAGAMENTO"]),
        })

    eventtime = pd.to_datetime(acts["EVENTTIME"], errors="coerce")
    sort = _num(acts["SORTING"]).fillna(0)
    produto = acts["PROD_NOME"].where(acts["PROD_NOME"].notna() & (acts["PROD_NOME"].astype(str) != ""),
                                      acts["PRODUTO"])

    def _txt(col):
        return acts[col].astype(str).where(acts[col].notna(), None) if col in acts else None

    log = pd.DataFrame({
        "case_id": acts["_CASE_KEY_O2C"].astype(str),
        "activity": acts["ACTIVITY_EN"].astype(str).str.strip(),
        "timestamp": eventtime + pd.to_timedelta(sort, unit="ms"),
        "sort": sort.astype("int64"),
        "resource": acts["USUARIO"].fillna("—"),
        "vendedor": acts["VENDEDOR"].fillna("—"),
        "cliente": acts["CLIENTE"].fillna("—"),
        "produto": produto.fillna("—"),
        "eventtime_raw": eventtime,
        "produto_cod": _txt("PRODUTO"),
        "prod_nome": _txt("PROD_NOME"),
        "orcamento": _txt("ORCAMENTO"),
        "orc_item": _txt("ORC_ITEM"),
        "pedido": _txt("PEDIDO"),
        "ped_item": _txt("PED_ITEM"),
        "fatura": _txt("FATURA"),
        "fat_item": _txt("FAT_ITEM"),
        "source_activity": _txt("SOURCE_ACTIVITY"),
        "old_value_changed": _txt("OLD_VALUE_CHANGED"),
        "new_value_changed": _txt("NEW_VALUE_CHANGED"),
    })
    log = log.dropna(subset=["timestamp"])

    # valor por caso = faturado (FAT_VALOR). PED_VALOR é majoritariamente nulo
    # no Cordeiro (deixava o KPI baixíssimo), então usa o faturado e só cai
    # para PED_VALOR quando não há faturamento.
    if not cases.empty:
        _v = _num(cases["FAT_VALOR"]).fillna(_num(cases["PED_VALOR"])).fillna(0.0)
        val = (cases.assign(_k=cases["_CASE_KEY_O2C"].astype(str), _v=_v)
                    .groupby("_k")["_v"].sum())
        log["valor"] = log["case_id"].map(val).fillna(0.0)
    else:
        log["valor"] = 0.0

    log = log.sort_values(["case_id", "timestamp"]).reset_index(drop=True)
    return log
