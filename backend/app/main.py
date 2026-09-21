import base64
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")  # backend/.env

import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import auth
from app import data_source
from app import modules as module_registry
from app.modules.cases import build_case_index, page_cases
from app.connectors.csv_connector import CSVConnector
from app.connectors.agent_connector import AgentConnector
from app.mining.dfg import discover_dfg
from app.mining.variants import discover_variants
from app.mining.stats import compute_statistics
from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP

app = FastAPI(title="Process Mining API")

# cache de payloads já enriquecidos (chave = módulo + assinatura dos filtros)
_ENRICH_CACHE: dict = {}
# cache do índice de casos (sorted_log + summary) p/ a Case Explorer não
# re-ordenar o log inteiro a cada busca. Entradas são grandes → limite baixo.
_CASES_CACHE: dict = {}

ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS", "http://localhost:5173"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    # Todo domínio novo por onde o frontend for servido precisa entrar aqui: sem
    # isso o navegador reprova o preflight e a tela mostra "Failed to fetch",
    # sem status HTTP — indistinguível de backend fora do ar. Ver test_cors.py.
    allow_origin_regex=r"https://(.*\.railway\.app|(.*\.)?ma3processmining\.com\.br"
                       r"|(.*\.)?processintelligence\.com\.br"
                       r"|(.*\.)?ampartsia\.com\.br)",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _prewarm():
    """Pré-aquece os logs das fontes reais em background, para o usuário não
    esperar no primeiro clique. Silencioso se a fonte estiver indisponível."""
    # CORDEIRO_PREWARM é o nome antigo da variável, aceito para não reativar o
    # prewarm em ambientes que já a tinham desligada.
    flag = os.environ.get("PREWARM") or os.environ.get("CORDEIRO_PREWARM", "1")
    if flag != "1":
        return
    for key in data_source.REAL_LOADERS:
        data_source.start_real_load(key)


def _apply_filters(
    log: pd.DataFrame,
    fornecedores: list[str],
    start_date: Optional[str],
    end_date: Optional[str],
    ano: Optional[int] = None,
    mes: Optional[int] = None,
    dias: Optional[list[int]] = None,
    produto: Optional[str] = None,
    order_activity: Optional[str] = None,
) -> pd.DataFrame:
    """Filtra o event log por fornecedor/cliente, período, dia e/ou produto.

    A data de referência de cada caso para os filtros de período é o 1º evento
    (case start), salvo se `order_activity` for informado: nesse caso usa a data
    desse evento (a "data do pedido"), e casos sem esse evento ficam de fora dos
    resultados quando há filtro de período.
    """
    if fornecedores:
        dim = "fornecedor" if "fornecedor" in log.columns else (
            "cliente" if "cliente" in log.columns else None)
        if dim:
            log = log[log[dim].isin(fornecedores)]

    if produto and "produto" in log.columns:
        cases_with = log[log["produto"] == produto][CASE_ID].unique()
        log = log[log[CASE_ID].isin(cases_with)]

    if ano or mes or dias or start_date or end_date:
        log[TIMESTAMP] = pd.to_datetime(log[TIMESTAMP])
        ref = _case_ref_date(log, order_activity)

    if ano or mes or dias:
        valid = ref
        if ano:
            valid = valid[valid.dt.year == ano]
        if mes:
            valid = valid[valid.dt.month == mes]
        if dias:
            valid = valid[valid.dt.day.isin(dias)]
        log = log[log[CASE_ID].isin(valid.index)]

    if start_date or end_date:
        valid = ref
        if start_date:
            valid = valid[valid >= pd.Timestamp(start_date)]
        if end_date:
            valid = valid[valid <= pd.Timestamp(end_date)]
        log = log[log[CASE_ID].isin(valid.index)]

    return log


def _case_ref_date(log: pd.DataFrame, order_activity: Optional[str]) -> pd.Series:
    """Data de referência por caso para os filtros de período.

    Sem `order_activity`: o 1º evento do caso (case start) — todo caso tem data.
    Com `order_activity`: a data desse evento; casos que não o têm ficam FORA do
    resultado quando há filtro de período. Só use quando "data do pedido" for
    mesmo o recorte desejado e a ausência de pedido puder ser ignorada.
    """
    if order_activity:
        ped = log[log["activity"] == order_activity]
        if not ped.empty:
            return ped.groupby(CASE_ID)[TIMESTAMP].min()
    return log.groupby(CASE_ID)[TIMESTAMP].min()


