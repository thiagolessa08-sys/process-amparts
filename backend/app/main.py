import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")  # backend/.env

import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import data_source
from app import modules as module_registry
from app.modules.cases import build_case_index, page_cases
from app.connectors.csv_connector import CSVConnector
from app.sources import cordeiro_queries as cq
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
    allow_origin_regex=r"https://.*\.railway\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _prewarm():
    """Pré-aquece os logs das fontes reais (carga ~90s do agent) em background,
    para o usuário não esperar no primeiro clique. Silencioso se o agent estiver fora."""
    if os.environ.get("CORDEIRO_PREWARM", "1") != "1":
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
) -> pd.DataFrame:
    """Filtra o event log por fornecedor/cliente, período e/ou ano e mês do pedido."""
    if fornecedores:
        dim = "fornecedor" if "fornecedor" in log.columns else (
            "cliente" if "cliente" in log.columns else None)
        if dim:
            log = log[log[dim].isin(fornecedores)]

    if ano or mes:
        # filtra pelo ano/mês do primeiro evento do caso (data do pedido)
        log[TIMESTAMP] = pd.to_datetime(log[TIMESTAMP])
        case_start = log.groupby(CASE_ID)[TIMESTAMP].min()
        valid = case_start
        if ano:
            valid = valid[valid.dt.year == ano]
        if mes:
            valid = valid[valid.dt.month == mes]
        log = log[log[CASE_ID].isin(valid.index)]

    if start_date or end_date:
        # filtra pelo timestamp do primeiro evento do caso (case start date)
        log[TIMESTAMP] = pd.to_datetime(log[TIMESTAMP])
        case_start = log.groupby(CASE_ID)[TIMESTAMP].min()
        valid_cases = case_start.index
        if start_date:
            valid_cases = case_start[case_start >= pd.Timestamp(start_date)].index
        if end_date:
            valid_cases = case_start.loc[valid_cases][
                case_start.loc[valid_cases] <= pd.Timestamp(end_date)
            ].index
        log = log[log[CASE_ID].isin(valid_cases)]

    return log


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


def _guard_cordeiro(key: str) -> None:
    """Fontes reais (cordeiro/vedara): carga assíncrona. Nunca bloqueia/recarrega
    dentro do request — devolve 503 enquanto carrega (o front reexibe e reconsulta)."""
    if not data_source.is_real(key) or data_source._state["path"] is not None:
        return
    st = data_source.real_status(key)
    if st == "ready":
        return
    data_source.start_real_load(key)
    label = key.capitalize()
    if st == "error":
        raise HTTPException(status_code=503,
                            detail=f"Falha ao carregar {label} do banco: {data_source.real_error(key)}")
    raise HTTPException(status_code=503,
                        detail=f"Carregando dados do {label} do banco… aguarde ~1–2 min e recarregue.")


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
    """Diagnóstico seguro: mostra o que o backend enxerga, sem vazar a chave."""
    url = os.environ.get("AGENT_URL", "")
    key = os.environ.get("AGENT_API_KEY", "")
    return {
        "agent_url_set": bool(url),
        "agent_url_host": url.split("//")[-1].split("/")[0] if url else None,
        "agent_api_key_set": bool(key),
        "agent_api_key_len": len(key),
        "anthropic_key_set": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "cordeiro_prewarm": os.environ.get("CORDEIRO_PREWARM", "1"),
        "cordeiro_status": data_source.cordeiro_status(),
        "cordeiro_error": data_source.cordeiro_error(),
    }


def _require_admin(token: Optional[str]) -> None:
    """Gate opcional: se ADMIN_TOKEN existir no ambiente, exige o header."""
    admin = os.environ.get("ADMIN_TOKEN")
    if admin and token != admin:
        raise HTTPException(status_code=403, detail="Token de administração inválido")


class QueryValidateBody(BaseModel):
    source: str
    table: str
    columns: str
    where: str = ""


class QuerySaveBody(BaseModel):
    sources: dict


@app.get("/api/cordeiro/queries")
def cordeiro_queries_get():
    return {
        "order": cq.ORDER,
        "labels": cq.LABELS,
        "sources": cq.get_config(),
        "required": cq.REQUIRED_COLUMNS,
        "defaults": cq.DEFAULT_QUERIES,
        "customized": cq.is_customized(),
        "aiConfigured": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "status": data_source.cordeiro_status(),
    }


@app.post("/api/cordeiro/queries/validate")
def cordeiro_queries_validate(body: QueryValidateBody):
    if body.source not in cq.STRUCT:
        raise HTTPException(status_code=400, detail=f"Fonte desconhecida: {body.source}")
    res = cq.validate_source(body.source, body.table, body.columns, body.where)
    from app.ai.query_review import review_query
    res["ai"] = review_query(
        cq.LABELS.get(body.source, body.source), res["sql"],
        res["error"], res["missing"], cq.REQUIRED_COLUMNS[body.source])
    return res


@app.post("/api/cordeiro/queries/preview")
def cordeiro_queries_preview(body: QueryValidateBody):
    if body.source not in cq.STRUCT:
        raise HTTPException(status_code=400, detail=f"Fonte desconhecida: {body.source}")
    return cq.preview_source(body.source, body.table, body.columns, body.where, limit=100)


def _reload_real(key: str):
    data_source.refresh(key)
    _ENRICH_CACHE.clear()
    _CASES_CACHE.clear()
    data_source.start_real_load(key)


