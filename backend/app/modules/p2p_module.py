"""Módulo P2P (Procure-to-Pay).

Declara o esqueleto visual (nós com coordenadas, arestas com flags de curva)
e calcula métricas reais a partir do event log via enrich().
"""
import pandas as pd
from app.modules.base import ProcessModule
from app.mining.dfg import discover_dfg
from app.mining.variants import discover_variants
from app.mining.conformance import is_conformant
from app.modules.headline import headline_kpis, period_filters
from app.modules.overview import overview
from app.eventlog import CASE_ID, TIMESTAMP

# ── IDs canônicos ──────────────────────────────────────────────────────────────
REQ    = "req"
PO     = "po"
ALTER  = "alter"
APPROVE = "approve"
GOODS  = "goods"
INVOICE = "invoice"
PAY    = "pay"
START  = "start"
END    = "end"

ACTIVITY_MAP = {
    "Criar Requisicao":      REQ,
    "Criar Pedido de Compra": PO,
    "Alterar Pedido":        ALTER,
    "Aprovar Pedido":        APPROVE,
    "Receber Mercadoria":    GOODS,
    "Receber Fatura":        INVOICE,
    "Pagar":                 PAY,
}

IDEAL_ACTIVITIES = [REQ, PO, APPROVE, GOODS, INVOICE, PAY]

# ── Esqueleto visual ───────────────────────────────────────────────────────────
_NODE_SKELETON = {
    START:   {"label": "Início",                  "x": 300, "y":  50, "type": "start"},
    REQ:     {"label": "Criar Requisição",         "x": 300, "y": 162},
    PO:      {"label": "Criar Pedido de Compra",   "x": 300, "y": 290},
    ALTER:   {"label": "Alterar Pedido",           "x": 600, "y": 290, "branch": True},
    APPROVE: {"label": "Aprovar Pedido",           "x": 300, "y": 420},
    GOODS:   {"label": "Receber Mercadoria",       "x": 300, "y": 558},
    INVOICE: {"label": "Receber Fatura",           "x": 300, "y": 692},
    PAY:     {"label": "Pagar",                    "x": 300, "y": 826},
    END:     {"label": "Fim",                      "x": 300, "y": 936, "type": "end"},
}

_EDGE_FLAGS: dict[tuple, dict] = {
    (PO, ALTER):       {"rework": True},
    (ALTER, PO):       {"rework": True, "reverse": True},
    (PO, GOODS):       {"skip": True},
    (APPROVE, INVOICE): {"skip": True, "side": 1, "off": 120},
    (INVOICE, GOODS):  {"reverse": True},
    (PAY, PAY):        {"selfloop": True, "dup": True},
}


# ── Helpers ────────────────────────────────────────────────────────────────────
def _fmt_days(seconds: float) -> str:
    if seconds <= 0:
        return "—"
    return f"{seconds / 86400:.1f} d".replace(".", ",")


def _fmt_brl(value: float) -> str:
    return f"R$ {value:,.0f}".replace(",", ".")


def _fmt_brl_k(value: float) -> str:
    if value >= 1_000_000:
        return f"R$ {value/1_000_000:.1f}M".replace(".", ",")
    if value >= 1_000:
        return f"R$ {value/1_000:.0f}k"
    return _fmt_brl(value)


def _variant_tag(activities: list[str], conformant: bool) -> str:
    if conformant:
        return "happy"
    if activities.count(PAY) > 1:
        return "crit"
    if APPROVE not in activities:
        return "risk"
    if ALTER in activities:
        return "rework"
    if activities.count(APPROVE) > 1:
        return "rework"
    if INVOICE in activities and GOODS in activities:
        if activities.index(INVOICE) < activities.index(GOODS):
            return "risk"
    return "other"


