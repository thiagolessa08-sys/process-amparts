# Catálogo de Dados

Banco: **Sybase IQ**. É **case-sensitive** — nomes de tabela/coluna **e** valores
(atividades, clientes, produtos) diferenciam maiúsculas/minúsculas. Use sempre
`schema.TABELA` e as strings exatamente como estão aqui.

Cada processo fica em seu próprio schema:

| Processo | Schema | Atividades (event log) | Casos | Col. atividade | Chave do caso |
|---|---|---|---|---|---|
| Veddara-O2C | `veddara` | `SQL_PM_ATIVIDADES` | `SQL_PM_CASES` | `ACTIVITY_EN` | `_CASE_KEY_O2C` |
| Cordeiro-O2C | `cordeiro` | `SQL_PM_ATIVIDADES` | `SQL_PM_CASES` | `ACTIVITY_EN` | `_CASE_KEY_O2C` |
| Biolab-P2P | `biolab` | `SQL_PM_ATIVIDADES` | `SQL_PM_CASES` (+ `SQL_PM_DADOS`) | `ACTIVITY_NAME` | `_CASE_KEY` |

- **ATIVIDADES** = event log: 1 linha por EVENTO. Um CASO = a chave do caso.
- **CASES** = 1 linha por caso/item, com datas e valores.
- Ordem lógica dos eventos = campo **SORTING** (não a data — ver regras de negócio).

---

## Veddara-O2C — schema `veddara`

### veddara.SQL_PM_ATIVIDADES  (18 colunas)
| coluna | tipo | descrição |
|---|---|---|
| _CASE_KEY_O2C | varchar(40) | chave do caso (orc\|orc_item\|ped\|ped_item\|fat\|fat_item) |
| ACTIVITY_EN | varchar(50) | nome da atividade (evento) |
| EVENTTIME | timestamp | data/hora do evento |
| SORTING | integer | ordem lógica do evento no caso |
| USUARIO | varchar(50) | usuário que executou |
| VENDEDOR | varchar(50) | vendedor/representante |
| ORCAMENTO / ORC_ITEM | varchar(10) | nº do orçamento / item |
| PEDIDO / PED_ITEM | varchar(10) | nº do pedido / item |
| FATURA / FAT_ITEM | varchar(10) | nº da fatura / item |
| CLIENTE | varchar(50) | código do cliente |
| PRODUTO / PROD_NOME | varchar(10)/(100) | código / nome do produto |
| OLD_VALUE_CHANGED / NEW_VALUE_CHANGED | varchar(100) | valor antigo/novo (em alterações) |
| SOURCE_ACTIVITY | varchar(30) | origem (ORCAMENTO/PEDIDO/FATURA) |

### veddara.SQL_PM_CASES  (18 colunas)
| coluna | tipo | descrição |
|---|---|---|
| _CASE_KEY_O2C | varchar(40) | chave do caso |
| NR_ORCAMENTO / NR_ITEM_ORCAMENTO | varchar | nº e item do orçamento |
| NR_PEDIDO | varchar(24) | nº do pedido |
| NR_INVOICE | varchar(40) | nº da nota/fatura |
| CD_CLIENTE / NOME_CLIENTE | varchar | código / nome do cliente |
| CD_PRODUTO / NOME_PRODUTO | varchar | código / nome do produto |
| CRM_MEDICO / NOME_MEDICO | varchar(100) | CRM / nome do médico |
| NOME_REP | varchar(100) | representante/vendedor |
| NOME_USER_CRIACAO | varchar(100) | usuário que criou |
| DT_ORCAMENTO / DT_PEDIDO / DT_INVOICE | timestamp | datas do orçamento/pedido/nota |
| QT_ORC_ITEM | float | quantidade do item |
| VL_ORC_TOTAL_ITEM | float | **valor total do item** (é o "valor" do caso) |

### Atividades (ACTIVITY_EN)
Fluxo: `CRIACAO DO ORCAMENTO` → `CRIACAO DO PEDIDO` → `CRIACAO DA FATURA`.
Retrabalho: `ALTERACAO DO ORCAMENTO`, `ALTERACAO DO PEDIDO`,
`CANCELAMENTO DO ORCAMENTO`, `CANCELAMENTO DO PEDIDO`, `CANCELAMENTO DA FATURA`.

---

## Cordeiro-O2C — schema `cordeiro`  (SAP Business One)

### cordeiro.SQL_PM_ATIVIDADES  (18 colunas)
Mesma estrutura da Veddara: `_CASE_KEY_O2C`, `ACTIVITY_EN`, `EVENTTIME`,
`SORTING`, `USUARIO`, `VENDEDOR`, `ORCAMENTO/ORC_ITEM`, `PEDIDO/PED_ITEM`,
`FATURA/FAT_ITEM`, `CLIENTE`, `PRODUTO/PROD_NOME`,
`OLD_VALUE_CHANGED/NEW_VALUE_CHANGED`, `SOURCE_ACTIVITY`.

