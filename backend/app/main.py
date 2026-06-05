from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import data_source
from app.mining.dfg import discover_dfg
from app.mining.variants import discover_variants
from app.mining.stats import compute_statistics

app = FastAPI(title="Process Mining API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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
