"""Event log Biolab (P2P/Compras, base JD Edwards) do schema `biolab`:
SQL_PM_ATIVIDADES (eventos) + SQL_PM_CASES (atributos por caso) + SQL_PM_DADOS
(detalhe para a tela Detalhes). Mapeia para o formato padrão do app.
"""
import pandas as pd

from ..connectors.agent_connector import AgentConnector

SCHEMA = "biolab"
ACT_TABLE = f"{SCHEMA}.SQL_PM_ATIVIDADES"
CASE_TABLE = f"{SCHEMA}.SQL_PM_CASES"
DADOS_TABLE = f"{SCHEMA}.SQL_PM_DADOS"

# recorte: de 2025 até a data atual (exclui histórico antigo e datas futuras/inválidas)
DESDE = "2025-01-01"


def _periodo_where() -> str:
    hoje = pd.Timestamp.now().strftime("%Y-%m-%d")
    return f"EVENTTIME >= '{DESDE}' AND EVENTTIME <= '{hoje} 23:59:59'"

# colunas da tela Detalhes (a partir da SQL_PM_DADOS)
DETAIL_COLS = [
    {"key": "documento", "label": "Documento", "fmt": "id"},
    {"key": "item", "label": "Item", "fmt": "id"},
    {"key": "data", "label": "Emissão", "fmt": "text"},
    {"key": "tipo", "label": "Tipo", "fmt": "text"},
    {"key": "fornecedor", "label": "Fornecedor", "fmt": "text"},
    {"key": "produto", "label": "Produto", "fmt": "text"},
    {"key": "qtde", "label": "Qtde", "fmt": "int"},
    {"key": "preco", "label": "Preço Unit.", "fmt": "money"},
    {"key": "valor", "label": "Líquido Pedido", "fmt": "money"},
    {"key": "cancelado", "label": "Cancelado", "fmt": "text"},
]

_CASES_DETAIL: pd.DataFrame | None = None


def get_cases_detail() -> pd.DataFrame:
    return _CASES_DETAIL if _CASES_DETAIL is not None else pd.DataFrame()


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def load_biolab_eventlog(conn: AgentConnector | None = None, progress=None) -> pd.DataFrame:
    progress = progress or (lambda p: None)
    conn = conn or AgentConnector()
    if not conn.configured():
        raise RuntimeError("AGENT_URL/AGENT_API_KEY não configurados")

    periodo = _periodo_where()
    total = conn.query_df(
        f"SELECT COUNT(*) AS n FROM {ACT_TABLE} WHERE {periodo}", limit=1)
    total = max(int(total["n"].iloc[0]) if not total.empty else 1, 1)
    progress(3)

    acts = conn.paginate_offset(
        "_CASE_KEY, ACTIVITY_NAME, EVENTTIME, _SORTING, _USER_NAME",
        ACT_TABLE, order="_CASE_KEY, _SORTING, EVENTTIME",
        where=periodo,
        on_rows=lambda n: progress(3 + 78 * min(n, total) / total))
    progress(82)

    # atributos por caso (fornecedor/produto/valor) — uma linha por _CASE_KEY
    cases = conn.paginate_offset(
        "_CASE_KEY, PDAN8, PDDSC1, PDAEXP", CASE_TABLE, order="_CASE_KEY")
    progress(88)

    # detalhe (tela Detalhes) — SQL_PM_DADOS
    dados = conn.paginate_offset(
        "DOCUMENTO, LINHAITEM, EMISSAO, TIPODOCTO, FORNECEDOR, PRODUTO, "
        "QUANTIDADE, PRECOUNITARIO, LIQUIDOPEDIDO, CANCELADO",
        DADOS_TABLE, order="DOCUMENTO, LINHAITEM")
    progress(93)

    global _CASES_DETAIL
    if not dados.empty:
        _CASES_DETAIL = pd.DataFrame({
            "documento": dados["DOCUMENTO"],
            "item": dados["LINHAITEM"],
            "data": pd.to_datetime(dados["EMISSAO"], errors="coerce").dt.strftime("%Y-%m-%d"),
            "tipo": dados["TIPODOCTO"],
            "fornecedor": dados["FORNECEDOR"],
            "produto": dados["PRODUTO"],
            "qtde": _num(dados["QUANTIDADE"]),
            "preco": _num(dados["PRECOUNITARIO"]),
            "valor": _num(dados["LIQUIDOPEDIDO"]),
            "cancelado": dados["CANCELADO"],
        })

    eventtime = pd.to_datetime(acts["EVENTTIME"], errors="coerce")
    sort = _num(acts["_SORTING"]).fillna(0)

    log = pd.DataFrame({
        "case_id": acts["_CASE_KEY"].astype(str),
        "activity": acts["ACTIVITY_NAME"].astype(str).str.strip(),
        "timestamp": eventtime + pd.to_timedelta(sort, unit="ms"),
        "sort": sort.astype("int64"),
        "resource": acts["_USER_NAME"].fillna("—"),
    })
    log = log.dropna(subset=["timestamp"])

    # fornecedor (→ coluna 'cliente'), produto e valor por caso, via _CASE_KEY
    if not cases.empty:
        ck = cases["_CASE_KEY"].astype(str)
        forn = cases.assign(_k=ck).groupby("_k")["PDAN8"].first()
        prod = cases.assign(_k=ck).groupby("_k")["PDDSC1"].first()
        val = cases.assign(_k=ck, _v=_num(cases["PDAEXP"]).fillna(0.0)).groupby("_k")["_v"].sum()
        log["cliente"] = log["case_id"].map(forn).fillna("—").astype(str)
        log["produto"] = log["case_id"].map(prod).fillna("—").astype(str)
        log["valor"] = log["case_id"].map(val).fillna(0.0)
    else:
        log["cliente"], log["produto"], log["valor"] = "—", "—", 0.0

    log = log.sort_values(["case_id", "timestamp"]).reset_index(drop=True)
    return log
