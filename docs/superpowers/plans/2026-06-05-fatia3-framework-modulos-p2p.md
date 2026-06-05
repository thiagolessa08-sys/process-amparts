# Fatia 3 — Framework de Módulos + P2P Completo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Criar o framework `ProcessModule` e implementar o `P2PModule` completo, produzindo um endpoint `/api/modules/p2p` que devolve o payload exato esperado pelo design (nós com coordenadas/dwell, arestas com flags de gargalo/retrabalho, variantes com conformidade, KPIs com tendência, drill-downs).

**Architecture:** Cada módulo declara um **esqueleto visual** (nós com posição x/y + arestas com flags de renderização) e uma função `enrich(log)` que preenche métricas a partir do event log. O motor chama `module.enrich(log)` e devolve o payload pronto. O backend serve `/api/modules/{key}` (P2P hoje, O2C na Fatia 4). O contrato de dados espelha exatamente o `data.js` do design, para o port do frontend ser só um `fetch`.

**Tech Stack:** Python (FastAPI, pandas). Sem novas dependências.

**Contrato de saída de `/api/modules/p2p`** (espelha `data.js`):
```json
{
  "key": "p2p",
  "name": "Procure-to-Pay",
  "short": "P2P",
  "color": "#4F46E5",
  "totalCases": 2000,
  "avgVariants": 4,
  "dimension": "Fornecedor",
  "nodes": [{"id":"req","label":"Criar Requisicao","x":300,"y":162,"cases":2000,"avgDwell":"1,2 d"}],
  "edges": [{"id":"req->po","from":"req","to":"po","cases":2000,"time":"1,2 d","bottleneck":false,"rework":false}],
  "variants": [{"id":"v1","name":"Caminho feliz","tag":"happy","pct":70,"cases":1400,"path":["start","req",...],"avgDur":"5,1 d","conformant":true}],
  "kpis": [{"id":"lead","icon":"clock","sev":"info","label":"Lead time medio","value":"5,1","unit":"dias","sub":"...","trend":[...],"trendDir":"down"}],
  "drill": {},
  "filters": {"variantLabel":"Variante","dimLabel":"Fornecedor","dims":[]}
}
```

---

## Estrutura de arquivos

```
backend/
  app/
    modules/
      __init__.py               # NOVO: registro de módulos
      base.py                   # NOVO: ProcessModule (ABC)
      p2p_module.py             # NOVO: P2PModule com esqueleto visual + enrich()
    mining/
      dfg.py                    # MOD: adicionar avgDwell por nó e flags bottleneck por aresta
      variants.py               # MOD: adicionar tag, name, avgDur, conformant
    main.py                     # MOD: endpoint /api/modules/{key}
  tests/
    test_p2p_module.py          # NOVO
    test_mining_enriched.py     # NOVO: testa dwell e bottleneck
    test_api.py                 # MOD: endpoint /api/modules/p2p
```

---

### Task 1: DFG enriquecido — avgDwell por nó e flag bottleneck por aresta

O motor hoje devolve `{nodes: [{id, count}], edges: [{source, target, count, mean_duration_seconds}]}`.
Precisamos adicionar `avg_dwell_seconds` nos nós (tempo que o caso passa nessa atividade antes de avançar) e
`bottleneck: bool` nas arestas (arestas com tempo médio acima do percentil 75 do processo).

**Files:**
- Modify: `backend/app/mining/dfg.py`
- Create: `backend/tests/test_mining_enriched.py`

- [ ] **Step 1: Escrever os testes que falham**