def _seq_key(activities: list[str]) -> str:
    """Assinatura curta e estável de uma sequência de atividades (variante).
    Independe da numeração posicional (v1, v2…): identifica pela sequência em si."""
    raw = "".join(str(a) for a in activities)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _apply_variant_filter(log: pd.DataFrame, module, keys: list[str], mode: str) -> pd.DataFrame:
    """Filtra os casos pela variante (sequência de atividades), como o Celonis:
    mode 'include' mantém só os casos das variantes selecionadas; 'exclude' remove.
    A sequência é remapeada pelo activity_map do módulo (mesma base do discover_variants)."""
    if not keys:
        return log
    wanted = set(keys)
    amap = getattr(module, "activity_map", {}) or {}
    tmp = log.copy()
    acts = tmp[ACTIVITY].astype(str)
    tmp[ACTIVITY] = acts.map(amap).fillna(acts)
    tmp[TIMESTAMP] = pd.to_datetime(tmp[TIMESTAMP])
    seqs = (tmp.sort_values([CASE_ID, TIMESTAMP])
               .groupby(CASE_ID, sort=False)[ACTIVITY].agg(tuple))
    case_key = seqs.map(lambda t: _seq_key(list(t)))
    hit = case_key.isin(wanted)
    keep = case_key.index[~hit if mode == "exclude" else hit]
    return log[log[CASE_ID].isin(keep)]


def _apply_activity_filter(log: pd.DataFrame, module, act_id, act_mode) -> pd.DataFrame:
    """Filtra os casos por uma atividade (with / without / start / end)."""
    if not act_id or not act_mode:
        return log
    raws = set(module.raw_activities(act_id))
    log[TIMESTAMP] = pd.to_datetime(log[TIMESTAMP])
    ordered = log.sort_values([CASE_ID, TIMESTAMP])
    if act_mode == "with":
        cases = ordered[ordered[ACTIVITY].isin(raws)][CASE_ID].unique()
    elif act_mode == "without":
        has = set(ordered[ordered[ACTIVITY].isin(raws)][CASE_ID].unique())
        cases = [c for c in ordered[CASE_ID].unique() if c not in has]
    elif act_mode == "start":
        firsts = ordered.groupby(CASE_ID, sort=False)[ACTIVITY].first()
        cases = firsts[firsts.isin(raws)].index
    elif act_mode == "end":
        lasts = ordered.groupby(CASE_ID, sort=False)[ACTIVITY].last()
        cases = lasts[lasts.isin(raws)].index
    else:
        return log
    return log[log[CASE_ID].isin(cases)]


def _guard_real(key: str) -> None:
    """Fonte real (AM Parts): carga assíncrona. Nunca bloqueia/recarrega
    dentro do request — devolve 503 enquanto carrega (o front reexibe e reconsulta)."""
    if not data_source.is_real(key) or data_source._state["path"] is not None:
        return
    st = data_source.real_status(key)
    if st == "ready":
        return
    data_source.start_real_load(key)
    module = module_registry.get(key)
    label = getattr(module, "name", None) or key.capitalize()
    if st == "error":
        raise HTTPException(status_code=503,
                            detail=f"Falha ao carregar {label}: {data_source.real_error(key)}")
    raise HTTPException(status_code=503,
                        detail=f"Carregando dados do {label}… aguarde ~1–2 min e recarregue.")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/process-graph")
def process_graph():
    return discover_dfg(data_source.get_log())


@app.get("/api/variants")
def variants():
    return discover_variants(data_source.get_log())


@app.get("/api/statistics")
def statistics():
    return compute_statistics(data_source.get_log())


@app.get("/api/debug/config")
def debug_config():
    """Diagnóstico seguro: mostra o que o backend enxerga, sem vazar a chave.

    Endpoint é público, então nada de host/usuário do banco aqui — só os
    booleanos que respondem "por que o Railway não está lendo do MySQL?".
    """
    from app.connectors.mysql_connector import MySQLConnector
    from app.sources.amparts import get_origem

    url = os.environ.get("AGENT_URL", "")
    key = os.environ.get("AGENT_API_KEY", "")
    db = MySQLConnector()
    return {
        "agent_url_set": bool(url),
        "agent_url_host": url.split("//")[-1].split("/")[0] if url else None,
        "agent_api_key_set": bool(key),
        "agent_api_key_len": len(key),
        "anthropic_key_set": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "amparts_status": data_source.real_status("amparts"),
        "amparts_error": data_source.real_error("amparts"),
        # "db" = leu do MySQL; "csv" = caiu na contingência (dado congelado)
        "amparts_origem": get_origem(),
        "db_password_set": bool(db.password),
        "db_name": db.database,
        "db_ca_set": bool(db.ca),
    }


