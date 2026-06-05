# Plataforma de Process Mining

Produto web de mineração de processos (estilo Celonis), modular, começando pelo
módulo Financeiro com os processos **P2P** e **O2C**.

- Design: [docs/superpowers/specs/2026-06-05-process-mining-platform-design.md](docs/superpowers/specs/2026-06-05-process-mining-platform-design.md)
- Plano da Fatia 1: [docs/superpowers/plans/2026-06-05-fatia1-esqueleto-vertical-p2p.md](docs/superpowers/plans/2026-06-05-fatia1-esqueleto-vertical-p2p.md)

## Status

**Fatia 1 — Esqueleto vertical P2P (concluída):** importa um event log, descobre o
fluxo do processo (Directly-Follows Graph) e desenha o grafo na tela.

## Como rodar

### Backend (FastAPI)

```powershell
cd backend
python -m venv .venv                       # primeira vez
.venv\Scripts\python -m pip install -r requirements.txt --trusted-host pypi.org --trusted-host files.pythonhosted.org
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

API em http://localhost:8000 — endpoints: `/api/health`, `/api/process-graph`.

> Nota: os flags `--trusted-host` contornam a inspeção SSL do proxy corporativo.

### Frontend (React + Vite)

```powershell
cd frontend
npm install                                # primeira vez
npm run dev
```

App em http://localhost:5173 (precisa do backend rodando em paralelo).

### Testes do backend

```powershell
cd backend
.venv\Scripts\python -m pytest -v
```

## Estrutura

```
backend/   API FastAPI, conectores, núcleo de mineração, gerador de dados demo
frontend/  React + React Flow (grafo do processo)
docs/      design e planos de implementação
```
