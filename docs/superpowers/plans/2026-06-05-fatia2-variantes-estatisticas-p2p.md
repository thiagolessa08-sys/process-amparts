# Fatia 2 — Variantes e Estatísticas P2P — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Analisar as variantes do processo P2P e suas estatísticas (tempo de ciclo, gargalos), expor por novos endpoints lendo o CSV via `CSVConnector`, permitir upload de CSV do usuário e mostrar tudo no frontend com destaque do caminho da variante selecionada no grafo.

**Architecture:** O núcleo ganha dois módulos genéricos: `variants` (caminhos distintos início→fim, ordenados por frequência) e `stats` (nº de casos/eventos/variantes, tempo de ciclo médio/mediano). Um `data_source` centraliza qual event log está ativo (demo por padrão, ou CSV enviado). O backend passa a ler via `CSVConnector` em vez de gerar em memória. O frontend vira controlado: o `App` busca grafo+variantes+estatísticas, mostra barra de estatísticas e painel de variantes; clicar numa variante destaca o caminho no grafo.

**Tech Stack:** Python (FastAPI, pandas, python-multipart para upload), pytest. Frontend React + React Flow.

**Decisão sobre pm4py:** variantes e estatísticas são computadas em pandas (leves, determinísticas, testáveis). `pm4py` fica reservado para conformance/inductive miner numa fatia futura.

---

## Estrutura de arquivos

```
backend/
  requirements.txt                # + python-multipart
  app/
    data_source.py                # NOVO: event log ativo (demo ou upload)
    main.py                       # MOD: endpoints variants/statistics/upload; usa data_source
    demo/generate_p2p.py          # MOD: variantes estruturais (não só caminho feliz)
    mining/
      variants.py                 # NOVO: discover_variants()
      stats.py                    # NOVO: compute_statistics()
  tests/
    test_demo_p2p.py              # MOD: testes das variantes
    test_variants.py              # NOVO
    test_stats.py                 # NOVO
    test_api.py                   # MOD: novos endpoints + upload
frontend/
  src/
    api.js                        # MOD: fetchVariants, fetchStatistics, uploadCsv
    App.jsx                       # MOD: estado central + layout
    components/
      ProcessGraph.jsx            # MOD: controlado, recebe graph + highlightPath
      StatsBar.jsx                # NOVO
      VariantsPanel.jsx           # NOVO
```

---

### Task 1: Variantes estruturais no gerador demo

Hoje o gerador só produz o caminho feliz (uma variante). Para a tela de variantes ter
conteúdo, o gerador passa a produzir 4 variantes deterministicamente.

**Files:**
- Modify: `backend/app/demo/generate_p2p.py`
- Modify: `backend/tests/test_demo_p2p.py`

- [ ] **Step 1: Reescrever os testes do gerador**

Substituir todo o conteúdo de `backend/tests/test_demo_p2p.py` por:
```python
import pandas as pd
from app.demo.generate_p2p import build_p2p_log, HAPPY_PATH
from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP


def _sequences(df):
    df = df.sort_values([CASE_ID, TIMESTAMP])
    return df.groupby(CASE_ID, sort=False)[ACTIVITY].apply(lambda s: tuple(s))


def test_build_log_has_requested_number_of_cases():
    df = build_p2p_log(n_cases=200, seed=1)
    assert df[CASE_ID].nunique() == 200


def test_required_columns_present():
    df = build_p2p_log(n_cases=10, seed=1)
    assert {CASE_ID, ACTIVITY, TIMESTAMP}.issubset(df.columns)


def test_happy_path_is_the_most_common_variant():
    df = build_p2p_log(n_cases=500, seed=1)
    counts = _sequences(df).value_counts()
    assert counts.index[0] == tuple(HAPPY_PATH)
    # caminho feliz deve ser maioria, mas nao 100%
    assert 0.5 < counts.iloc[0] / counts.sum() < 0.95


def test_has_multiple_variants():
    df = build_p2p_log(n_cases=500, seed=1)
    assert _sequences(df).nunique() >= 3


def test_maverick_variant_skips_approval():
    # existe pelo menos um caso que paga sem "Aprovar Pedido"
    df = build_p2p_log(n_cases=500, seed=1)
    seqs = _sequences(df)
    assert any("Aprovar Pedido" not in s and "Pagar" in s for s in seqs)


def test_is_deterministic_with_seed():
    a = build_p2p_log(n_cases=100, seed=42)
    b = build_p2p_log(n_cases=100, seed=42)
    pd.testing.assert_frame_equal(a, b)
```

