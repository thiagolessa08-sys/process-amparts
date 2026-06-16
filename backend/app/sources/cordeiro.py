"""Event log O2C (schema cordeiro / SAP B1) — réplica da transformação oficial
do Celonis (_CEL_O2C_ACTIVITIES).

Modelo:
- CASE KEY item-level = ORC#|ORCi|PED#|PEDi|FAT#|FATi (número do doc + linha do item).
- Joins com a linha do item:
    Pedido→Orçamento : OrderItemBaseDocIntNumber + OrderItemBaseLine
    Fatura→Pedido    : InvoiceItemSourceDocIntNumber + InvoiceItemSourceLine
- Cada atividade tem um SORTING (desempate); embutido como offset de ms no timestamp.
- Timestamp = DocCreationDate (data) + horário extraído do CreationTS ('YYYY-...HH:MI:SS').

Atividades (ACTIVITY_EN / SORTING):
  CRIOU ORCAMENTO 10 · CANCELOU ORCAMENTO 11 · APROVOU ORCAMENTO 15
  CRIOU PEDIDO    20 · CANCELOU PEDIDO    21 · APROVOU PEDIDO    25   (inferido)
  CRIOU FATURA    30 · CANCELOU FATURA    31 · APROVOU FATURA    35   (inferido)
"""
import gc

import pandas as pd

from ..connectors.agent_connector import AgentConnector
from . import cordeiro_queries as cq

SCHEMA = "cordeiro"


# ── helpers ──────────────────────────────────────────────────────────────────
def _num(s):
    return pd.to_numeric(s, errors="coerce")


def _kpart(s):
    """parte da case key: int do doc/linha, nulo → 0."""
    return _num(s).fillna(0).astype("int64").astype(str)


def _combine(date_s, tod_s):
    """Data real + horário 'HH:MM:SS' extraído do texto do TS (ano 0001 → fora do range)."""
    d = pd.to_datetime(date_s, errors="coerce").dt.normalize()
    hhmmss = tod_s.astype(str).str.extract(r"(\d{2}:\d{2}:\d{2})")[0]
    tod = pd.to_timedelta(hhmmss, errors="coerce").fillna(pd.Timedelta(0))
    return d + tod


def _lk(df, keys):
    """Frame de lookup p/ merge: remove linhas com chave NaN.

    O pandas casa NaN==NaN em merge (≠ SQL); sem isso, linhas sem chave de um
    lado cruzariam com TODAS as sem chave do outro → produto cartesiano (OOM).
    Chave nula não é uma ligação real, então a remoção também é mais correta.
    """
    return df.dropna(subset=list(keys))


def _key(df, orc, orci, ped, pedi, fat, fati):
    return (_kpart(df[orc]) + "|" + _kpart(df[orci]) + "|" + _kpart(df[ped]) + "|"
            + _kpart(df[pedi]) + "|" + _kpart(df[fat]) + "|" + _kpart(df[fati]))


def _rows(df, activity, sort, eventtime, usuario, vendedor, cliente, valor,
          orc, orci, ped, pedi, fat, fati, produto="produto"):
    """Monta as linhas de uma atividade (vetorizado)."""
    out = pd.DataFrame({
        "case_id": _key(df, orc, orci, ped, pedi, fat, fati),
        "activity": activity,
        "eventtime": eventtime.values,
        "sort": sort,
        "resource": df[usuario].fillna("—").values if usuario in df else "—",
        "vendedor": df[vendedor].fillna("—").values if vendedor in df else "—",
        "cliente": df[cliente].fillna("—").values if cliente in df else "—",
        "valor": _num(df[valor]).fillna(0).values if valor in df else 0.0,
        "produto": df[produto].fillna("—").values if produto in df else "—",
    })
    return out.dropna(subset=["eventtime"])


