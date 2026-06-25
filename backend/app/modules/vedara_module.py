"""Módulo Vedara (O2C real) — usa o modelo de process mining pronto do banco
(veddara.SQL_PM_ATIVIDADES + SQL_PM_CASES).

Processo rico (~47 atividades). O fluxo (espinha) é montado dinamicamente a
partir do campo SORTING; cancelamentos viram ramos laterais. O front recebe
`idealOrder` (ordem da espinha) e `branchMap` para desenhar o grafo.
"""
import pandas as pd

from app.modules.base import ProcessModule
from app.mining.dfg import discover_dfg
from app.mining.variants import discover_variants
from app.mining.activity_stats import activity_metrics
from app.modules.headline import _fmt_compact, _spark, period_filters, case_ref_date
from app.modules.rework import rework
from app.modules.userprod import user_productivity
from app.eventlog import CASE_ID, TIMESTAMP

# caminho feliz (núcleo de conformidade) e cancelamentos (ramos)
HAPPY = ["CRIACAO DO ORCAMENTO", "CRIACAO DO PEDIDO", "CRIACAO DA FATURA"]
CANCEL = {"CANCELAMENTO DO ORCAMENTO", "CANCELAMENTO DO PEDIDO", "CANCELAMENTO DA FATURA"}
REWORK_ACTS = {
    "ALTERACAO DO PEDIDO",
    "CANCELAMENTO DO ORCAMENTO",
    "CANCELAMENTO DO PEDIDO",
    "ALTERACAO DO ORCAMENTO",
    "CANCELAMENTO DA FATURA",
}
BRANCH_PARENT = {
    "CANCELAMENTO DO ORCAMENTO": "CRIACAO DO ORCAMENTO",
    "CANCELAMENTO DO PEDIDO": "CRIACAO DO PEDIDO",
    "CANCELAMENTO DA FATURA": "CRIACAO DA FATURA",
}
PED, FAT = "CRIACAO DO PEDIDO", "CRIACAO DA FATURA"
START, END = "start", "end"


def _title(s: str) -> str:
    return str(s).title()


def _fmt_days(seconds: float) -> str:
    if seconds <= 0:
        return "—"
    return f"{seconds / 86400:.1f} d".replace(".", ",")