- [ ] **Step 2: Rodar e confirmar a falha**

Run (a partir de `backend/`): `.venv\Scripts\python -m pytest tests/test_demo_p2p.py -v`
Expected: FAIL — `ImportError` (HAPPY_PATH já existe, mas os testes de variantes falham: hoje só há 1 variante)

- [ ] **Step 3: Reescrever o gerador com variantes**

Substituir todo o conteúdo de `backend/app/demo/generate_p2p.py` por:
```python
"""Gera um event log demo de P2P com variantes estruturais.

Variantes (estruturais) nesta fatia:
- happy:    caminho feliz completo (~70%)
- no_gr:    sem "Receber Mercadoria" (~12%)
- maverick: sem "Aprovar Pedido" (compra fora do processo) (~10%)
- rework:   "Aprovar Pedido" repetido (retrabalho de aprovacao) (~8%)

Os problemas baseados em atributos (pagamento duplicado, desconto perdido)
entram na Fatia 3 junto com os KPIs.
"""
import random
from pathlib import Path

import pandas as pd

from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP, RESOURCE

HAPPY_PATH = [
    "Criar Requisicao",
    "Criar Pedido de Compra",
    "Aprovar Pedido",
    "Receber Mercadoria",
    "Receber Fatura",
    "Pagar",
]

RESOURCES = ["Joao Silva", "Maria Souza", "Sistema", "Ana Lima"]


def _path_for(rng: random.Random) -> list[str]:
    r = rng.random()
    if r < 0.70:
        return list(HAPPY_PATH)
    if r < 0.82:
        return [a for a in HAPPY_PATH if a != "Receber Mercadoria"]
    if r < 0.92:
        return [a for a in HAPPY_PATH if a != "Aprovar Pedido"]
    # rework: duplica "Aprovar Pedido"
    path = []
    for a in HAPPY_PATH:
        path.append(a)
        if a == "Aprovar Pedido":
            path.append("Aprovar Pedido")
    return path


def build_p2p_log(n_cases: int = 2000, seed: int = 7) -> pd.DataFrame:
    rng = random.Random(seed)
    rows = []
    base = pd.Timestamp("2026-01-01 08:00:00")
    for case_idx in range(1, n_cases + 1):
        case_id = 4500000 + case_idx
        t = base + pd.Timedelta(days=rng.randint(0, 120))
        for activity in _path_for(rng):
            rows.append(
                {
                    CASE_ID: case_id,
                    ACTIVITY: activity,
                    TIMESTAMP: t,
                    RESOURCE: rng.choice(RESOURCES),
                }
            )
            t = t + pd.Timedelta(hours=rng.randint(2, 48))
    return pd.DataFrame(rows)


def write_demo_csv(path: str = "data/demo_p2p.csv", n_cases: int = 2000) -> str:
    df = build_p2p_log(n_cases=n_cases)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return path


if __name__ == "__main__":
    out = write_demo_csv()
    print(f"Dataset demo gerado em {out}")
```

- [ ] **Step 4: Rodar e confirmar GREEN**

Run: `.venv\Scripts\python -m pytest tests/test_demo_p2p.py -v`
Expected: PASS (6 testes)

- [ ] **Step 5: Regenerar o CSV demo**

Run: `.venv\Scripts\python -m app.demo.generate_p2p`
Expected: `Dataset demo gerado em data/demo_p2p.csv`

- [ ] **Step 6: Commit**

```bash
git add backend/app/demo/generate_p2p.py backend/tests/test_demo_p2p.py
git commit -m "feat(backend): variantes estruturais no gerador demo P2P"
```

---

### Task 2: Descoberta de variantes (núcleo)

**Files:**
- Create: `backend/app/mining/variants.py`
- Create: `backend/tests/test_variants.py`

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/test_variants.py`:
```python
import pandas as pd
from app.mining.variants import discover_variants
from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP


