from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app import data_source
from app import modules as module_registry
from app.connectors.csv_connector import CSVConnector
from app.mining.dfg import discover_dfg
from app.mining.variants import discover_variants
from app.mining.stats import compute_statistics

app = FastAPI(title="Process Mining API")

import os

ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:5173"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.railway\.app",
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.get("/api/modules/{key}")
def get_module(key: str):
    module = module_registry.get(key)
    if not module:
        raise HTTPException(status_code=404, detail=f"Modulo '{key}' nao encontrado")
    return module.enrich(data_source.get_log())
