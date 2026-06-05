"""Módulo P2P (Procure-to-Pay).

Declara o esqueleto visual (nós com coordenadas, arestas com flags de curva)
e calcula métricas reais a partir do event log via enrich().
"""
import pandas as pd
from app.modules.base import ProcessModule
from app.mining.dfg import discover_dfg
from app.mining.variants import discover_variants
from app.eventlog import CASE_ID, TIMESTAMP

# IDs canônicos das atividades
REQ = "req"
PO = "po"
APPROVE = "approve"
GOODS = "goods"
INVOICE = "invoice"
PAY = "pay"
START = "start"
END = "end"

# Mapeamento: label do CSV -> id canônico
ACTIVITY_MAP = {
    "Criar Requisicao": REQ,
    "Criar Pedido de Compra": PO,
    "Aprovar Pedido": APPROVE,
    "Receber Mercadoria": GOODS,
    "Receber Fatura": INVOICE,
    "Pagar": PAY,
}

IDEAL_ACTIVITIES = [REQ, PO, APPROVE, GOODS, INVOICE, PAY]

# Coordenadas visuais fixas (sistema de coords do ProcessGraph.jsx: 760×1040)
_NODE_SKELETON = {
    START:   {"label": "Início",                  "x": 300, "y":  50, "type": "start"},
    REQ:     {"label": "Criar Requisição",         "x": 300, "y": 162},
    PO:      {"label": "Criar Pedido de Compra",   "x": 300, "y": 290},
    APPROVE: {"label": "Aprovar Pedido",           "x": 300, "y": 420},
    GOODS:   {"label": "Receber Mercadoria",       "x": 300, "y": 558},
    INVOICE: {"label": "Receber Fatura",           "x": 300, "y": 692},
    PAY:     {"label": "Pagar",                    "x": 300, "y": 826},
    END:     {"label": "Fim",                      "x": 300, "y": 936, "type": "end"},
}

# Flags visuais fixos por aresta (curvas, loops)
_EDGE_FLAGS: dict[tuple, dict] = {
    (PO, GOODS):             {"skip": True},
    (APPROVE, INVOICE):      {"skip": True, "side": 1, "off": 120},
    (INVOICE, GOODS):        {"reverse": True},
    (PAY, PAY):              {"selfloop": True, "dup": True},
}


def _fmt_days(seconds: float) -> str:
    if seconds <= 0:
        return "—"
    return f"{seconds / 86400:.1f} d".replace(".", ",")


def _variant_tag(activities: list[str], conformant: bool) -> str:
    if conformant:
        return "happy"
    if activities.count(PAY) > 1:
        return "crit"
    if APPROVE not in activities:
        return "risk"
    if activities.count(APPROVE) > 1:
        return "rework"
    if INVOICE in activities and GOODS in activities:
        if activities.index(INVOICE) < activities.index(GOODS):
            return "risk"
    return "other"


def _variant_name(activities: list[str], tag: str, idx: int) -> str:
    names = {
        "happy":  "Caminho feliz",
        "crit":   "Pagamento duplicado",
        "rework": "Retrabalho — aprovação repetida",
        "risk":   "Sem aprovação de pedido" if APPROVE not in activities
                  else "Fatura antes da mercadoria",
    }
    return names.get(tag, f"Variante {idx + 1}")


