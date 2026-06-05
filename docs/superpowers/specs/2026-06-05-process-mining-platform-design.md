# Plataforma de Process Mining — Design (MVP modular)

**Data:** 2026-06-05
**Status:** Aprovado para planejamento

## 1. Objetivo e contexto

Construir um produto web de **process mining** (mineração de processos), no estilo Celonis, com
intenção comercial de longo prazo. A entrega é feita por **fatias verticais** que rodam de ponta a
ponta (ingestão → mineração → visualização), começando pelo **módulo Financeiro** com dois
processos: **P2P (Procure-to-Pay)** e **O2C (Order-to-Cash)**.

A arquitetura é **modular**: um núcleo genérico de mineração, agnóstico de domínio, mais **módulos de
processo** plugáveis. Adicionar novos processos no futuro (ex.: Atendimento, Saúde) deve significar
"criar um novo módulo", sem alterar o núcleo.

**Decisões fixadas com o usuário:**
- Objetivo: produto real, a evoluir e possivelmente comercializar.
- Domínio inicial: Financeiro → P2P e O2C.
- Ingestão inicial: **upload de CSV/Excel**, atrás de uma interface de conector para permitir
  SQL/SAP depois.
- Formato: **aplicação web** (SaaS).
- Stack: **Backend Python (FastAPI) + `pm4py`/`pandas`; Frontend React.**
- O usuário não programa; toda a implementação é feita pelo assistente.
- Incluir **datasets demo** sintéticos para P2P e O2C, com problemas plantados.

## 2. Arquitetura

```
Frontend (React)  ──HTTP/JSON──▶  Backend (FastAPI)
  Upload                            ┌ Conectores (ingestão)   → CSVConnector (1º)
  Grafo do processo                 ├ Núcleo de Process Mining (pm4py) — genérico
  Variantes                         ├ Módulos de Processo     → P2PModule, O2CModule
  Dashboards/KPIs                   └ Armazenamento           → SQLite + arquivos (1º)
```

**Quatro componentes do backend, cada um com responsabilidade única:**

1. **Conectores (ingestão).** Interface comum `Connector` que produz um event log padronizado.
   Implementação inicial: `CSVConnector`. Futuras (`SQLConnector`, `SAPConnector`) entram sem tocar
   no núcleo.
2. **Núcleo de Process Mining.** Genérico/agnóstico de domínio. Recebe o event log padrão e produz:
   descoberta do fluxo (grafo), variantes, estatísticas de tempo/frequência e conformidade contra um
   processo-modelo. Usa `pm4py` + `pandas`.
3. **Módulos de Processo.** Interface comum `ProcessModule`. Cada módulo declara: mapeamento das
   colunas brutas para o event log padrão, o **processo-ideal** de referência, e as **análises/KPIs**
   específicas. Primeiros: `P2PModule`, `O2CModule`.
4. **Armazenamento.** Começa simples (SQLite + arquivos), com acesso isolado para trocar por
   Postgres ao escalar.

**Princípio de modularidade:** o núcleo nunca importa um módulo específico; os módulos se registram
no núcleo. Crescimento em largura (mais processos) não mexe no motor.

## 3. Modelo de dados

**Event log padrão** (idioma do núcleo). Mínimo para minerar: os três primeiros campos.

| Campo       | Descrição                         |
|-------------|-----------------------------------|
| `case_id`   | identificador do caso             |
| `activity`  | atividade executada               |
| `timestamp` | quando ocorreu                    |
| `resource`  | quem/qual sistema executou        |
| *(atributos)* | colunas extras do domínio       |

### Módulo P2P (Procure-to-Pay)
- **Caso:** linha do pedido de compra.
- **Processo-ideal:** `Criar Requisição → Criar Pedido de Compra → Aprovar Pedido → Receber
  Mercadoria → Receber Fatura → Pagar`.
- **Atributos:** `valor`, `fornecedor`, `centro_de_custo`, `condição_de_pagamento`,
  `data_vencimento`.
- **KPIs:** pagamento em duplicidade; perda de desconto por antecipação; maverick buying (pagar/
  receber fatura sem aprovação prévia); retrabalho de aprovação; lead time e gargalos por etapa.

