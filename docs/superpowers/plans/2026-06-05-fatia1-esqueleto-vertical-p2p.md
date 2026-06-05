# Fatia 1 — Esqueleto Vertical P2P — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Importar um event log de P2P por CSV, descobrir o fluxo do processo (Directly-Follows Graph) no backend e desenhá-lo como grafo interativo no frontend — uma fatia vertical de ponta a ponta.

**Architecture:** Backend FastAPI expõe um endpoint REST que lê um CSV via `CSVConnector`, normaliza para o event log padrão (pandas) e computa o DFG (nós = atividades, arestas = transições com frequência e tempo médio). Frontend React (Vite) consome o endpoint e renderiza o grafo com React Flow. Um gerador cria o dataset demo `demo_p2p.csv` com o caminho feliz.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, pandas, pytest, httpx (TestClient). Frontend: Vite + React + React Flow.

**Nota sobre pm4py:** nesta fatia o DFG é computado diretamente com pandas (simples, determinístico, fácil de testar). `pm4py` entra na Fatia 2 (variantes, inductive miner). O núcleo permanece agnóstico de domínio.

---

## Estrutura de arquivos

```
backend/
  requirements.txt
  app/
    __init__.py
    main.py                     # FastAPI app + rotas
    eventlog.py                 # constantes de colunas do event log padrão
    connectors/
      __init__.py
      base.py                   # Connector (ABC)
      csv_connector.py          # CSVConnector
    mining/
      __init__.py
      dfg.py                    # discover_dfg() -> {nodes, edges}
    demo/
      __init__.py
      generate_p2p.py           # gera data/demo_p2p.csv
  data/
    demo_p2p.csv                # gerado (não versionado)
  tests/
    __init__.py
    test_csv_connector.py
    test_dfg.py
    test_demo_p2p.py
    test_api.py
frontend/
  (projeto Vite React)
  src/
    api.js                      # fetch do endpoint
    components/ProcessGraph.jsx # grafo com React Flow
    App.jsx
```

---

### Task 1: Scaffold do backend + endpoint de saúde

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_api.py`

- [ ] **Step 1: Criar requirements.txt**

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
pandas==2.2.2
httpx==0.27.2
pytest==8.3.2
```

- [ ] **Step 2: Criar o pacote app vazio**

`backend/app/__init__.py`:
```python
```
(arquivo vazio)

`backend/tests/__init__.py`:
```python
```
(arquivo vazio)

- [ ] **Step 3: Escrever o teste de saúde que falha**

`backend/tests/test_api.py`:
```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 4: Rodar o teste e confirmar a falha**

Run (a partir de `backend/`): `python -m pytest tests/test_api.py::test_health_returns_ok -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 5: Implementar o app mínimo**

`backend/app/main.py`:
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
```

- [ ] **Step 6: Instalar deps e rodar o teste**

Run (a partir de `backend/`):
```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest tests/test_api.py::test_health_returns_ok -v
```
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/requirements.txt backend/app/__init__.py backend/app/main.py backend/tests/__init__.py backend/tests/test_api.py
git commit -m "feat(backend): scaffold FastAPI com endpoint de saude"
```

---

### Task 2: Constantes do event log padrão

**Files:**
- Create: `backend/app/eventlog.py`

- [ ] **Step 1: Definir as constantes de coluna**

`backend/app/eventlog.py`:
```python
"""Esquema do event log padrão que o núcleo entende.

Toda fonte de dados, após passar por um conector, deve produzir um
DataFrame pandas com pelo menos as três colunas obrigatórias abaixo.
"""

CASE_ID = "case_id"
ACTIVITY = "activity"
TIMESTAMP = "timestamp"
RESOURCE = "resource"

REQUIRED_COLUMNS = [CASE_ID, ACTIVITY, TIMESTAMP]
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/eventlog.py
git commit -m "feat(backend): constantes do event log padrao"
```

---

### Task 3: Connector base + CSVConnector

**Files:**
- Create: `backend/app/connectors/__init__.py`
- Create: `backend/app/connectors/base.py`
- Create: `backend/app/connectors/csv_connector.py`
- Create: `backend/tests/test_csv_connector.py`

- [ ] **Step 1: Criar o pacote connectors**

