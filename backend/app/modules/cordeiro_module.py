"""Módulo Cordeiro-O2C (SAP) — cordeiro.SQL_PM_ATIVIDADES + SQL_PM_CASES.
Caminho feliz Orçamento → Aprovação → Pedido → Fatura → Aprovação → Pagamento;
cancelamentos viram ramos. Dimensão = Cliente.
"""
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