def _require_admin(token: Optional[str]) -> None:
    """Gate opcional: se ADMIN_TOKEN existir no ambiente, exige o header."""
    admin = os.environ.get("ADMIN_TOKEN")
    if admin and token != admin:
        raise HTTPException(status_code=403, detail="Token de administração inválido")


def _reload_real(key: str):
    data_source.refresh(key)
    _ENRICH_CACHE.clear()
    _CASES_CACHE.clear()
    data_source.start_real_load(key)


# ── autenticação por usuário + acesso por módulo ─────────────────────────────
class LoginBody(BaseModel):
    email: str
    password: str


@app.post("/api/login")
def login(body: LoginBody):
    u = auth.verify_login(body.email, body.password)
    if not u:
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos")
    return auth.public_user(u)


def require_module_access(key: str, authorization: Optional[str] = Header(default=None)):
    """Dependency: exige token válido e que o módulo {key} esteja liberado."""
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    user = auth.user_from_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Não autenticado")
    if key not in user.get("modules", []):
        raise HTTPException(status_code=403, detail="Sem acesso a este módulo")


@app.get("/api/modules/{key}/status", dependencies=[Depends(require_module_access)])
def module_status(key: str):
    """Status de carga de uma fonte: ready | loading | error | idle + progresso %."""
    if not data_source.is_real(key):
        return {"status": "ready", "progress": 100, "error": None}
    return {
        "status": data_source.real_status(key),
        "progress": data_source.real_progress(key),
        "error": data_source.real_error(key),
    }


@app.post("/api/modules/{key}/refresh", dependencies=[Depends(require_module_access)])
def refresh_module(key: str, x_admin_token: Optional[str] = Header(default=None)):
    """Descarta o cache da fonte real e recarrega do banco (sob demanda)."""
    if not data_source.is_real(key):
        raise HTTPException(status_code=400, detail=f"'{key}' não é uma fonte recarregável")
    _require_admin(x_admin_token)
    _reload_real(key)
    return {"ok": True, "status": data_source.real_status(key)}


@app.get("/api/modules/{key}", dependencies=[Depends(require_module_access)])
def get_module(
    key: str,
    fornecedores: list[str] = Query(default=[]),
    start_date: Optional[str] = Query(default=None),
    end_date:   Optional[str] = Query(default=None),
    ano: Optional[int] = Query(default=None),
    mes: Optional[int] = Query(default=None),
    dias: list[int] = Query(default=[]),
    produto: Optional[str] = Query(default=None),
    act_id: Optional[str] = Query(default=None),
    act_mode: Optional[str] = Query(default=None),
    variant: list[str] = Query(default=[]),
    variant_mode: str = Query(default="include"),
):
    module = module_registry.get(key)
    if not module:
        raise HTTPException(status_code=404, detail=f"Modulo '{key}' nao encontrado")
    _guard_real(key)
    ck = (key, tuple(sorted(fornecedores)), start_date, end_date, ano, mes, tuple(sorted(dias)), produto,
          act_id, act_mode, tuple(sorted(variant)), variant_mode)
    cached = _ENRICH_CACHE.get(ck)
    if cached is not None:
        return cached
    log = data_source.get_log(module_key=key)
    log = _apply_filters(log, fornecedores, start_date, end_date, ano, mes, dias, produto,
                         order_activity=module.order_activity)
    log = _apply_activity_filter(log, module, act_id, act_mode)
    log = _apply_variant_filter(log, module, variant, variant_mode)
    if log.empty or log[CASE_ID].nunique() == 0:
        raise HTTPException(status_code=422, detail="Nenhum caso encontrado para os filtros aplicados")
    payload = module.enrich(log)
    # chave de variante (assinatura da sequência) p/ o front filtrar pela seleção
    for v in payload.get("variants", []):
        path = v.get("path") or []
        v["key"] = _seq_key(path[1:-1])
    if len(_ENRICH_CACHE) > 64:
        _ENRICH_CACHE.clear()
    _ENRICH_CACHE[ck] = payload
    return payload