`backend/app/connectors/__init__.py`:
```python
```
(arquivo vazio)

- [ ] **Step 2: Definir a interface Connector**

`backend/app/connectors/base.py`:
```python
from abc import ABC, abstractmethod
import pandas as pd


class Connector(ABC):
    """Interface comum de ingestão. Produz um event log padronizado."""

    @abstractmethod
    def load(self) -> pd.DataFrame:
        """Retorna um DataFrame com as colunas do event log padrão."""
        raise NotImplementedError
```

- [ ] **Step 3: Escrever o teste do CSVConnector que falha**

`backend/tests/test_csv_connector.py`:
```python
import pandas as pd
import pytest
from app.connectors.csv_connector import CSVConnector
from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP


def _write_csv(tmp_path):
    csv = tmp_path / "log.csv"
    csv.write_text(
        "case_id,activity,timestamp\n"
        "1,Criar Requisicao,2026-03-01 09:00:00\n"
        "1,Aprovar Pedido,2026-03-02 10:00:00\n"
        "2,Criar Requisicao,2026-03-01 11:00:00\n",
        encoding="utf-8",
    )
    return csv


def test_load_returns_dataframe_with_required_columns(tmp_path):
    csv = _write_csv(tmp_path)
    df = CSVConnector(str(csv)).load()
    assert isinstance(df, pd.DataFrame)
    assert {CASE_ID, ACTIVITY, TIMESTAMP}.issubset(df.columns)
    assert len(df) == 3


def test_load_parses_timestamp_as_datetime(tmp_path):
    csv = _write_csv(tmp_path)
    df = CSVConnector(str(csv)).load()
    assert pd.api.types.is_datetime64_any_dtype(df[TIMESTAMP])


def test_load_raises_when_required_column_missing(tmp_path):
    csv = tmp_path / "bad.csv"
    csv.write_text("case_id,activity\n1,Criar\n", encoding="utf-8")
    with pytest.raises(ValueError, match="timestamp"):
        CSVConnector(str(csv)).load()
```

- [ ] **Step 4: Rodar o teste e confirmar a falha**

Run (a partir de `backend/`): `.venv\Scripts\python -m pytest tests/test_csv_connector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.connectors.csv_connector'`

- [ ] **Step 5: Implementar o CSVConnector**

`backend/app/connectors/csv_connector.py`:
```python
import pandas as pd
from app.connectors.base import Connector
from app.eventlog import TIMESTAMP, REQUIRED_COLUMNS


class CSVConnector(Connector):
    """Lê um event log de um arquivo CSV no formato padrão."""

    def __init__(self, path: str):
        self.path = path

    def load(self) -> pd.DataFrame:
        df = pd.read_csv(self.path)
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"Colunas obrigatorias ausentes: {missing}")
        df[TIMESTAMP] = pd.to_datetime(df[TIMESTAMP])
        return df
```

- [ ] **Step 6: Rodar o teste e confirmar que passa**

Run: `.venv\Scripts\python -m pytest tests/test_csv_connector.py -v`
Expected: PASS (3 testes)

- [ ] **Step 7: Commit**

```bash
git add backend/app/connectors/ backend/tests/test_csv_connector.py
git commit -m "feat(backend): Connector base e CSVConnector"
```

---

### Task 4: Descoberta do DFG (núcleo de mineração)

**Files:**
- Create: `backend/app/mining/__init__.py`
- Create: `backend/app/mining/dfg.py`
- Create: `backend/tests/test_dfg.py`

- [ ] **Step 1: Criar o pacote mining**

`backend/app/mining/__init__.py`:
```python
```
(arquivo vazio)

- [ ] **Step 2: Escrever o teste do DFG que falha**

