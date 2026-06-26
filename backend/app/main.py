import hashlib
import json
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
    allow_origin_regex=r"https://(.*\.railway\.app|(.*\.)?ma3processmining\.com\.br)",
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
    """Data de referência por caso: data do evento de pedido (se `order_activity`
    informado e presente) ou o 1º evento do caso (case start)."""
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
    """Fonte real (Vedara): carga assíncrona. Nunca bloqueia/recarrega
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
        "vedara_status": data_source.real_status("vedara"),
        "vedara_error": data_source.real_error("vedara"),
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


@app.get("/api/modules/{key}")
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


@app.get("/api/modules/{key}/cases")
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
    if key == "vedara":
        from app.sources import vedara as src
        return src
    if key == "biolab":
        from app.sources import biolab as src
        return src
    return None


@app.get("/api/modules/{key}/details")
def get_details(
    key: str,
    ano: Optional[int] = Query(default=None),
    mes: Optional[int] = Query(default=None),
    dias: list[int] = Query(default=[]),
    produto: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=500),
    offset: int = Query(default=0),
):
    """Detalhe por caso/item (tela Detalhes), por módulo."""
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
    df = df[mask]

    total = int(len(df))
    page = df.iloc[offset: offset + max(0, limit)]
    rows = json.loads(page.to_json(orient="records"))
    return {"rows": rows, "total": total, "columns": cols}


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
    log = _apply_filters(log, fornecedores, start_date, end_date, ano, mes,
                         order_activity=module.order_activity)
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
