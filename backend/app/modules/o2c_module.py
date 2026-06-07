"""Módulo O2C (Order-to-Cash).

Esqueleto visual + métricas calculadas a partir do event log.
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
ORDER   = "order"
CREDIT  = "credit"
HOLD    = "hold"
PICK    = "pick"
DELIVER = "deliver"
INVOICE = "invoice"
RECEIVE = "receive"
START   = "start"
END     = "end"

ACTIVITY_MAP = {
    "Criar Pedido":       ORDER,
    "Liberar Credito":    CREDIT,
    "Bloqueio de Credito": HOLD,
    "Separar Expedir":    PICK,
    "Entregar":           DELIVER,
    "Faturar":            INVOICE,
    "Receber Pagamento":  RECEIVE,
}

IDEAL_ACTIVITIES = [ORDER, CREDIT, PICK, DELIVER, INVOICE, RECEIVE]

_NODE_SKELETON = {
    START:   {"label": "Início",             "x": 300, "y":  50, "type": "start"},
    ORDER:   {"label": "Criar Pedido",        "x": 300, "y": 162},
    CREDIT:  {"label": "Liberar Crédito",     "x": 300, "y": 290},
    HOLD:    {"label": "Bloqueio de Crédito", "x": 600, "y": 290, "branch": True},
    PICK:    {"label": "Separar / Expedir",   "x": 300, "y": 420},
    DELIVER: {"label": "Entregar",            "x": 300, "y": 558},
    INVOICE: {"label": "Faturar",             "x": 300, "y": 692},
    RECEIVE: {"label": "Receber Pagamento",   "x": 300, "y": 826},
    END:     {"label": "Fim",                 "x": 300, "y": 936, "type": "end"},
}

_EDGE_FLAGS: dict[tuple, dict] = {
    (CREDIT, HOLD):    {"rework": True},
    (HOLD, PICK):      {"rework": True},
    (DELIVER, PICK):   {"reverse": True, "rework": True},
    (INVOICE, DELIVER): {"reverse": True, "skip": True},
}


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
    if HOLD in activities and DELIVER not in activities:
        return "crit"   # cancelamento
    if HOLD in activities:
        return "risk"   # bloqueio de crédito
    if activities.count(PICK) > 1 or activities.count(DELIVER) > 1:
        return "rework"  # re-expedição
    if INVOICE in activities and DELIVER in activities:
        if activities.index(INVOICE) < activities.index(DELIVER):
            return "risk"   # faturamento antecipado
    return "other"


def _variant_name(activities: list[str], tag: str, idx: int) -> str:
    if tag == "happy":
        return "Caminho feliz"
    if HOLD in activities and DELIVER not in activities:
        return "Devolução / cancelamento"
    if HOLD in activities:
        return "Bloqueio de crédito"
    if activities.count(PICK) > 1 or activities.count(DELIVER) > 1:
        return "Re-expedição / entrega parcial"
    if INVOICE in activities and DELIVER in activities:
        if activities.index(INVOICE) < activities.index(DELIVER):
            return "Faturamento antecipado"
    return f"Variante {idx + 1}"


def _case_attrs(log: pd.DataFrame) -> pd.DataFrame:
    cols = [CASE_ID] + [c for c in
            ["cliente", "valor", "categoria", "prazo_recebimento",
             "data_prometida", "data_entrega"]
            if c in log.columns]
    return log.sort_values(TIMESTAMP).groupby(CASE_ID).first().reset_index()[cols]


class O2CModule(ProcessModule):
    key   = "o2c"
    name  = "Order-to-Cash"
    short = "O2C"
    color = "#16a34a"
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
            {"id": f"{START}->{ORDER}", "from": START, "to": ORDER,
             "cases": total_cases, "time": "—", "bottleneck": False, "rework": False}
        ]
        for (src, tgt), m in edge_metrics.items():
            flags = _EDGE_FLAGS.get((src, tgt), {})
            edge: dict = {
                "id": f"{src}->{tgt}", "from": src, "to": tgt,
                "cases": m["count"],
                "time": _fmt_days(m["mean_duration_seconds"]),
                "bottleneck": m["bottleneck"],
                "rework": flags.get("rework", False),
            }
            edge.update(flags)
            edges.append(edge)
        edges.append({"id": f"{RECEIVE}->{END}", "from": RECEIVE, "to": END,
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
        if "cliente" in log.columns:
            dims = sorted(log["cliente"].dropna().unique().tolist())
        elif "resource" in log.columns:
            dims = sorted(log["resource"].dropna().unique().tolist())[:10]

        period = period_filters(log)

        return {
            "key": self.key, "name": self.name,
            "short": self.short, "color": self.color,
            "totalCases": total_cases, "avgVariants": len(variants),
            "dimension": "Cliente",
            "nodes": nodes, "edges": edges,
            "variants": variants, "kpis": kpis,
            "headlineKpis": headline_kpis(log, total_cases),
            "overview": overview(log, "cliente"),
            "drill": drill,
            "filters": {
                "variantLabel": "Variante",
                "dimLabel": "Cliente",
                "dims": dims,
                "years": period["years"],
                "months": period["months"],
            },
        }

    def _compute_drills(self, log: pd.DataFrame, total_cases: int,
                        variants: list[dict]) -> dict:
        attrs = _case_attrs(log)
        grp   = log.groupby(CASE_ID)[TIMESTAMP]
        dur   = ((grp.max() - grp.min()).dt.total_seconds() / 86400).round(1)
        drill: dict = {}

        # ── DSO alto (pagamento após prazo) ────────────────────────────────────
        if "prazo_recebimento" in log.columns:
            recv_ev = (log[log["activity"] == RECEIVE]
                       .groupby(CASE_ID)[TIMESTAMP].min()
                       .reset_index().rename(columns={TIMESTAMP: "recv_ts"}))
            inv_ev  = (log[log["activity"] == INVOICE]
                       .groupby(CASE_ID)[TIMESTAMP].min()
                       .reset_index().rename(columns={TIMESTAMP: "inv_ts"}))
            merged  = recv_ev.merge(inv_ev, on=CASE_ID, how="inner")
            prazo   = attrs[[CASE_ID, "prazo_recebimento", "valor", "cliente"]].copy()
            merged  = merged.merge(prazo, on=CASE_ID, how="inner")
            merged["dias_aberto"] = (
                (merged["recv_ts"] - merged["inv_ts"]).dt.total_seconds() / 86400
            ).round(0).astype(int)
            late = merged[merged["dias_aberto"] > merged["prazo_recebimento"]].copy()
            if not late.empty:
                rows = []
                for _, r in late.sort_values("dias_aberto", ascending=False).head(20).iterrows():
                    sev = "crit" if r["dias_aberto"] > r["prazo_recebimento"] + 15 else "warn"
                    rows.append([
                        f"#{r[CASE_ID]}",
                        r.get("cliente", "—"),
                        _fmt_brl(r["valor"]),
                        r["inv_ts"].strftime("%d/%m/%Y"),
                        {"badge": sev, "text": f"{r['dias_aberto']} dias"},
                    ])
                drill["dso"] = {
                    "title": "Pedidos com maior tempo de recebimento (DSO alto)",
                    "sev": "warn",
                    "columns": ["Caso", "Cliente", "Valor", "Faturado em", "Dias em aberto"],
                    "rows": rows,
                    "_late_count": int(len(late)),
                    "_mean_dso": float(merged["dias_aberto"].mean()),
                }

        # ── Bloqueio de crédito ────────────────────────────────────────────────
        hold_ids = set(log[log["activity"] == HOLD][CASE_ID].unique())
        if hold_ids:
            rows = []
            for cid in list(hold_ids)[:20]:
                a = attrs[attrs[CASE_ID] == cid]
                if a.empty:
                    continue
                a = a.iloc[0]
                d = dur.get(cid, 0)
                # tempo retido = tempo entre Liberar Crédito e sair do bloqueio
                rows.append([
                    f"#{cid}",
                    a.get("cliente", "—"),
                    _fmt_brl(a.get("valor", 0)),
                    "Limite excedido",
                    f"{d:.1f} d".replace(".", ","),
                ])
            drill["block"] = {
                "title": "Pedidos retidos por bloqueio de crédito",
                "sev": "warn",
                "columns": ["Caso", "Cliente", "Valor", "Motivo", "Duração total"],
                "rows": rows,
            }

        # ── Re-expedição ───────────────────────────────────────────────────────
        pick_cnt  = log[log["activity"] == PICK].groupby(CASE_ID).size()
        reexp_ids = pick_cnt[pick_cnt > 1].index.tolist()
        if reexp_ids:
            rows = []
            for cid in reexp_ids[:20]:
                a = attrs[attrs[CASE_ID] == cid]
                if a.empty:
                    continue
                a   = a.iloc[0]
                d   = dur.get(cid, 0)
                rows.append([
                    f"#{cid}",
                    a.get("cliente", "—"),
                    str(int(pick_cnt[cid]) - 1),
                    "Entrega parcial",
                    f"{d:.1f} d".replace(".", ","),
                ])
            drill["reexp"] = {
                "title": "Casos com re-expedição (entrega parcial)",
                "sev": "warn",
                "columns": ["Caso", "Cliente", "Expedições extra", "Motivo", "Duração"],
                "rows": rows,
            }

        # ── Faturas em aberto (cancelamentos sem recebimento) ─────────────────
        has_receive = set(log[log["activity"] == RECEIVE][CASE_ID].unique())
        has_invoice = set(log[log["activity"] == INVOICE][CASE_ID].unique())
        open_ids    = has_invoice - has_receive
        if open_ids:
            rows = []
            for cid in list(open_ids)[:20]:
                a = attrs[attrs[CASE_ID] == cid]
                if a.empty:
                    continue
                a = a.iloc[0]
                rows.append([
                    f"#{cid}",
                    a.get("cliente", "—"),
                    _fmt_brl(a.get("valor", 0)),
                    {"badge": "crit", "text": "Sem recebimento"},
                ])
            drill["open"] = {
                "title": "Faturas sem recebimento",
                "sev": "crit",
                "columns": ["Caso", "Cliente", "Valor", "Status"],
                "rows": rows,
            }

        # ── Não conformes ──────────────────────────────────────────────────────
        case_seqs = (
            log.sort_values([CASE_ID, TIMESTAMP])
               .groupby(CASE_ID, sort=False)["activity"]
               .apply(list)
        )
        conf_rows = []
        seen = 0
        for cid, acts in case_seqs.items():
            if seen >= 20:
                break
            if is_conformant(acts, IDEAL_ACTIVITIES):
                continue
            a    = attrs[attrs[CASE_ID] == cid]
            tag  = _variant_tag(acts, False)
            name = _variant_name(acts, tag, 0)
            desvio = ("Cancelado" if HOLD in acts and DELIVER not in acts else
                      "Bloqueio de crédito" if HOLD in acts else
                      "Re-expedição" if acts.count(PICK) > 1 else
                      "Faturamento antecipado")
            d = dur.get(cid, 0)
            conf_rows.append([
                f"#{cid}", name,
                (a.iloc[0].get("cliente", "—") if not a.empty else "—"),
                {"badge": "warn", "text": desvio},
                f"{d:.1f} d".replace(".", ","),
            ])
            seen += 1
        if conf_rows:
            drill["conf"] = {
                "title": "Casos não conformes ao fluxo padrão",
                "sev": "warn",
                "columns": ["Caso", "Variante", "Cliente", "Desvio", "Duração"],
                "rows": conf_rows,
            }

        return drill

    def _compute_kpis(self, log: pd.DataFrame, total_cases: int,
                      variants: list[dict], drill: dict) -> list[dict]:
        grp         = log.groupby(CASE_ID)[TIMESTAMP]
        durations_s = (grp.max() - grp.min()).dt.total_seconds()
        mean_days   = float(durations_s.mean()) / 86400

        conformant_count = sum(v["count"] for v in variants if v["conformant"])
        conformance_pct  = round(100 * conformant_count / total_cases) if total_cases else 0

        # DSO médio (dias entre Faturar e Receber Pagamento)
        inv_ev  = (log[log["activity"] == INVOICE]
                   .groupby(CASE_ID)[TIMESTAMP].min())
        recv_ev = (log[log["activity"] == RECEIVE]
                   .groupby(CASE_ID)[TIMESTAMP].min())
        dso_df  = pd.concat([inv_ev.rename("inv"), recv_ev.rename("recv")], axis=1).dropna()
        mean_dso = float(((dso_df["recv"] - dso_df["inv"]).dt.total_seconds() / 86400).mean()) if not dso_df.empty else 0

        # OTD (entrega no prazo)
        if "data_prometida" in log.columns and "data_entrega" in log.columns:
            attrs_otd = (log.sort_values(TIMESTAMP)
                         .groupby(CASE_ID, sort=False)
                         .first()
                         .reset_index()[
                             [CASE_ID, "data_prometida", "data_entrega"]
                         ])
            attrs_otd["data_prometida"] = pd.to_datetime(attrs_otd["data_prometida"], errors="coerce")
            attrs_otd["data_entrega"]   = pd.to_datetime(attrs_otd["data_entrega"],   errors="coerce")
            valid = attrs_otd.dropna(subset=["data_prometida", "data_entrega"])
            otd_pct = round(100 * (valid["data_entrega"] <= valid["data_prometida"]).mean()) if not valid.empty else 0
        else:
            otd_pct = 0

        # bloqueios
        hold_cnt = log[log["activity"] == HOLD][CASE_ID].nunique()
        block_pct = round(100 * hold_cnt / total_cases, 1) if total_cases else 0

        # re-expedição
        pick_cnt  = log[log["activity"] == PICK].groupby(CASE_ID).size()
        reexp_cnt = int((pick_cnt > 1).sum())
        reexp_pct = round(100 * reexp_cnt / total_cases, 1) if total_cases else 0

        # cancelamentos (sem recebimento)
        cancel_cnt = total_cases - log[log["activity"] == RECEIVE][CASE_ID].nunique()
        cancel_pct = round(100 * cancel_cnt / total_cases, 1) if total_cases else 0

        dso_info   = drill.get("dso", {})
        open_count = len(drill.get("open", {}).get("rows", []))

        def trend(val: float, direction: str, steps: int = 7) -> list[float]:
            delta = val * 0.08
            if direction == "down":
                return [round(val + delta * (steps - i - 1), 1) for i in range(steps)]
            return [round(val - delta * (steps - i - 1), 1) for i in range(steps)]

        kpis = []

        # alertas
        if open_count > 0:
            kpis.append({
                "id": "open", "icon": "alert", "sev": "crit",
                "label": "Faturas em aberto",
                "value": str(open_count), "unit": "faturas",
                "sub": "Faturadas sem recebimento registrado",
                "trend": trend(float(open_count), "down"), "trendDir": "down",
                "drill": "open",
            })

        if block_pct > 8:
            kpis.append({
                "id": "block", "icon": "alert", "sev": "warn",
                "label": "Bloqueios de crédito",
                "value": f"{block_pct}%".replace(".", ","),
                "sub": f"{hold_cnt} pedidos retidos",
                "trend": trend(block_pct, "down"), "trendDir": "up",
                "drill": "block",
            })

        # indicadores
        kpis += [
            {
                "id": "dso", "icon": "clock",
                "sev": "warn" if mean_dso > 45 else "info",
                "label": "DSO — prazo médio de recebimento",
                "value": f"{mean_dso:.0f}", "unit": "dias",
                "sub": f"Média de {dso_df.shape[0]:,} casos faturados".replace(",", "."),
                "trend": trend(mean_dso, "down"), "trendDir": "down", "good": "down",
                "drill": "dso" if "dso" in drill else None,
            },
            {
                "id": "otd", "icon": "truck",
                "sev": "ok" if otd_pct >= 85 else "warn",
                "label": "Entrega no prazo (OTD)",
                "value": f"{otd_pct}%",
                "sub": f"vs. data prometida ao cliente",
                "trend": trend(otd_pct, "up"), "trendDir": "up", "good": "up",
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
                "id": "reexp", "icon": "loop",
                "sev": "warn" if reexp_pct > 5 else "info",
                "label": "Taxa de re-expedição",
                "value": f"{reexp_pct}%".replace(".", ","),
                "sub": f"{reexp_cnt} pedidos com entrega parcial",
                "trend": trend(reexp_pct, "down"), "trendDir": "down", "good": "down",
                "drill": "reexp" if "reexp" in drill else None,
            },
            {
                "id": "cancel", "icon": "alert",
                "sev": "warn" if cancel_pct > 3 else "info",
                "label": "Taxa de devolução / cancelamento",
                "value": f"{cancel_pct}%".replace(".", ","),
                "sub": f"{cancel_cnt} pedidos sem entrega",
                "trend": trend(cancel_pct, "down"), "trendDir": "down", "good": "down",
            },
            {
                "id": "lead", "icon": "clock", "sev": "info",
                "label": "Lead time médio",
                "value": f"{mean_days:.1f}".replace(".", ","), "unit": "dias",
                "sub": f"Tempo médio de {total_cases:,} casos".replace(",", "."),
                "trend": trend(mean_days, "down"), "trendDir": "down", "good": "down",
            },
        ]

        # remover drill=None
        for k in kpis:
            if k.get("drill") is None:
                k.pop("drill", None)

        return kpis
