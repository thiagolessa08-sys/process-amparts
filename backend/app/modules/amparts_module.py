"""Módulo AM Parts-O2C — acessórios automotivos com Ordem de Serviço.

Fluxo real extraído do dado (SORTING é rank fixo por atividade no export):

     5  CANCELOU ORCAMENTO        20  CRIOU PEDIDO          40  LIBEROU BAIXA
    10  CRIOU ORCAMENTO           21  EDITOU ITENS          45  FATUROU SAIDA
    15  CONVERTEU ORCAMENTO       22  CANCELOU PEDIDO       50  PAGAMENTO
                                  25  LIBEROU PEDIDO N1     60  SOLICITOU RM
                                  26  LIBEROU PEDIDO N2     62  RM ATENDIDA
                                  30  ABRIU OS              70  SOLICITOU RETORNO
                                  32  RECEBEU VEICULO       72  APROVOU RETORNO
                                  35  FINALIZOU OS          75  RETORNOU PECA
                                  36  CANCELOU OS

Difere do O2C clássico em duas coisas: a dupla liberação do pedido (N1/N2) e o
bloco de Ordem de Serviço (abrir OS → receber veículo → finalizar OS), que só
ocorre nos casos com instalação.
"""
from app.eventlog import CASE_ID
from app.modules.headline import _fmt_compact, _spark
from app.modules.pm_base import PMModule


class AmPartsModule(PMModule):
    key   = "amparts"
    name  = "AM Parts-O2C"
    short = "AM Parts-O2C"
    color = "#d4145a"
    dimension = "Cliente"

    # Caminho feliz = espinha comercial de maior volume, uma atividade por
    # posição. O bloco de OS (ABRIU OS / RECEBEU VEICULO / FINALIZOU OS) e o de
    # RM ficam de fora: só ocorrem nos casos com instalação, e entrariam como
    # não conformidade.
    #
    # ATENÇÃO — a origem renomeia atividades entre exports, e isso já zerou a
    # conformidade duas vezes. Histórico da mesma etapa:
    #   LIBEROU PEDIDO N2  -> LIBEROU AUTOMATICO N2 -> APROVOU PEDIDO N2
    #   LIBEROU BAIXA      -> BAIXA AUTOMATICA      -> LIBERACAO FINANCEIRO
    #   PAGAMENTO          -> PAGAMENTO PEDIDO
    # Ao trocar a base, confira a cobertura das atividades ANTES de confiar na
    # conformidade: se ela cair a zero, a causa é esta, não o processo.
    #
    # Coberturas medidas no export de 03/08 (conformidade resultante: 58,2%):
    #   CRIOU ORCAMENTO 88,2% · CONVERTEU ORCAMENTO 64,9% · CRIOU PEDIDO 64,9%
    #   APROVOU PEDIDO N2 65,0% · APROVOU PEDIDO N1 65,1%
    #   LIBERACAO FINANCEIRO 62,6% · PAGAMENTO PEDIDO 60,0%
    HAPPY = [
        "CRIOU ORCAMENTO", "CONVERTEU ORCAMENTO", "CRIOU PEDIDO",
        "APROVOU PEDIDO N2", "APROVOU PEDIDO N1", "LIBERACAO FINANCEIRO",
        "PAGAMENTO PEDIDO",
    ]
    CANCEL = {"CANCELOU ORCAMENTO", "CANCELOU PEDIDO", "CANCELOU OS"}
    # retrabalho = cancelamentos + edição de itens + o ciclo de retorno de peça
    REWORK_ACTS = {
        "EDITOU ITENS", "CANCELOU ORCAMENTO", "CANCELOU PEDIDO", "CANCELOU OS",
        "SOLICITOU RETORNO", "APROVOU RETORNO", "RETORNOU PECA",
    }
    BRANCH_PARENT = {
        "CANCELOU ORCAMENTO": "CRIOU ORCAMENTO",
        "CANCELOU PEDIDO": "CRIOU PEDIDO",
        "CANCELOU OS": "ABRIU OS",
    }
    REVERSAL_ACTS = {"RETORNOU PECA"}    # devolução entra na análise de cancelamentos
    PED = "CRIOU PEDIDO"
    FAT = "FATUROU SAIDA"
    order_activity = PED                 # filtro de período usa a data do pedido
    cancel_month_activity = "CANCELOU PEDIDO"

    def _headline(self, log, total_cases):
        """4 KPIs da AM Parts: Qtde Unidades, Valor Orçado, Valor Pedido e
        Valor Faturado — os quatro somados uma vez por caso."""
        first = log.groupby(CASE_ID).first()

        def soma(col):
            return float(first[col].sum()) if col in first.columns else 0.0

        kpis = [
            ("qtdeun", "Qtde Unidades", "itens", "layers", soma("qtde_un"), ""),
            ("valorc", "Valor Orçado", "pedidos", "cart", soma("orc_total"), "R$"),
            ("valped", "Valor Total Pedido", "value", "check", soma("valor"), "R$"),
            ("valfat", "Valor Faturado", "valortotal", "dollar", soma("fat_total"), "R$"),
        ]
        return [
            {"id": i, "label": lbl, "accent": acc, "icon": ic,
             "value": _fmt_compact(v), "unit": u, "delta": "", "spark": _spark(v)}
            for i, lbl, acc, ic, v, u in kpis
        ]