def _log():
    return pd.DataFrame(
        {
            CASE_ID: [1, 1, 2, 2, 3, 3],
            ACTIVITY: ["A", "B", "A", "B", "A", "C"],
            TIMESTAMP: pd.to_datetime(
                [
                    "2026-03-01 09:00",
                    "2026-03-01 10:00",
                    "2026-03-02 09:00",
                    "2026-03-02 10:00",
                    "2026-03-03 09:00",
                    "2026-03-03 10:00",
                ]
            ),
        }
    )


def test_returns_variants_ordered_by_frequency():
    result = discover_variants(_log())
    assert result[0]["activities"] == ["A", "B"]
    assert result[0]["count"] == 2
    assert result[1]["activities"] == ["A", "C"]
    assert result[1]["count"] == 1


def test_percentages_sum_to_100():
    result = discover_variants(_log())
    assert round(sum(v["percentage"] for v in result), 1) == 100.0


def test_each_variant_has_sequential_id():
    result = discover_variants(_log())
    assert [v["variant_id"] for v in result] == [1, 2]
```

- [ ] **Step 2: Rodar e confirmar a falha**

Run: `.venv\Scripts\python -m pytest tests/test_variants.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.mining.variants'`

- [ ] **Step 3: Implementar discover_variants**

`backend/app/mining/variants.py`:
```python
"""Descoberta de variantes: cada caminho distinto inicio->fim de um caso."""
import pandas as pd
from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP


def discover_variants(log: pd.DataFrame) -> list[dict]:
    """Retorna lista de {variant_id, activities, count, percentage},
    ordenada por frequencia decrescente."""
    log = log.sort_values([CASE_ID, TIMESTAMP])
    sequences = log.groupby(CASE_ID, sort=False)[ACTIVITY].apply(
        lambda s: tuple(str(a) for a in s)
    )

    counts: dict[tuple, int] = {}
    for seq in sequences:
        counts[seq] = counts.get(seq, 0) + 1

    total = len(sequences)
    ordered = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return [
        {
            "variant_id": i + 1,
            "activities": list(seq),
            "count": count,
            "percentage": round(100 * count / total, 1),
        }
        for i, (seq, count) in enumerate(ordered)
    ]
```

- [ ] **Step 4: Rodar e confirmar GREEN**

Run: `.venv\Scripts\python -m pytest tests/test_variants.py -v`
Expected: PASS (3 testes)

- [ ] **Step 5: Commit**

```bash
git add backend/app/mining/variants.py backend/tests/test_variants.py
git commit -m "feat(backend): descoberta de variantes no nucleo"
```

---

### Task 3: Estatísticas do processo (núcleo)

**Files:**
- Create: `backend/app/mining/stats.py`
- Create: `backend/tests/test_stats.py`

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/test_stats.py`:
```python
import pandas as pd
from app.mining.stats import compute_statistics
from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP


def _log():
    return pd.DataFrame(
        {
            CASE_ID: [1, 1, 2, 2],
            ACTIVITY: ["A", "B", "A", "B"],
            TIMESTAMP: pd.to_datetime(
                [
                    "2026-03-01 09:00",  # caso 1 dura 3600s
                    "2026-03-01 10:00",
                    "2026-03-02 09:00",  # caso 2 dura 7200s
                    "2026-03-02 11:00",
                ]
            ),
        }
    )


def test_counts():
    s = compute_statistics(_log())
    assert s["num_cases"] == 2
    assert s["num_events"] == 4
    assert s["num_variants"] == 1


def test_throughput_mean_and_median():
    s = compute_statistics(_log())
    # media de 3600 e 7200 = 5400
    assert s["mean_throughput_seconds"] == 5400.0
    assert s["median_throughput_seconds"] == 5400.0
```

- [ ] **Step 2: Rodar e confirmar a falha**

Run: `.venv\Scripts\python -m pytest tests/test_stats.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.mining.stats'`

- [ ] **Step 3: Implementar compute_statistics**

