"""Módulo Veddara-O2C (O2C real) — veddara.SQL_PM_ATIVIDADES + SQL_PM_CASES.
Caminho feliz Orçamento → Pedido → Fatura; cancelamentos viram ramos.
"""
from app.eventlog import CASE_ID
from app.modules.headline import _fmt_compact, _spark
from app.modules.pm_base import PMModule


class VedaraModule(PMModule):
    key   = "vedara"
    name  = "Veddara-O2C"
    short = "Veddara-O2C"
    color = "#0e9f93"
    dimension = "Cliente"

    HAPPY = ["CRIACAO DO ORCAMENTO", "CRIACAO DO PEDIDO", "CRIACAO DA FATURA"]
    CANCEL = {"CANCELAMENTO DO ORCAMENTO", "CANCELAMENTO DO PEDIDO", "CANCELAMENTO DA FATURA"}
    REWORK_ACTS = {
        "ALTERACAO DO PEDIDO", "CANCELAMENTO DO ORCAMENTO", "CANCELAMENTO DO PEDIDO",
        "ALTERACAO DO ORCAMENTO", "CANCELAMENTO DA FATURA",
    }
    BRANCH_PARENT = {
        "CANCELAMENTO DO ORCAMENTO": "CRIACAO DO ORCAMENTO",
        "CANCELAMENTO DO PEDIDO": "CRIACAO DO PEDIDO",
        "CANCELAMENTO DA FATURA": "CRIACAO DA FATURA",
    }
    PED = "CRIACAO DO PEDIDO"
    FAT = "CRIACAO DA FATURA"
    order_activity = PED                 # filtro de período usa a data do pedido
    cancel_month_activity = "CANCELAMENTO DO PEDIDO"

    def _headline(self, log, total_cases):
        """3 KPIs do Veddara (base orçamento-cêntrica, sem valor de pedido/pago):
        Qtde Unidades, Valor Orçado e Valor Faturado."""
        first = log.groupby(CASE_ID).first()

        def soma(col):
            return float(first[col].sum()) if col in first.columns else 0.0

        kpis = [
            ("qtdeun", "Qtde Unidades", "itens", "layers", soma("qtde_un"), ""),
            ("valorc", "Valor Orçado", "pedidos", "cart", soma("valor"), "R$"),
            ("valfat", "Valor Faturado", "valortotal", "dollar", soma("fat_total"), "R$"),
        ]
        return [
            {"id": i, "label": lbl, "accent": acc, "icon": ic,
             "value": _fmt_compact(v), "unit": u, "delta": "", "spark": _spark(v)}
            for i, lbl, acc, ic, v, u in kpis
        ]
