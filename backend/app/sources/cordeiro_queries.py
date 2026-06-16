"""Configuração editável das 4 consultas-base do Cordeiro.

O event log do Cordeiro é montado a partir de 4 fontes (cotações, pedidos, notas
fiscais e aprovações). Cada fonte tem três partes editáveis pela UI — `table`
(FROM), `columns` (projeção) e `where` (filtro). As chaves de paginação, o
GROUP BY (aprovações) e o ORDER BY são fixos (parte do modelo) e ficam em STRUCT.

Defaults vivem aqui; um override é persistido em JSON no caminho de
`CORDEIRO_QUERY_CONFIG` (ex.: um Volume do Railway) e tem prioridade.
"""
import json
import os
from pathlib import Path

# fontes na ordem de exibição
ORDER = ["cotacoes", "pedidos", "nfsaida", "aprovacoes"]
LABELS = {
    "cotacoes": "Cotações",
    "pedidos": "Pedidos",
    "nfsaida": "Notas Fiscais",
    "aprovacoes": "Aprovações",
}

DEFAULT_QUERIES = {
    "cotacoes": {
        "table": "cordeiro.COTACOES_SAP_PRODUCAO",
        "columns": (
            "QuotationDocNumber, QuotationItemLine, QuotationDocInternalNumber, "
            "QuotationDocCreationDate, QuotationDocCreationTS, QuotationDocCancellationStatus, "
            "QuotationUserSignName, QuotationSalesEmployeeName, QuotationCustomerName, "
            "QuotationItemTotal, QuotationItemCode"
        ),
        "where": "",
    },
    "pedidos": {
        "table": "cordeiro.PEDIDOS_SAP_PRODUCAO",
        "columns": (
            "OrderDocNumber, OrderItemLine, OrderDocInternalNumber, "
            "OrderItemBaseDocIntNumber, OrderItemBaseLine, "
            "OrderDocCreationDate, OrderDocCreationTS, OrderDocCancellationStatus, "
            "OrderUserSignName, OrderSalesEmployeeName, OrderCustomerName, "
            "OrderItemItemTotal, OrderItemCode"
        ),
        "where": "",
    },
    "nfsaida": {
        "table": "cordeiro.NFSAIDA_SAP_PRODUCAO",
        "columns": (
            "InvoiceDocNumber, InvoiceItemLine, InvoiceDocInternalNumber, "
            "InvoiceItemSourceDocIntNumber, InvoiceItemSourceLine, "
            "InvoiceDocCreationDate, InvoiceDocCreationTS, InvoiceDocCancellationStatus, "
            "InvoiceUserSignName, InvoiceSalesEmployeeName, InvoiceCustomerName, "
            "InvoiceItemItemTotal, InvoiceItemCode"
        ),
        "where": "",
    },
    "aprovacoes": {
        "table": "cordeiro.APROVACOES_SAP_PRODUCAO",
        "columns": (
            "DocumentInternalNumber k, DocumentType dtype, "
            "MAX(DocumentApprovalStatus) st, MAX(DocumentItemApprovalDate) adate, "
            "MAX(DocumentItemApprovalTime) atime, MAX(DocumentCurrStepName) step"
        ),
        "where": "",
    },
}

# estrutura fixa (não editável): paginação / agregação
STRUCT = {
    "cotacoes":   {"kind": "keyset", "k1": "QuotationDocInternalNumber", "k2": "QuotationItemLine"},
    "pedidos":    {"kind": "keyset", "k1": "OrderDocInternalNumber",     "k2": "OrderItemLine"},
    "nfsaida":    {"kind": "keyset", "k1": "InvoiceDocInternalNumber",   "k2": "InvoiceItemLine"},
    "aprovacoes": {"kind": "group",  "key": "DocumentInternalNumber",
                   "group": "DocumentInternalNumber, DocumentType"},
}

