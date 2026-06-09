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
import pandas as pd

from ..connectors.agent_connector import AgentConnector

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


def _key(df, orc, orci, ped, pedi, fat, fati):
    return (_kpart(df[orc]) + "|" + _kpart(df[orci]) + "|" + _kpart(df[ped]) + "|"
            + _kpart(df[pedi]) + "|" + _kpart(df[fat]) + "|" + _kpart(df[fati]))


def _rows(df, activity, sort, eventtime, usuario, vendedor, cliente, valor,
          orc, orci, ped, pedi, fat, fati):
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
    })
    return out.dropna(subset=["eventtime"])


# ── carga ────────────────────────────────────────────────────────────────────
def load_cordeiro_eventlog(conn: AgentConnector | None = None) -> pd.DataFrame:
    conn = conn or AgentConnector()
    if not conn.configured():
        raise RuntimeError("AGENT_URL/AGENT_API_KEY não configurados")

    # itens (paginação keyset por intnum+linha)
    q = conn.paginate_keyset(
        "QuotationDocNumber, QuotationItemLine, QuotationDocInternalNumber, "
        "QuotationDocCreationDate, QuotationDocCreationTS, QuotationDocCancellationStatus, "
        "QuotationUserSignName, QuotationSalesEmployeeName, QuotationCustomerName, "
        "QuotationItemCode, QuotationItemDescription, QuotationItemTotal",
        f"{SCHEMA}.COTACOES_SAP_PRODUCAO",
        "QuotationDocInternalNumber", "QuotationItemLine")
    o = conn.paginate_keyset(
        "OrderDocNumber, OrderItemLine, OrderDocInternalNumber, "
        "OrderItemBaseDocIntNumber, OrderItemBaseLine, "
        "OrderDocCreationDate, OrderDocCreationTS, OrderDocCancellationStatus, "
        "OrderUserSignName, OrderSalesEmployeeName, OrderCustomerName, "
        "OrderItemCode, OrderItemDescription, OrderItemItemTotal",
        f"{SCHEMA}.PEDIDOS_SAP_PRODUCAO",
        "OrderDocInternalNumber", "OrderItemLine")
    inv = conn.paginate_keyset(
        "InvoiceDocNumber, InvoiceItemLine, InvoiceDocInternalNumber, "
        "InvoiceItemSourceDocIntNumber, InvoiceItemSourceLine, "
        "InvoiceDocCreationDate, InvoiceDocCreationTS, InvoiceDocCancellationStatus, "
        "InvoiceUserSignName, InvoiceSalesEmployeeName, InvoiceCustomerName, "
        "InvoiceItemCode, InvoiceItemDescription, InvoiceItemItemTotal",
        f"{SCHEMA}.NFSAIDA_SAP_PRODUCAO",
        "InvoiceDocInternalNumber", "InvoiceItemLine")
    apr = conn.paginate_df(
        "DocumentInternalNumber k, DocumentType dtype, MAX(DocumentApprovalStatus) st, "
        "MAX(DocumentItemApprovalDate) adate, MAX(DocumentItemApprovalTime) atime, "
        "MAX(DocumentCurrStepName) step",
        f"{SCHEMA}.APROVACOES_SAP_PRODUCAO", "DocumentInternalNumber",
        group="DocumentInternalNumber, DocumentType")

    # chaves numéricas p/ join
    q["q_int"], q["q_line"] = _num(q["QuotationDocInternalNumber"]), _num(q["QuotationItemLine"])
    o["o_int"], o["o_line"] = _num(o["OrderDocInternalNumber"]), _num(o["OrderItemLine"])
    o["o_bint"], o["o_bline"] = _num(o["OrderItemBaseDocIntNumber"]), _num(o["OrderItemBaseLine"])
    inv["i_int"], inv["i_line"] = _num(inv["InvoiceDocInternalNumber"]), _num(inv["InvoiceItemLine"])
    inv["i_sint"], inv["i_sline"] = _num(inv["InvoiceItemSourceDocIntNumber"]), _num(inv["InvoiceItemSourceLine"])

    # ── perspectivas (cada doc resolve a cadeia ORC→PED→FAT) ──
    qoi = (q.merge(o, left_on=["q_int", "q_line"], right_on=["o_bint", "o_bline"], how="left")
             .merge(inv, left_on=["o_int", "o_line"], right_on=["i_sint", "i_sline"], how="left"))
    oqi = (o.merge(q, left_on=["o_bint", "o_bline"], right_on=["q_int", "q_line"], how="left")
             .merge(inv, left_on=["o_int", "o_line"], right_on=["i_sint", "i_sline"], how="left"))
    ioq = (inv.merge(o, left_on=["i_sint", "i_sline"], right_on=["o_int", "o_line"], how="left")
              .merge(q, left_on=["o_bint", "o_bline"], right_on=["q_int", "q_line"], how="left"))

    KP = ("QuotationDocNumber", "QuotationItemLine", "OrderDocNumber", "OrderItemLine",
          "InvoiceDocNumber", "InvoiceItemLine")
    parts = []

    # ORÇAMENTO
    qoi_ts = _combine(qoi["QuotationDocCreationDate"], qoi["QuotationDocCreationTS"])
    parts.append(_rows(qoi, "CRIOU ORCAMENTO", 10, qoi_ts,
                       "QuotationUserSignName", "QuotationSalesEmployeeName",
                       "QuotationCustomerName", "QuotationItemTotal", *KP))
    canc = qoi[qoi["QuotationDocCancellationStatus"].astype(str).str.upper() == "Y"]
    if not canc.empty:
        parts.append(_rows(canc, "CANCELOU ORCAMENTO", 11,
                           _combine(canc["QuotationDocCreationDate"], canc["QuotationDocCreationTS"]),
                           "QuotationUserSignName", "QuotationSalesEmployeeName",
                           "QuotationCustomerName", "QuotationItemTotal", *KP))

    # PEDIDO
    oqi_ts = _combine(oqi["OrderDocCreationDate"], oqi["OrderDocCreationTS"])
    parts.append(_rows(oqi, "CRIOU PEDIDO", 20, oqi_ts,
                       "OrderUserSignName", "OrderSalesEmployeeName",
                       "OrderCustomerName", "OrderItemItemTotal", *KP))
    cancp = oqi[oqi["OrderDocCancellationStatus"].astype(str).str.upper() == "Y"]
    if not cancp.empty:
        parts.append(_rows(cancp, "CANCELOU PEDIDO", 21,
                           _combine(cancp["OrderDocCreationDate"], cancp["OrderDocCreationTS"]),
                           "OrderUserSignName", "OrderSalesEmployeeName",
                           "OrderCustomerName", "OrderItemItemTotal", *KP))

    # FATURA
    ioq_ts = _combine(ioq["InvoiceDocCreationDate"], ioq["InvoiceDocCreationTS"])
    parts.append(_rows(ioq, "CRIOU FATURA", 30, ioq_ts,
                       "InvoiceUserSignName", "InvoiceSalesEmployeeName",
                       "InvoiceCustomerName", "InvoiceItemItemTotal", *KP))
    cancf = ioq[ioq["InvoiceDocCancellationStatus"].astype(str).str.upper().isin(["Y", "C"])]
    if not cancf.empty:
        parts.append(_rows(cancf, "CANCELOU FATURA", 31,
                           _combine(cancf["InvoiceDocCreationDate"], cancf["InvoiceDocCreationTS"]),
                           "InvoiceUserSignName", "InvoiceSalesEmployeeName",
                           "InvoiceCustomerName", "InvoiceItemItemTotal", *KP))

    # ── APROVAÇÕES (anexam ao doc aprovado pelo tipo) ──
    apr["dt_n"] = _num(apr["dtype"])
    apr["st_u"] = apr["st"].astype(str).str.upper()
    apr["appr_ts"] = _combine(apr["adate"], apr["atime"])

    def _aprov(persp, dtype, intcol, activity, sort):
        ok = apr[(apr["dt_n"] == dtype) & (apr["st_u"] == "Y")][["k", "appr_ts", "step"]].copy()
        if ok.empty:
            return None
        ok["k"] = _num(ok["k"])
        m = persp.merge(ok, left_on=intcol, right_on="k", how="inner")
        if m.empty:
            return None
        out = _rows(m, activity, sort, m["appr_ts"], "step",
                    "QuotationSalesEmployeeName", "QuotationCustomerName",
                    "QuotationItemTotal", *KP)
        return out

    a_orc = _aprov(qoi, 23, "q_int", "APROVOU ORCAMENTO", 15)
    a_ped = _aprov(oqi, 17, "o_int", "APROVOU PEDIDO", 25)
    a_fat = _aprov(ioq, 13, "i_int", "APROVOU FATURA", 35)
    for a in (a_orc, a_ped, a_fat):
        if a is not None:
            parts.append(a)

    log = pd.concat(parts, ignore_index=True)
    log["eventtime"] = pd.to_datetime(log["eventtime"], errors="coerce")
    log = log.dropna(subset=["eventtime"])
    # SORTING vira desempate via offset de ms no timestamp
    log["timestamp"] = log["eventtime"] + pd.to_timedelta(log["sort"], unit="ms")
    log = log.drop(columns=["eventtime", "sort"])
    log = log.drop_duplicates(subset=["case_id", "activity", "timestamp"])
    log = log.sort_values(["case_id", "timestamp"]).reset_index(drop=True)
    return log