`backend/app/mining/stats.py`:
```python
"""Estatisticas gerais do processo a partir do event log padrao."""
import pandas as pd
from app.eventlog import CASE_ID, TIMESTAMP
from app.mining.variants import discover_variants


def compute_statistics(log: pd.DataFrame) -> dict:
    grp = log.groupby(CASE_ID)[TIMESTAMP]
    durations = (grp.max() - grp.min()).dt.total_seconds()
    return {
        "num_cases": int(log[CASE_ID].nunique()),
        "num_events": int(len(log)),
        "num_variants": len(discover_variants(log)),
        "mean_throughput_seconds": round(float(durations.mean()), 2),
        "median_throughput_seconds": round(float(durations.median()), 2),
    }
```

- [ ] **Step 4: Rodar e confirmar GREEN**

Run: `.venv\Scripts\python -m pytest tests/test_stats.py -v`
Expected: PASS (2 testes)

- [ ] **Step 5: Commit**

```bash
git add backend/app/mining/stats.py backend/tests/test_stats.py
git commit -m "feat(backend): estatisticas do processo no nucleo"
```

---

### Task 4: Fonte de dados central + endpoints variants/statistics lendo CSV

**Files:**
- Create: `backend/app/data_source.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_api.py`

- [ ] **Step 1: Criar a fonte de dados central**

`backend/app/data_source.py`:
```python
"""Mantem qual event log esta ativo. Por padrao, o dataset demo P2P.

Ao receber upload, aponta para o arquivo enviado. Centraliza o acesso
para que os endpoints nao saibam de onde o log vem.
"""
from pathlib import Path

import pandas as pd

from app.connectors.csv_connector import CSVConnector
from app.demo.generate_p2p import write_demo_csv

DEMO_PATH = "data/demo_p2p.csv"

_state = {"path": None}


def get_log() -> pd.DataFrame:
    path = _state["path"] or DEMO_PATH
    if not Path(path).exists():
        write_demo_csv(DEMO_PATH)
        path = DEMO_PATH
    return CSVConnector(path).load()


def set_source(path: str) -> None:
    _state["path"] = path


def reset_to_demo() -> None:
    _state["path"] = None
```

- [ ] **Step 2: Escrever os testes dos novos endpoints**

Substituir todo o conteúdo de `backend/tests/test_api.py` por:
```python
from fastapi.testclient import TestClient
from app.main import app
from app import data_source

client = TestClient(app)


def setup_function():
    data_source.reset_to_demo()


def test_health_returns_ok():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_process_graph_returns_nodes_and_edges():
    response = client.get("/api/process-graph")
    assert response.status_code == 200
    body = response.json()
    assert "nodes" in body and "edges" in body
    node_ids = {n["id"] for n in body["nodes"]}
    assert "Criar Requisicao" in node_ids
    assert "Pagar" in node_ids
    pairs = {(e["source"], e["target"]) for e in body["edges"]}
    assert ("Criar Requisicao", "Criar Pedido de Compra") in pairs


def test_variants_returns_ordered_list():
    response = client.get("/api/variants")
    assert response.status_code == 200
    variants = response.json()
    assert isinstance(variants, list)
    assert len(variants) >= 3
    # ordenado por frequencia decrescente
    counts = [v["count"] for v in variants]
    assert counts == sorted(counts, reverse=True)
    # o caminho feliz completo esta entre as variantes
    seqs = [tuple(v["activities"]) for v in variants]
    assert ("Criar Requisicao", "Criar Pedido de Compra", "Aprovar Pedido",
            "Receber Mercadoria", "Receber Fatura", "Pagar") in seqs


def test_statistics_returns_summary():
    response = client.get("/api/statistics")
    assert response.status_code == 200
    s = response.json()
    assert s["num_cases"] == 2000
    assert s["num_variants"] >= 3
    assert s["mean_throughput_seconds"] > 0
```

- [ ] **Step 3: Rodar e confirmar a falha**

Run: `.venv\Scripts\python -m pytest tests/test_api.py -v`
Expected: FAIL — `/api/variants` e `/api/statistics` retornam 404

- [ ] **Step 4: Atualizar o main.py para usar data_source e expor os endpoints**

Substituir todo o conteúdo de `backend/app/main.py` por:
```python
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
```

- [ ] **Step 5: Rodar a suíte completa**

