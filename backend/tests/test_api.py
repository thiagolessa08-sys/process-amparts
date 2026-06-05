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
