"""O regex de CORS decide quais dominios conseguem falar com a API.

Errar aqui produz um sintoma que engana: o navegador reprova o preflight e a
tela mostra "Failed to fetch", sem status HTTP — igualzinho a backend fora do
ar. Ja aconteceu duas vezes neste projeto (processintelligence e ampartsia).

Ao publicar o frontend num dominio novo, acrescente-o em PERMITIDAS e no regex.
"""
import re

import pytest
from starlette.middleware.cors import CORSMiddleware

from app.main import app

PERMITIDAS = [
    "https://amparts.up.railway.app",
    "https://process-amparts-production.up.railway.app",
    "https://www.processintelligence.com.br",
    "https://processintelligence.com.br",
    "https://pi.ampartsia.com.br",
    "https://www.ampartsia.com.br",
    "https://ampartsia.com.br",
]

NEGADAS = [
    # sufixo colado num dominio maior: o atacante controla o dominio final
    "https://ampartsia.com.br.attacker.com",
    "https://processintelligence.com.br.attacker.com",
    "https://railway.app.attacker.com",
    # parecido, mas outro dominio (sem o ponto separador)
    "https://evilampartsia.com.br",
    "https://naoampartsia.com.br",
    # http puro nao entra
    "http://www.ampartsia.com.br",
    "https://exemplo.com",
]


def _regex() -> str:
    for m in app.user_middleware:
        if m.cls is CORSMiddleware:
            return m.kwargs["allow_origin_regex"]
    raise AssertionError("CORSMiddleware nao encontrado em app.user_middleware")


@pytest.mark.parametrize("origin", PERMITIDAS)
def test_origens_permitidas(origin):
    # Starlette casa com fullmatch — o mesmo criterio e usado aqui de proposito
    assert re.fullmatch(_regex(), origin), f"{origin} deveria ser aceita"


@pytest.mark.parametrize("origin", NEGADAS)
def test_origens_negadas(origin):
    assert not re.fullmatch(_regex(), origin), f"{origin} NAO deveria ser aceita"