# colunas/aliases que o pipeline EXIGE de cada fonte (validação)
REQUIRED_COLUMNS = {
    "cotacoes": [
        "QuotationDocNumber", "QuotationItemLine", "QuotationDocInternalNumber",
        "QuotationDocCreationDate", "QuotationDocCreationTS", "QuotationDocCancellationStatus",
        "QuotationUserSignName", "QuotationSalesEmployeeName", "QuotationCustomerName",
        "QuotationItemTotal", "QuotationItemCode",
    ],
    "pedidos": [
        "OrderDocNumber", "OrderItemLine", "OrderDocInternalNumber",
        "OrderItemBaseDocIntNumber", "OrderItemBaseLine",
        "OrderDocCreationDate", "OrderDocCreationTS", "OrderDocCancellationStatus",
        "OrderUserSignName", "OrderSalesEmployeeName", "OrderCustomerName",
        "OrderItemItemTotal", "OrderItemCode",
    ],
    "nfsaida": [
        "InvoiceDocNumber", "InvoiceItemLine", "InvoiceDocInternalNumber",
        "InvoiceItemSourceDocIntNumber", "InvoiceItemSourceLine",
        "InvoiceDocCreationDate", "InvoiceDocCreationTS", "InvoiceDocCancellationStatus",
        "InvoiceUserSignName", "InvoiceSalesEmployeeName", "InvoiceCustomerName",
        "InvoiceItemItemTotal", "InvoiceItemCode",
    ],
    "aprovacoes": ["k", "dtype", "st", "adate", "atime", "step"],
}

_FIELDS = ("table", "columns", "where")


def _config_path() -> Path:
    default = Path(__file__).resolve().parents[2] / "data" / "cordeiro_queries.json"
    return Path(os.environ.get("CORDEIRO_QUERY_CONFIG", str(default)))


def get_config() -> dict:
    """Defaults mesclados com o override persistido (se existir)."""
    cfg = {s: dict(DEFAULT_QUERIES[s]) for s in ORDER}
    path = _config_path()
    if path.exists():
        try:
            override = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            override = {}
        for s in ORDER:
            ov = override.get(s) or {}
            for f in _FIELDS:
                if isinstance(ov.get(f), str):
                    cfg[s][f] = ov[f]
    return cfg


def save_config(cfg: dict) -> dict:
    """Valida o formato, normaliza e grava o override. Retorna a config salva."""
    clean = {}
    for s in ORDER:
        src = cfg.get(s) or {}
        clean[s] = {
            "table": str(src.get("table", DEFAULT_QUERIES[s]["table"])).strip(),
            "columns": str(src.get("columns", DEFAULT_QUERIES[s]["columns"])).strip(),
            "where": str(src.get("where", "")).strip(),
        }
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    return clean


def reset_config() -> None:
    """Remove o override → volta aos defaults do código."""
    path = _config_path()
    if path.exists():
        path.unlink()


def is_customized() -> bool:
    return _config_path().exists()


def probe_sql(source: str, table: str, columns: str, where: str) -> str:
    """SQL de validação (TOP 1) espelhando a estrutura real da fonte."""
    st = STRUCT[source]
    wc = f" WHERE {where}" if where and where.strip() else ""
    if st["kind"] == "group":
        return (f"SELECT TOP 1 {columns} FROM {table}{wc} "
                f"GROUP BY {st['group']} ORDER BY {st['key']}")
    return (f"SELECT TOP 1 {st['k1']} AS kk1, {st['k2']} AS kk2, {columns} "
            f"FROM {table}{wc} ORDER BY {st['k1']}, {st['k2']}")


def validate_source(source: str, table: str, columns: str, where: str, conn=None) -> dict:
    """Roda a query de prova e confere as colunas obrigatórias.

    Retorna {ok, sql, columns, missing, error}.
    """
    from app.connectors.agent_connector import AgentConnector
    if source not in STRUCT:
        return {"ok": False, "sql": "", "columns": [], "missing": [],
                "error": f"Fonte desconhecida: {source}"}
    sql = probe_sql(source, table, columns, where)
    conn = conn or AgentConnector()
    if not conn.configured():
        return {"ok": False, "sql": sql, "columns": [], "missing": [],
                "error": "AGENT_URL/AGENT_API_KEY não configurados"}
    try:
        df = conn.query_df(sql, limit=1)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        resp = getattr(exc, "response", None)  # httpx: corpo traz o erro SQL do agent
        if resp is not None:
            try:
                body = (resp.text or "").strip()
                if body:
                    msg = f"{msg} — {body[:500]}"
            except Exception:
                pass
        return {"ok": False, "sql": sql, "columns": [], "missing": [], "error": msg}

    returned = [str(c).strip() for c in df.columns]
    ret_lower = {c.lower() for c in returned}
    missing = [c for c in REQUIRED_COLUMNS[source] if c.lower() not in ret_lower]
    return {"ok": not missing, "sql": sql, "columns": returned, "missing": missing, "error": None}
