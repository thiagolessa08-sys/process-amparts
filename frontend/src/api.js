const BASE = "http://localhost:8000";

export async function fetchProcessGraph() {
  const res = await fetch(`${BASE}/api/process-graph`);
  if (!res.ok) throw new Error(`Erro ${res.status} ao buscar o grafo`);
  return res.json();
}