`backend/tests/test_mining_enriched.py`:
```python
import pandas as pd
from app.mining.dfg import discover_dfg
from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP


def _log():
    """Caso 1: A(9h)->B(10h)->C(11h). Caso 2: A(9h)->B(11h)."""
    return pd.DataFrame({
        CASE_ID: [1, 1, 1, 2, 2],
        ACTIVITY: ["A", "B", "C", "A", "B"],
        TIMESTAMP: pd.to_datetime([
            "2026-03-01 09:00", "2026-03-01 10:00", "2026-03-01 11:00",
            "2026-03-02 09:00", "2026-03-02 11:00",
        ]),
    })


def test_nodes_have_avg_dwell_seconds():
    r = discover_dfg(_log())
    nodes = {n["id"]: n for n in r["nodes"]}
    # B tem dwell de: caso1=(C-B=3600s), caso2=nao tem sucessor -> 0; media = (3600+0)/2=1800
    assert "avg_dwell_seconds" in nodes["A"]
    assert nodes["B"]["avg_dwell_seconds"] == 1800.0


def test_edges_have_bottleneck_flag():
    r = discover_dfg(_log())
    edges = {(e["source"], e["target"]): e for e in r["edges"]}
    # A->B: media 5400s (maior); B->C: 3600s. p75 = 5400. A->B eh bottleneck.
    assert "bottleneck" in edges[("A", "B")]
    assert edges[("A", "B")]["bottleneck"] is True
    assert edges[("B", "C")]["bottleneck"] is False
```

- [ ] **Step 2: Rodar e confirmar a falha**

Run (a partir de `backend/`): `.venv\Scripts\python -m pytest tests/test_mining_enriched.py -v`
Expected: FAIL — `KeyError: 'avg_dwell_seconds'`

- [ ] **Step 3: Atualizar discover_dfg**

Substituir todo o conteúdo de `backend/app/mining/dfg.py` por:
```python
"""Descoberta do Directly-Follows Graph a partir de um event log padrão.

Agnóstico de domínio: opera apenas sobre case_id / activity / timestamp.
"""
import pandas as pd
from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP


def discover_dfg(log: pd.DataFrame) -> dict:
    """Retorna {"nodes": [...], "edges": [...]}.

    nodes: {id, count, avg_dwell_seconds}
    edges: {source, target, count, mean_duration_seconds, bottleneck}

    avg_dwell_seconds = tempo médio que um caso permanece nessa atividade
    antes de avançar para a próxima (0 para a última atividade do caso).

    bottleneck = True quando mean_duration_seconds >= percentil 75 das arestas.
    """
    log = log.sort_values([CASE_ID, TIMESTAMP])

    node_counts = log[ACTIVITY].value_counts()

    edge_counts: dict[tuple[str, str], int] = {}
    edge_durations: dict[tuple[str, str], float] = {}
    node_dwell_total: dict[str, float] = {}
    node_dwell_count: dict[str, int] = {}

    for _, group in log.groupby(CASE_ID, sort=False):
        acts = group[ACTIVITY].tolist()
        times = group[TIMESTAMP].tolist()
        for i in range(len(acts) - 1):
            key = (str(acts[i]), str(acts[i + 1]))
            duration = (times[i + 1] - times[i]).total_seconds()
            edge_counts[key] = edge_counts.get(key, 0) + 1
            edge_durations[key] = edge_durations.get(key, 0.0) + duration
            # dwell da atividade i = tempo até a próxima atividade
            act = str(acts[i])
            node_dwell_total[act] = node_dwell_total.get(act, 0.0) + duration
            node_dwell_count[act] = node_dwell_count.get(act, 0) + 1

    edges_raw = [
        {
            "source": src,
            "target": tgt,
            "count": cnt,
            "mean_duration_seconds": round(edge_durations[(src, tgt)] / cnt, 2),
        }
        for (src, tgt), cnt in edge_counts.items()
    ]

    # bottleneck = aresta com tempo médio >= p75
    if edges_raw:
        import statistics
        durations = [e["mean_duration_seconds"] for e in edges_raw]
        p75 = sorted(durations)[int(len(durations) * 0.75)]
        for e in edges_raw:
            e["bottleneck"] = e["mean_duration_seconds"] >= p75
    else:
        for e in edges_raw:
            e["bottleneck"] = False

    nodes = [
        {
            "id": str(act),
            "count": int(cnt),
            "avg_dwell_seconds": round(
                node_dwell_total.get(str(act), 0.0) / node_dwell_count[str(act)], 2
            ) if str(act) in node_dwell_count else 0.0,
        }
        for act, cnt in node_counts.items()
    ]

    return {"nodes": nodes, "edges": edges_raw}
```

- [ ] **Step 4: Rodar e confirmar GREEN**

Run: `.venv\Scripts\python -m pytest tests/test_mining_enriched.py tests/test_dfg.py -v`
Expected: PASS (todos — os testes antigos do DFG ainda passam pois os campos novos são aditivos)

