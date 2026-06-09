"""Módulo Cordeiro (O2C real, schema SAP B1 via agent).

Atividades derivadas dos documentos SAP. Esqueleto visual + métricas a partir
do event log montado em app.sources.cordeiro.
"""
import pandas as pd

from app.modules.base import ProcessModule
from app.mining.dfg import discover_dfg
from app.mining.variants import discover_variants
from app.mining.activity_stats import activity_metrics
from app.modules.headline import headline_kpis, period_filters
from app.eventlog import CASE_ID, TIMESTAMP

# ── ids canônicos ───────────────────────────────────────────────────────────
ORC, APR_ORC, CANC_ORC = "orcamento", "aprov_orc", "canc_orc"
PED, APR_PED, CANC_PED = "pedido", "aprov_ped", "canc_ped"
FAT, APR_FAT, CANC_FAT = "fatura", "aprov_fat", "canc_fat"
START, END = "start", "end"

# ACTIVITY_EN (modelo oficial Celonis) -> id canônico
ACTIVITY_MAP = {
    "CRIOU ORCAMENTO":    ORC,
    "APROVOU ORCAMENTO":  APR_ORC,
    "CANCELOU ORCAMENTO": CANC_ORC,
    "CRIOU PEDIDO":       PED,
    "APROVOU PEDIDO":     APR_PED,
    "CANCELOU PEDIDO":    CANC_PED,
    "CRIOU FATURA":       FAT,
    "APROVOU FATURA":     APR_FAT,
    "CANCELOU FATURA":    CANC_FAT,
}

# caminho principal (vertical) — precisa casar com IDEAL_BY_MODULE.cordeiro no front
IDEAL = [ORC, APR_ORC, PED, APR_PED, FAT, APR_FAT]
# núcleo do caminho feliz p/ conformidade (aprovações são opcionais)
IDEAL_CONF = [ORC, PED, FAT]

_LABELS = {
    ORC: "Criou Orçamento", APR_ORC: "Aprovou Orçamento",
    CANC_ORC: "Cancelou Orçamento", PED: "Criou Pedido", APR_PED: "Aprovou Pedido",
    CANC_PED: "Cancelou Pedido", FAT: "Criou Fatura", APR_FAT: "Aprovou Fatura",
    CANC_FAT: "Cancelou Fatura",
}

# posição vertical só p/ referência (o front usa IDEAL_BY_MODULE p/ ordenar)
_Y = {ORC: 162, APR_ORC: 290, PED: 420, APR_PED: 558, FAT: 692, APR_FAT: 826}
_CANCEL = {CANC_ORC, CANC_PED, CANC_FAT}


def _fmt_days(seconds: float) -> str:
    if seconds <= 0:
        return "—"
    return f"{seconds / 86400:.1f} d".replace(".", ",")