`backend/tests/test_dfg.py`:
```python
import pandas as pd
from app.mining.dfg import discover_dfg
from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP


def _log():
    return pd.DataFrame(
        {
            CASE_ID: [1, 1, 1, 2, 2],
            ACTIVITY: ["A", "B", "C", "A", "B"],
            TIMESTAMP: pd.to_datetime(
                [
                    "2026-03-01 09:00",
                    "2026-03-01 10:00",
                    "2026-03-01 11:00",
                    "2026-03-02 09:00",
                    "2026-03-02 11:00",
                ]
            ),
        }
    )


def test_nodes_have_activities_with_counts():
    result = discover_dfg(_log())
    nodes = {n["id"]: n for n in result["nodes"]}
    assert set(nodes) == {"A", "B", "C"}
    assert nodes["A"]["count"] == 2
    assert nodes["C"]["count"] == 1


def test_edges_have_frequency():
    result = discover_dfg(_log())
    edges = {(e["source"], e["target"]): e for e in result["edges"]}
    # A->B ocorre nos dois casos; B->C apenas no caso 1
    assert edges[("A", "B")]["count"] == 2
    assert edges[("B", "C")]["count"] == 1


def test_edges_have_mean_duration_seconds():
    result = discover_dfg(_log())
    edges = {(e["source"], e["target"]): e for e in result["edges"]}
    # caso1 A->B = 3600s; caso2 A->B = 7200s; media = 5400s
    assert edges[("A", "B")]["mean_duration_seconds"] == 5400.0
```

- [ ] **Step 3: Rodar o teste e confirmar a falha**

Run: `.venv\Scripts\python -m pytest tests/test_dfg.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.mining.dfg'`

- [ ] **Step 4: Implementar discover_dfg**

`backend/app/mining/dfg.py`:
```python
"""Descoberta do Directly-Follows Graph a partir de um event log padrão.

Agnóstico de domínio: opera apenas sobre case_id / activity / timestamp.
"""
import pandas as pd
from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP


def discover_dfg(log: pd.DataFrame) -> dict:
    """Retorna {"nodes": [...], "edges": [...]}.

    nodes: {id, count}
    edges: {source, target, count, mean_duration_seconds}
    """
    log = log.sort_values([CASE_ID, TIMESTAMP])

    node_counts = log[ACTIVITY].value_counts()
    nodes = [
        {"id": str(act), "count": int(cnt)}
        for act, cnt in node_counts.items()
    ]

    edge_counts: dict[tuple[str, str], int] = {}
    edge_durations: dict[tuple[str, str], float] = {}

    for _, group in log.groupby(CASE_ID, sort=False):
        acts = group[ACTIVITY].tolist()
        times = group[TIMESTAMP].tolist()
        for i in range(len(acts) - 1):
            key = (str(acts[i]), str(acts[i + 1]))
            duration = (times[i + 1] - times[i]).total_seconds()
            edge_counts[key] = edge_counts.get(key, 0) + 1
            edge_durations[key] = edge_durations.get(key, 0.0) + duration

    edges = [
        {
            "source": src,
            "target": tgt,
            "count": cnt,
            "mean_duration_seconds": round(edge_durations[(src, tgt)] / cnt, 2),
        }
        for (src, tgt), cnt in edge_counts.items()
    ]

    return {"nodes": nodes, "edges": edges}
```

- [ ] **Step 5: Rodar o teste e confirmar que passa**

Run: `.venv\Scripts\python -m pytest tests/test_dfg.py -v`
Expected: PASS (3 testes)

- [ ] **Step 6: Commit**

```bash
git add backend/app/mining/ backend/tests/test_dfg.py
git commit -m "feat(backend): descoberta do DFG no nucleo de mineracao"
```

---

### Task 5: Gerador do dataset demo P2P

**Files:**
- Create: `backend/app/demo/__init__.py`
- Create: `backend/app/demo/generate_p2p.py`
- Create: `backend/tests/test_demo_p2p.py`

- [ ] **Step 1: Criar o pacote demo**

`backend/app/demo/__init__.py`:
```python
```
(arquivo vazio)

- [ ] **Step 2: Escrever o teste do gerador que falha**