- [ ] **Step 5: Commit**

```bash
git add backend/app/mining/dfg.py backend/tests/test_mining_enriched.py
git commit -m "feat(backend): DFG enriquecido com avgDwell e flag bottleneck"
```

---

### Task 2: Variantes enriquecidas — tag, name, avgDur, conformant

**Files:**
- Modify: `backend/app/mining/variants.py`
- Create: `backend/app/mining/conformance.py`
- Modify: `backend/tests/test_variants.py`

- [ ] **Step 1: Criar o módulo de conformidade**

`backend/app/mining/conformance.py`:
```python
"""Checa se uma sequência de atividades conforma com o processo-ideal."""


def is_conformant(sequence: list[str], ideal: list[str]) -> bool:
    """Retorna True se 'sequence' contém todas as atividades de 'ideal'
    na mesma ordem relativa (subsequência), sem atividades extras
    que não estejam no ideal."""
    ideal_set = set(ideal)
    # atividades do caso que estão no ideal
    filtered = [a for a in sequence if a in ideal_set]
    # deve ser exatamente o ideal (sem repetições, sem pulos)
    return filtered == ideal
```

- [ ] **Step 2: Atualizar os testes de variantes**

Substituir todo o conteúdo de `backend/tests/test_variants.py` por:
```python
import pandas as pd
from app.mining.variants import discover_variants
from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP

IDEAL = ["A", "B", "C"]


def _log():
    return pd.DataFrame({
        CASE_ID: [1, 1, 1, 2, 2, 3, 3],
        ACTIVITY: ["A", "B", "C", "A", "B", "A", "C"],
        TIMESTAMP: pd.to_datetime([
            "2026-03-01 09:00", "2026-03-01 10:00", "2026-03-01 11:00",
            "2026-03-02 09:00", "2026-03-02 10:00",
            "2026-03-03 09:00", "2026-03-03 10:00",
        ]),
    })


def test_returns_variants_ordered_by_frequency():
    result = discover_variants(_log(), ideal_path=IDEAL)
    assert result[0]["activities"] == ["A", "B", "C"]
    assert result[0]["count"] == 1


def test_percentages_sum_to_100():
    result = discover_variants(_log(), ideal_path=IDEAL)
    assert round(sum(v["percentage"] for v in result), 1) == 100.0


def test_each_variant_has_sequential_id():
    result = discover_variants(_log(), ideal_path=IDEAL)
    ids = [v["variant_id"] for v in result]
    assert ids == list(range(1, len(ids) + 1))


def test_variants_have_avg_duration():
    result = discover_variants(_log(), ideal_path=IDEAL)
    for v in result:
        assert "avg_duration_seconds" in v
        assert v["avg_duration_seconds"] >= 0


def test_conformant_flag_matches_ideal():
    result = discover_variants(_log(), ideal_path=IDEAL)
    by_acts = {tuple(v["activities"]): v for v in result}
    assert by_acts[("A", "B", "C")]["conformant"] is True
    assert by_acts[("A", "B")]["conformant"] is False
    assert by_acts[("A", "C")]["conformant"] is False
```

- [ ] **Step 3: Rodar e confirmar a falha**

Run: `.venv\Scripts\python -m pytest tests/test_variants.py -v`
Expected: FAIL — `discover_variants() missing argument 'ideal_path'`

- [ ] **Step 4: Atualizar discover_variants**