Run: `.venv\Scripts\python -m pytest -v`
Expected: PASS — todos os testes (incluindo os novos de variants/statistics)

- [ ] **Step 6: Commit**

```bash
git add backend/app/data_source.py backend/app/main.py backend/tests/test_api.py
git commit -m "feat(backend): fonte de dados central e endpoints variants/statistics"
```

---

### Task 5: Upload de CSV do usuário

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_api.py`

- [ ] **Step 1: Adicionar python-multipart ao requirements**

Adicionar a linha ao final de `backend/requirements.txt`:
```
python-multipart==0.0.9
```

- [ ] **Step 2: Instalar a dependência**

Run (a partir de `backend/`):
```
.venv\Scripts\python -m pip install python-multipart==0.0.9 --trusted-host pypi.org --trusted-host files.pythonhosted.org
```
Expected: instala com sucesso.

- [ ] **Step 3: Escrever o teste de upload que falha**

Adicionar a `backend/tests/test_api.py`:
```python
def test_upload_replaces_active_log():
    csv = (
        "case_id,activity,timestamp\n"
        "1,Inicio,2026-05-01 09:00:00\n"
        "1,Fim,2026-05-01 10:00:00\n"
    )
    response = client.post(
        "/api/upload",
        files={"file": ("meu.csv", csv, "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    # apos upload, o grafo reflete o novo log
    graph = client.get("/api/process-graph").json()
    node_ids = {n["id"] for n in graph["nodes"]}
    assert node_ids == {"Inicio", "Fim"}


def test_upload_rejects_invalid_csv():
    bad = "coluna_errada\n1\n"
    response = client.post(
        "/api/upload",
        files={"file": ("ruim.csv", bad, "text/csv")},
    )
    assert response.status_code == 400
```

- [ ] **Step 4: Rodar e confirmar a falha**

Run: `.venv\Scripts\python -m pytest tests/test_api.py::test_upload_replaces_active_log tests/test_api.py::test_upload_rejects_invalid_csv -v`
Expected: FAIL — rota `/api/upload` retorna 404/405

- [ ] **Step 5: Implementar o endpoint de upload**

Adicionar os imports no topo de `backend/app/main.py` (junto aos imports existentes):
```python
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from app.connectors.csv_connector import CSVConnector
```
E adicionar a rota ao final de `backend/app/main.py`:
```python
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
```

Nota: o `FastAPI` já é importado; mantenha apenas um import de `FastAPI`. A linha
de import acima substitui `from fastapi import FastAPI` existente por
`from fastapi import FastAPI, UploadFile, File, HTTPException`.

- [ ] **Step 6: Rodar a suíte completa**

Run: `.venv\Scripts\python -m pytest -v`
Expected: PASS — todos os testes, incluindo os 2 de upload.

- [ ] **Step 7: Commit**

```bash
git add backend/requirements.txt backend/app/main.py backend/tests/test_api.py
git commit -m "feat(backend): upload de CSV do usuario com validacao"
```

---

### Task 6: Frontend — barra de estatísticas, painel de variantes e destaque no grafo

**Files:**
- Modify: `frontend/src/api.js`
- Create: `frontend/src/components/StatsBar.jsx`
- Create: `frontend/src/components/VariantsPanel.jsx`
- Modify: `frontend/src/components/ProcessGraph.jsx`
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Estender o cliente de API**

Substituir todo o conteúdo de `frontend/src/api.js` por:
```javascript
const BASE = "http://localhost:8000";

async function getJson(path) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`Erro ${res.status} em ${path}`);
  return res.json();
}

export const fetchProcessGraph = () => getJson("/api/process-graph");
export const fetchVariants = () => getJson("/api/variants");
export const fetchStatistics = () => getJson("/api/statistics");

export async function uploadCsv(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/api/upload`, { method: "POST", body: form });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Erro ${res.status} no upload`);
  }
  return res.json();
}
```

- [ ] **Step 2: Criar a barra de estatísticas**

`frontend/src/components/StatsBar.jsx`:
```javascript
function fmtDays(seconds) {
  const days = seconds / 86400;
  return `${days.toFixed(1)} dias`;
}

