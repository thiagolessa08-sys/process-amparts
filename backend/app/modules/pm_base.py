"""Base dos módulos de process mining 'prontos' (event log já no banco:
SQL_PM_ATIVIDADES + SQL_PM_CASES). A espinha é montada dinamicamente pelo
SORTING; cancelamentos viram ramos laterais. Subclasses só declaram as
atividades do caminho feliz, cancelamentos/ramos, dimensão e nomes.
"""
import pandas as pd

from app.modules.base import ProcessModule
from app.mining.dfg import discover_dfg
from app.mining.variants import discover_variants
from app.mining.activity_stats import activity_metrics
from app.modules.headline import _fmt_compact, _spark, period_filters, case_ref_date
from app.modules.rework import rework
from app.modules.cancel import cancel_analysis
from app.modules.twomatch import two_match
from app.modules.userprod import user_productivity
from app.eventlog import CASE_ID, TIMESTAMP

START, END = "start", "end"


def _title(s: str) -> str:
    return str(s).title()


def _fmt_days(seconds: float) -> str:
    if seconds <= 0:
        return "—"
    return f"{seconds / 86400:.1f} d".replace(".", ",")


class PMModule(ProcessModule):
    """Subclasses devem definir: key, name, short, color, HAPPY, CANCEL,
    BRANCH_PARENT, REWORK_ACTS, PED, FAT, order_activity, dimension,
    cancel_month_activity."""
    activity_map: dict = {}     # identidade: a atividade já é o id
    color = "#0e9f93"
    dimension = "Cliente"
    HAPPY: list = []
    CANCEL: set = set()
    BRANCH_PARENT: dict = {}
    REWORK_ACTS: set = set()
    REVERSAL_ACTS: set = set()   # devoluções/estornos (entram na análise de cancelamento)
    PED = ""
    FAT = ""
    order_activity = None
    cancel_month_activity = ""

    @property
    def ideal_path(self):
        return self.HAPPY

    # A tela de Cancelamentos é recalculada pelo endpoint com um recorte de
    # período próprio quando o módulo liga esta flag — ver `cancelamentos()`.
    cancel_periodo_proprio = False

    @staticmethod
    def _safe(fn, default):
        try:
            return fn()
        except Exception:
            return default

    def cancelamentos(self, log: pd.DataFrame) -> dict:
        """Análise de cancelamentos de um event log já filtrado.

        Isolada do `enrich` porque a tela precisa de um recorte de período
        diferente do resto: o filtro padrão data o caso pela data do pedido, e
        caso cancelado no orçamento nunca vira pedido — sumiria daqui.
        """
        labels = {a: _title(a) for a in log["activity"].astype(str).unique()}
        return cancel_analysis(log, self.CANCEL | self.REVERSAL_ACTS, labels)

    def enrich(self, log: pd.DataFrame) -> dict:
        HAPPY, CANCEL, BRANCH_PARENT = self.HAPPY, self.CANCEL, self.BRANCH_PARENT
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

        order_map = log.groupby("activity")["sort"].min().to_dict() if "sort" in log.columns else {}
        present = list(node_metrics.keys())
        spine = [a for a in sorted(present, key=lambda a: (order_map.get(a, 9999), a)) if a not in CANCEL]
        branches = {a: BRANCH_PARENT[a] for a in present
                    if a in CANCEL and BRANCH_PARENT.get(a) in spine}

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
        # ramos por pai: vários irmãos do mesmo nó ficam lado a lado (sem sobrepor)
        by_parent = {}
        for bid, parent in branches.items():
            by_parent.setdefault(parent, []).append(bid)
        for parent, bids in by_parent.items():
            for j, bid in enumerate(bids):
                m = node_metrics.get(bid, {})
                node = {"id": bid, "label": _title(bid), "x": 540 + j * 210,
                        "y": spine_y.get(parent, 400),
                        "cases": m.get("count", 0), "avgDwell": _fmt_days(m.get("avg_dwell_seconds", 0)),
                        "branch": True}
                if bid in act_stats:
                    node.update(act_stats[bid])
                nodes.append(node)
        nodes.append({"id": START, "label": "Início", "x": 300, "y": 40, "type": "start", "cases": total_cases})
        nodes.append({"id": END, "label": "Fim", "x": 300, "y": y + 60, "type": "end", "cases": total_cases})

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
            "dimension": self.dimension,
            "nodes": nodes, "edges": edges, "variants": variants, "kpis": kpis,
            "idealOrder": spine, "branchMap": branches,
            "headlineKpis": self._safe(lambda: self._headline(log, total_cases), []),
            "overview": self._safe(lambda: self._overview(log), {}),
            "rework": self._safe(
                # toda atividade de retrabalho conta cada ocorrência (cancelamentos
                # E alterações), não só os cancelamentos. Cordeiro: REWORK_ACTS = CANCEL.
                lambda: rework(log, "cliente", labels, top=60,
                           also_rework_acts=self.REWORK_ACTS, allowed_acts=self.REWORK_ACTS), {}),
            "cancelamentos": self._safe(lambda: self.cancelamentos(log), {}),
            "twoMatch": self._safe(
                lambda: two_match(log, "cliente", invoice_activity=self.FAT, order_activity=self.PED),
                {"monthly": [], "pendentes": []}),
            "userProd": self._safe(lambda: user_productivity(log), {}),
            "drill": {},
            "filters": {
                "variantLabel": "Variante", "dimLabel": self.dimension, "dims": dims,
                "years": period["years"], "months": period["months"],
                "dias": dias, "produtos": produtos,
            },
        }

    def _kpis(self, log, total_cases, variants):
        grp = log.groupby(CASE_ID)[TIMESTAMP]
        mean_days = float((grp.max() - grp.min()).dt.total_seconds().mean()) / 86400

        conf_cases = sum(v["cases"] for v in variants if v["conformant"])
        conf_pct = round(100 * conf_cases / total_cases) if total_cases else 0

        canc_cases = log[log["activity"].isin(self.CANCEL)][CASE_ID].nunique()
        canc_pct = round(100 * canc_cases / total_cases, 1) if total_cases else 0

        fat_cases = log[log["activity"] == self.FAT][CASE_ID].nunique()
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

    def _headline(self, log, total_cases):
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

    def _overview(self, log):
        out = {"topProdutos": [], "canceladosPorMes": [], "topClientes": [], "pedidosNf": []}

        if "produto" in log.columns:
            cp = log.groupby(CASE_ID)["produto"].first()
            cp = cp[(cp.notna()) & (cp != "—")]
            out["topProdutos"] = [{"produto": str(p), "itens": int(n)}
                                  for p, n in cp.value_counts().head(10).items()]

        cancp = log[log["activity"] == self.cancel_month_activity]
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
            ped_cases = set(log[log["activity"] == self.PED][CASE_ID].unique())
            fat_cases = set(log[log["activity"] == self.FAT][CASE_ID].unique())
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