@app.get("/api/modules/{key}/cases", dependencies=[Depends(require_module_access)])
def get_cases(
    key: str,
    fornecedores: list[str] = Query(default=[]),
    start_date: Optional[str] = Query(default=None),
    end_date:   Optional[str] = Query(default=None),
    ano: Optional[int] = Query(default=None),
    mes: Optional[int] = Query(default=None),
    dias: list[int] = Query(default=[]),
    produto: Optional[str] = Query(default=None),
    act_id: Optional[str] = Query(default=None),
    act_mode: Optional[str] = Query(default=None),
    variant: list[str] = Query(default=[]),
    variant_mode: str = Query(default="include"),
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=500),
):
    module = module_registry.get(key)
    if not module:
        raise HTTPException(status_code=404, detail=f"Modulo '{key}' nao encontrado")
    _guard_real(key)

    # índice (ordenar+resumir) é caro → cacheado por assinatura de filtro.
    # A busca por Case Id (q) e a página (limit) ficam fora da chave: rodam barato.
    sig = (key, tuple(sorted(fornecedores)), start_date, end_date, ano, mes, tuple(sorted(dias)), produto,
           act_id, act_mode, tuple(sorted(variant)), variant_mode)
    idx = _CASES_CACHE.get(sig)
    if idx is None:
        log = data_source.get_log(module_key=key)
        log = _apply_filters(log, fornecedores, start_date, end_date, ano, mes, dias, produto,
                             order_activity=module.order_activity)
        log = _apply_activity_filter(log, module, act_id, act_mode)
        log = _apply_variant_filter(log, module, variant, variant_mode)
        if log.empty or log[CASE_ID].nunique() == 0:
            return {"cases": [], "total": 0}
        idx = build_case_index(log)
        if len(_CASES_CACHE) > 8:
            _CASES_CACHE.clear()
        _CASES_CACHE[sig] = idx
    sorted_log, summary = idx
    src = _detail_source(key)
    event_attrs = getattr(src, "EVENT_ATTRS", None) if src else None
    return page_cases(sorted_log, summary, q=q, limit=limit, event_attrs=event_attrs)


def _detail_source(key: str):
    """Fonte da tela Detalhes por módulo (expõe DETAIL_COLS + get_cases_detail)."""
    if key == "amparts":
        from app.sources import amparts as src
        return src
    return None


@app.get("/api/modules/{key}/details", dependencies=[Depends(require_module_access)])
def get_details(
    key: str,
    ano: Optional[int] = Query(default=None),
    mes: Optional[int] = Query(default=None),
    dias: list[int] = Query(default=[]),
    produto: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    colf: list[str] = Query(default=[]),
    act_id: Optional[str] = Query(default=None),
    act_mode: Optional[str] = Query(default=None),
    variant: list[str] = Query(default=[]),
    variant_mode: str = Query(default="include"),
    limit: int = Query(default=500),
    offset: int = Query(default=0),
):
    """Detalhe por caso/item (tela Detalhes), por módulo.

    `colf`: filtros por coluna no formato "chave:valor" (contains, sem
    distinção de maiúsculas) — varre a base inteira antes de paginar.
    `variant`/`act_id`: mesmos filtros das outras telas (via event log)."""
    module = module_registry.get(key)
    if not module:
        raise HTTPException(status_code=404, detail=f"Modulo '{key}' nao encontrado")
    _guard_real(key)
    src = _detail_source(key)
    cols = getattr(src, "DETAIL_COLS", []) if src else []
    df = src.get_cases_detail() if src else pd.DataFrame()
    if df.empty:
        return {"rows": [], "total": 0, "columns": cols}

    df = df.copy()
    mask = pd.Series(True, index=df.index)
    if (ano or mes or dias) and "data" in df.columns:
        dt = pd.to_datetime(df["data"], errors="coerce")
        if ano:
            mask &= (dt.dt.year == ano)
        if mes:
            mask &= (dt.dt.month == mes)
        if dias:
            mask &= dt.dt.day.isin(dias)
    if produto and "produto" in df.columns:
        mask &= (df["produto"].astype(str) == produto)
    if q and q.strip():
        ql = q.strip().lower()
        text_cols = [c["key"] for c in cols if c.get("fmt") in (None, "text", "id")]
        hay = None
        for c in text_cols:
            if c in df.columns:
                s = df[c].astype(str).str.lower()
                hay = s if hay is None else (hay + " " + s)
        if hay is not None:
            mask &= hay.str.contains(ql, regex=False, na=False)
    # filtros por coluna (chave:valor, contains case-insensitive)
    for cf in colf:
        ckey, _, cval = cf.partition(":")
        cval = cval.strip().lower()
        if cval and ckey in df.columns:
            mask &= df[ckey].astype(str).str.lower().str.contains(cval, regex=False, na=False)

    # filtro por variante / atividade — usa o event log (sequências) e cruza
    # pelos case_ids. Só aplica quando o detalhe tem a coluna oculta "_case_id".
    if (variant or act_id) and "_case_id" in df.columns:
        elog = data_source.get_log(module_key=key)
        elog = _apply_filters(elog, [], None, None, ano, mes, dias, produto,
                              order_activity=module.order_activity)
        elog = _apply_activity_filter(elog, module, act_id, act_mode)
        elog = _apply_variant_filter(elog, module, variant, variant_mode)
        allowed = set(elog[CASE_ID].astype(str).unique())
        mask &= df["_case_id"].astype(str).isin(allowed)

    df = df[mask].drop(columns=["_case_id"], errors="ignore")

    total = int(len(df))
    page = df.iloc[offset: offset + max(0, limit)]
    rows = json.loads(page.to_json(orient="records"))
    return {"rows": rows, "total": total, "columns": cols}