Substituir todo o conteúdo de `backend/app/mining/variants.py` por:
```python
"""Descoberta de variantes: cada caminho distinto inicio->fim de um caso."""
import pandas as pd
from app.eventlog import CASE_ID, ACTIVITY, TIMESTAMP
from app.mining.conformance import is_conformant


def discover_variants(log: pd.DataFrame, ideal_path: list[str] | None = None) -> list[dict]:
    """Retorna lista de {variant_id, activities, count, percentage,
    avg_duration_seconds, conformant}, ordenada por frequencia decrescente."""
    log = log.sort_values([CASE_ID, TIMESTAMP])

    case_sequences: dict[int | str, list[str]] = {}
    case_durations: dict[int | str, float] = {}

    for case_id, group in log.groupby(CASE_ID, sort=False):
        group = group.sort_values(TIMESTAMP)
        acts = [str(a) for a in group[ACTIVITY].tolist()]
        times = group[TIMESTAMP].tolist()
        duration = (times[-1] - times[0]).total_seconds() if len(times) > 1 else 0.0
        case_sequences[case_id] = acts
        case_durations[case_id] = duration

    seq_cases: dict[tuple, list] = {}
    for case_id, acts in case_sequences.items():
        key = tuple(acts)
        if key not in seq_cases:
            seq_cases[key] = []
        seq_cases[key].append(case_id)

    total = len(case_sequences)
    ordered = sorted(seq_cases.items(), key=lambda kv: len(kv[1]), reverse=True)

    result = []
    for i, (seq, case_ids) in enumerate(ordered):
        count = len(case_ids)
        durations = [case_durations[cid] for cid in case_ids]
        avg_dur = round(sum(durations) / count, 2) if durations else 0.0
        conformant = is_conformant(list(seq), ideal_path) if ideal_path else True
        result.append({
            "variant_id": i + 1,
            "activities": list(seq),
            "count": count,
            "percentage": round(100 * count / total, 1),
            "avg_duration_seconds": avg_dur,
            "conformant": conformant,
        })

    return result
```

- [ ] **Step 5: Atualizar compute_statistics para usar a nova assinatura**

Abrir `backend/app/mining/stats.py` e atualizar a chamada:
```python
"""Estatisticas gerais do processo a partir do event log padrao."""
import pandas as pd
from app.eventlog import CASE_ID, TIMESTAMP
from app.mining.variants import discover_variants


def compute_statistics(log: pd.DataFrame, ideal_path: list[str] | None = None) -> dict:
    grp = log.groupby(CASE_ID)[TIMESTAMP]
    durations = (grp.max() - grp.min()).dt.total_seconds()
    return {
        "num_cases": int(log[CASE_ID].nunique()),
        "num_events": int(len(log)),
        "num_variants": len(discover_variants(log, ideal_path=ideal_path)),
        "mean_throughput_seconds": round(float(durations.mean()), 2),
        "median_throughput_seconds": round(float(durations.median()), 2),
    }
```

- [ ] **Step 6: Rodar a suíte completa**

Run: `.venv\Scripts\python -m pytest -v`
Expected: PASS — todos os testes (a API usa `discover_variants` sem ideal_path, que é backwards-compatible)

- [ ] **Step 7: Commit**

```bash
git add backend/app/mining/variants.py backend/app/mining/conformance.py backend/app/mining/stats.py backend/tests/test_variants.py
git commit -m "feat(backend): variantes enriquecidas com conformidade e duracao media"
```

---

### Task 3: Framework ProcessModule

**Files:**
- Create: `backend/app/modules/__init__.py`
- Create: `backend/app/modules/base.py`

- [ ] **Step 1: Criar a interface base**

`backend/app/modules/__init__.py`:
```python
from app.modules.base import ProcessModule

_registry: dict[str, ProcessModule] = {}


def register(module: "ProcessModule") -> None:
    _registry[module.key] = module


def get(key: str) -> "ProcessModule | None":
    return _registry.get(key)


def all_keys() -> list[str]:
    return list(_registry.keys())
```

`backend/app/modules/base.py`:
```python
"""Interface que todo módulo de processo deve implementar."""
from abc import ABC, abstractmethod
import pandas as pd


class ProcessModule(ABC):
    """Declara o esqueleto visual e calcula métricas a partir do event log."""

    @property
    @abstractmethod
    def key(self) -> str:
        """Identificador único: 'p2p', 'o2c', etc."""
        ...

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def short(self) -> str: ...

    @property
    @abstractmethod
    def color(self) -> str: ...

    @property
    @abstractmethod
    def ideal_path(self) -> list[str]:
        """IDs das atividades do caminho feliz, na ordem correta."""
        ...

    @abstractmethod
    def enrich(self, log: pd.DataFrame) -> dict:
        """Recebe o event log e devolve o payload completo do módulo
        no contrato esperado pelo frontend."""
        ...
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/modules/
git commit -m "feat(backend): framework ProcessModule (interface + registro)"
```

---

