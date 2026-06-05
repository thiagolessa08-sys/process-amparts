from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


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
    # caminho feliz: existe a transicao Criar Requisicao -> Criar Pedido de Compra
    pairs = {(e["source"], e["target"]) for e in body["edges"]}
    assert ("Criar Requisicao", "Criar Pedido de Compra") in pairs