`backend/tests/test_demo_p2p.py`:
```python
import pandas as pd
from app.demo.generate_p2p import build_p2p_log
from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP

HAPPY_PATH = [
    "Criar Requisicao",
    "Criar Pedido de Compra",
    "Aprovar Pedido",
    "Receber Mercadoria",
    "Receber Fatura",
    "Pagar",
]


def test_build_log_has_requested_number_of_cases():
    df = build_p2p_log(n_cases=50, seed=1)
    assert df[CASE_ID].nunique() == 50


def test_required_columns_present():
    df = build_p2p_log(n_cases=10, seed=1)
    assert {CASE_ID, ACTIVITY, TIMESTAMP}.issubset(df.columns)


def test_happy_path_case_follows_full_sequence():
    df = build_p2p_log(n_cases=10, seed=1)
    first_case = df[df[CASE_ID] == df[CASE_ID].iloc[0]]
    activities = first_case.sort_values(TIMESTAMP)[ACTIVITY].tolist()
    assert activities == HAPPY_PATH


def test_is_deterministic_with_seed():
    a = build_p2p_log(n_cases=20, seed=42)
    b = build_p2p_log(n_cases=20, seed=42)
    pd.testing.assert_frame_equal(a, b)
```

- [ ] **Step 3: Rodar o teste e confirmar a falha**

Run: `.venv\Scripts\python -m pytest tests/test_demo_p2p.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.demo.generate_p2p'`

- [ ] **Step 4: Implementar o gerador (apenas caminho feliz nesta fatia)**

`backend/app/demo/generate_p2p.py`:
```python
"""Gera um event log demo de P2P. Nesta fatia, apenas o caminho feliz.

Os casos com problemas (pagamento duplicado, maverick buying, etc.)
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


def build_p2p_log(n_cases: int = 2000, seed: int = 7) -> pd.DataFrame:
    rng = random.Random(seed)
    rows = []
    base = pd.Timestamp("2026-01-01 08:00:00")
    for case_idx in range(1, n_cases + 1):
        case_id = 4500000 + case_idx
        t = base + pd.Timedelta(days=rng.randint(0, 120))
        for activity in HAPPY_PATH:
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

- [ ] **Step 5: Rodar o teste e confirmar que passa**

Run: `.venv\Scripts\python -m pytest tests/test_demo_p2p.py -v`
Expected: PASS (4 testes)

- [ ] **Step 6: Gerar o arquivo CSV demo**

Run (a partir de `backend/`): `.venv\Scripts\python -m app.demo.generate_p2p`
Expected: imprime `Dataset demo gerado em data/demo_p2p.csv` e cria `backend/data/demo_p2p.csv`

- [ ] **Step 7: Commit**

```bash
git add backend/app/demo/ backend/tests/test_demo_p2p.py
git commit -m "feat(backend): gerador do dataset demo P2P (caminho feliz)"
```

---

### Task 6: Endpoint /api/process-graph

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_api.py`

- [ ] **Step 1: Escrever o teste do endpoint que falha**

Adicionar a `backend/tests/test_api.py`:
```python
def test_process_graph_returns_nodes_and_edges():
    response = client.get("/api/process-graph")
    assert response.status_code == 200
    body = response.json()
    assert "nodes" in body and "edges" in body
    node_ids = {n["id"] for n in body["nodes"]}
    assert "Criar Requisicao" in node_ids
    assert "Pagar" in node_ids
    # caminho feliz: existe a transicao Criar Requisicao -> Criar Pedido de Compra
    pairs = {(e["source"], e["target"]) for e in body["edges"]}
    assert ("Criar Requisicao", "Criar Pedido de Compra") in pairs
```

- [ ] **Step 2: Rodar o teste e confirmar a falha**

Run: `.venv\Scripts\python -m pytest tests/test_api.py::test_process_graph_returns_nodes_and_edges -v`
Expected: FAIL — status 404 (rota inexistente)

- [ ] **Step 3: Implementar a rota usando o gerador em memória**

Substituir o conteúdo de `backend/app/main.py` por:
```python
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
```

- [ ] **Step 4: Rodar a suíte completa de testes**

Run (a partir de `backend/`): `.venv\Scripts\python -m pytest -v`
Expected: PASS — todos os testes (health, csv_connector x3, dfg x3, demo_p2p x4, process-graph x2)

- [ ] **Step 5: Subir o servidor e checar manualmente**