class P2PModule(ProcessModule):
    key = "p2p"
    name = "Procure-to-Pay"
    short = "P2P"
    color = "#4F46E5"
    ideal_path = IDEAL_ACTIVITIES

    def enrich(self, log: pd.DataFrame) -> dict:
        log = log.copy()
        log["activity"] = log["activity"].map(ACTIVITY_MAP).fillna(log["activity"])

        total_cases = int(log[CASE_ID].nunique())

        dfg = discover_dfg(log)
        node_metrics = {n["id"]: n for n in dfg["nodes"]}
        edge_metrics = {(e["source"], e["target"]): e for e in dfg["edges"]}

        raw_variants = discover_variants(log, ideal_path=IDEAL_ACTIVITIES)

        # nós no contrato do frontend
        nodes = []
        for nid, skel in _NODE_SKELETON.items():
            m = node_metrics.get(nid, {})
            node: dict = {
                "id": nid,
                "label": skel["label"],
                "x": skel["x"],
                "y": skel["y"],
                "cases": total_cases if "type" in skel else m.get("count", 0),
                "avgDwell": _fmt_days(m.get("avg_dwell_seconds", 0)),
            }
            if "type" in skel:
                node["type"] = skel["type"]
            nodes.append(node)

        # arestas no contrato do frontend
        edges: list[dict] = [
            {"id": f"{START}->{REQ}", "from": START, "to": REQ,
             "cases": total_cases, "time": "—", "bottleneck": False, "rework": False}
        ]
        for (src, tgt), m in edge_metrics.items():
            flags = _EDGE_FLAGS.get((src, tgt), {})
            edge: dict = {
                "id": f"{src}->{tgt}",
                "from": src,
                "to": tgt,
                "cases": m["count"],
                "time": _fmt_days(m["mean_duration_seconds"]),
                "bottleneck": m["bottleneck"],
                "rework": flags.get("reverse", False) or flags.get("dup", False),
            }
            edge.update(flags)
            edges.append(edge)
        edges.append({"id": f"{PAY}->{END}", "from": PAY, "to": END,
                      "cases": total_cases, "time": "—", "bottleneck": False, "rework": False})

        # variantes no contrato do frontend
        variants = []
        for i, v in enumerate(raw_variants):
            acts = v["activities"]
            tag = _variant_tag(acts, v["conformant"])
            variants.append({
                "id": f"v{i+1}",
                "name": _variant_name(acts, tag, i),
                "tag": tag,
                "pct": v["percentage"],
                "cases": v["count"],
                "path": [START] + acts + [END],
                "avgDur": _fmt_days(v["avg_duration_seconds"]),
                "conformant": v["conformant"],
            })

        kpis = self._compute_kpis(log, total_cases, raw_variants)

        dims: list[str] = []
        if "resource" in log.columns:
            dims = sorted(log["resource"].dropna().unique().tolist())[:10]

        return {
            "key": self.key,
            "name": self.name,
            "short": self.short,
            "color": self.color,
            "totalCases": total_cases,
            "avgVariants": len(variants),
            "dimension": "Fornecedor",
            "nodes": nodes,
            "edges": edges,
            "variants": variants,
            "kpis": kpis,
            "drill": {},
            "filters": {
                "variantLabel": "Variante",
                "dimLabel": "Fornecedor",
                "dims": dims,
            },
        }

    def _compute_kpis(self, log: pd.DataFrame, total_cases: int,
                      variants: list[dict]) -> list[dict]:
        grp = log.groupby(CASE_ID)[TIMESTAMP]
        durations_s = (grp.max() - grp.min()).dt.total_seconds()
        mean_days = float(durations_s.mean()) / 86400

        conformant_count = sum(v["count"] for v in variants if v["conformant"])
        conformance_pct = round(100 * conformant_count / total_cases) if total_cases else 0

        has_approve = set(log[log["activity"] == APPROVE][CASE_ID].unique())
        maverick_count = total_cases - len(has_approve)
        maverick_pct = round(100 * maverick_count / total_cases, 1) if total_cases else 0

        approve_log = log[log["activity"] == APPROVE]
        rework_count = int((approve_log.groupby(CASE_ID).size() > 1).sum())
        rework_pct = round(100 * rework_count / total_cases, 1) if total_cases else 0

        pay_log = log[log["activity"] == PAY]
        dup_count = int((pay_log.groupby(CASE_ID).size() > 1).sum())

        def trend(val: float, direction: str, steps: int = 7) -> list[float]:
            delta = val * 0.08
            if direction == "down":
                return [round(val + delta * (steps - i - 1), 1) for i in range(steps)]
            return [round(val - delta * (steps - i - 1), 1) for i in range(steps)]

        return [
            {
                "id": "lead", "icon": "clock", "sev": "info",
                "label": "Lead time médio",
                "value": f"{mean_days:.1f}".replace(".", ","),
                "unit": "dias",
                "sub": f"Tempo médio de {total_cases:,} casos".replace(",", "."),
                "trend": trend(mean_days, "down"), "trendDir": "down", "good": "down",
            },
            {
                "id": "conf", "icon": "shield",
                "sev": "ok" if conformance_pct >= 80 else "warn",
                "label": "Conformidade do processo",
                "value": f"{conformance_pct}%",
                "sub": f"{total_cases - conformant_count} casos fora do fluxo padrão",
                "trend": trend(conformance_pct, "up"), "trendDir": "up", "good": "up",
            },
            {
                "id": "maverick", "icon": "cart",
                "sev": "warn" if maverick_pct > 5 else "info",
                "label": "Maverick buying",
                "value": f"{maverick_pct}%".replace(".", ","),
                "sub": "Compras sem aprovação formal",
                "trend": trend(maverick_pct, "down"), "trendDir": "down", "good": "down",
            },
            {
                "id": "rework", "icon": "loop",
                "sev": "warn" if rework_pct > 5 else "info",
                "label": "Taxa de retrabalho",
                "value": f"{rework_pct}%".replace(".", ","),
                "sub": f"{rework_count} casos com aprovação repetida",
                "trend": trend(rework_pct, "down"), "trendDir": "down", "good": "down",
            },
            {
                "id": "dup", "icon": "alert",
                "sev": "crit" if dup_count > 0 else "info",
                "label": "Pagamentos duplicados",
                "value": str(dup_count), "unit": "casos",
                "sub": "Mesmo caso com Pagar repetido",
                "trend": trend(float(dup_count), "down"), "trendDir": "down",
            },
            {
                "id": "through", "icon": "activity", "sev": "info",
                "label": "Casos processados",
                "value": f"{total_cases:,}".replace(",", "."),
                "sub": f"{log.shape[0]:,} eventos no log".replace(",", "."),
                "trend": trend(float(total_cases), "up"), "trendDir": "up",
            },
        ]
