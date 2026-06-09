import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")  # backend/.env

import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import data_source
from app import modules as module_registry
from app.modules.cases import build_cases
from app.connectors.csv_connector import CSVConnector
from app.mining.dfg import discover_dfg
from app.mining.variants import discover_variants
from app.mining.stats import compute_statistics
from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP

app = FastAPI(title="Process Mining API")

# cache de payloads já enriquecidos (chave = módulo + assinatura dos filtros)
_ENRICH_CACHE: dict = {}

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
    """Pré-aquece o log do Cordeiro (carga ~90s do agent) em background, para o
    usuário não esperar no primeiro clique. Silencioso se o agent estiver fora."""
    if os.environ.get("CORDEIRO_PREWARM", "1") != "1":
        return
    data_source.start_cordeiro_load()


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
    # Cordeiro: carga real é assíncrona; nunca bloqueia/recarrega dentro do request
    if key == "cordeiro" and data_source._state["path"] is None:
        st = data_source.cordeiro_status()
        if st != "ready":
            data_source.start_cordeiro_load()
            if st == "error":
                raise HTTPException(status_code=503,
                                    detail=f"Falha ao carregar Cordeiro do banco: {data_source.cordeiro_error()}")
            raise HTTPException(status_code=503,
                                detail="Carregando dados do Cordeiro do banco… aguarde ~1–2 min e recarregue.")
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
):
    module = module_registry.get(key)
    if not module:
        raise HTTPException(status_code=404, detail=f"Modulo '{key}' nao encontrado")
    log = data_source.get_log(module_key=key)
    log = _apply_filters(log, fornecedores, start_date, end_date, ano, mes)
    log = _apply_activity_filter(log, module, act_id, act_mode)
    if log.empty or log[CASE_ID].nunique() == 0:
        return {"cases": []}
    return {"cases": build_cases(log)}


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
    return {"status": "ok", "filename": file.filename}
