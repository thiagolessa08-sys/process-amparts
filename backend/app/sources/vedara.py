"""Event log Vedara (O2C) a partir do modelo de process mining já pronto no
banco (schema `veddara`): SQL_PM_ATIVIDADES (eventos) + SQL_PM_CASES (atributos).

Diferente do Cordeiro, aqui o event log já existe pronto — uma linha por evento
com case key, atividade, timestamp e ordenação. Basta projetar para o formato
padrão e enriquecer o valor a partir da tabela de casos.
"""
import pandas as pd

from ..connectors.agent_connector import AgentConnector

SCHEMA = "veddara"
ACT_TABLE = f"{SCHEMA}.SQL_PM_ATIVIDADES"
CASE_TABLE = f"{SCHEMA}.SQL_PM_CASES"

# recorte do período: só eventos a partir de 2024
DESDE = "2024-01-01"

# colunas da tela Detalhes (a partir da SQL_PM_CASES)
DETAIL_COLS = [
    {"key": "nrPed", "label": "Nr. PED", "fmt": "id"},
    {"key": "data", "label": "Data", "fmt": "text"},
    {"key": "nrOrc", "label": "Nr. ORC", "fmt": "id"},
    {"key": "itemOrc", "label": "Item ORC", "fmt": "id"},
    {"key": "nrNf", "label": "Nr. NF", "fmt": "id"},
    {"key": "cliente", "label": "Cliente", "fmt": "text"},
    {"key": "produto", "label": "Produto", "fmt": "text"},
    {"key": "qtde", "label": "Qtde Itens", "fmt": "int"},
    {"key": "valor", "label": "Valor Total", "fmt": "money"},
]

# painel de atributos do evento (clicar na atividade no Case Explorer)
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

# detalhe da SQL_PM_CASES (tela "Detalhes"), preenchido após a carga
_CASES_DETAIL: pd.DataFrame | None = None


def get_cases_detail() -> pd.DataFrame:
    """DataFrame de detalhe (uma linha por caso) da SQL_PM_CASES, ou vazio."""
    return _CASES_DETAIL if _CASES_DETAIL is not None else pd.DataFrame()


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def load_vedara_eventlog(conn: AgentConnector | None = None, progress=None) -> pd.DataFrame:
    progress = progress or (lambda p: None)
    conn = conn or AgentConnector()
    if not conn.configured():
        raise RuntimeError("AGENT_URL/AGENT_API_KEY não configurados")

    # total p/ % honesto (a tabela de eventos é a parte pesada)
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
        "_CASE_KEY_O2C, NR_PEDIDO, DT_PEDIDO, NR_ORCAMENTO, NR_ITEM_ORCAMENTO, "
        "NR_INVOICE, CD_CLIENTE, NOME_CLIENTE, NOME_PRODUTO, QT_ORC_ITEM, "
        "VL_ORC_TOTAL_ITEM, NOME_REP",
        CASE_TABLE, order="_CASE_KEY_O2C")
    progress(90)

    # detalhe para a tela "Detalhes" (uma linha por caso)
    global _CASES_DETAIL
    if not cases.empty:
        _CASES_DETAIL = pd.DataFrame({
            "_case_id": cases["_CASE_KEY_O2C"].astype(str),   # oculto: casar com variante
            "nrPed": cases["NR_PEDIDO"],
            "data": pd.to_datetime(cases["DT_PEDIDO"], errors="coerce").dt.strftime("%Y-%m-%d"),
            "nrOrc": cases["NR_ORCAMENTO"],
            "itemOrc": cases["NR_ITEM_ORCAMENTO"],
            "nrNf": cases["NR_INVOICE"],
            "cliente": cases["CD_CLIENTE"],
            "produto": cases["NOME_PRODUTO"],
            "qtde": _num(cases["QT_ORC_ITEM"]),
            "valor": _num(cases["VL_ORC_TOTAL_ITEM"]),
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
        # SORTING entra como desempate (offset de ms) dentro do mesmo timestamp
        "timestamp": eventtime + pd.to_timedelta(sort, unit="ms"),
        "sort": sort.astype("int64"),
        "resource": acts["USUARIO"].fillna("—"),
        "vendedor": acts["VENDEDOR"].fillna("—"),
        "cliente": acts["CLIENTE"].fillna("—"),
        "produto": produto.fillna("—"),
        # atributos crus do evento (painel de detalhe no Case Explorer)
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

    # valor por caso (soma do valor de item dos orçamentos do caso)
    if not cases.empty:
        val = (cases.assign(_k=cases["_CASE_KEY_O2C"].astype(str),
                            _v=_num(cases["VL_ORC_TOTAL_ITEM"]).fillna(0.0))
                    .groupby("_k")["_v"].sum())
        log["valor"] = log["case_id"].map(val).fillna(0.0)
    else:
        log["valor"] = 0.0

    log = log.sort_values(["case_id", "timestamp"]).reset_index(drop=True)
    return log