def _reload_cordeiro():
    _reload_real("cordeiro")


@app.get("/api/modules/{key}/status")
def module_status(key: str):
    """Status de carga de uma fonte: ready | loading | error | idle + progresso %."""
    if not data_source.is_real(key):
        return {"status": "ready", "progress": 100, "error": None}
    return {
        "status": data_source.real_status(key),
        "progress": data_source.real_progress(key),
        "error": data_source.real_error(key),
    }


@app.post("/api/modules/{key}/refresh")
def refresh_module(key: str, x_admin_token: Optional[str] = Header(default=None)):
    """Descarta o cache da fonte real e recarrega do banco (sob demanda)."""
    if not data_source.is_real(key):
        raise HTTPException(status_code=400, detail=f"'{key}' não é uma fonte recarregável")
    _require_admin(x_admin_token)
    _reload_real(key)
    return {"ok": True, "status": data_source.real_status(key)}


@app.put("/api/cordeiro/queries")
def cordeiro_queries_save(body: QuerySaveBody,
                          x_admin_token: Optional[str] = Header(default=None)):
    _require_admin(x_admin_token)
    cfg = cq.save_config(body.sources)
    _reload_cordeiro()
    return {"ok": True, "sources": cfg, "status": data_source.cordeiro_status()}


@app.post("/api/cordeiro/queries/reset")
def cordeiro_queries_reset(x_admin_token: Optional[str] = Header(default=None)):
    _require_admin(x_admin_token)
    cq.reset_config()
    _reload_cordeiro()
    return {"ok": True, "sources": cq.get_config(), "status": data_source.cordeiro_status()}


@app.get("/api/modules/{key}")
def get_module(
    key: str,
    fornecedores: list[str] = Query(default=[]),
    start_date: Optional[str] = Query(default=None),
    end_date:   Optional[str] = Query(default=None),
    ano: Optional[int] = Query(default=None),
    mes: Optional[int] = Query(default=None),
    act_id: Optional[str] = Query(default=None),
    act_mode: Optional[str] = Query(default=None),
):
    module = module_registry.get(key)
    if not module:
        raise HTTPException(status_code=404, detail=f"Modulo '{key}' nao encontrado")
    _guard_cordeiro(key)
    ck = (key, tuple(sorted(fornecedores)), start_date, end_date, ano, mes, act_id, act_mode)
    cached = _ENRICH_CACHE.get(ck)
    if cached is not None:
        return cached
    log = data_source.get_log(module_key=key)
    log = _apply_filters(log, fornecedores, start_date, end_date, ano, mes)
    log = _apply_activity_filter(log, module, act_id, act_mode)
    if log.empty or log[CASE_ID].nunique() == 0:
        raise HTTPException(status_code=422, detail="Nenhum caso encontrado para os filtros aplicados")
    payload = module.enrich(log)
    if len(_ENRICH_CACHE) > 64:
        _ENRICH_CACHE.clear()
    _ENRICH_CACHE[ck] = payload
    return payload


@app.get("/api/modules/{key}/cases")
def get_cases(
    key: str,
    fornecedores: list[str] = Query(default=[]),
    start_date: Optional[str] = Query(default=None),
    end_date:   Optional[str] = Query(default=None),
    ano: Optional[int] = Query(default=None),
    mes: Optional[int] = Query(default=None),
    act_id: Optional[str] = Query(default=None),
    act_mode: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=500),
):
    module = module_registry.get(key)
    if not module:
        raise HTTPException(status_code=404, detail=f"Modulo '{key}' nao encontrado")
    _guard_cordeiro(key)

    # índice (ordenar+resumir) é caro → cacheado por assinatura de filtro.
    # A busca por Case Id (q) e a página (limit) ficam fora da chave: rodam barato.
    sig = (key, tuple(sorted(fornecedores)), start_date, end_date, ano, mes, act_id, act_mode)
    idx = _CASES_CACHE.get(sig)
    if idx is None:
        log = data_source.get_log(module_key=key)
        log = _apply_filters(log, fornecedores, start_date, end_date, ano, mes)
        log = _apply_activity_filter(log, module, act_id, act_mode)
        if log.empty or log[CASE_ID].nunique() == 0:
            return {"cases": [], "total": 0}
        idx = build_case_index(log)
        if len(_CASES_CACHE) > 8:
            _CASES_CACHE.clear()
        _CASES_CACHE[sig] = idx
    sorted_log, summary = idx
    return page_cases(sorted_log, summary, q=q, limit=limit)


class AskBody(BaseModel):
    question: str


@app.get("/api/ai/status")
def ai_status():
    from app.ai.agent import is_configured
    return {"configured": is_configured()}


@app.post("/api/modules/{key}/ask")
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

    log = data_source.get_log(module_key=key)
    log = _apply_filters(log, fornecedores, start_date, end_date, ano, mes)
    if log.empty:
        raise HTTPException(status_code=422, detail="Nenhum caso para os filtros aplicados")

    dim_label = "Fornecedor" if "fornecedor" in log.columns else (
        "Cliente" if "cliente" in log.columns else "Dimensão")
    try:
        return ask(body.question, log, module.name, dim_label)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Falha ao consultar a IA: {exc}")


@app.get("/api/modules/{key}/user/{name}")
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
    log = _apply_filters(log, fornecedores, start_date, end_date, ano, mes)
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