### Módulo O2C (Order-to-Cash)
- **Caso:** linha do pedido de venda.
- **Processo-ideal:** `Criar Pedido → Liberar Crédito → Separar/Expedir → Entregar → Faturar →
  Receber Pagamento`.
- **Atributos:** `valor`, `cliente`, `data_prometida`, `data_entrega`, `status_crédito`.
- **KPIs:** DSO (prazo médio de recebimento) e vencidos; OTD (entrega no prazo); impacto de bloqueio
  de crédito; alteração de pedido (retrabalho); gargalos por etapa.

## 4. Motor de mineração (núcleo)

1. **Descoberta do processo** — *Directly-Follows Graph* (DFG) inicial: nós = atividades, arestas =
   transições, com frequência e tempo médio. Evolução futura: *inductive miner* (`pm4py`).
2. **Análise de variantes** — caminhos distintos início→fim, ordenados por frequência.
3. **Conformidade** — comparação dos casos reais contra o processo-ideal do módulo; marca desvios
   (etapas puladas, fora de ordem, repetidas).
4. **Estatísticas** — throughput time, tempo por etapa, gargalos, volume.
5. **KPIs do módulo** — o núcleo invoca as análises específicas do `ProcessModule` ativo.

Exposto via **endpoints REST** consumidos pelo frontend.

## 5. Frontend (React)

Bibliotecas de grafo candidatas: **React Flow** ou **Cytoscape.js** (escolha na implementação,
conforme densidade do processo).

**Telas da primeira versão:**
- **Explorador de processo** — grafo interativo (espessura da aresta = frequência) + filtros (por
  variante, fornecedor/cliente, período).
- **Variantes** — lista navegável; clique destaca o caminho no grafo.
- **Dashboard de KPIs/alertas** — indicadores do módulo, com casos problemáticos clicáveis
  (drill-down).
- **Barra superior** — upload de CSV, seletor de módulo (P2P/O2C), carregar dataset demo.

## 6. Datasets demo (gerados pelo assistente)

- **`demo_p2p.csv`** — ~2.000 casos / ~12.000 eventos. ~70% caminho feliz; restante com pagamento
  duplicado, maverick buying, retrabalho de aprovação, desconto perdido. Fornecedores, valores e
  datas variados.
- **`demo_o2c.csv`** — ~2.000 casos / ~12.000 eventos. Caminho feliz + bloqueio de crédito, entrega
  atrasada, alteração de pedido, recebimento em atraso (DSO alto).

Cada KPI tem casos correspondentes nos dados, para as telas "acenderem" na demo.

## 7. Roadmap incremental (ordem de construção)

Cada fatia roda de ponta a ponta e é testável isoladamente.

1. **Esqueleto vertical (P2P, caminho feliz).** FastAPI + React no ar → `CSVConnector` → núcleo
   descobre o grafo → frontend desenha o grafo do `demo_p2p`. Sem KPIs. Objetivo: ver um processo
   real na tela.
2. **Variantes + estatísticas (P2P).** Variantes, tempos, gargalos, filtros; tela de variantes ligada
   ao grafo.
3. **KPIs e alertas do P2P.** Pagamento duplicado, maverick buying, retrabalho, desconto perdido, com
   drill-down.
4. **Módulo O2C completo.** Prova da modularidade: adicionar O2C = criar um `ProcessModule`
   reaproveitando o núcleo. Seletor de módulo. DSO, OTD, bloqueio de crédito, alteração de pedido.
5. **Acabamento de produto.** Persistência (salvar/recarregar datasets), polimento visual, tratamento
   de erros de upload, conformidade contra processo-ideal.

Após a Fatia 4, um 3º processo (ex.: Atendimento) repete o padrão de módulo.

## 8. Fora de escopo (por enquanto)

- Conectores SQL/SAP (apenas a interface fica preparada).
- Multiusuário/autenticação, permissões, billing.
- Camada de automação/ação (Execution Management).
- Postgres e deploy em produção (SQLite local no MVP).
