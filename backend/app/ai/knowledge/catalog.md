# Catálogo de Dados

Banco: **Sybase IQ**. É **case-sensitive** — nomes de tabela/coluna **e** valores
(atividades, clientes, produtos) diferenciam maiúsculas/minúsculas. Use sempre
`schema.TABELA` e as strings exatamente como estão aqui.

O processo fica em seu próprio schema:

| Processo | Schema | Atividades (event log) | Casos | Col. atividade | Chave do caso |
|---|---|---|---|---|---|
| AM Parts-O2C | `amparts` | `SQL_PM_ATIVIDADES` | `SQL_PM_CASES` | `ACTIVITY_EN` | `CASE_KEY` |

- **ATIVIDADES** = event log: 1 linha por EVENTO. Um CASO = a chave do caso.
- **CASES** = 1 linha por caso/item, com datas e valores.
- Ordem lógica dos eventos = campo **SORTING** (não a data — ver regras de negócio).

---

## AM Parts-O2C — schema `amparts`

O2C de acessórios automotivos. Difere do O2C clássico em duas coisas: a **dupla
liberação do pedido** (N1/N2) e o bloco de **Ordem de Serviço** (abrir OS →
receber veículo → finalizar OS), que só ocorre nos casos com instalação.

### amparts.SQL_PM_ATIVIDADES  (event log)
| coluna | descrição |
|---|---|
| CASE_KEY | chave do caso |
| ACTIVITY_EN | nome da atividade (evento) |
| EVENTTIME | data/hora do evento |
| SORTING | ordem lógica do evento no caso (**rank fixo por atividade** neste export) |
| USUARIO | usuário que executou |
| VENDEDOR | vendedor/representante |
| ORCAMENTO / ORC_ITEM | nº do orçamento / item |
| PEDIDO / PED_ITEM | nº do pedido / item |
| OS | nº da ordem de serviço |
| SAIDA | nº da saída (faturamento) |
| CLIENTE | cliente |
| CONCESSIONARIA | concessionária |
| PRODUTO / PROD_NOME | código / nome do produto |
| SOURCE_ACTIVITY | origem do evento |

### amparts.SQL_PM_CASES  (1 linha por caso/item)
| coluna | descrição |
|---|---|
| CASE_KEY | chave do caso |
| ORCAMENTO / ORC_ITEM | nº e item do orçamento |
| PEDIDO | nº do pedido |
| OS | nº da ordem de serviço |
| SAIDA | nº da saída |
| DATA_ORCAMENTO / DATA_PEDIDO | datas do orçamento e do pedido |
| CLIENTE | cliente |
| CONCESSIONARIA | concessionária |
| PROD_NOME | nome do produto |
| ORC_VALOR | valor orçado |
| PED_QTDE | quantidade do pedido |
| PED_TOTAL | **valor total do pedido** |
| FAT_TOTAL | **valor faturado** |
| FOI_CANCELADO | flag de cancelamento (`> 0` ⇒ cancelado) |

> **Emissão do caso** = `DATA_ORCAMENTO`, caindo para `DATA_PEDIDO` quando o caso
> nasce direto como pedido (sem orçamento anterior). ~33,6% dos casos são
> orçamentos que nunca viraram pedido — não os descarte ao filtrar por período.

### Atividades (ACTIVITY_EN)
Ordem lógica pelo SORTING:

| SORTING | atividade | | SORTING | atividade |
|---|---|---|---|---|
| 5 | CANCELOU ORCAMENTO | | 35 | FINALIZOU OS |
| 10 | CRIOU ORCAMENTO | | 36 | CANCELOU OS |
| 15 | CONVERTEU ORCAMENTO | | 40 | LIBEROU BAIXA |
| 20 | CRIOU PEDIDO | | 45 | FATUROU SAIDA |
| 21 | EDITOU ITENS | | 50 | PAGAMENTO |
| 22 | CANCELOU PEDIDO | | 60 | SOLICITOU RM |
| 25 | LIBEROU PEDIDO N1 | | 62 | RM ATENDIDA |
| 26 | LIBEROU PEDIDO N2 | | 70 | SOLICITOU RETORNO |
| 30 | ABRIU OS | | 72 | APROVOU RETORNO |
| 32 | RECEBEU VEICULO | | 75 | RETORNOU PECA |

Cancelamentos: `CANCELOU ORCAMENTO`, `CANCELOU PEDIDO`, `CANCELOU OS`.
Retrabalho: os cancelamentos + `EDITOU ITENS` + o ciclo de retorno de peça
(`SOLICITOU RETORNO`, `APROVOU RETORNO`, `RETORNOU PECA`).

> **Atenção — a origem renomeia atividades entre exports**, e isso já zerou a
> conformidade duas vezes. Histórico da mesma etapa:
> `LIBEROU PEDIDO N2` → `LIBEROU AUTOMATICO N2` → `APROVOU PEDIDO N2`;
> `LIBEROU BAIXA` → `BAIXA AUTOMATICA` → `LIBERACAO FINANCEIRO`;
> `PAGAMENTO` → `PAGAMENTO PEDIDO`.
> Confira a cobertura das atividades antes de confiar na conformidade: se ela
> cair a zero, a causa é esta, não o processo.