function Card({ label, value }) {
  return (
    <div
      style={{
        padding: "10px 16px",
        background: "#f9fafb",
        border: "1px solid #e5e7eb",
        borderRadius: 8,
        minWidth: 120,
      }}
    >
      <div style={{ fontSize: 12, color: "#6b7280" }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 600 }}>{value}</div>
    </div>
  );
}

export default function StatsBar({ stats }) {
  if (!stats) return null;
  return (
    <div style={{ display: "flex", gap: 12, padding: "12px 20px" }}>
      <Card label="Casos" value={stats.num_cases.toLocaleString("pt-BR")} />
      <Card label="Eventos" value={stats.num_events.toLocaleString("pt-BR")} />
      <Card label="Variantes" value={stats.num_variants} />
      <Card label="Tempo medio" value={fmtDays(stats.mean_throughput_seconds)} />
      <Card label="Tempo mediano" value={fmtDays(stats.median_throughput_seconds)} />
    </div>
  );
}
```

- [ ] **Step 3: Criar o painel de variantes**

`frontend/src/components/VariantsPanel.jsx`:
```javascript
export default function VariantsPanel({ variants, selectedId, onSelect }) {
  return (
    <aside
      style={{
        width: 320,
        borderLeft: "1px solid #e5e7eb",
        overflowY: "auto",
        padding: 12,
      }}
    >
      <h3 style={{ margin: "4px 8px 12px" }}>Variantes</h3>
      {variants.map((v) => {
        const active = v.variant_id === selectedId;
        return (
          <button
            key={v.variant_id}
            onClick={() => onSelect(active ? null : v.variant_id)}
            style={{
              display: "block",
              width: "100%",
              textAlign: "left",
              marginBottom: 8,
              padding: 10,
              borderRadius: 8,
              cursor: "pointer",
              border: active ? "2px solid #4f46e5" : "1px solid #e5e7eb",
              background: active ? "#eef2ff" : "#fff",
            }}
          >
            <div style={{ fontWeight: 600 }}>
              Variante {v.variant_id} — {v.percentage}%
            </div>
            <div style={{ fontSize: 12, color: "#6b7280" }}>
              {v.count.toLocaleString("pt-BR")} casos
            </div>
            <div style={{ fontSize: 12, marginTop: 4 }}>
              {v.activities.join(" → ")}
            </div>
          </button>
        );
      })}
    </aside>
  );
}
```

- [ ] **Step 4: Tornar o ProcessGraph controlado, com destaque de caminho**

Substituir todo o conteúdo de `frontend/src/components/ProcessGraph.jsx` por:
```javascript
import ReactFlow, { Background, Controls } from "reactflow";
import "reactflow/dist/style.css";

// Converte o grafo da API + um caminho destacado em nos/arestas do React Flow.
function toFlow(graph, highlightPath) {
  const onPath = new Set(highlightPath || []);
  // pares consecutivos do caminho destacado
  const pathPairs = new Set();
  if (highlightPath) {
    for (let i = 0; i < highlightPath.length - 1; i++) {
      pathPairs.add(`${highlightPath[i]}->${highlightPath[i + 1]}`);
    }
  }
  const hasHighlight = onPath.size > 0;

  const nodes = graph.nodes.map((n, i) => {
    const active = onPath.has(n.id);
    return {
      id: n.id,
      data: { label: `${n.id}  (${n.count})` },
      position: { x: 250, y: i * 110 },
      style: {
        padding: 10,
        borderRadius: 8,
        border: active ? "2px solid #4f46e5" : "1px solid #c7d2fe",
        background: active ? "#eef2ff" : "#fff",
        opacity: hasHighlight && !active ? 0.35 : 1,
        width: 220,
      },
    };
  });

  const maxCount = Math.max(...graph.edges.map((e) => e.count), 1);
  const edges = graph.edges.map((e) => {
    const active = pathPairs.has(`${e.source}->${e.target}`);
    return {
      id: `${e.source}->${e.target}`,
      source: e.source,
      target: e.target,
      label: `${e.count}`,
      style: {
        strokeWidth: 1 + (e.count / maxCount) * 6,
        stroke: active ? "#4f46e5" : "#a5b4fc",
        opacity: hasHighlight && !active ? 0.2 : 1,
      },
    };
  });

  return { nodes, edges };
}

