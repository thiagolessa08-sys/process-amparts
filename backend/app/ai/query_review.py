"""Revisão de query com Claude: diagnóstico + sugestão de correção.

Best-effort — se a IA não estiver configurada, devolve vazio. Usado pela
validação do editor de queries-base do Cordeiro.
"""
import json
import os

from app.ai.agent import MODEL, _build_client, is_configured

_SYS = (
    "Você revisa uma consulta SQL (SELECT, dialeto Sybase IQ 16) que alimenta um "
    "pipeline de mineração de processos. A consulta NÃO pode ter DDL/DML — só SELECT. "
    "Ela deve devolver um conjunto de colunas obrigatórias (aliases contam). "
    "Responda SEMPRE em português, de forma curta e objetiva."
)


def review_query(source_label: str, sql: str, error: str | None,
                 missing: list[str], required: list[str]) -> dict:
    """Retorna {summary, suggestion}. Vazio se IA não configurada ou em erro."""
    if not is_configured():
        return {"summary": None, "suggestion": None}

    parts = [
        f"Fonte: {source_label}.",
        f"Colunas obrigatórias: {', '.join(required)}.",
        f"Consulta de validação executada:\n{sql}",
    ]
    if error:
        parts.append(f"O agent retornou ERRO ao executar:\n{error}")
    if missing:
        parts.append(f"Faltaram colunas obrigatórias no resultado: {', '.join(missing)}.")
    if not error and not missing:
        parts.append("A consulta rodou e trouxe todas as colunas obrigatórias.")
    parts.append(
        "Responda em JSON puro com as chaves: "
        '"summary" (1-2 frases diagnosticando) e '
        '"suggestion" (um SELECT corrigido, ou null se já estiver ok ou não houver correção óbvia). '
        "Não inclua texto fora do JSON."
    )
    prompt = "\n\n".join(parts)

    try:
        client = _build_client()
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1200,
            system=[{"type": "text", "text": _SYS}],
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        data = _parse_json(text)
        return {
            "summary": (data.get("summary") or None) if isinstance(data, dict) else text or None,
            "suggestion": (data.get("suggestion") or None) if isinstance(data, dict) else None,
        }
    except Exception as exc:  # noqa: BLE001
        return {"summary": f"Não foi possível revisar com a IA: {exc}", "suggestion": None}


def _parse_json(text: str):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except Exception:
        a, b = text.find("{"), text.rfind("}")
        if 0 <= a < b:
            try:
                return json.loads(text[a:b + 1])
            except Exception:
                return {}
        return {}