### cordeiro.SQL_PM_CASES  (25 colunas)
| coluna | tipo | descrição |
|---|---|---|
| _CASE_KEY_O2C | varchar(40) | chave do caso |
| USUARIO / VENDEDOR | varchar(50) | usuário / vendedor |
| ORCAMENTO/ORC_ITEM, PEDIDO/PED_ITEM, FATURA/FAT_ITEM | varchar(10) | documentos e itens |
| CLIENTE | varchar(50) | código do cliente |
| PRODUTO / PROD_NOME | varchar | código / nome do produto |
| DATA_PEDIDO | timestamp | data do pedido |
| DATA_EMISSAO_NF | timestamp | data de emissão da NF |
| DATA_VENCIMENTO | timestamp | vencimento |
| DATA_PAGAMENTO | timestamp | data do pagamento |
| PED_QTDE_ITEM, PED_VALOR, PED_TOTAL | float | qtde, **valor UNITÁRIO**, **valor TOTAL** do pedido |
| FAT_QTDE_ITEM, FAT_VALOR, FAT_TOTAL | float | qtde, unitário, **TOTAL** da fatura |
| PAG_QTDE_ITEM, PAG_VALOR, PAG_TOTAL | float | qtde, unitário, **TOTAL** pago |

> **Atenção**: `*_VALOR` é preço **unitário**; o valor da linha é `*_TOTAL`
> (= unitário × quantidade). Para faturamento use **`FAT_TOTAL`**.

### Atividades (ACTIVITY_EN)
Fluxo: `CRIOU ORCAMENTO` → `APROVOU ORCAMENTO` → `CRIOU PEDIDO` →
`CRIOU FATURA` → `PAGOU FATURA` (há também `APROVOU PEDIDO`, `APROVOU FATURA`).
Retrabalho: `CANCELOU ORCAMENTO`, `CANCELOU PEDIDO`, `CANCELOU FATURA`,
`CANCELOU PAGAMENTO`, `DEVOLUÇÃO FATURA`. (Cordeiro **não tem** atividade de alteração.)

---

## Biolab-P2P — schema `biolab`  (JD Edwards)

### biolab.SQL_PM_ATIVIDADES  (16 colunas)
| coluna | tipo | descrição |
|---|---|---|
| _CASE_KEY | varchar(22) | chave do caso |
| ACTIVITY_NAME | varchar(21) | nome da atividade (**truncado em ~21 chars**) |
| EVENTTIME | varchar(19) | data/hora (string 'YYYY-MM-DD HH:MM:SS') |
| _SORTING | integer | ordem lógica do evento |
| PDKCOO, PDDOCO, PDDCTO, PDSFXO, PDLNID | varchar | chaves do documento JDE |
| _DESCRIPTION | varchar(32) | descrição |
| _USER_NAME | varchar(12) | usuário |
| CHANGED_FROM / CHANGED_TO | varchar | valor antigo/novo (em alterações) |
| AUDIT_PROGRAM / AUDIT_COMPUTER | varchar(12) | auditoria |
| DT_INCLUSAO | timestamp | data de inclusão no PM |

### biolab.SQL_PM_CASES  (78 colunas — campos crus do JDE, prefixo PD/FD)
Principais: `_CASE_KEY`, `PDAN8` (fornecedor), `PDDSC1` (descrição/produto),
`PDAEXP` (valor), `PDUOM` (unidade), datas `*_CONV` (PDDRQJ_CONV solicitação,
PDPDDJ_CONV promessa, etc.), `PDAEXP_CANCELADO`, `PDAEXP_DEVOLVIDO`.
(Tabela ampla; consulte só as colunas necessárias.)

### biolab.SQL_PM_DADOS  (25 colunas — detalhe P2P)
| coluna | tipo | descrição |
|---|---|---|
| DOCUMENTO / LINHAITEM | integer | nº do documento / item |
| TIPO_COMPRA, TIPODOCTO | varchar | tipo de compra / documento |
| DTSOLICITACAO, DTENTREGA, DTREMESSA, EMISSAO | date | datas |
| ALTERACOES, RETRABALHO, VAZAMENTOCONTR | varchar | flags |
| FORNECEDOR | varchar(42) | fornecedor |
| PRODUTO | varchar(58) | produto |
| QUANTIDADE, PRECOUNITARIO, LIQUIDOPEDIDO | decimal | qtde, preço unit., **valor líquido** |
| CANCELADO | decimal | valor cancelado |

### Atividades (ACTIVITY_NAME) — nomes truncados em ~21 chars
Fluxo: `Entrar Requisição` → `Entrar Pedido de Comp` → `Recebimento` →
`Entrar Nota Fiscal de` → `Baixar Fatura`.
Alterações: `Alterar Data Prometid`, `Alterar Preço Total`, `Alterar Quantidade Un`,
`Alterar Preço Unitári`, `Alterar Termo Pagamen`, `Alterar Data Real Rem`,
`Alterar Data Solicita`, `Alterar Endereço Entr`, `Alterar Peso Unitário`,
`Alterar Unidade Negóc`, `Ajuste Resíduos Saldo`.
Cancelamentos/estornos: `Cancelar Requisição`, `Requisição Rejeitada`,
`Cancelar Pedido`, `Cancelar Pedido Blank`, `Pedido Rejeitado`, `Cancelar Entrada`,
`Estornar Recebimento`, `Estornar Voucher - Re`.