export default function ProcessGraph({ graph, highlightPath }) {
  if (!graph) return null;
  const { nodes, edges } = toFlow(graph, highlightPath);
  return (
    <div style={{ flex: 1, height: "100%" }}>
      <ReactFlow nodes={nodes} edges={edges} fitView>
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
```

- [ ] **Step 5: Reescrever o App com estado central, upload e layout**

Substituir todo o conteúdo de `frontend/src/App.jsx` por:
```javascript
import { useEffect, useState } from "react";
import ProcessGraph from "./components/ProcessGraph";
import StatsBar from "./components/StatsBar";
import VariantsPanel from "./components/VariantsPanel";
import {
  fetchProcessGraph,
  fetchVariants,
  fetchStatistics,
  uploadCsv,
} from "./api";

export default function App() {
  const [graph, setGraph] = useState(null);
  const [variants, setVariants] = useState([]);
  const [stats, setStats] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [error, setError] = useState(null);

  async function loadAll() {
    try {
      const [g, v, s] = await Promise.all([
        fetchProcessGraph(),
        fetchVariants(),
        fetchStatistics(),
      ]);
      setGraph(g);
      setVariants(v);
      setStats(s);
      setSelectedId(null);
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  async function onUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    setError(null);
    try {
      await uploadCsv(file);
      await loadAll();
    } catch (e) {
      setError(e.message);
    }
    event.target.value = "";
  }

  const selected = variants.find((v) => v.variant_id === selectedId);
  const highlightPath = selected ? selected.activities : null;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <header
        style={{
          padding: "12px 20px",
          borderBottom: "1px solid #e5e7eb",
          display: "flex",
          alignItems: "center",
          gap: 16,
        }}
      >
        <strong>Process Mining</strong>
        <span style={{ color: "#6b7280" }}>Modulo Financeiro · P2P</span>
        <label
          style={{
            marginLeft: "auto",
            cursor: "pointer",
            color: "#4f46e5",
            fontWeight: 600,
          }}
        >
          Upload CSV
          <input
            type="file"
            accept=".csv"
            onChange={onUpload}
            style={{ display: "none" }}
          />
        </label>
      </header>

      {error && (
        <div style={{ padding: "8px 20px", color: "crimson" }}>
          Falha: {error}
        </div>
      )}

      <StatsBar stats={stats} />

      <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
        <ProcessGraph graph={graph} highlightPath={highlightPath} />
        <VariantsPanel
          variants={variants}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Verificação manual de ponta a ponta**

Com o backend rodando (`.venv\Scripts\python -m uvicorn app.main:app --reload` em `backend/`),
rodar em `frontend/`: `npm run dev`. Abrir `http://localhost:5173`. Esperado:
- barra de estatísticas no topo (Casos 2.000, Variantes ≥3, tempos);
- grafo do processo à esquerda; painel de variantes à direita;
- clicar numa variante destaca o caminho no grafo (resto esmaecido); clicar de novo limpa;
- "Upload CSV" troca o dataset e recarrega tudo.

- [ ] **Step 7: Build de verificação e commit**

Run (a partir de `frontend/`): `npm run build`
Expected: build sem erros.

```bash
git add frontend/src/
git commit -m "feat(frontend): estatisticas, variantes e destaque de caminho no grafo"
```

---

## Verificação final da fatia

- [ ] `cd backend && .venv\Scripts\python -m pytest -v` — todos os testes passam.
- [ ] Endpoints `/api/variants` e `/api/statistics` respondem; `/api/upload` troca o log.
- [ ] Frontend mostra estatísticas, variantes e destaque de caminho; upload funciona.
- [ ] `cd frontend && npm run build` — sem erros.

Entregável: explorar variantes e estatísticas do P2P, com destaque interativo, e carregar dados próprios via upload.

## Notas para a próxima fatia

- **Fatia 3:** interface `ProcessModule` + `P2PModule`; estender o gerador com problemas
  baseados em atributos (pagamento duplicado, desconto perdido, valores/fornecedores) e os KPIs
  com drill-down nos casos.