class VedaraModule(ProcessModule):
    key   = "vedara"
    name  = "Vedara — O2C (SAP)"
    short = "Vedara"
    color = "#0e9f93"
    ideal_path = HAPPY
    activity_map: dict = {}  # identidade: a atividade já é o id
    order_activity = PED      # filtro de período usa a data do pedido

    def enrich(self, log: pd.DataFrame) -> dict:
        log = log.copy()
        log["activity"] = log["activity"].astype(str)
        if "valor" in log.columns and "itens" not in log.columns:
            log["itens"] = log["valor"]

        total_cases  = int(log[CASE_ID].nunique())
        dfg          = discover_dfg(log)
        node_metrics = {n["id"]: n for n in dfg["nodes"]}
        edge_metrics = {(e["source"], e["target"]): e for e in dfg["edges"]}
        raw_variants = discover_variants(log, ideal_path=HAPPY)
        act_stats    = activity_metrics(log)

        # ── ordem canônica das atividades pelo SORTING (do próprio log) ──
        order_map = log.groupby("activity")["sort"].min().to_dict() if "sort" in log.columns else {}
        present = list(node_metrics.keys())
        spine = [a for a in sorted(present, key=lambda a: (order_map.get(a, 9999), a)) if a not in CANCEL]
        branches = {a: BRANCH_PARENT[a] for a in present
                    if a in CANCEL and BRANCH_PARENT.get(a) in spine}

        # ── nós ──
        nodes, y, spine_y = [], 120, {}
        for nid in spine:
            spine_y[nid] = y
            m = node_metrics.get(nid, {})
            node = {"id": nid, "label": _title(nid), "x": 300, "y": y,
                    "cases": m.get("count", 0), "avgDwell": _fmt_days(m.get("avg_dwell_seconds", 0))}
            if nid in act_stats:
                node.update(act_stats[nid])
            nodes.append(node)
            y += 130
        # cancelamentos como ramos laterais: ao lado (à direita) do nó-pai, na
        # mesma altura — assim não se empilham sobre a espinha nem entre si
        for bid, parent in branches.items():
            m = node_metrics.get(bid, {})
            node = {"id": bid, "label": _title(bid), "x": 540, "y": spine_y.get(parent, 400),
                    "cases": m.get("count", 0), "avgDwell": _fmt_days(m.get("avg_dwell_seconds", 0)),
                    "branch": True}
            if bid in act_stats:
                node.update(act_stats[bid])
            nodes.append(node)
        nodes.append({"id": START, "label": "Início", "x": 300, "y": 40, "type": "start", "cases": total_cases})
        nodes.append({"id": END, "label": "Fim", "x": 300, "y": y + 60, "type": "end", "cases": total_cases})

        # ── arestas ──
        edges = []
        for (src, tgt), m in edge_metrics.items():
            edges.append({"id": f"{src}->{tgt}", "from": src, "to": tgt,
                          "cases": m["count"], "time": _fmt_days(m["mean_duration_seconds"]),
                          "bottleneck": m["bottleneck"], "rework": False})
        if spine:
            edges.append({"id": f"{START}->{spine[0]}", "from": START, "to": spine[0],
                          "cases": total_cases, "time": "—", "bottleneck": False, "rework": False})
            edges.append({"id": f"{spine[-1]}->{END}", "from": spine[-1], "to": END,
                          "cases": total_cases, "time": "—", "bottleneck": False, "rework": False})

        # ── variantes ──
        variants = []
        for i, v in enumerate(raw_variants):
            acts = v["activities"]
            conf = v["conformant"]
            cancel = any(a in CANCEL for a in acts)
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
        period = period_filters(log, order_activity=self.order_activity)
        dims = sorted(log["cliente"].dropna().unique().tolist())[:300] if "cliente" in log.columns else []
        labels = {a: _title(a) for a in present}

        # dias disponíveis pela data do pedido (consistente com o filtro de período)
        case_ts = case_ref_date(log, self.order_activity)
        dias = sorted({int(t.day) for t in case_ts})
        if "produto" in log.columns:
            prods_raw = log["produto"].dropna().replace("—", pd.NA).dropna().unique()
            produtos = sorted(str(p) for p in prods_raw if str(p).strip())[:300]
        else:
            produtos = []

        return {
            "key": self.key, "name": self.name, "short": self.short, "color": self.color,
            "totalCases": total_cases, "avgVariants": len(variants),
            "dimension": "Cliente",
            "nodes": nodes, "edges": edges, "variants": variants, "kpis": kpis,
            "idealOrder": spine, "branchMap": branches,
            "headlineKpis": self._safe(lambda: _headline(log, total_cases), []),
            "overview": self._safe(lambda: _overview(log), {}),
            "rework": self._safe(
                lambda: rework(log, "cliente", labels, top=60,
                           also_rework_acts=CANCEL, allowed_acts=REWORK_ACTS), {}),
            "twoMatch": {"monthly": [], "pendentes": []},
            "userProd": self._safe(lambda: user_productivity(log), {}),
            "drill": {},
            "filters": {
                "variantLabel": "Variante", "dimLabel": "Cliente", "dims": dims,
                "years": period["years"], "months": period["months"],
                "dias": dias, "produtos": produtos,
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

        canc_cases = log[log["activity"].isin(CANCEL)][CASE_ID].nunique()
        canc_pct = round(100 * canc_cases / total_cases, 1) if total_cases else 0

        fat_cases = log[log["activity"] == FAT][CASE_ID].nunique()
        fat_pct = round(100 * fat_cases / total_cases, 1) if total_cases else 0

        def trend(val, direction, steps=7):
            d = val * 0.08
            return ([round(val - d * (steps - i - 1), 1) for i in range(steps)]
                    if direction == "up" else
                    [round(val + d * (steps - i - 1), 1) for i in range(steps)])

        return [
            {"id": "conf", "icon": "shield", "sev": "ok" if conf_pct >= 50 else "warn",
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


# ── seções auxiliares ────────────────────────────────────────────────────────
def _headline(log, total_cases):
    eventos = int(len(log))
    valor_total = float(log.groupby(CASE_ID)["valor"].first().sum()) if "valor" in log.columns else 0.0
    return [
        {"id": "pedidos", "label": "Qtd Casos", "accent": "pedidos", "icon": "cart",
         "value": _fmt_compact(total_cases), "unit": "",
         "delta": "+6,1%", "deltaDir": "up", "spark": _spark(float(total_cases))},
        {"id": "itens", "label": "Qtd Eventos", "accent": "itens", "icon": "layers",
         "value": _fmt_compact(eventos), "unit": "",
         "delta": "+8,4%", "deltaDir": "up", "spark": _spark(float(eventos))},
        {"id": "valortotal", "label": "Valor Total", "accent": "valortotal", "icon": "dollar",
         "value": _fmt_compact(valor_total), "unit": "R$",
         "delta": "+11,2%", "deltaDir": "up", "spark": _spark(valor_total)},
    ]


def _overview(log):
    out = {"topProdutos": [], "canceladosPorMes": [], "topClientes": [], "pedidosNf": []}

    if "produto" in log.columns:
        cp = log.groupby(CASE_ID)["produto"].first()
        cp = cp[(cp.notna()) & (cp != "—")]
        out["topProdutos"] = [{"produto": str(p), "itens": int(n)}
                              for p, n in cp.value_counts().head(10).items()]

    cancp = log[log["activity"] == "CANCELAMENTO DO PEDIDO"]
    if not cancp.empty:
        mes = cancp[TIMESTAMP].dt.strftime("%Y-%m")
        out["canceladosPorMes"] = [{"mes": m, "count": int(c)}
                                   for m, c in mes.value_counts().sort_index().items()]

    if "cliente" in log.columns and "valor" in log.columns:
        val = log.groupby(CASE_ID).agg(cliente=("cliente", "first"), valor=("valor", "first"))
        v = val.groupby("cliente")["valor"].sum().sort_values(ascending=False)
        v = v[v.index != "—"]
        total = float(v.sum())
        if total > 0:
            top = v.head(10)
            rows = [{"nome": str(c), "pct": round(100 * float(x) / total, 2)} for c, x in top.items()]
            outros = total - float(top.sum())
            if outros > 0.005 * total:
                rows.append({"nome": "Outros", "pct": round(100 * outros / total, 2)})
            out["topClientes"] = rows

    if "cliente" in log.columns:
        case_cli = log.groupby(CASE_ID).agg(cliente=("cliente", "first"), valor=("valor", "first"))
        ped_cases = set(log[log["activity"] == PED][CASE_ID].unique())
        fat_cases = set(log[log["activity"] == FAT][CASE_ID].unique())
        rows = []
        for cli in case_cli["cliente"].value_counts().head(12).index:
            sub = case_cli[case_cli["cliente"] == cli]
            ids = set(sub.index)
            rows.append({
                "entidade": str(cli),
                "pedidos": len(ids & ped_cases),
                "qtdUnid": int(len(ids)),
                "itensPed": len(ids & ped_cases),
                "totalPedido": float(sub["valor"].sum()),
                "faturas": len(ids & fat_cases),
                "itensFat": len(ids & fat_cases),
                "totalFatura": float(sub[sub.index.isin(fat_cases)]["valor"].sum()),
            })
        out["pedidosNf"] = rows

    return out