class AskBody(BaseModel):
    question: str
    history: list = []   # últimas trocas [{role, text}] p/ contexto de follow-up


@app.get("/api/ai/status")
def ai_status():
    from app.ai.agent import is_configured
    return {"configured": is_configured()}


@app.post("/api/modules/{key}/ask", dependencies=[Depends(require_module_access)])
def ask_module(
    key: str,
    body: AskBody,
    fornecedores: list[str] = Query(default=[]),
    start_date: Optional[str] = Query(default=None),
    end_date:   Optional[str] = Query(default=None),
    ano: Optional[int] = Query(default=None),
    mes: Optional[int] = Query(default=None),
):
    from app.ai.agent import ask, is_configured
    module = module_registry.get(key)
    if not module:
        raise HTTPException(status_code=404, detail=f"Modulo '{key}' nao encontrado")
    if not is_configured():
        raise HTTPException(status_code=503,
                            detail="Assistente de IA não configurado. Defina ANTHROPIC_API_KEY no backend.")
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Pergunta vazia")

    # SQL direto no banco (ignora filtros de tela): schema + conector do agent
    src = _detail_source(key)
    schema = getattr(src, "SCHEMA", None)
    conn = AgentConnector()
    if not (schema and conn.configured()):
        raise HTTPException(status_code=503,
                            detail="Fonte SQL não configurada para este módulo.")
    dim_label = getattr(module, "dimension", None) or "Dimensão"
    wants_report = bool(re.search(r"\b(pdf|relat[óo]rios?)\b", body.question, re.IGNORECASE))
    try:
        result = ask(body.question, module.name, dim_label, sql_conn=conn, schema=schema,
                     allow_report=wants_report, history=body.history)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Falha ao consultar a IA: {exc}")

    # relatório/PDF: monta o PDF (base64) para download. Se a IA emitiu o relatório
    # estruturado, usa o template rico; senão cai no PDF simples. Falha aqui não
    # derruba a resposta em texto.
    if wants_report:
        try:
            from app.ai.report_pdf import build_pdf, build_report_pdf
            rep = result.pop("report", None)
            pdf_bytes = None
            if rep:
                try:
                    pdf_bytes = build_report_pdf(rep, module.name)   # template rico
                except Exception:  # noqa: BLE001 — cai no simples se o rico falhar
                    pdf_bytes = None
            if pdf_bytes is None:
                pdf_bytes = build_pdf(module.name, body.question,
                                      result.get("answer", ""), result.get("steps"))
            result["pdf"] = base64.b64encode(pdf_bytes).decode("ascii")
            result["pdfName"] = f"relatorio-{key}.pdf"
        except Exception as exc:  # noqa: BLE001
            result["pdfError"] = str(exc)
    result.pop("report", None)
    return result


@app.get("/api/modules/{key}/user/{name}", dependencies=[Depends(require_module_access)])
def get_user(
    key: str,
    name: str,
    fornecedores: list[str] = Query(default=[]),
    start_date: Optional[str] = Query(default=None),
    end_date:   Optional[str] = Query(default=None),
    ano: Optional[int] = Query(default=None),
    mes: Optional[int] = Query(default=None),
    act_id: Optional[str] = Query(default=None),
    act_mode: Optional[str] = Query(default=None),
):
    from app.modules.userprod import user_detail
    module = module_registry.get(key)
    if not module:
        raise HTTPException(status_code=404, detail=f"Modulo '{key}' nao encontrado")
    log = data_source.get_log(module_key=key)
    log = _apply_filters(log, fornecedores, start_date, end_date, ano, mes,
                         order_activity=module.order_activity)
    log = _apply_activity_filter(log, module, act_id, act_mode)
    return user_detail(log, name)


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    dest = Path("data/uploaded.csv")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(await file.read())
    try:
        CSVConnector(str(dest)).load()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    data_source.set_source(str(dest))
    _ENRICH_CACHE.clear()
    _CASES_CACHE.clear()
    return {"status": "ok", "filename": file.filename}
