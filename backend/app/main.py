import os
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app import data_source
from app import modules as module_registry
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
) -> pd.DataFrame:
    """Filtra o event log por fornecedor e/ou período."""
    if fornecedores and "fornecedor" in log.columns:
        log = log[log["fornecedor"].isin(fornecedores)]

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
):
    module = module_registry.get(key)
    if not module:
        raise HTTPException(status_code=404, detail=f"Modulo '{key}' nao encontrado")
    log = data_source.get_log()
    log = _apply_filters(log, fornecedores, start_date, end_date)
    if log.empty or log[CASE_ID].nunique() == 0:
        raise HTTPException(status_code=422, detail="Nenhum caso encontrado para os filtros aplicados")
    return module.enrich(log)


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
