"""Assistente de IA: traduz perguntas em consultas pandas, executa e analisa.

Fluxo (tool use / Claude):
  pergunta -> Claude escreve uma consulta pandas -> backend executa num
  namespace restrito sobre o event log filtrado -> Claude analisa e responde.
"""
import os
import json
import re
import pathlib

import pandas as pd

from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP

_KNOWLEDGE_DIR = pathlib.Path(__file__).resolve().parent / "knowledge"

MODEL = os.environ.get("AI_MODEL", "claude-sonnet-4-6")
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

_REPORT_TOOL = {
    "name": "emit_report",
    "description": (
        "Emite o RELATÓRIO final estruturado (vira um PDF bonito). Chame UMA única "
        "vez, DEPOIS de coletar os números com run_query. Não responda em texto — "
        "preencha os campos. Use rótulos e valores já formatados (ex.: 'R$ 12.345,67')."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "título curto, ex.: 'Vendas em Aberto'"},
            "subtitle": {"type": "string", "description": "período/escopo, ex.: 'Junho de 2026'"},
            "definition": {"type": "string", "description": "1 frase com o critério adotado"},
            "kpis": {
                "type": "array", "description": "3 a 4 indicadores principais",
                "items": {"type": "object", "properties": {
                    "label": {"type": "string"}, "value": {"type": "string"},
                    "sub": {"type": "string"}, "highlight": {"type": "boolean"},
                }, "required": ["label", "value"]},
            },
            "composition": {
                "type": "object", "description": "barra de composição (opcional)",
                "properties": {
                    "label": {"type": "string"}, "total": {"type": "string"},
                    "segments": {"type": "array", "items": {"type": "object", "properties": {
                        "label": {"type": "string"}, "value": {"type": "number"},
                        "color": {"type": "string", "enum": ["green", "violet", "red", "amber", "gray"]},
                    }}},
                },
            },
            "bars": {
                "type": "array", "description": "1 ou 2 painéis de ranking (top clientes, vendedores…)",
                "items": {"type": "object", "properties": {
                    "title": {"type": "string"}, "subtitle": {"type": "string"},
                    "items": {"type": "array", "items": {"type": "object", "properties": {
                        "label": {"type": "string"}, "value": {"type": "string"}, "amount": {"type": "number"},
                    }}},
                    "note": {"type": "string"},
                }},
            },
            "risks": {
                "type": "array", "description": "2 a 3 riscos/recomendações",
                "items": {"type": "object", "properties": {
                    "title": {"type": "string"}, "text": {"type": "string"},
                    "tone": {"type": "string", "enum": ["red", "amber", "green", "violet"]},
                }},
            },
            "summary": {"type": "string", "description": "1 a 2 frases de fechamento"},
        },
        "required": ["title", "kpis", "summary"],
    },
}

_SQL_TOOL = {
    "name": "run_sql",
    "description": (
        "Executa uma consulta SQL (somente SELECT) DIRETO no banco Sybase IQ e "
        "retorna as linhas. Use `schema.TABELA`, sempre `SELECT TOP n`, aspas simples "
        "para strings/datas, e as strings EXATAMENTE como no catálogo (case-sensitive). "
        "Sem comentários. Não consulta filtros de tela — é o banco inteiro."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"sql": {"type": "string", "description": "SELECT ... (Sybase IQ)"}},
        "required": ["sql"],
    },
}

# palavras que indicam escrita/DDL — bloqueadas (só SELECT de leitura)
_SQL_BANNED = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|merge|grant|revoke|"
    r"exec|execute|call|into|commit|rollback)\b", re.IGNORECASE)


def _load_knowledge() -> str:
    parts = []
    for name in ("catalog.md", "business_rules.md"):
        f = _KNOWLEDGE_DIR / name
        if f.exists():
            parts.append(f.read_text(encoding="utf-8"))
    return "\n\n".join(parts)


