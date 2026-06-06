const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function getJson(path) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`Erro ${res.status} em ${path}`);
  return res.json();
}

export function fetchModule(key, filters = {}) {
  const params = new URLSearchParams();
  if (filters.fornecedores?.length) {
    filters.fornecedores.forEach((f) => params.append("fornecedores", f));
  }
  if (filters.startDate) params.set("start_date", filters.startDate);
  if (filters.endDate)   params.set("end_date",   filters.endDate);
  const qs = params.toString();
  return getJson(`/api/modules/${key}${qs ? "?" + qs : ""}`);
}

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
