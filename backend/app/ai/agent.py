"""Assistente de IA: traduz perguntas em consultas pandas, executa e analisa.

Fluxo (tool use / Claude):
  pergunta -> Claude escreve uma consulta pandas -> backend executa num
  namespace restrito sobre o event log filtrado -> Claude analisa e responde.
"""
import os
import json

import pandas as pd

from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP

MODEL = os.environ.get("AI_MODEL", "claude-opus-4-8")
MAX_STEPS = 5

_RUN_QUERY_TOOL = {
    "name": "run_query",
    "description": (
        "Executa uma consulta pandas (somente leitura) sobre o DataFrame `df` "
        "que contém o event log já filtrado. Escreva código Python que usa `df` "
        "e `pd`, e atribua o resultado final à variável `result` "
        "(pode ser DataFrame, Series, número ou string). "
        "Não use import, open, arquivos ou rede."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Código Python pandas. Ex.: result = df.groupby('fornecedor')['valor'].sum().sort_values(ascending=False).head(5)",
            }
        },
        "required": ["code"],
    },
}

_BANNED = ("__", "import", "open(", "exec(", "eval(", "compile(",
           "os.", "sys.", "subprocess", "globals(", "locals(", "getattr", "setattr")

_SAFE_BUILTINS = {
    "len": len, "min": min, "max": max, "sum": sum, "sorted": sorted, "round": round,
    "abs": abs, "range": range, "list": list, "dict": dict, "set": set, "tuple": tuple,
    "float": float, "int": int, "str": str, "bool": bool, "enumerate": enumerate,
    "zip": zip, "map": map, "filter": filter, "any": any, "all": all,
}


def is_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _build_client():
    import anthropic
    # Em rede corporativa com inspeção SSL, AI_INSECURE_SSL=1 desliga a verificação.
    if os.environ.get("AI_INSECURE_SSL") == "1":
        from anthropic import DefaultHttpxClient
        return anthropic.Anthropic(http_client=DefaultHttpxClient(verify=False))
    return anthropic.Anthropic()


def _schema_text(log: pd.DataFrame, module_name: str, dim_label: str) -> str:
    cols = []
    for c in log.columns:
        cols.append(f"  - {c} ({log[c].dtype})")
    acts = [str(a) for a in log[ACTIVITY].dropna().unique().tolist()]
    return (
        f"Você é um analista de dados do processo **{module_name}** (mineração de processos).\n"
        f"Há um DataFrame pandas chamado `df` (um event log). Cada linha é um EVENTO; "
        f"um CASO é identificado por `{CASE_ID}`.\n\n"
        f"Colunas de `df`:\n" + "\n".join(cols) + "\n\n"
        f"Atividades possíveis (coluna `{ACTIVITY}`): {', '.join(acts)}\n"
        f"A dimensão de negócio é **{dim_label}**.\n\n"
        "Para responder, use a ferramenta `run_query` com código pandas que atribui o "
        "resultado a `result`. Pense em métricas por caso quando fizer sentido "
        f"(ex.: agrupar por `{CASE_ID}`). Após obter os dados, responda em **português**, "
        "de forma concisa e objetiva, citando os números. Não invente dados: baseie-se "
        "apenas no que a consulta retornou.\n"
        "Se o usuário pedir um **relatório** ou **PDF**, faça uma análise mais completa "
        "(rode as consultas necessárias) e estruture a resposta com títulos em markdown "
        "(`##` seção, `###` subseção): ex. Visão geral, Principais clientes/produtos, "
        "Retrabalho/cancelamentos, Riscos e Resumo — cada um com bullets e os números."
    )


def _serialize(result):
    """Retorna (texto_para_o_modelo, tabela_para_o_frontend|None)."""
    if isinstance(result, pd.DataFrame):
        head = result.head(50)
        table = {"columns": [str(c) for c in head.columns],
                 "rows": [[_cell(v) for v in row] for row in head.itertuples(index=False, name=None)]}
        txt = json.dumps({"shape": list(result.shape), "rows": table["rows"][:50],
                          "columns": table["columns"]}, ensure_ascii=False, default=str)
        return txt[:6000], table
    if isinstance(result, pd.Series):
        s = result.head(50)
        table = {"columns": ["índice", str(result.name or "valor")],
                 "rows": [[_cell(i), _cell(v)] for i, v in s.items()]}
        txt = json.dumps({"length": int(result.shape[0]), "rows": table["rows"][:50]},
                         ensure_ascii=False, default=str)
        return txt[:6000], table
    return (str(result)[:2000], None)


def _cell(v):
    if isinstance(v, (pd.Timestamp,)):
        return v.isoformat()
    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            return str(v)
    return v


def _safe_run(df: pd.DataFrame, code: str):
    """Executa o código pandas num namespace restrito. Retorna (texto, tabela, erro)."""
    low = code.lower()
    for bad in _BANNED:
        if bad in low:
            return None, None, f"Consulta rejeitada: uso não permitido de '{bad}'."
    glb = {"__builtins__": _SAFE_BUILTINS, "pd": pd, "df": df}
    loc: dict = {}
    try:
        exec(code, glb, loc)  # noqa: S102 — sandbox restrito, somente leitura
    except Exception as exc:  # noqa: BLE001
        return None, None, f"Erro ao executar: {type(exc).__name__}: {exc}"
    result = loc.get("result", glb.get("result"))
    if result is None:
        return None, None, "A consulta não atribuiu nada a `result`."
    txt, table = _serialize(result)
    return txt, table, None


def ask(question: str, log: pd.DataFrame, module_name: str, dim_label: str) -> dict:
    client = _build_client()
    system = _schema_text(log, module_name, dim_label)
    messages = [{"role": "user", "content": question}]
    steps: list[dict] = []

    for _ in range(MAX_STEPS):
        resp = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            tools=[_RUN_QUERY_TOOL],
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            messages=messages,
        )

        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            tool_results = []
            for block in resp.content:
                if block.type == "tool_use" and block.name == "run_query":
                    code = block.input.get("code", "")
                    txt, table, err = _safe_run(log, code)
                    steps.append({"code": code, "table": table, "error": err})
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": err or txt or "(sem resultado)",
                        "is_error": bool(err),
                    })
            messages.append({"role": "user", "content": tool_results})
            continue

        answer = "".join(b.text for b in resp.content if b.type == "text").strip()
        return {"answer": answer or "(sem resposta)", "steps": steps}

    return {"answer": "Não consegui concluir a análise em poucos passos. Tente reformular a pergunta.",
            "steps": steps}
