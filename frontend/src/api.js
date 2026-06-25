const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function getJson(path) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    const err = new Error(detail.detail || `Erro ${res.status} em ${path}`);
    err.status = res.status;
    throw err;
  }
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
  if (filters.dias?.length) filters.dias.forEach((d) => params.append("dias", d));
  if (filters.produto) params.set("produto", filters.produto);
  if (filters.variantKeys?.length) {
    filters.variantKeys.forEach((k) => params.append("variant", k));
    params.set("variant_mode", filters.variantMode || "include");
  }
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

export function fetchModuleStatus(key) {
  return getJson(`/api/modules/${key}/status`);
}

export function fetchCases(key, filters = {}, opts = {}) {
  const params = new URLSearchParams(filterParams(filters));
  if (opts.q && opts.q.trim()) params.set("q", opts.q.trim());
  if (opts.limit) params.set("limit", opts.limit);
  const qs = params.toString();
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

/* ───────── recarga da fonte (admin) ───────── */
function adminHeaders(extra = {}) {
  const t = (typeof localStorage !== "undefined" && localStorage.getItem("pm-admin-token")) || "";
  return t ? { ...extra, "X-Admin-Token": t } : extra;
}

async function sendJson(path, body, method = "POST") {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: adminHeaders(body ? { "Content-Type": "application/json" } : {}),
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Erro ${res.status}`);
  }
  return res.json();
}

export function refreshModule(key) {
  return sendJson(`/api/modules/${key}/refresh`, null);
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
