const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function getJson(path) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`Erro ${res.status} em ${path}`);
  return res.json();
}

function filterParams(filters = {}) {
  const params = new URLSearchParams();
  if (filters.fornecedores?.length) {
    filters.fornecedores.forEach((f) => params.append("fornecedores", f));
  }
  if (filters.startDate) params.set("start_date", filters.startDate);
  if (filters.endDate)   params.set("end_date",   filters.endDate);
  if (filters.ano)       params.set("ano", filters.ano);
  if (filters.mes)       params.set("mes", filters.mes);
  if (filters.activity?.id && filters.activity?.mode) {
    params.set("act_id", filters.activity.id);
    params.set("act_mode", filters.activity.mode);
  }
  return params.toString();
}

export function fetchModule(key, filters = {}) {
  const qs = filterParams(filters);
  return getJson(`/api/modules/${key}${qs ? "?" + qs : ""}`);
}

export function fetchCases(key, filters = {}) {
  const qs = filterParams(filters);
  return getJson(`/api/modules/${key}/cases${qs ? "?" + qs : ""}`);
}

export function fetchUser(key, name, filters = {}) {
  const qs = filterParams(filters);
  return getJson(`/api/modules/${key}/user/${encodeURIComponent(name)}${qs ? "?" + qs : ""}`);
}

export function aiStatus() {
  return getJson("/api/ai/status");
}

export async function askAssistant(key, question, filters = {}) {
  const qs = filterParams(filters);
  const res = await fetch(`${BASE}/api/modules/${key}/ask${qs ? "?" + qs : ""}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Erro ${res.status}`);
  }
  return res.json();
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