# ── carga ────────────────────────────────────────────────────────────────────
def load_cordeiro_eventlog(conn: AgentConnector | None = None) -> pd.DataFrame:
    conn = conn or AgentConnector()
    if not conn.configured():
        raise RuntimeError("AGENT_URL/AGENT_API_KEY não configurados")

    # consultas-base editáveis (colunas/tabela/where vêm da config; chaves e
    # group são fixos no modelo). Ver app.sources.cordeiro_queries.
    cfg = cq.get_config()
    sc = cq.STRUCT

    # itens (paginação keyset por intnum+linha) — só colunas usadas, p/ poupar memória
    q = conn.paginate_keyset(
        cfg["cotacoes"]["columns"], cfg["cotacoes"]["table"],
        sc["cotacoes"]["k1"], sc["cotacoes"]["k2"], where=cfg["cotacoes"]["where"])
    o = conn.paginate_keyset(
        cfg["pedidos"]["columns"], cfg["pedidos"]["table"],
        sc["pedidos"]["k1"], sc["pedidos"]["k2"], where=cfg["pedidos"]["where"])
    inv = conn.paginate_keyset(
        cfg["nfsaida"]["columns"], cfg["nfsaida"]["table"],
        sc["nfsaida"]["k1"], sc["nfsaida"]["k2"], where=cfg["nfsaida"]["where"])
    apr = conn.paginate_df(
        cfg["aprovacoes"]["columns"], cfg["aprovacoes"]["table"],
        sc["aprovacoes"]["key"], where=cfg["aprovacoes"]["where"],
        group=sc["aprovacoes"]["group"])

    # chaves numéricas p/ join
    q["q_int"], q["q_line"] = _num(q["QuotationDocInternalNumber"]), _num(q["QuotationItemLine"])
    o["o_int"], o["o_line"] = _num(o["OrderDocInternalNumber"]), _num(o["OrderItemLine"])
    o["o_bint"], o["o_bline"] = _num(o["OrderItemBaseDocIntNumber"]), _num(o["OrderItemBaseLine"])
    inv["i_int"], inv["i_line"] = _num(inv["InvoiceDocInternalNumber"]), _num(inv["InvoiceItemLine"])
    inv["i_sint"], inv["i_sline"] = _num(inv["InvoiceItemSourceDocIntNumber"]), _num(inv["InvoiceItemSourceLine"])

    # projeções slim — só o necessário para encadear/montar a case key
    q_slim = q[["QuotationDocNumber", "QuotationItemLine", "q_int", "q_line"]]
    o_slim = o[["OrderDocNumber", "OrderItemLine", "o_int", "o_line", "o_bint", "o_bline"]]
    i_slim = inv[["InvoiceDocNumber", "InvoiceItemLine", "i_sint", "i_sline"]]

    KP = ("QuotationDocNumber", "QuotationItemLine", "OrderDocNumber", "OrderItemLine",
          "InvoiceDocNumber", "InvoiceItemLine")

    # aprovações por tipo (status Y), pré-fatiadas
    apr["dt_n"] = _num(apr["dtype"])
    apr["st_u"] = apr["st"].astype(str).str.upper()
    apr["appr_ts"] = _combine(apr["adate"], apr["atime"])
    apr_ok = apr[apr["st_u"] == "Y"]

    parts = []

    def _aprov(persp, dtype, intcol, activity, sort):
        ok = apr_ok[apr_ok["dt_n"] == dtype][["k", "appr_ts", "step"]].copy()
        if ok.empty:
            return
        ok["k"] = _num(ok["k"])
        ok = _lk(ok, ["k"])
        m = persp.merge(ok, left_on=intcol, right_on="k", how="inner")
        if not m.empty:
            parts.append(_rows(m, activity, sort, m["appr_ts"], "step",
                               "salesemp", "customer", "valor", *KP))

    # ── ORÇAMENTO ──
    qoi = (q.merge(_lk(o_slim, ["o_bint", "o_bline"]), left_on=["q_int", "q_line"], right_on=["o_bint", "o_bline"], how="left")
             .merge(_lk(i_slim, ["i_sint", "i_sline"]), left_on=["o_int", "o_line"], right_on=["i_sint", "i_sline"], how="left")
             .rename(columns={"QuotationSalesEmployeeName": "salesemp",
                              "QuotationCustomerName": "customer", "QuotationItemTotal": "valor",
                              "QuotationItemCode": "produto"}))
    ts = _combine(qoi["QuotationDocCreationDate"], qoi["QuotationDocCreationTS"])
    parts.append(_rows(qoi, "CRIOU ORCAMENTO", 10, ts,
                       "QuotationUserSignName", "salesemp", "customer", "valor", *KP))
    canc = qoi[qoi["QuotationDocCancellationStatus"].astype(str).str.upper() == "Y"]
    if not canc.empty:
        parts.append(_rows(canc, "CANCELOU ORCAMENTO", 11,
                           _combine(canc["QuotationDocCreationDate"], canc["QuotationDocCreationTS"]),
                           "QuotationUserSignName", "salesemp", "customer", "valor", *KP))
    _aprov(qoi, 23, "q_int", "APROVOU ORCAMENTO", 15)
    del qoi, canc
    gc.collect()

    # ── PEDIDO ──
    oqi = (o.merge(_lk(q_slim, ["q_int", "q_line"]), left_on=["o_bint", "o_bline"], right_on=["q_int", "q_line"], how="left")
             .merge(_lk(i_slim, ["i_sint", "i_sline"]), left_on=["o_int", "o_line"], right_on=["i_sint", "i_sline"], how="left")
             .rename(columns={"OrderSalesEmployeeName": "salesemp",
                              "OrderCustomerName": "customer", "OrderItemItemTotal": "valor",
                              "OrderItemCode": "produto"}))
    ts = _combine(oqi["OrderDocCreationDate"], oqi["OrderDocCreationTS"])
    parts.append(_rows(oqi, "CRIOU PEDIDO", 20, ts,
                       "OrderUserSignName", "salesemp", "customer", "valor", *KP))
    cancp = oqi[oqi["OrderDocCancellationStatus"].astype(str).str.upper() == "Y"]
    if not cancp.empty:
        parts.append(_rows(cancp, "CANCELOU PEDIDO", 21,
                           _combine(cancp["OrderDocCreationDate"], cancp["OrderDocCreationTS"]),
                           "OrderUserSignName", "salesemp", "customer", "valor", *KP))
    _aprov(oqi, 17, "o_int", "APROVOU PEDIDO", 25)
    del oqi, cancp
    gc.collect()

    # ── FATURA ──
    ioq = (inv.merge(_lk(o_slim, ["o_int", "o_line"]), left_on=["i_sint", "i_sline"], right_on=["o_int", "o_line"], how="left")
              .merge(_lk(q_slim, ["q_int", "q_line"]), left_on=["o_bint", "o_bline"], right_on=["q_int", "q_line"], how="left")
              .rename(columns={"InvoiceSalesEmployeeName": "salesemp",
                               "InvoiceCustomerName": "customer", "InvoiceItemItemTotal": "valor",
                               "InvoiceItemCode": "produto"}))
    ts = _combine(ioq["InvoiceDocCreationDate"], ioq["InvoiceDocCreationTS"])
    parts.append(_rows(ioq, "CRIOU FATURA", 30, ts,
                       "InvoiceUserSignName", "salesemp", "customer", "valor", *KP))
    cancf = ioq[ioq["InvoiceDocCancellationStatus"].astype(str).str.upper().isin(["Y", "C"])]
    if not cancf.empty:
        parts.append(_rows(cancf, "CANCELOU FATURA", 31,
                           _combine(cancf["InvoiceDocCreationDate"], cancf["InvoiceDocCreationTS"]),
                           "InvoiceUserSignName", "salesemp", "customer", "valor", *KP))
    _aprov(ioq, 13, "i_int", "APROVOU FATURA", 35)
    del ioq, cancf
    gc.collect()

    log = pd.concat(parts, ignore_index=True)
    log["eventtime"] = pd.to_datetime(log["eventtime"], errors="coerce")
    log = log.dropna(subset=["eventtime"])
    # SORTING vira desempate via offset de ms no timestamp
    log["timestamp"] = log["eventtime"] + pd.to_timedelta(log["sort"], unit="ms")
    log = log.drop(columns=["eventtime", "sort"])
    log = log.drop_duplicates(subset=["case_id", "activity", "timestamp"])
    log = log.sort_values(["case_id", "timestamp"]).reset_index(drop=True)
    return log
