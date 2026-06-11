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

## Deploy (Railway)

Backend e frontend são publicados no [Railway](https://railway.app) (cada um é
um serviço, com `railway.toml` próprio). O deploy é automatizado por GitHub
Actions (`.github/workflows/deploy.yml`): todo push na `main` publica os dois
serviços.

Para ativar (uma vez só):

1. **Railway → projeto → Settings → Tokens** → gere um *Project Token*.
2. **GitHub → repo → Settings → Secrets and variables → Actions** → crie o
   secret `RAILWAY_TOKEN` com esse valor.
3. Confirme que os serviços no Railway se chamam `backend` e `frontend`
   (senão, ajuste a matriz `service` no workflow).

Variáveis de ambiente importantes:

- **frontend** — `VITE_API_URL` apontando para a URL pública do backend.
- **backend** — `ALLOWED_ORIGINS` com a URL do frontend (o CORS já libera
  `*.railway.app` por regex).

Também é possível disparar manualmente em **Actions → "Deploy (Railway)" → Run
workflow**.