### Task 4: P2PModule — esqueleto visual + enrich completo

**Files:**
- Create: `backend/app/modules/p2p_module.py`
- Create: `backend/tests/test_p2p_module.py`

- [ ] **Step 1: Escrever o teste que falha**

`backend/tests/test_p2p_module.py`:
```python
from app.modules.p2p_module import P2PModule
from app.demo.generate_p2p import build_p2p_log

module = P2PModule()
log = build_p2p_log(n_cases=500, seed=7)


def test_payload_has_required_keys():
    payload = module.enrich(log)
    for key in ["key", "name", "short", "color", "totalCases", "avgVariants",
                "nodes", "edges", "variants", "kpis", "drill", "filters"]:
        assert key in payload, f"chave ausente: {key}"


def test_nodes_have_visual_and_metric_fields():
    payload = module.enrich(log)
    node = next(n for n in payload["nodes"] if n["id"] == "req")
    assert "x" in node and "y" in node
    assert "cases" in node
    assert "avgDwell" in node


def test_edges_have_bottleneck_and_time():
    payload = module.enrich(log)
    edge = payload["edges"][0]
    assert "bottleneck" in edge
    assert "time" in edge
    assert "cases" in edge


def test_variants_have_conformance_and_tag():
    payload = module.enrich(log)
    v = payload["variants"][0]
    assert "conformant" in v
    assert "tag" in v
    assert "avgDur" in v
    assert "path" in v


def test_happy_path_variant_is_conformant():
    payload = module.enrich(log)
    happy = next((v for v in payload["variants"] if v["conformant"]), None)
    assert happy is not None


def test_kpis_have_trend_and_severity():
    payload = module.enrich(log)
    kpi = payload["kpis"][0]
    assert "trend" in kpi
    assert "sev" in kpi
    assert "value" in kpi


def test_total_cases_matches_log():
    payload = module.enrich(log)
    assert payload["totalCases"] == log["case_id"].nunique()
```

- [ ] **Step 2: Rodar e confirmar a falha**

Run: `.venv\Scripts\python -m pytest tests/test_p2p_module.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.modules.p2p_module'`

- [ ] **Step 3: Implementar o P2PModule**

