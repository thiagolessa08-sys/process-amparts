"""Event log Biolab (P2P/Compras, base JD Edwards) do export Celonis (schema
`biolab`): TB_BIOLAB_CELONIS_EXPORT_ACTIVITIES (eventos) +
TB_BIOLAB_CELONIS_EXPORT_CASE (atributos por caso + detalhe da tela Detalhes).
Mapeia para o formato padrão do app.
"""
import pandas as pd

from ..connectors.agent_connector import AgentConnector

SCHEMA = "biolab"
ACT_TABLE = f"{SCHEMA}.TB_BIOLAB_CELONIS_EXPORT_ACTIVITIES"
CASE_TABLE = f"{SCHEMA}.TB_BIOLAB_CELONIS_EXPORT_CASE"

# recorte: de 2025 até a data atual (exclui histórico antigo e datas futuras/inválidas)
DESDE = "2025-01-01"


def _periodo_where() -> str:
    hoje = pd.Timestamp.now().strftime("%Y-%m-%d")
    return f"EVENTTIME >= '{DESDE}' AND EVENTTIME <= '{hoje} 23:59:59'"

# colunas da tela Detalhes (a partir da TB_BIOLAB_CELONIS_EXPORT_CASE)
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

# painel de atributos do evento (clicar na atividade no Case Explorer)
EVENT_ATTRS = [
    {"label": "Atividade", "col": "activity"},
    {"label": "Case Key", "col": "case_id"},
    {"label": "Eventtime", "col": "timestamp", "fmt": "date"},
    {"label": "Empresa", "col": "empresa"},
    {"label": "Documento", "col": "documento"},
    {"label": "Tipo Doc", "col": "tipo_doc"},
    {"label": "Item", "col": "item"},
    {"label": "Descrição", "col": "descricao"},
    {"label": "Fornecedor", "col": "cliente"},
    {"label": "Valor Anterior", "col": "changed_from"},
    {"label": "Valor Novo", "col": "changed_to"},
    {"label": "Usuário", "col": "resource"},
    {"label": "Sorting", "col": "sort"},
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
        "_CASE_KEY, ACTIVITY_NAME, EVENTTIME, _SORTING, _USER_NAME, "
        "PDKCOO, PDDOCO, PDDCTO, PDLNID, _DESCRIPTION, CHANGED_FROM, CHANGED_TO",
        ACT_TABLE, order="_CASE_KEY, _SORTING, EVENTTIME",
        where=periodo,
        on_rows=lambda n: progress(3 + 78 * min(n, total) / total))
    progress(82)

    # atributos por caso (fornecedor/produto/valor) + colunas da tela Detalhes —
    # uma linha por _CASE_KEY, tudo da mesma CASE (aposenta a antiga SQL_PM_DADOS)
    cases = conn.paginate_offset(
        "_CASE_KEY, PDAN8, PDDSC1, PDAEXP, IC_TYPE, PDDOCO, PDDCTO, PDLNID, "
        "PDUORG, PDPRRC, PDAEXP_CANCELADO, PDTRDJ_CONV, FDISSU_CONV",
        CASE_TABLE, order="_CASE_KEY")
    progress(90)

    global _CASES_DETAIL
    if not cases.empty:
        _cancel = _num(cases["PDAEXP_CANCELADO"]).fillna(0.0)
        # Emissão = data do pedido (PDTRDJ_CONV, já convertida do Juliano no
        # export); cai para a data da nota (FDISSU_CONV) nos casos NF sem pedido
        _emissao = pd.to_datetime(cases["PDTRDJ_CONV"], errors="coerce").fillna(
            pd.to_datetime(cases["FDISSU_CONV"], errors="coerce"))
        _CASES_DETAIL = pd.DataFrame({
            "_case_id": cases["_CASE_KEY"].astype(str),   # oculto: filtro de variante
            "documento": cases["PDDOCO"],
            "item": cases["PDLNID"],
            "data": _emissao.dt.strftime("%Y-%m-%d"),
            "tipo": cases["IC_TYPE"],
            "fornecedor": cases["PDAN8"],
            "produto": cases["PDDSC1"],
            # PDUORG traz 3 casas decimais implícitas (qtde real = PDUORG / 1000)
            "qtde": _num(cases["PDUORG"]) / 1000.0,
            "preco": _num(cases["PDPRRC"]),
            "valor": _num(cases["PDAEXP"]),
            "cancelado": _cancel.gt(0).map({True: "Sim", False: "Não"}),
        })

    eventtime = pd.to_datetime(acts["EVENTTIME"], errors="coerce")
    sort = _num(acts["_SORTING"]).fillna(0)

    def _txt(col):
        return acts[col].astype(str).where(acts[col].notna(), None) if col in acts else None

    log = pd.DataFrame({
        "case_id": acts["_CASE_KEY"].astype(str),
        "activity": acts["ACTIVITY_NAME"].astype(str).str.strip(),
        "timestamp": eventtime + pd.to_timedelta(sort, unit="ms"),
        "sort": sort.astype("int64"),
        "resource": acts["_USER_NAME"].fillna("—"),
        # atributos crus do evento (painel de detalhe no Case Explorer)
        "empresa": _txt("PDKCOO"),
        "documento": _txt("PDDOCO"),
        "tipo_doc": _txt("PDDCTO"),
        "item": _txt("PDLNID"),
        "descricao": _txt("_DESCRIPTION"),
        "changed_from": _txt("CHANGED_FROM"),
        "changed_to": _txt("CHANGED_TO"),
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