Run: `.venv\Scripts\python -m uvicorn app.main:app --reload`
Abrir `http://localhost:8000/api/process-graph` no navegador — deve retornar JSON com `nodes` e `edges`. Encerrar com Ctrl+C.

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py backend/tests/test_api.py
git commit -m "feat(backend): endpoint /api/process-graph com DFG do demo P2P"
```

---

### Task 7: Frontend — grafo do processo com React Flow

**Files:**
- Create: projeto Vite em `frontend/`
- Create: `frontend/src/api.js`
- Create: `frontend/src/components/ProcessGraph.jsx`
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Criar o projeto Vite React**

Run (a partir da raiz do projeto):
```
npm create vite@latest frontend -- --template react
cd frontend
npm install
npm install reactflow
```

- [ ] **Step 2: Criar o cliente de API**

`frontend/src/api.js`:
```javascript
const BASE = "http://localhost:8000";

export async function fetchProcessGraph() {
  const res = await fetch(`${BASE}/api/process-graph`);
  if (!res.ok) throw new Error(`Erro ${res.status} ao buscar o grafo`);
  return res.json();
}
```

- [ ] **Step 3: Criar o componente ProcessGraph**

`frontend/src/components/ProcessGraph.jsx`:
```javascript
import { useEffect, useState } from "react";
import ReactFlow, { Background, Controls } from "reactflow";
import "reactflow/dist/style.css";
import { fetchProcessGraph } from "../api";

// Layout vertical simples: empilha as atividades na ordem em que chegam.
function toFlow(graph) {
  const order = graph.nodes.map((n) => n.id);
  const nodes = graph.nodes.map((n, i) => ({
    id: n.id,
    data: { label: `${n.id}  (${n.count})` },
    position: { x: 250, y: i * 110 },
    style: {
      padding: 10,
      borderRadius: 8,
      border: "1px solid #4f46e5",
      background: "#eef2ff",
      width: 220,
    },
  }));

  const maxCount = Math.max(...graph.edges.map((e) => e.count), 1);
  const edges = graph.edges.map((e) => ({
    id: `${e.source}->${e.target}`,
    source: e.source,
    target: e.target,
    label: `${e.count}`,
    style: { strokeWidth: 1 + (e.count / maxCount) * 6, stroke: "#6366f1" },
  }));

  return { nodes, edges, order };
}

export default function ProcessGraph() {
  const [flow, setFlow] = useState({ nodes: [], edges: [] });
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchProcessGraph()
      .then((graph) => setFlow(toFlow(graph)))
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <p style={{ color: "crimson" }}>Falha: {error}</p>;

  return (
    <div style={{ width: "100%", height: "100vh" }}>
      <ReactFlow nodes={flow.nodes} edges={flow.edges} fitView>
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
```

- [ ] **Step 4: Renderizar o grafo no App**

Substituir o conteúdo de `frontend/src/App.jsx` por:
```javascript
import ProcessGraph from "./components/ProcessGraph";

export default function App() {
  return (
    <div>
      <header style={{ padding: "12px 20px", borderBottom: "1px solid #e5e7eb" }}>
        <strong>Process Mining</strong> — Modulo Financeiro · P2P
      </header>
      <ProcessGraph />
    </div>
  );
}
```

- [ ] **Step 5: Verificação manual de ponta a ponta**

Com o backend rodando (`uvicorn app.main:app --reload` em `backend/`), rodar em `frontend/`:
```
npm run dev
```
Abrir `http://localhost:5173`. Esperado: o grafo aparece com os 6 nós do caminho feliz P2P (Criar Requisicao → … → Pagar), arestas com espessura proporcional à frequência e rótulo de contagem.

- [ ] **Step 6: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): grafo do processo P2P com React Flow"
```

---

## Verificação final da fatia

- [ ] `cd backend && .venv\Scripts\python -m pytest -v` — todos os testes passam.
- [ ] Backend serve `/api/process-graph` com JSON de nós/arestas.
- [ ] Frontend desenha o grafo do P2P em `http://localhost:5173`.
- [ ] Dataset `backend/data/demo_p2p.csv` gerado.

Entregável: ver um processo real (P2P, caminho feliz) na tela, de ponta a ponta.

## Notas para as próximas fatias

- **Fatia 2:** introduzir `pm4py` no núcleo para variantes e estatísticas; tela de variantes; filtros. Trocar o endpoint para usar o `CSVConnector` lendo `data/demo_p2p.csv` (em vez de gerar em memória) e adicionar upload.
- **Fatia 3:** estender `generate_p2p.py` com casos problemáticos; criar a interface `ProcessModule` e o `P2PModule` com os KPIs.
