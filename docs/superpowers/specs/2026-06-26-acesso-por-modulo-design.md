# Acesso por módulo (login + permissões)

Data: 2026-06-26

## Objetivo
Quatro usuários com visibilidade restrita por processo:
- `veddara@fluxo.com` → só **Veddara** (`vedara`)
- `biolab@fluxo.com` → só **Biolab** (`biolab`)
- `cordeiro@fluxo.com` → só **Cordeiro** (`cordeiro`)
- `admin@fluxo.com` → **todos** os três

Nível "meio-termo": o frontend esconde as abas não permitidas **e** o backend
bloqueia chamadas diretas a módulos fora da permissão (não é JWT completo).

## Store de usuários
`backend/data/users.json` (override por env `USERS_CONFIG`):
```json
{ "users": [
  { "email": "veddara@fluxo.com",  "name": "Veddara",  "modules": ["vedara"],
    "pass_sha256": "<hash>" },
  { "email": "biolab@fluxo.com",   "name": "Biolab",   "modules": ["biolab"],   "pass_sha256": "<hash>" },
  { "email": "cordeiro@fluxo.com", "name": "Cordeiro", "modules": ["cordeiro"], "pass_sha256": "<hash>" },
  { "email": "admin@fluxo.com",    "name": "Admin",    "modules": ["vedara","biolab","cordeiro"], "pass_sha256": "<hash>" }
] }
```
Senha guardada como **SHA-256** (sem texto puro). Trocar senha = gerar novo hash.

## Backend (FastAPI) — `app/auth.py`
- `load_users()`: lê o JSON (defaults se ausente), com cache leve.
- `verify_login(email, password)`: confere `sha256(password)` com `pass_sha256`.
- Token **stateless**: `token = email + "|" + hmac_sha256(email, AUTH_SECRET)`
  (`AUTH_SECRET` via env; fallback fixo para dev). `user_from_token(token)`
  separa, recomputa o HMAC (comparação constante) e devolve o usuário.
- `POST /api/login {email, password}` → `{email, name, modules, token}` ou 401.
- Dependency `require_module_access(key)`: lê `Authorization: Bearer <token>`,
  resolve o usuário, e se `key ∉ user.modules` → **403**. Se não houver token
  válido → 401. Aplicada em `/api/modules/{key}` e derivados (`/status`,
  `/details`, `/cases`, `/user`, `/ask`).

## Frontend
- `ScreenLogin`: `submit` chama `POST /api/login`; em sucesso salva
  `{email, name, modules, token}` no localStorage (`pm-auth`).
- `api.js`: header `Authorization: Bearer <token>` em todas as chamadas;
  trata 401 (sessão inválida → logout) e 403 (sem acesso → aviso).
- `App.jsx`: as abas (`TABS`) são filtradas por `auth.modules`; `moduleKey`
  default = primeiro permitido. Usuário de 1 módulo abre direto nele.

## Fora de escopo (YAGNI)
Cadastro/reset de senha, papéis além da lista de módulos, expiração de token.
`ADMIN_TOKEN` atual (refresh/queries) permanece como está.

## Verificação
- Login de cada usuário → vê só suas abas; admin vê 3.
- `curl` direto em `/api/modules/<outro>` com token de usuário restrito → 403;
  sem token → 401.
- Build do frontend OK; login real funciona contra `/api/login`.
