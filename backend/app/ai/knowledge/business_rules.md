# Regras de Negócio

Regras de domínio e boas práticas para consultar/analisar os processos.
(Catálogo de tabelas e colunas: ver `catalog.md`.)

## Boas práticas de SQL (Sybase IQ)
- **SELECT apenas** — nunca INSERT/UPDATE/DELETE/DDL.
- **Case-sensitive**: valores diferenciam maiúsc./minúsc. Use as strings **exatamente**
  como no catálogo. Para nome citado pelo usuário, prefira `LOWER(col) LIKE '%nome%'`
  (case-insensitive) ou verifique os valores reais primeiro (`SELECT DISTINCT col ...`).
- **Limite sempre**: use `SELECT TOP n ...` (Sybase IQ). Nunca traga a tabela inteira.
- **Aspas simples** para strings e datas: `'2026-01-01'`. Datas no formato `YYYY-MM-DD`.
- **Sem comentários** no SQL. Código limpo e direto.
- `schema.TABELA` sempre (ex.: `cordeiro.SQL_PM_CASES`).
- Agregar por caso quando fizer sentido (`GROUP BY _CASE_KEY_O2C` / `_CASE_KEY`).
- Se um filtro voltar **vazio**, revise valor/caixa e tente de novo — não conclua no vazio.

## Ordem dos eventos
- A ordem lógica de um caso é o campo **SORTING** (`_SORTING` no Biolab), **não** o EVENTTIME.
- A data do evento na origem às vezes vem **fora de ordem** (ex.: no Cordeiro, APROVOU
  ORCAMENTO pode ter data anterior ao CRIOU ORCAMENTO quando são quase simultâneos).
  Para sequência/1ª atividade, ordene por SORTING; EVENTTIME serve para durações.

## Chave do caso (`_CASE_KEY_O2C`, O2C)
Formato: `orcamento|orc_item|pedido|ped_item|fatura|fat_item` — **números visíveis**
(DocNumber), não os internos. Ex.: `14072|1|14271|0|29419|0`.

## Valor / Faturamento
- **Cordeiro**: `*_VALOR` é **preço unitário**; o valor da linha é **`*_TOTAL`** (= unitário × qtde).
  - Faturamento = **`SUM(FAT_TOTAL)`**. "Valor" do caso = `COALESCE(FAT_TOTAL, PED_TOTAL, 0)`.
  - Validado com a base do Rafael: jan/2026 `SUM(FAT_TOTAL)` ≈ R$ 211,8M (total geral de NFs).
- **Veddara**: valor do caso = `VL_ORC_TOTAL_ITEM`.
- **Biolab**: valor = `LIQUIDOPEDIDO` (SQL_PM_DADOS, detalhe) ou `PDAEXP`
  (TB_BIOLAB_CELONIS_EXPORT_CASE). Quantidade tem **3 casas implícitas** em ambas
  (`QUANTIDADE`/`PDUORG` ÷ 1000); o valor já vem correto.

## Datas / período
- Filtro "por data do pedido": Cordeiro/Veddara usam a data do evento **CRIOU/CRIACAO DO
  PEDIDO** (ou `DATA_PEDIDO`/`DT_PEDIDO` em CASES). Biolab: `Entrar Pedido de Comp`.
- Faturamento "por competência" = por **data de emissão da NF** (`DATA_EMISSAO_NF`),
  que é corte diferente de "data do pedido". Um pedido de dezembro pode ter NF em janeiro.

## Retrabalho
- **Retrabalho = ALTERAÇÃO + CANCELAMENTO** (cada ocorrência conta), nos 3 processos.
- Custo estimado de retrabalho: **30 min × R$ 50/h = R$ 25 por item** cancelado/alterado
  (conta o item uma vez, não por ocorrência).
- Atividades de retrabalho por processo: ver `catalog.md`.
  - Cordeiro **não tem** atividade de alteração (só cancelamentos + DEVOLUÇÃO FATURA).

## Fluxo (happy path)
- **Veddara**: CRIACAO DO ORCAMENTO → CRIACAO DO PEDIDO → CRIACAO DA FATURA.
- **Cordeiro**: CRIOU ORCAMENTO → APROVOU ORCAMENTO → CRIOU PEDIDO → CRIOU FATURA → PAGOU FATURA.
- **Biolab**: Entrar Requisição → Entrar Pedido de Comp → Recebimento → Entrar Nota Fiscal de → Baixar Fatura.

## Peculiaridades conhecidas dos dados
- **Dupla aprovação (Cordeiro)**: muitos casos têm APROVOU ORCAMENTO 2× (dois aprovadores,
  ex.: "Regional Sul" + um nome) com o mesmo horário/SORTING. Isso divide variantes.
- **NF fantasma (Cordeiro)**: às vezes a mesma NF aparece 2× (uma completa/paga e uma
  parcial/não paga) — infla FAT_TOTAL. A não paga costuma ser a duplicata; `PAG_TOTAL`
  (pago) tende a bater com o faturamento real.
- **DocNumber ≠ interno (SAP B1)**: a chave usa o número **visível**; ao cruzar com as
  tabelas cruas `*_SAP_PRODUCAO`, use o DocNumber (não o InternalNumber).
- **Datas de criação**: no SAP, a data "real" de criação é `*DocCreationDate` (+ `*DocCreationTS`),
  não `*DocumentDate`.

## Tabelas cruas do SAP (schema `cordeiro`, além das SQL_PM_*)
`PEDIDOS_SAP_PRODUCAO`, `COTACOES_SAP_PRODUCAO`, `APROVACOES_SAP_PRODUCAO`,
`NFE_SAP_PRODUCAO`, `NFSAIDA_SAP_PRODUCAO`, `DEVOLUCAONF_SAP_PRODUCAO`,
`ENTREGA_SAP_PRODUCAO`, `RETORNOITENS_SAP_PRODUCAO`, `FATURAADIANTAMENTO_SAP_PRODUCAO`,
`APROVACAOCREDITO_SAP_PRODUCAO`. Use só se precisar de dado que não está nas SQL_PM_*.
