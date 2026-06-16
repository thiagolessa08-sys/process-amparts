# Editor de queries-base do Cordeiro

Data: 2026-06-15

## Objetivo
Um botão na UI do Cordeiro que abre um editor para o usuário editar as 4 consultas-base
que alimentam o event log (cotações, pedidos, notas fiscais, aprovações), com validação
(determinística + Claude) antes de salvar.

## Escopo (decisões aprovadas)
- **Editável:** por fonte, três campos — `table` (FROM), `columns` (projeção), `where` (filtro).
- **Fixo no backend:** chaves de paginação, `GROUP BY` (aprovações), `ORDER BY`, junções e o
  modelo Celonis item-level. O usuário não mexe nisso.
- **Persistência:** JSON num caminho de env var `CORDEIRO_QUERY_CONFIG`
  (ex.: `/data/cordeiro_queries.json` num Volume do Railway). Defaults no código.
- **Validação:** (1) determinística — roda `SELECT TOP 1 {columns} FROM {table} [WHERE {where}]`
  no agent e confere se as **colunas obrigatórias** vieram; (2) Claude — diagnóstico em
  português + sugestão de correção (best-effort; pula se IA não configurada).

## Backend
- `app/sources/cordeiro_queries.py`:
  - `DEFAULT_QUERIES`: dict das 4 fontes `{table, columns, where}`.
  - `REQUIRED_COLUMNS`: dict fonte -> conjunto de colunas/aliases obrigatórios.
  - `STRUCT`: dict fonte -> chaves de paginação / group (uso interno).
  - `get_config()` (merge defaults + override JSON), `save_config(cfg)`, `reset_config()`.
  - `validate_source(source, table, columns, where)` -> `{ok, columns, missing, error}`.
- `app/sources/cordeiro.py`: `load_cordeiro_eventlog` passa a montar as queries a partir de
  `get_config()` (mantendo chaves/group/order fixos).
- `app/ai/query_review.py`: `review_query(source, sql, error, missing, required)` -> `{summary, suggestion}`
  via Claude (reusa `_build_client`/MODEL do `ai/agent.py`).
- Endpoints (`app/main.py`):
  - `GET  /api/cordeiro/queries` -> config atual + required + defaults.
  - `POST /api/cordeiro/queries/validate` -> valida uma fonte (determinístico + Claude).
  - `PUT  /api/cordeiro/queries` -> salva config e dispara recarga (`refresh` + `start_cordeiro_load`).
  - `POST /api/cordeiro/queries/reset` -> apaga override e recarrega.
- **Segurança:** o agent já bloqueia DDL/DML (só SELECT) e limita 5000 linhas. Endpoints
  mutantes (PUT/reset) opcionalmente exigem header `X-Admin-Token` == env `ADMIN_TOKEN`
  quando essa env existir; sem ela, ficam abertos (igual ao restante da API hoje).

## Frontend
- Botão "Fonte de dados" na ribbon, visível só quando `moduleKey === "cordeiro"`.
- `QueryEditor.jsx` (modal): 4 abas (Cotações/Pedidos/Notas Fiscais/Aprovações), cada uma com
  `Tabela`, `Colunas`, `Filtro (WHERE)`, botão **Validar** e painel de resultado
  (✓/✗, colunas retornadas, faltantes em destaque, diagnóstico do Claude + "usar sugestão").
  Rodapé: **Restaurar padrão**, **Salvar e recarregar** (habilitado quando as 4 validam OK).
- `api.js`: `fetchCordeiroQueries`, `validateCordeiroQuery`, `saveCordeiroQueries`, `resetCordeiroQueries`.

## Testes
- `tests/test_cordeiro_queries.py`: merge defaults+override, build da query, `validate_source`
  com conector fake (sucesso, erro de SQL, coluna faltante), save/reset em arquivo temporário.

## Fora de escopo (YAGNI)
- Editar junções/chaves/modelo. Versionamento/histórico de queries. Multiusuário/RBAC fino.
