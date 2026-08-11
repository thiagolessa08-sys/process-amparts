# Regras de Negócio

Regras de domínio e boas práticas para consultar/analisar o processo.
(Catálogo de tabelas e colunas: ver `catalog.md`.)

## Boas práticas de SQL (Sybase IQ)
- **SELECT apenas** — nunca INSERT/UPDATE/DELETE/DDL.
- **Case-sensitive**: valores diferenciam maiúsc./minúsc. Use as strings **exatamente**
  como no catálogo. Para nome citado pelo usuário, prefira `LOWER(col) LIKE '%nome%'`
  (case-insensitive) ou verifique os valores reais primeiro (`SELECT DISTINCT col ...`).
- **Limite sempre**: use `SELECT TOP n ...` (Sybase IQ). Nunca traga a tabela inteira.
- **Aspas simples** para strings e datas: `'2026-01-01'`. Datas no formato `YYYY-MM-DD`.
- **Sem comentários** no SQL. Código limpo e direto.
- `schema.TABELA` sempre (ex.: `amparts.SQL_PM_CASES`).
- Agregar por caso quando fizer sentido (`GROUP BY CASE_KEY`).
- Se um filtro voltar **vazio**, revise valor/caixa e tente de novo — não conclua no vazio.

## Ordem dos eventos
- A ordem lógica de um caso é o campo **SORTING**, **não** o EVENTTIME.
- Na AM Parts isso é decisivo. Medido sobre o recorte de 2026:
  `LIBEROU PEDIDO N1 → N2` vem **invertido em 89,6%** dos casos (as duas liberações
  são quase simultâneas) e `CRIOU PEDIDO → PAGAMENTO` em **53,9%** (a data do
  pagamento tem semântica diferente da data do pedido). Os demais pares da espinha
  estão 100% consistentes.
- Para sequência/1ª atividade, ordene por SORTING; EVENTTIME serve para durações.

## Valor / Faturamento
- **Valor orçado** = `ORC_VALOR`. **Valor do pedido** = `PED_TOTAL`.
  **Faturamento** = `SUM(FAT_TOTAL)`. **Quantidade** = `PED_QTDE`.
- Os quatro são somados **uma vez por caso** (a CASES tem 1 linha por caso/item).
- Caso cancelado: `FOI_CANCELADO > 0`.

## Datas / período
- O recorte de período usa a **menor data do caso** (1º evento), **não** a data do
  pedido. Motivo: **33,6% dos casos são orçamentos que nunca viraram pedido** —
  filtrar pela data do pedido descartaria esse terço da base em silêncio, levando
  junto quase todos os cancelamentos (que, por definição, acontecem antes de o
  pedido existir).
- Efeito esperado disso na conformidade: **48,6%**, não 73,1%. Os 73,1% eram
  calculados só sobre os casos que viraram pedido; 48,6% é o número real,
  incluindo os orçamentos que morreram. Não trate a diferença como piora do processo.
- "Emissão" do caso = `DATA_ORCAMENTO`, com fallback em `DATA_PEDIDO`.

## Retrabalho
- **Retrabalho = cancelamentos + `EDITOU ITENS` + o ciclo de retorno de peça**
  (`SOLICITOU RETORNO`, `APROVOU RETORNO`, `RETORNOU PECA`). Cada ocorrência conta.
- Cancelamentos: `CANCELOU ORCAMENTO`, `CANCELOU PEDIDO`, `CANCELOU OS`.
- `RETORNOU PECA` (devolução) também entra na análise de cancelamentos.
- Custo estimado de retrabalho: **30 min × R$ 50/h = R$ 25 por item**
  cancelado/alterado (conta o item uma vez, não por ocorrência).

## Fluxo (happy path)
`CRIOU ORCAMENTO` → `CONVERTEU ORCAMENTO` → `CRIOU PEDIDO` → `APROVOU PEDIDO N1`
→ `LIBEROU AUTOMATICO N2` → `BAIXA AUTOMATICA` → `PAGAMENTO`.

O bloco de **Ordem de Serviço** (`ABRIU OS` → `RECEBEU VEICULO` → `FINALIZOU OS`)
e o de **RM** ficam **fora** do caminho feliz: só ocorrem nos casos com instalação,
e entrariam como não conformidade.

## Peculiaridades conhecidas dos dados
- **Renomeação de atividades entre exports**: a origem já trocou o nome da mesma
  etapa duas vezes, zerando a conformidade. Ver o histórico em `catalog.md`.
  Ao trocar a base, confira a cobertura das atividades **antes** de confiar na
  conformidade.
- **Dupla liberação do pedido (N1/N2)**: são quase simultâneas e a origem grava
  os timestamps fora de ordem — por isso a ordenação por SORTING (acima).
- **SORTING é rank fixo por atividade** neste export, não um contador por caso.