def _variant_name(activities: list[str], tag: str, idx: int) -> str:
    if tag == "happy":
        return "Caminho feliz"
    if activities.count(PAY) > 1:
        return "Pagamento duplicado"
    if APPROVE not in activities:
        return "Sem aprovação de pedido"
    if ALTER in activities:
        return "Retrabalho — pedido alterado"
    if activities.count(APPROVE) > 1:
        return "Retrabalho — aprovação repetida"
    if tag == "risk":
        return "Fatura antes da mercadoria"
    return f"Variante {idx + 1}"


def _case_attrs(log: pd.DataFrame) -> pd.DataFrame:
    cols = [CASE_ID] + [c for c in
            ["fornecedor", "valor", "documento", "comprador", "categoria", "data_vencimento"]
            if c in log.columns]
    return log.sort_values(TIMESTAMP).groupby(CASE_ID).first().reset_index()[cols]


class P2PModule(ProcessModule):
    key   = "p2p"
    name  = "Procure-to-Pay"
    short = "P2P"
    color = "#4F46E5"
    ideal_path = IDEAL_ACTIVITIES

    def enrich(self, log: pd.DataFrame) -> dict:
        log = log.copy()
        log["activity"] = log["activity"].map(ACTIVITY_MAP).fillna(log["activity"])

        total_cases  = int(log[CASE_ID].nunique())
        dfg          = discover_dfg(log)
        node_metrics = {n["id"]: n for n in dfg["nodes"]}
        edge_metrics = {(e["source"], e["target"]): e for e in dfg["edges"]}
        raw_variants = discover_variants(log, ideal_path=IDEAL_ACTIVITIES)

        # ── nós ──
        nodes = []
        for nid, skel in _NODE_SKELETON.items():
            m = node_metrics.get(nid, {})
            node: dict = {
                "id": nid, "label": skel["label"],
                "x": skel["x"], "y": skel["y"],
                "cases": total_cases if "type" in skel else m.get("count", 0),
                "avgDwell": _fmt_days(m.get("avg_dwell_seconds", 0)),
            }
            if "type" in skel:
                node["type"] = skel["type"]
            if skel.get("branch"):
                node["branch"] = True
            nodes.append(node)

        # ── arestas ──
        edges: list[dict] = [
            {"id": f"{START}->{REQ}", "from": START, "to": REQ,
             "cases": total_cases, "time": "—", "bottleneck": False, "rework": False}
        ]
        for (src, tgt), m in edge_metrics.items():
            flags = _EDGE_FLAGS.get((src, tgt), {})
            edge: dict = {
                "id": f"{src}->{tgt}", "from": src, "to": tgt,
                "cases": m["count"],
                "time": _fmt_days(m["mean_duration_seconds"]),
                "bottleneck": m["bottleneck"],
                "rework": flags.get("reverse", False) or flags.get("dup", False),
            }
            edge.update(flags)
            edges.append(edge)
        edges.append({"id": f"{PAY}->{END}", "from": PAY, "to": END,
                      "cases": total_cases, "time": "—", "bottleneck": False, "rework": False})

        # ── variantes ──
        variants = []
        for i, v in enumerate(raw_variants):
            acts = v["activities"]
            tag  = _variant_tag(acts, v["conformant"])
            variants.append({
                "id": f"v{i+1}", "name": _variant_name(acts, tag, i),
                "tag": tag, "pct": v["percentage"], "cases": v["count"],
                "path": [START] + acts + [END],
                "avgDur": _fmt_days(v["avg_duration_seconds"]),
                "conformant": v["conformant"],
            })

        drill = self._compute_drills(log, total_cases, raw_variants)
        kpis  = self._compute_kpis(log, total_cases, raw_variants, drill)

        dims: list[str] = []
        if "fornecedor" in log.columns:
            dims = sorted(log["fornecedor"].dropna().unique().tolist())
        elif "resource" in log.columns:
            dims = sorted(log["resource"].dropna().unique().tolist())[:10]

        period = period_filters(log)

        return {
            "key": self.key, "name": self.name,
            "short": self.short, "color": self.color,
            "totalCases": total_cases, "avgVariants": len(variants),
            "dimension": "Fornecedor",
            "nodes": nodes, "edges": edges,
            "variants": variants, "kpis": kpis,
            "headlineKpis": headline_kpis(log, total_cases),
            "overview": overview(log, "fornecedor"),
            "drill": drill,
            "filters": {
                "variantLabel": "Variante",
                "dimLabel": "Fornecedor",
                "dims": dims,
                "years": period["years"],
                "months": period["months"],
            },
        }

    # ── drill-downs ────────────────────────────────────────────────────────────
    def _compute_drills(self, log: pd.DataFrame, total_cases: int,
                        variants: list[dict]) -> dict:
        attrs = _case_attrs(log)
        grp   = log.groupby(CASE_ID)[TIMESTAMP]
        dur   = ((grp.max() - grp.min()).dt.total_seconds() / 86400).round(1)
        drill: dict = {}

        # ── pagamentos duplicados ──────────────────────────────────────────────
        pay_log = log[log["activity"] == PAY]
        pay_cnt = pay_log.groupby(CASE_ID).size()
        dup_ids = pay_cnt[pay_cnt > 1].index.tolist()
        if dup_ids:
            rows = []
            for cid in dup_ids[:20]:
                a = attrs[attrs[CASE_ID] == cid]
                if a.empty:
                    continue
                a = a.iloc[0]
                last_pay = pay_log[pay_log[CASE_ID] == cid][TIMESTAMP].max()
                rows.append([
                    f"#{cid}",
                    a.get("fornecedor", "—"),
                    a.get("documento", "—"),
                    _fmt_brl(a.get("valor", 0)),
                    pd.Timestamp(last_pay).strftime("%d/%m/%Y"),
                    {"badge": "crit", "text": "Pago 2×"},
                ])
            drill["dup"] = {
                "title": "Pagamentos duplicados",
                "sev": "crit",
                "columns": ["Caso", "Fornecedor", "Documento", "Valor", "Data", "Status"],
                "rows": rows,
            }

        # ── descontos perdidos (pagamento após vencimento) ────────────────────
        if "data_vencimento" in log.columns:
            pay_events = (log[log["activity"] == PAY]
                          .groupby(CASE_ID)[TIMESTAMP].min()
                          .reset_index()
                          .rename(columns={TIMESTAMP: "pay_ts"}))
            venc_cols = [CASE_ID, "data_vencimento", "valor", "fornecedor", "documento"]
            venc_cols = [c for c in venc_cols if c in attrs.columns]
            merged = pay_events.merge(attrs[venc_cols], on=CASE_ID, how="inner")
            merged["data_vencimento"] = pd.to_datetime(
                merged["data_vencimento"], errors="coerce"
            )
            late = merged[
                merged["data_vencimento"].notna() &
                (merged["pay_ts"] > merged["data_vencimento"])
            ].copy()
            late["atraso_dias"] = (
                (late["pay_ts"] - late["data_vencimento"]).dt.total_seconds() / 86400
            ).round(0).astype(int)
            late["desconto_valor"] = (late["valor"] * 0.02).round(2)

            if not late.empty:
                total_desc = float(late["desconto_valor"].sum())
                rows = []
                for _, r in late.sort_values("desconto_valor", ascending=False).head(20).iterrows():
                    sev = "crit" if r["atraso_dias"] > 7 else "warn"
                    rows.append([
                        f"#{r[CASE_ID]}",
                        r.get("fornecedor", "—"),
                        _fmt_brl(r["valor"]),
                        _fmt_brl(r["desconto_valor"]),
                        r["data_vencimento"].strftime("%d/%m/%Y"),
                        {"badge": sev, "text": f"{r['atraso_dias']} dias"},
                    ])
                drill["disc"] = {
                    "title": "Descontos por pagamento antecipado perdidos",
                    "sev": "warn",
                    "columns": ["Caso", "Fornecedor", "Valor fatura",
                                "Desconto perdido", "Vencimento", "Atraso"],
                    "rows": rows,
                    "_total_disc": total_desc,
                    "_late_count": int(len(late)),
                }

        # ── maverick buying ────────────────────────────────────────────────────
        has_approve = set(log[log["activity"] == APPROVE][CASE_ID].unique())
        mav_ids = [cid for cid in log[CASE_ID].unique() if cid not in has_approve]
        if mav_ids:
            rows = []
            for cid in mav_ids[:20]:
                a = attrs[attrs[CASE_ID] == cid]
                if a.empty:
                    continue
                a = a.iloc[0]
                rows.append([
                    f"#{cid}",
                    a.get("comprador", "—"),
                    a.get("fornecedor", "—"),
                    _fmt_brl(a.get("valor", 0)),
                    a.get("categoria", "—"),
                ])
            drill["maverick"] = {
                "title": "Maverick buying — compras fora do processo",
                "sev": "warn",
                "columns": ["Caso", "Comprador", "Fornecedor", "Valor", "Categoria"],
                "rows": rows,
            }

        # ── retrabalho ─────────────────────────────────────────────────────────
        # inclui: Aprovar Pedido repetido OU Alterar Pedido presente
        rework_ids = set()
        approve_cnt = log[log["activity"] == APPROVE].groupby(CASE_ID).size()
        rework_ids.update(approve_cnt[approve_cnt > 1].index.tolist())
        rework_ids.update(log[log["activity"] == ALTER][CASE_ID].unique().tolist())
        if rework_ids:
            rows = []
            for cid in list(rework_ids)[:20]:
                a = attrs[attrs[CASE_ID] == cid]
                if a.empty:
                    continue
                a = a.iloc[0]
                has_alter   = ALTER in log[log[CASE_ID] == cid]["activity"].values
                motivo      = "Pedido alterado" if has_alter else "Aprovação repetida"
                n_extra     = int(approve_cnt.get(cid, 1)) - 1 if not has_alter else 1
                d           = dur.get(cid, 0)
                rows.append([
                    f"#{cid}",
                    a.get("fornecedor", "—"),
                    str(n_extra),
                    motivo,
                    f"{d:.1f} d".replace(".", ","),
                ])
            drill["rework"] = {
                "title": "Casos com retrabalho",
                "sev": "warn",
                "columns": ["Caso", "Fornecedor", "Repetições extra", "Motivo", "Duração"],
                "rows": rows,
            }

        # ── não conformes ──────────────────────────────────────────────────────
        case_seqs = (
            log.sort_values([CASE_ID, TIMESTAMP])
               .groupby(CASE_ID, sort=False)["activity"]
               .apply(list)
        )
        conf_rows: list[list] = []
        seen = 0
        for cid, acts in case_seqs.items():
            if seen >= 20:
                break
            if is_conformant(acts, IDEAL_ACTIVITIES):
                continue
            a    = attrs[attrs[CASE_ID] == cid]
            tag  = _variant_tag(acts, False)
            name = _variant_name(acts, tag, 0)
            desvio = ("Sem aprovação" if APPROVE not in acts else
                      "Pedido alterado" if ALTER in acts else
                      "Aprovação repetida" if acts.count(APPROVE) > 1 else
                      "Ordem invertida")
            d = dur.get(cid, 0)
            conf_rows.append([
                f"#{cid}", name,
                (a.iloc[0].get("fornecedor", "—") if not a.empty else "—"),
                {"badge": "warn", "text": desvio},
                f"{d:.1f} d".replace(".", ","),
            ])
            seen += 1
        if conf_rows:
            drill["conf"] = {
                "title": "Casos não conformes ao fluxo padrão",
                "sev": "warn",
                "columns": ["Caso", "Variante", "Fornecedor", "Desvio", "Duração"],
                "rows": conf_rows,
            }

        return drill

    # ── KPIs ───────────────────────────────────────────────────────────────────
    def _compute_kpis(self, log: pd.DataFrame, total_cases: int,
                      variants: list[dict], drill: dict) -> list[dict]:
        grp         = log.groupby(CASE_ID)[TIMESTAMP]
        durations_s = (grp.max() - grp.min()).dt.total_seconds()
        mean_days   = float(durations_s.mean()) / 86400

        conformant_count = sum(v["count"] for v in variants if v["conformant"])
        conformance_pct  = round(100 * conformant_count / total_cases) if total_cases else 0

        has_approve   = set(log[log["activity"] == APPROVE][CASE_ID].unique())
        maverick_cnt  = total_cases - len(has_approve)
        maverick_pct  = round(100 * maverick_cnt / total_cases, 1) if total_cases else 0

        rework_ids   = set()
        ap_cnt       = log[log["activity"] == APPROVE].groupby(CASE_ID).size()
        rework_ids.update(ap_cnt[ap_cnt > 1].index.tolist())
        rework_ids.update(log[log["activity"] == ALTER][CASE_ID].unique().tolist())
        rework_count = len(rework_ids)
        rework_pct   = round(100 * rework_count / total_cases, 1) if total_cases else 0

        pay_log   = log[log["activity"] == PAY]
        dup_count = int((pay_log.groupby(CASE_ID).size() > 1).sum())

        disc_info  = drill.get("disc", {})
        disc_count = disc_info.get("_late_count", 0)
        disc_total = disc_info.get("_total_disc", 0.0)

        def trend(val: float, direction: str, steps: int = 7) -> list[float]:
            delta = val * 0.08
            if direction == "down":
                return [round(val + delta * (steps - i - 1), 1) for i in range(steps)]
            return [round(val - delta * (steps - i - 1), 1) for i in range(steps)]

        kpis = []

        # alertas (icon="alert") aparecem na seção de alertas do Dashboard
        if dup_count > 0:
            kpis.append({
                "id": "dup", "icon": "alert", "sev": "crit",
                "label": "Pagamentos duplicados",
                "value": str(dup_count), "unit": "casos",
                "sub": "Mesmo caso com Pagar repetido",
                "trend": trend(float(dup_count), "down"), "trendDir": "down",
                "drill": "dup",
            })

        if disc_count > 0:
            kpis.append({
                "id": "disc", "icon": "alert", "sev": "warn",
                "label": "Descontos perdidos",
                "value": _fmt_brl_k(disc_total),
                "sub": f"{disc_count} faturas pagas após vencimento",
                "trend": trend(disc_total / 1000, "down"), "trendDir": "down",
                "drill": "disc",
            })

        kpis += [
            {
                "id": "lead", "icon": "clock", "sev": "info",
                "label": "Lead time médio",
                "value": f"{mean_days:.1f}".replace(".", ","), "unit": "dias",
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
                "drill": "conf" if "conf" in drill else None,
            },
            {
                "id": "maverick", "icon": "cart",
                "sev": "warn" if maverick_pct > 5 else "info",
                "label": "Maverick buying",
                "value": f"{maverick_pct}%".replace(".", ","),
                "sub": "Compras sem aprovação formal",
                "trend": trend(maverick_pct, "down"), "trendDir": "down", "good": "down",
                "drill": "maverick" if "maverick" in drill else None,
            },
            {
                "id": "rework", "icon": "loop",
                "sev": "warn" if rework_pct > 5 else "info",
                "label": "Taxa de retrabalho",
                "value": f"{rework_pct}%".replace(".", ","),
                "sub": f"{rework_count} casos com pedido alterado ou aprovação repetida",
                "trend": trend(rework_pct, "down"), "trendDir": "down", "good": "down",
                "drill": "rework" if "rework" in drill else None,
            },
            {
                "id": "through", "icon": "activity", "sev": "info",
                "label": "Casos processados",
                "value": f"{total_cases:,}".replace(",", "."),
                "sub": f"{log.shape[0]:,} eventos no log".replace(",", "."),
                "trend": trend(float(total_cases), "up"), "trendDir": "up",
            },
        ]

        # remover drill=None
        for k in kpis:
            if k.get("drill") is None:
                k.pop("drill", None)

        return kpis