`backend/app/modules/p2p_module.py`:
```python
"""Módulo P2P (Procure-to-Pay).

Declara o esqueleto visual (nós com coordenadas, arestas com flags de curva)
e calcula métricas reais a partir do event log via enrich().
"""
import pandas as pd
from app.modules.base import ProcessModule
from app.mining.dfg import discover_dfg
from app.mining.variants import discover_variants
from app.eventlog import CASE_ID, TIMESTAMP

# IDs canônicos das atividades (usados no esqueleto e no ideal_path)
REQ = "req"
PO = "po"
APPROVE = "approve"
GOODS = "goods"
INVOICE = "invoice"
PAY = "pay"
START = "start"
END = "end"

# Mapeamento: label do CSV -> id canônico
ACTIVITY_MAP = {
    "Criar Requisicao": REQ,
    "Criar Pedido de Compra": PO,
    "Aprovar Pedido": APPROVE,
    "Receber Mercadoria": GOODS,
    "Receber Fatura": INVOICE,
    "Pagar": PAY,
}

IDEAL = [START, REQ, PO, APPROVE, GOODS, INVOICE, PAY, END]
IDEAL_ACTIVITIES = [REQ, PO, APPROVE, GOODS, INVOICE, PAY]

# Coordenadas visuais fixas (sistema de coords do ProcessGraph.jsx: 760×1040)
_NODE_SKELETON = {
    START:   {"label": "Início",                  "x": 300, "y":  50, "type": "start"},
    REQ:     {"label": "Criar Requisição",         "x": 300, "y": 162},
    PO:      {"label": "Criar Pedido de Compra",   "x": 300, "y": 290},
    APPROVE: {"label": "Aprovar Pedido",           "x": 300, "y": 420},
    GOODS:   {"label": "Receber Mercadoria",       "x": 300, "y": 558},
    INVOICE: {"label": "Receber Fatura",           "x": 300, "y": 692},
    PAY:     {"label": "Pagar",                    "x": 300, "y": 826},
    END:     {"label": "Fim",                      "x": 300, "y": 936, "type": "end"},
}

# Flags visuais fixos por aresta (curvas, loops — não dependem do dado)
_EDGE_FLAGS = {
    (PO, APPROVE): {},
    (PO, GOODS):   {"skip": True},
    (APPROVE, GOODS): {},
    (APPROVE, INVOICE): {"skip": True, "side": 1, "off": 120},
    (INVOICE, GOODS): {"reverse": True},
    (INVOICE, PAY): {},
    (PAY, PAY):    {"selfloop": True, "dup": True},
}


def _fmt_days(seconds: float) -> str:
    if seconds <= 0:
        return "—"
    days = seconds / 86400
    return f"{days:.1f} d".replace(".", ",")


def _variant_tag(activities: list[str], conformant: bool) -> str:
    if conformant:
        return "happy"
    acts_set = set(activities)
    if PAY in activities and activities.count(PAY) > 1:
        return "crit"
    if APPROVE not in acts_set:
        return "risk"
    if APPROVE in activities and activities.count(APPROVE) > 1:
        return "rework"
    if INVOICE in acts_set and GOODS in acts_set:
        inv_idx = activities.index(INVOICE)
        goods_idx = activities.index(GOODS)
        if inv_idx < goods_idx:
            return "risk"
    return "other"


def _variant_name(activities: list[str], tag: str, idx: int) -> str:
    names = {
        "happy": "Caminho feliz",
        "crit": "Pagamento duplicado",
        "risk": "Sem aprovação de pedido" if APPROVE not in activities else "Fatura antes da mercadoria",
        "rework": "Retrabalho — aprovação repetida",
    }
    return names.get(tag, f"Variante {idx + 1}")


class P2PModule(ProcessModule):
    key = "p2p"
    name = "Procure-to-Pay"
    short = "P2P"
    color = "#4F46E5"
    ideal_path = IDEAL_ACTIVITIES

    def enrich(self, log: pd.DataFrame) -> dict:
        # 1. normalizar activity labels -> ids canônicos
        log = log.copy()
        log["activity"] = log["activity"].map(ACTIVITY_MAP).fillna(log["activity"])

        total_cases = int(log[CASE_ID].nunique())

        # 2. DFG enriquecido
        dfg = discover_dfg(log)
        node_metrics = {n["id"]: n for n in dfg["nodes"]}
        edge_metrics = {(e["source"], e["target"]): e for e in dfg["edges"]}

        # 3. Variantes enriquecidas
        raw_variants = discover_variants(log, ideal_path=IDEAL_ACTIVITIES)

        # 4. Montar nós no contrato do frontend
        nodes = []
        for nid, skel in _NODE_SKELETON.items():
            m = node_metrics.get(nid, {})
            node = {
                "id": nid,
                "label": skel["label"],
                "x": skel["x"],
                "y": skel["y"],
                "cases": m.get("count", 0),
                "avgDwell": _fmt_days(m.get("avg_dwell_seconds", 0)),
            }
            if "type" in skel:
                node["type"] = skel["type"]
                node["cases"] = total_cases
            nodes.append(node)

        # 5. Montar arestas no contrato do frontend
        edges = []
        for (src, tgt), m in edge_metrics.items():
            flags = _EDGE_FLAGS.get((src, tgt), {})
            edge = {
                "id": f"{src}->{tgt}",
                "from": src,
                "to": tgt,
                "cases": m["count"],
                "time": _fmt_days(m["mean_duration_seconds"]),
                "bottleneck": m["bottleneck"],
                "rework": flags.get("reverse", False) or flags.get("dup", False),
            }
            edge.update(flags)
            edges.append(edge)

        # nós start/end com arestas fixas
        edges = [{"id": f"{START}->{REQ}", "from": START, "to": REQ,
                   "cases": total_cases, "time": "—", "bottleneck": False, "rework": False}] + edges
        edges.append({"id": f"{PAY}->{END}", "from": PAY, "to": END,
                      "cases": total_cases, "time": "—", "bottleneck": False, "rework": False})

        # 6. Variantes no contrato do frontend
        variants = []
        for i, v in enumerate(raw_variants):
            acts = v["activities"]
            tag = _variant_tag(acts, v["conformant"])
            variants.append({
                "id": f"v{i+1}",
                "name": _variant_name(acts, tag, i),
                "tag": tag,
                "pct": v["percentage"],
                "cases": v["count"],
                "path": [START] + acts + [END],
                "avgDur": _fmt_days(v["avg_duration_seconds"]),
                "conformant": v["conformant"],
            })

        # 7. KPIs calculados do log
        kpis = self._compute_kpis(log, total_cases, raw_variants)

        # 8. Filtros (fornecedores únicos se a coluna existir)
        dims: list[str] = []
        if "resource" in log.columns:
            dims = sorted(log["resource"].dropna().unique().tolist())[:10]

        return {
            "key": self.key,
            "name": self.name,
            "short": self.short,
            "color": self.color,
            "totalCases": total_cases,
            "avgVariants": len(variants),
            "dimension": "Fornecedor",
            "nodes": nodes,
            "edges": edges,
            "variants": variants,
            "kpis": kpis,
            "drill": {},
            "filters": {
                "variantLabel": "Variante",
                "dimLabel": "Fornecedor",
                "dims": dims,
            },
        }

    def _compute_kpis(self, log: pd.DataFrame, total_cases: int,
                      variants: list[dict]) -> list[dict]:
        grp = log.groupby(CASE_ID)[TIMESTAMP]
        durations_s = (grp.max() - grp.min()).dt.total_seconds()
        mean_days = durations_s.mean() / 86400

        # conformidade
        conformant_count = sum(v["count"] for v in variants if v["conformant"])
        conformance_pct = round(100 * conformant_count / total_cases) if total_cases else 0

        # maverick buying: casos sem APPROVE
        has_approve = log[log["activity"] == APPROVE][CASE_ID].unique()
        maverick_count = total_cases - len(has_approve)
        maverick_pct = round(100 * maverick_count / total_cases, 1) if total_cases else 0

        # retrabalho: casos com APPROVE repetido
        approve_log = log[log["activity"] == APPROVE]
        rework_count = int((approve_log.groupby(CASE_ID).size() > 1).sum())
        rework_pct = round(100 * rework_count / total_cases, 1) if total_cases else 0

        # pagamentos duplicados: casos com PAY repetido
        pay_log = log[log["activity"] == PAY]
        dup_count = int((pay_log.groupby(CASE_ID).size() > 1).sum())

        # tendência simulada (últimos 7 "períodos" convergindo para o valor atual)
        def trend(val: float, direction: str, steps: int = 7) -> list[float]:
            delta = val * 0.08
            if direction == "down":
                return [round(val + delta * (steps - i - 1), 1) for i in range(steps)]
            return [round(val - delta * (steps - i - 1), 1) for i in range(steps)]

        return [
            {
                "id": "lead", "icon": "clock", "sev": "info",
                "label": "Lead time médio",
                "value": f"{mean_days:.1f}".replace(".", ","),
                "unit": "dias",
                "sub": f"Tempo médio de {total_cases:,} casos".replace(",", "."),
                "trend": trend(mean_days, "down"),
                "trendDir": "down", "good": "down",
            },
            {
                "id": "conf", "icon": "shield",
                "sev": "ok" if conformance_pct >= 80 else "warn",
                "label": "Conformidade do processo",
                "value": f"{conformance_pct}%",
                "sub": f"{total_cases - conformant_count} casos fora do fluxo padrão",
                "trend": trend(conformance_pct, "up"),
                "trendDir": "up", "good": "up",
            },
            {
                "id": "maverick", "icon": "cart",
                "sev": "warn" if maverick_pct > 5 else "info",
                "label": "Maverick buying",
                "value": f"{maverick_pct}%".replace(".", ","),
                "sub": "Compras sem aprovação formal",
                "trend": trend(maverick_pct, "down"),
                "trendDir": "down", "good": "down",
            },
            {
                "id": "rework", "icon": "loop",
                "sev": "warn" if rework_pct > 5 else "info",
                "label": "Taxa de retrabalho",
                "value": f"{rework_pct}%".replace(".", ","),
                "sub": f"{rework_count} casos com aprovação repetida",
                "trend": trend(rework_pct, "down"),
                "trendDir": "down", "good": "down",
            },
            {
                "id": "dup", "icon": "alert",
                "sev": "crit" if dup_count > 0 else "info",
                "label": "Pagamentos duplicados",
                "value": str(dup_count),
                "unit": "casos",
                "sub": "Mesmo caso com Pagar repetido",
                "trend": trend(float(dup_count), "down"),
                "trendDir": "down",
            },
            {
                "id": "through", "icon": "activity", "sev": "info",
                "label": "Casos processados",
                "value": f"{total_cases:,}".replace(",", "."),
                "sub": f"{log.shape[0]:,} eventos no log".replace(",", "."),
                "trend": trend(float(total_cases), "up"),
                "trendDir": "up",
            },
        ]
```