def _safe_sql(conn, sql: str):
    """Valida (SELECT-only) e executa a query no banco. Retorna (texto, tabela, erro)."""
    s = (sql or "").strip().rstrip(";").strip()
    low = s.lower()
    if not (low.startswith("select") or low.startswith("with")):
        return None, None, "Apenas SELECT é permitido."
    if ";" in s:
        return None, None, "Envie apenas UMA instrução SELECT (sem ';')."
    if _SQL_BANNED.search(s):
        return None, None, "Comando não permitido — somente SELECT de leitura."
    try:
        d = conn.query(s, limit=200)
    except Exception as exc:  # noqa: BLE001
        return None, None, f"Erro no banco: {exc}"
    if isinstance(d, dict) and d.get("error"):
        return None, None, f"Erro SQL: {str(d['error'])[:300]}"
    cols = [str(c).strip() for c in d.get("columns", [])]
    rows = d.get("rows", [])
    table = {"columns": cols, "rows": [[_cell(v) for v in r] for r in rows[:50]]}
    txt = json.dumps({"columns": cols, "nrows": len(rows), "rows": table["rows"][:50]},
                     ensure_ascii=False, default=str)[:6000]
    return txt, table, None


def _sql_system(module_name: str, dim_label: str, schema: str) -> str:
    return (
        f"Você é um analista de dados do processo **{module_name}** (mineração de processos).\n"
        f"Consulte SEMPRE o banco via a ferramenta **run_sql** (SELECT direto no Sybase IQ). "
        f"O schema deste processo é **{schema}** — use as tabelas `{schema}.SQL_PM_*`.\n"
        f"NÃO há filtros de tela: você consulta o banco INTEIRO. A dimensão de negócio é "
        f"**{dim_label}**.\n\n"
        f"=== CATÁLOGO DE DADOS E REGRAS DE NEGÓCIO ===\n{_load_knowledge()}\n"
        "=== FIM ===\n\n"
        "Rode as consultas necessárias, depois responda em **português**, conciso e citando "
        "os números. Não invente dados. Se um SELECT voltar vazio, revise valor/caixa "
        "(case-sensitive) e tente de novo antes de concluir."
    )


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
        "apenas no que a consulta retornou.\n\n"
        "BOAS PRÁTICAS (a origem é um Sybase IQ, sensível a maiúsc./minúsc.):\n"
        "- Os VALORES são CASE-SENSITIVE. Use as strings EXATAMENTE como aparecem "
        "(as atividades estão listadas acima — copie-as literalmente). NUNCA force a "
        "caixa para comparar (nada de .str.upper()/.lower() antes de igualar).\n"
        "- Para filtrar por um nome que o usuário citou (cliente, vendedor, produto), "
        "faça match SEM diferenciar caixa: "
        "df[df['cliente'].str.contains('nome', case=False, na=False)] — ou primeiro "
        "olhe os valores reais com df['cliente'].dropna().unique().\n"
        "- Se um filtro voltar VAZIO, NÃO conclua nem invente: revise o valor/caixa "
        "e tente de novo (ex.: contains sem caixa) antes de responder.\n"
        "- Escreva código LIMPO e direto, SEM comentários.\n\n"
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


def _history_messages(history, question: str) -> list[dict]:
    """Monta os `messages` do Claude com o histórico (últimas trocas) + a pergunta
    atual. Garante início em 'user' e alternância (a API exige)."""
    raw = []
    for h in (history or [])[-8:]:
        role = h.get("role") if isinstance(h, dict) else None
        text = (h.get("text") if isinstance(h, dict) else "") or ""
        text = str(text).strip()[:2000]
        if role in ("user", "assistant") and text:
            raw.append({"role": role, "content": text})
    raw.append({"role": "user", "content": question})
    msgs: list[dict] = []
    for m in raw:
        if not msgs and m["role"] != "user":
            continue                      # deve começar com user
        if msgs and msgs[-1]["role"] == m["role"]:
            msgs[-1] = m                  # colapsa consecutivos do mesmo papel
        else:
            msgs.append(m)
    return msgs


