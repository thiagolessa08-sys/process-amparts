import { useState, useEffect } from "react";
import { Icon } from "./icons.jsx";
import { fetchCases } from "./api.js";

const PAGE_LIMIT = 500;

/* ───────── formatadores ───────── */
function fmtDuration(s) {
  s = Number(s) || 0;
  if (s < 60) return "—";
  const d = s / 86400, h = s / 3600, m = s / 60;
  if (d >= 1) return `${Math.round(d)} d`;
  if (h >= 1) return `${Math.round(h)} h`;
  return `${Math.round(m)} min`;
}
function fmtDelta(s) {
  if (s == null) return "";
  s = Number(s);
  const d = s / 86400, h = s / 3600, m = s / 60;
  if (d >= 1) return `+${Math.round(d)}d`;
  if (h >= 1) return `+${Math.round(h)}h`;
  if (m >= 1) return `+${Math.round(m)}m`;
  return `+${Math.round(s)}s`;
}
function fmtTs(iso) {
  if (!iso) return "—";
  const dt = new Date(iso);
  const p = (n) => String(n).padStart(2, "0");
  const yy = String(dt.getFullYear()).slice(2);
  return `${p(dt.getDate())}/${p(dt.getMonth() + 1)}/${yy} ${p(dt.getHours())}:${p(dt.getMinutes())}:${p(dt.getSeconds())}`;
}

/* ───────── painel de detalhes do caso ───────── */
function CaseDetail({ caseObj, onPrev, onNext }) {
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(() => new Set());
  useEffect(() => { setSearch(""); setOpen(new Set()); }, [caseObj?.id]);
  const toggle = (i) => setOpen((s) => { const n = new Set(s); n.has(i) ? n.delete(i) : n.add(i); return n; });

  if (!caseObj) {
    return <div className="cex-detail"><div className="cex-empty">Selecione um caso para ver os detalhes</div></div>;
  }
  const acts = caseObj.activities.filter((a) => a.label.toLowerCase().includes(search.toLowerCase()));
  return (
    <div className="cex-detail">
      <div className="cex-detail-head">
        <div className="cex-detail-title">Detalhes do caso: <b>{caseObj.id}</b></div>
        <div className="cex-nav">
          <button onClick={onPrev} title="Caso anterior"><Icon name="chevronR" size={16} style={{ transform: "rotate(180deg)" }} /></button>
          <button onClick={onNext} title="Próximo caso"><Icon name="chevronR" size={16} /></button>
        </div>
      </div>
      <div className="cex-search">
        <Icon name="search" size={15} />
        <input placeholder="Buscar atividade…" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      <div className="cex-acts-head">
        <span>Activities</span>
        <span className="cex-acts-count">{acts.length} {acts.length === 1 ? "item" : "itens"}</span>
      </div>
      <div className="cex-acts">
        {acts.map((a, i) => {
          const attrs = a.attrs && Object.entries(a.attrs);
          const expandable = !!(attrs && attrs.length);
          const isOpen = open.has(i);
          return (
            <div className={"cex-act" + (isOpen ? " open" : "")} key={i}>
              <div className="cex-act-row" style={{ cursor: expandable ? "pointer" : "default" }}
                onClick={() => expandable && toggle(i)}>
                <span className="cex-act-dot" />
                <div className="cex-act-body">
                  <div className="cex-act-label">{a.label}</div>
                  <div className="cex-act-ts mono">{fmtTs(a.ts)}</div>
                </div>
                {a.deltaSeconds != null && <span className="cex-act-delta mono">{fmtDelta(a.deltaSeconds)}</span>}
                {expandable && <span className="cex-act-chev"><Icon name="chevronD" size={15} style={{ transform: isOpen ? "rotate(180deg)" : "none" }} /></span>}
              </div>
              {isOpen && expandable && (
                <div className="cex-attrs">
                  {attrs.map(([k, v]) => (
                    <div className="cex-attr" key={k}>
                      <span className="cex-attr-k">{k}</span>
                      <span className="cex-attr-v mono">{v}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
        {acts.length === 0 && <div className="cex-empty">Nenhuma atividade encontrada</div>}
      </div>
    </div>
  );
}

/* ───────── tela ───────── */
export function CaseExplorerScreen({ data, filters }) {
  const [cases, setCases] = useState(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [query, setQuery] = useState("");

  // busca por Case Id é server-side (escala p/ centenas de milhares de casos); debounce 300ms
  useEffect(() => {
    let alive = true;
    setLoading(true); setError(null);
    const t = setTimeout(() => {
      fetchCases(data.key, filters, { q: query, limit: PAGE_LIMIT })
        .then((res) => { if (alive) { setCases(res.cases); setTotal(res.total ?? res.cases.length); setSelectedId(res.cases[0]?.id ?? null); } })
        .catch((e) => { if (alive) setError(e.message); })
        .finally(() => { if (alive) setLoading(false); });
    }, 300);
    return () => { alive = false; clearTimeout(t); };
  }, [data.key, filters, query]);

  const rows = cases || [];
  const selIndex = rows.findIndex((c) => c.id === selectedId);
  const selected = (selIndex >= 0 ? rows[selIndex] : rows[0]) || null;
  const go = (delta) => {
    if (rows.length === 0) return;
    const i = Math.max(0, Math.min(rows.length - 1, (selIndex < 0 ? 0 : selIndex) + delta));
    setSelectedId(rows[i].id);
  };
  const capped = total > rows.length;

  return (
    <div className="caseexp">
      <div className="cex-list">
        <div className="cex-list-toolbar">
          <div className="cex-search inline">
            <Icon name="search" size={15} />
            <input placeholder="Buscar Case Id…" value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
          <span className="cex-count mono" title={capped ? `Mostrando ${rows.length} de ${total} — refine a busca por Case Id` : ""}>
            {loading ? "…" : capped
              ? `${rows.length.toLocaleString("pt-BR")} de ${total.toLocaleString("pt-BR")} casos`
              : `${total.toLocaleString("pt-BR")} casos`}
          </span>
        </div>
        <div className="cex-table-wrap">
          <table className="cex-table">
            <thead>
              <tr>
                <th>Case Id</th><th className="r"># Atividades</th><th className="r">Throughput</th>
                <th>1ª Atividade</th><th>Início</th><th>Última Atividade</th><th>Fim</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.id} className={selected && c.id === selected.id ? "sel" : ""} onClick={() => setSelectedId(c.id)}>
                  <td className="cex-id">{c.id}</td>
                  <td className="r mono">{c.nActivities}</td>
                  <td className="r mono">{fmtDuration(c.throughputSeconds)}</td>
                  <td>{c.firstActivity}</td>
                  <td className="mono">{fmtTs(c.firstTs)}</td>
                  <td>{c.lastActivity}</td>
                  <td className="mono">{fmtTs(c.lastTs)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {loading && <div className="cex-empty">Carregando casos…</div>}
          {error && !loading && <div className="cex-empty">Erro: {error}</div>}
          {!loading && !error && rows.length === 0 && <div className="cex-empty">Nenhum caso encontrado</div>}
        </div>
      </div>

      <CaseDetail caseObj={selected} onPrev={() => go(-1)} onNext={() => go(1)} />
    </div>
  );
}
