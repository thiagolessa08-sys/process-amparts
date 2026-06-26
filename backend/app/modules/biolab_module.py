"""Módulo Biolab-P2P (Compras, base JD Edwards) — biolab.SQL_PM_ATIVIDADES +
SQL_PM_CASES + SQL_PM_DADOS (detalhe). Caminho feliz Requisição → Pedido →
Recebimento → Nota Fiscal → Voucher → Baixar Fatura; cancelamentos/estornos/
rejeições viram ramos. Dimensão = Fornecedor.
"""
from app.modules.pm_base import PMModule


class BiolabModule(PMModule):
    key   = "biolab"
    name  = "Biolab-P2P"
    short = "Biolab-P2P"
    color = "#e0820e"
    dimension = "Fornecedor"

    # núcleo de conformidade (P2P ponta a ponta); o grafo mostra todas as
    # atividades — isto define só o "caminho feliz" do KPI de conformidade
    HAPPY = [
        "Entrar Requisição", "Entrar Pedido de Comp", "Recebimento",
        "Entrar Nota Fiscal de", "Baixar Fatura",
    ]
    CANCEL = {
        "Cancelar Requisição", "Requisição Rejeitada", "Cancelar Pedido",
        "Pedido Rejeitado", "Cancelar Entrada", "Estornar Recebimento",
        "Estornar Voucher - Re",
    }
    BRANCH_PARENT = {
        "Cancelar Requisição": "Entrar Requisição",
        "Requisição Rejeitada": "Entrar Requisição",
        "Cancelar Pedido": "Entrar Pedido de Comp",
        "Pedido Rejeitado": "Entrar Pedido de Comp",
        "Cancelar Entrada": "Entrar Nota Fiscal de",
        "Estornar Recebimento": "Recebimento",
        "Estornar Voucher - Re": "Criar Voucher - Receb",
    }
    REWORK_ACTS = {
        "Alterar Data Prometid", "Alterar Preço Total", "Alterar Termo Pagamen",
        "Alterar Quantidade Un", "Alterar Preço Unitári", "Alterar Peso Unitário",
        "Alterar Data Real Rem", "Alterar Data Solicita", "Alterar Endereço Entr",
        "Alterar Unidade Negóc", "Ajuste Resíduos Saldo",
        "Cancelar Requisição", "Requisição Rejeitada", "Cancelar Pedido",
        "Pedido Rejeitado", "Cancelar Entrada", "Estornar Recebimento",
        "Estornar Voucher - Re",
    }
    PED = "Entrar Pedido de Comp"
    FAT = "Entrar Nota Fiscal de"
    order_activity = PED                 # filtro de período usa a data do pedido
    cancel_month_activity = "Cancelar Pedido"