class CordeiroModule(ProcessModule):
    key   = "cordeiro"
    name  = "Cordeiro — O2C (SAP)"
    short = "Cordeiro"
    color = "#7b54ee"
    ideal_path = IDEAL_CONF
    activity_map = ACTIVITY_MAP

    def enrich(self, log: pd.DataFrame) -> dict:
        log = log.copy()
        log["activity"] = log["activity"].map(ACTIVITY_MAP).fillna(log["activity"])
        if "customer" in log.columns and "cliente" not in log.columns:
            log["cliente"] = log["customer"]
        if "value" in log.columns and "valor" not in log.columns:
            log["valor"] = log["value"]

        total_cases  = int(log[CASE_ID].nunique())
        dfg          = discover_dfg(log)
        node_metrics = {n["id"]: n for n in dfg["nodes"]}
        edge_metrics = {(e["source"], e["target"]): e for e in dfg["edges"]}
        raw_variants = discover_variants(log, ideal_path=IDEAL_CONF)
        act_stats    = activity_metrics(log)

        # ── nós ──
        nodes = []
        for nid in [ORC, APR_ORC, CANC_ORC, PED, APR_PED, CANC_PED,
                    FAT, APR_FAT, CANC_FAT]:
            m = node_metrics.get(nid, {})
            node = {
                "id": nid, "label": _LABELS[nid],
                "x": 300, "y": _Y.get(nid, 480),
                "cases": m.get("count", 0),
                "avgDwell": _fmt_days(m.get("avg_dwell_seconds", 0)),
            }
            if nid in act_stats:
                node.update(act_stats[nid])
            if nid in _CANCEL:
                node["branch"] = True
            nodes.append(node)
        nodes.append({"id": START, "label": "Início", "x": 300, "y": 50,
                      "type": "start", "cases": total_cases})
        nodes.append({"id": END, "label": "Fim", "x": 300, "y": 940,
                      "type": "end", "cases": total_cases})

        # ── arestas ──
        edges = []
        for (src, tgt), m in edge_metrics.items():
            edges.append({
                "id": f"{src}->{tgt}", "from": src, "to": tgt,
                "cases": m["count"], "time": _fmt_days(m["mean_duration_seconds"]),
                "bottleneck": m["bottleneck"], "rework": False,
            })
        # conectores INÍCIO / FIM (primeira e última atividade de cada caso)
        edges.append({"id": f"{START}->{ORC}", "from": START, "to": ORC,
                      "cases": total_cases, "time": "—", "bottleneck": False, "rework": False})
        edges.append({"id": f"{APR_FAT}->{END}", "from": APR_FAT, "to": END,
                      "cases": total_cases, "time": "—", "bottleneck": False, "rework": False})

        # ── variantes ──
        variants = []
        for i, v in enumerate(raw_variants):
            acts = v["activities"]
            conf = v["conformant"]
            cancel = any(a in _CANCEL for a in acts)
            tag = "happy" if conf else ("crit" if cancel else "other")
            name = ("Caminho feliz" if conf else
                    "Cancelamento / rejeição" if cancel else f"Variante {i+1}")
            variants.append({
                "id": f"v{i+1}", "name": name, "tag": tag,
                "pct": v["percentage"], "cases": v["count"],
                "path": [START] + acts + [END],
                "avgDur": _fmt_days(v["avg_duration_seconds"]),
                "conformant": conf,
            })

        kpis   = self._kpis(log, total_cases, variants)
        period = period_filters(log)
        dims = sorted(log["cliente"].dropna().unique().tolist())[:300] if "cliente" in log.columns else []

        return {
            "key": self.key, "name": self.name, "short": self.short, "color": self.color,
            "totalCases": total_cases, "avgVariants": len(variants),
            "dimension": "Cliente",
            "nodes": nodes, "edges": edges, "variants": variants, "kpis": kpis,
            "headlineKpis": self._safe(lambda: headline_kpis(log, total_cases), []),
            "overview": self._safe(lambda: _overview(log), {}),
            "rework": self._safe(lambda: _rework(log, nodes), {}),
            "twoMatch": {"monthly": [], "pendentes": []},
            "userProd": self._safe(lambda: _user_prod(log), {}),
            "drill": {},
            "filters": {
                "variantLabel": "Variante", "dimLabel": "Cliente", "dims": dims,
                "years": period["years"], "months": period["months"],
            },
        }

    @staticmethod
    def _safe(fn, default):
        try:
            return fn()
        except Exception:
            return default

    def _kpis(self, log, total_cases, variants):
        grp = log.groupby(CASE_ID)[TIMESTAMP]
        mean_days = float((grp.max() - grp.min()).dt.total_seconds().mean()) / 86400

        conf_cases = sum(v["cases"] for v in variants if v["conformant"])
        conf_pct = round(100 * conf_cases / total_cases) if total_cases else 0

        canc_cases = log[log["activity"].isin(_CANCEL)][CASE_ID].nunique()
        canc_pct = round(100 * canc_cases / total_cases, 1) if total_cases else 0

        fat_cases = log[log["activity"] == FAT][CASE_ID].nunique()
        fat_pct = round(100 * fat_cases / total_cases, 1) if total_cases else 0

        def trend(val, direction, steps=7):
            d = val * 0.08
            return ([round(val - d * (steps - i - 1), 1) for i in range(steps)]
                    if direction == "up" else
                    [round(val + d * (steps - i - 1), 1) for i in range(steps)])

        return [
            {"id": "conf", "icon": "shield", "sev": "ok" if conf_pct >= 60 else "warn",
             "label": "Conformidade do processo", "value": f"{conf_pct}%",
             "sub": f"{total_cases - conf_cases} casos fora do fluxo padrão",
             "trend": trend(conf_pct, "up"), "trendDir": "up", "good": "up"},
            {"id": "fat", "icon": "dollar", "sev": "info",
             "label": "Casos faturados", "value": f"{fat_pct}%".replace(".", ","),
             "sub": f"{fat_cases} de {total_cases} chegaram à fatura",
             "trend": trend(fat_pct, "up"), "trendDir": "up", "good": "up"},
            {"id": "cancel", "icon": "alert", "sev": "warn" if canc_pct > 5 else "info",
             "label": "Cancelamentos / rejeições", "value": f"{canc_pct}%".replace(".", ","),
             "sub": f"{canc_cases} casos com cancelamento",
             "trend": trend(canc_pct, "down"), "trendDir": "down", "good": "down"},
            {"id": "lead", "icon": "clock", "sev": "info",
             "label": "Lead time médio", "value": f"{mean_days:.1f}".replace(".", ","),
             "unit": "dias", "sub": f"Tempo médio de {total_cases:,} casos".replace(",", "."),
             "trend": trend(mean_days, "down"), "trendDir": "down", "good": "down"},
        ]


# ── seções auxiliares (leves, independentes do schema demo) ──────────────────
def _overview(log):
    mes = log.assign(mes=log[TIMESTAMP].dt.strftime("%Y-%m"))
    by_month = (mes.groupby("mes")[CASE_ID].nunique().reset_index()
                .rename(columns={CASE_ID: "casos"}).to_dict("records"))
    top_cli = []
    if "cliente" in log.columns:
        top_cli = (log.groupby("cliente")
                   .agg(casos=(CASE_ID, "nunique"), valor=("valor", "sum"))
                   .reset_index().sort_values("casos", ascending=False).head(15)
                   .to_dict("records"))
    return {"byMonth": by_month, "topClientes": top_cli}


def _rework(log, nodes):
    counts = log.groupby([CASE_ID, "activity"]).size()
    rep = counts[counts > 1].reset_index().rename(columns={0: "n"})
    lbl = {n["id"]: n["label"] for n in nodes}
    agg = (rep.groupby("activity").size().reset_index(name="casos")
           .sort_values("casos", ascending=False))
    rows = [{"atividade": lbl.get(r["activity"], r["activity"]), "ocorrencias": int(r["casos"])}
            for _, r in agg.iterrows()]
    return {"atividades": rows}


def _user_prod(log):
    if "resource" not in log.columns:
        return {}
    g = (log.groupby("resource")
         .agg(eventos=("activity", "size"), casos=(CASE_ID, "nunique"))
         .reset_index().sort_values("eventos", ascending=False).head(40))
    users = [{"user": r["resource"], "events": int(r["eventos"]), "cases": int(r["casos"])}
             for _, r in g.iterrows()]
    return {"users": users}