- [ ] **Step 4: Rodar e confirmar GREEN**

Run: `.venv\Scripts\python -m pytest tests/test_p2p_module.py -v`
Expected: PASS (7 testes)

- [ ] **Step 5: Registrar o módulo e rodar a suíte completa**

Adicionar ao final de `backend/app/modules/__init__.py`:
```python
# auto-registro dos módulos disponíveis
from app.modules.p2p_module import P2PModule
register(P2PModule())
```

Run: `.venv\Scripts\python -m pytest -v`
Expected: PASS — todos os testes

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/ backend/tests/test_p2p_module.py
git commit -m "feat(backend): P2PModule com esqueleto visual e KPIs calculados"
```

---

### Task 5: Endpoint /api/modules/{key}

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_api.py`

- [ ] **Step 1: Escrever o teste do endpoint que falha**

Adicionar ao final de `backend/tests/test_api.py`:
```python
def test_module_p2p_returns_full_payload():
    response = client.get("/api/modules/p2p")
    assert response.status_code == 200
    body = response.json()
    for key in ["key", "name", "nodes", "edges", "variants", "kpis", "filters"]:
        assert key in body, f"chave ausente: {key}"
    assert body["key"] == "p2p"
    assert body["totalCases"] == 2000
    assert len(body["variants"]) >= 3
    # KPIs devem ter trend e sev
    kpi = body["kpis"][0]
    assert "trend" in kpi and "sev" in kpi


def test_module_unknown_returns_404():
    response = client.get("/api/modules/xyz")
    assert response.status_code == 404
```

