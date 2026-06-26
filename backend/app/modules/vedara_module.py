"""Módulo Veddara-O2C (O2C real) — veddara.SQL_PM_ATIVIDADES + SQL_PM_CASES.
Caminho feliz Orçamento → Pedido → Fatura; cancelamentos viram ramos.
"""
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
