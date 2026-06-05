from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.demo.generate_p2p import build_p2p_log
from app.mining.dfg import discover_dfg

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
    log = build_p2p_log(n_cases=2000)
    return discover_dfg(log)