def ask(question: str, module_name: str, dim_label: str, *,
        log: pd.DataFrame = None, sql_conn=None, schema: str = None,
        allow_report: bool = False, history=None) -> dict:
    client = _build_client()
    sql_mode = sql_conn is not None and bool(schema)
    query_name = "run_sql" if sql_mode else "run_query"
    if sql_mode:
        system = _sql_system(module_name, dim_label, schema)
        query_tool = _SQL_TOOL
    else:
        system = _schema_text(log, module_name, dim_label)
        query_tool = _RUN_QUERY_TOOL
    if history:
        system += ("\n\nHá um histórico da conversa (perguntas/respostas anteriores) "
                   "nas mensagens anteriores — use-o para entender pedidos de "
                   f"acompanhamento (ex.: 'e o segundo?', 'detalha esse cliente'). "
                   f"Sempre reexecute as consultas com {query_name}.")
    if allow_report:
        system += (
            f"\n\nO usuário pediu um RELATÓRIO/PDF. Colete os dados necessários com "
            f"{query_name} (KPIs, rankings por cliente/vendedor, composição, "
            "cancelamentos/retrabalho) e então chame **emit_report** UMA vez com o "
            "relatório estruturado (KPIs, composição, barras, riscos e resumo). "
            "Traga insights e recomendações acionáveis. NÃO responda em texto."
        )
    tools = [query_tool] + ([_REPORT_TOOL] if allow_report else [])
    messages = _history_messages(history, question)
    steps: list[dict] = []
    forced = False   # no modo relatório, força emit_report se a IA tentar texto

    for _ in range(MAX_STEPS + (4 if allow_report else 0)):
        kwargs = {
            "model": MODEL, "max_tokens": 6000 if allow_report else 4000,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "tools": tools, "messages": messages,
        }
        if allow_report:
            # relatório: sem extended thinking (incompatível com tool_choice forçado)
            if forced:
                kwargs["tool_choice"] = {"type": "tool", "name": "emit_report"}
        else:
            kwargs["thinking"] = {"type": "adaptive"}
            kwargs["output_config"] = {"effort": "medium"}
        resp = client.messages.create(**kwargs)

        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            tool_results = []
            report = None
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                if block.name == "emit_report":
                    report = block.input
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id,
                                         "content": "Relatório recebido."})
                elif block.name == "run_query":
                    code = block.input.get("code", "")
                    txt, table, err = _safe_run(log, code)
                    steps.append({"code": code, "table": table, "error": err})
                    tool_results.append({
                        "type": "tool_result", "tool_use_id": block.id,
                        "content": err or txt or "(sem resultado)", "is_error": bool(err),
                    })
                elif block.name == "run_sql":
                    sql = block.input.get("sql", "")
                    txt, table, err = _safe_sql(sql_conn, sql)
                    steps.append({"code": sql, "table": table, "error": err})
                    tool_results.append({
                        "type": "tool_result", "tool_use_id": block.id,
                        "content": err or txt or "(sem resultado)", "is_error": bool(err),
                    })
            if report is not None:
                summary = report.get("summary") or "Relatório gerado."
                return {"answer": summary, "steps": steps, "report": report}
            messages.append({"role": "user", "content": tool_results})
            continue

        # resposta em texto (end_turn)
        answer = "".join(b.text for b in resp.content if b.type == "text").strip()
        if allow_report and not forced:
            # a IA respondeu em texto em vez de emitir o relatório → força emit_report
            messages.append({"role": "assistant", "content": answer or "Análise concluída."})
            messages.append({"role": "user", "content":
                             "Gere agora o RELATÓRIO chamando a ferramenta emit_report "
                             "com os dados já coletados (KPIs, rankings, riscos e resumo)."})
            forced = True
            continue
        return {"answer": answer or "(sem resposta)", "steps": steps}

    return {"answer": "Não consegui concluir a análise em poucos passos. Tente reformular a pergunta.",
            "steps": steps}
