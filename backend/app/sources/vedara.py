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
        "CLIENTE, PRODUTO, PROD_NOME",
        ACT_TABLE, order="_CASE_KEY_O2C, SORTING, EVENTTIME",
        where=f"EVENTTIME >= '{DESDE}'",
        on_rows=lambda n: progress(3 + 80 * min(n, total) / total))
    progress(84)
    cases = conn.paginate_offset(
        "_CASE_KEY_O2C, VL_ORC_TOTAL_ITEM, NOME_REP",
        CASE_TABLE, order="_CASE_KEY_O2C")
    progress(90)

    eventtime = pd.to_datetime(acts["EVENTTIME"], errors="coerce")
    sort = _num(acts["SORTING"]).fillna(0)
    produto = acts["PROD_NOME"].where(acts["PROD_NOME"].notna() & (acts["PROD_NOME"].astype(str) != ""),
                                      acts["PRODUTO"])

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
