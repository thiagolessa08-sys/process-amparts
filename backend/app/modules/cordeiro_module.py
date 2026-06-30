"""Módulo Cordeiro-O2C (SAP) — cordeiro.SQL_PM_ATIVIDADES + SQL_PM_CASES.
Caminho feliz Orçamento → Aprovação → Pedido → Fatura → Aprovação → Pagamento;
cancelamentos viram ramos. Dimensão = Cliente.
"""
from app.eventlog import CASE_ID
from app.modules.headline import _fmt_compact, _spark
from app.modules.pm_base import PMModule


class CordeiroModule(PMModule):
    key   = "cordeiro"
    name  = "Cordeiro-O2C"
    short = "Cordeiro-O2C"
    color = "#7b54ee"
    dimension = "Cliente"

    # APROVOU FATURA é raro (~347 casos) → fora do núcleo de conformidade
    HAPPY = [
        "CRIOU ORCAMENTO", "APROVOU ORCAMENTO", "CRIOU PEDIDO",
        "CRIOU FATURA", "PAGOU FATURA",
    ]
    CANCEL = {"CANCELOU ORCAMENTO", "CANCELOU PEDIDO", "CANCELOU FATURA"}
    REWORK_ACTS = {"CANCELOU ORCAMENTO", "CANCELOU PEDIDO", "CANCELOU FATURA"}
    BRANCH_PARENT = {
        "CANCELOU ORCAMENTO": "CRIOU ORCAMENTO",
        "CANCELOU PEDIDO": "CRIOU PEDIDO",
        "CANCELOU FATURA": "CRIOU FATURA",
    }
    PED = "CRIOU PEDIDO"
    FAT = "CRIOU FATURA"
    order_activity = PED                 # filtro de período usa a data do pedido
    cancel_month_activity = "CANCELOU PEDIDO"

    def _headline(self, log, total_cases):
        """4 KPIs específicos do Cordeiro (iguais ao Celonis):
        Qtde Unidades, Valor Total Pedido, Faturamento e Pago."""
        first = log.groupby(CASE_ID).first()

        def soma(col):
            return float(first[col].sum()) if col in first.columns else 0.0

        kpis = [
            ("qtdeun", "Qtde Unidades", "itens", "layers", soma("qtde_un"), ""),
            ("valped", "Valor Total Pedido", "pedidos", "cart", soma("ped_total"), "R$"),
            ("valfat", "Valor Total Faturamento", "valortotal", "dollar", soma("fat_total"), "R$"),
            ("valpag", "Valor Total Pago", "value", "check", soma("pag_total"), "R$"),
        ]
        return [
            {"id": i, "label": lbl, "accent": acc, "icon": ic,
             "value": _fmt_compact(v), "unit": u, "delta": "", "spark": _spark(v)}
            for i, lbl, acc, ic, v, u in kpis
        ]
