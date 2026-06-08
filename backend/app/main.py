import os
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app import data_source
from app import modules as module_registry
from app.modules.cases import build_cases
from app.connectors.csv_connector import CSVConnector
from app.mining.dfg import discover_dfg
from app.mining.variants import discover_variants
from app.mining.stats import compute_statistics
from app.eventlog import CASE_ID, TIMESTAMP

app = FastAPI(title="Process Mining API")

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
):
    module = module_registry.get(key)
    if not module:
        raise HTTPException(status_code=404, detail=f"Modulo '{key}' nao encontrado")
    log = data_source.get_log(module_key=key)
    log = _apply_filters(log, fornecedores, start_date, end_date, ano, mes)
    if log.empty or log[CASE_ID].nunique() == 0:
        raise HTTPException(status_code=422, detail="Nenhum caso encontrado para os filtros aplicados")
    return module.enrich(log)


@app.get("/api/modules/{key}/cases")
def get_cases(
    key: str,
    fornecedores: list[str] = Query(default=[]),
    start_date: Optional[str] = Query(default=None),
    end_date:   Optional[str] = Query(default=None),
    ano: Optional[int] = Query(default=None),
    mes: Optional[int] = Query(default=None),
):
    module = module_registry.get(key)
    if not module:
        raise HTTPException(status_code=404, detail=f"Modulo '{key}' nao encontrado")
    log = data_source.get_log(module_key=key)
    log = _apply_filters(log, fornecedores, start_date, end_date, ano, mes)
    if log.empty or log[CASE_ID].nunique() == 0:
        return {"cases": []}
    return {"cases": build_cases(log)}


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
    return {"status": "ok", "filename": file.filename}