- [ ] **Step 2: Rodar e confirmar a falha**

Run: `.venv\Scripts\python -m pytest tests/test_api.py::test_module_p2p_returns_full_payload tests/test_api.py::test_module_unknown_returns_404 -v`
Expected: FAIL — 404

- [ ] **Step 3: Adicionar o endpoint ao main.py**

Adicionar imports no topo de `backend/app/main.py` (após os imports existentes):
```python
from app import modules as module_registry
```

Adicionar a rota ao final de `backend/app/main.py`:
```python
@app.get("/api/modules/{key}")
def get_module(key: str):
    module = module_registry.get(key)
    if not module:
        raise HTTPException(status_code=404, detail=f"Modulo '{key}' nao encontrado")
    return module.enrich(data_source.get_log())
```

Nota: `HTTPException` já está importado da Task 5 da Fatia 2.

- [ ] **Step 4: Rodar a suíte completa**

Run: `.venv\Scripts\python -m pytest -v`
Expected: PASS — todos os testes

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_api.py
git commit -m "feat(backend): endpoint /api/modules/{key} para payload completo do modulo"
```

---

## Verificação final da fatia

- [ ] `cd backend && .venv\Scripts\python -m pytest -v` — todos os testes passam.
- [ ] `GET /api/modules/p2p` retorna payload com nodes/edges/variants/kpis no contrato do design.
- [ ] `GET /api/modules/xyz` retorna 404.

Entregável: backend pronto para ser consumido pelo design portado; trocar `window.PM_DATA["p2p"]` por `fetch("/api/modules/p2p")` é suficiente para ligar o frontend real.

## Notas para a próxima fatia

- **Port do frontend:** portar o design (ZIP) para o app Vite, substituindo `window.PM_DATA` por `fetch`. É o "Visual primeiro" que ficou para depois.
- **Fatia 4 — O2C:** criar `O2CModule` seguindo o mesmo padrão do `P2PModule`, com gerador `generate_o2c.py`.
