"""Autenticação leve por usuário com acesso por módulo (meio-termo).

Usuários ficam num JSON (backend/data/users.json, override por USERS_CONFIG)
com senha em SHA-256 e a lista de módulos permitidos. O login devolve um token
stateless `email|HMAC(email, AUTH_SECRET)`; cada request a /api/modules/{key}
verifica o token e se o módulo está liberado para o usuário.
"""
import hashlib
import hmac
import json
import os
from pathlib import Path

_SECRET = os.environ.get("AUTH_SECRET", "fluxo-mining-dev-secret")

# fallback (produção sem users.json): senhas veddara123/biolab123/cordeiro123/fluxo123
DEFAULT_USERS = [
    {"email": "veddara@fluxo.com", "name": "Veddara", "modules": ["vedara"],
     "pass_sha256": "ed9d8e8c9652426151cc9d1a6b3f59e06f71b0d1bab44eda57621ee5c369b873"},
    {"email": "biolab@fluxo.com", "name": "Biolab", "modules": ["biolab"],
     "pass_sha256": "da13ef6f75dab6c675b1fbcd13b61eb5954b44ef8a0ff82398d8665184f1ec85"},
    {"email": "cordeiro@fluxo.com", "name": "Cordeiro", "modules": ["cordeiro"],
     "pass_sha256": "953dc82f1be1752afcf6b22b75e895eb99c393d54cf14e5f77e0008e53fb9c3d"},
    {"email": "admin@fluxo.com", "name": "Admin", "modules": ["vedara", "biolab", "cordeiro"],
     "pass_sha256": "d1cf075905f55ad7676c780045fa33b8391dcb60ac33c5457948ac531c6242e4"},
]


def _config_path() -> Path:
    default = Path(__file__).resolve().parent.parent / "data" / "users.json"
    return Path(os.environ.get("USERS_CONFIG", str(default)))


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def load_users() -> list[dict]:
    path = _config_path()
    if not path.exists():
        return DEFAULT_USERS
    try:
        users = json.loads(path.read_text(encoding="utf-8")).get("users", [])
        return users or DEFAULT_USERS
    except Exception:  # noqa: BLE001
        return DEFAULT_USERS


def find_user(email: str) -> dict | None:
    email = (email or "").strip().lower()
    for u in load_users():
        if str(u.get("email", "")).strip().lower() == email:
            return u
    return None


def verify_login(email: str, password: str) -> dict | None:
    u = find_user(email)
    if not u:
        return None
    if not hmac.compare_digest(str(u.get("pass_sha256", "")), _sha256(password or "")):
        return None
    return u


def make_token(email: str) -> str:
    email = (email or "").strip().lower()
    sig = hmac.new(_SECRET.encode("utf-8"), email.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{email}|{sig}"


def user_from_token(token: str | None) -> dict | None:
    if not token or "|" not in token:
        return None
    email, sig = token.rsplit("|", 1)
    expected = hmac.new(_SECRET.encode("utf-8"), email.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    return find_user(email)


def public_user(u: dict) -> dict:
    """Dados do usuário para o frontend (sem o hash)."""
    return {
        "email": u.get("email"),
        "name": u.get("name") or str(u.get("email", "")).split("@")[0],
        "modules": list(u.get("modules", [])),
        "token": make_token(u.get("email", "")),
    }
