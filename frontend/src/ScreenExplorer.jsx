import { useState, useMemo, useEffect } from "react";
import { Icon } from "./icons.jsx";
import { Sev, DataTable } from "./components.jsx";
import { ProcessGraph } from "./ProcessGraph.jsx";

/* ───────────────────────── Drill-down drawer ───────────────────────── */
export function DrillDrawer({ drill, onClose }) {
  useEffect(() => {
    const h = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  if (!drill) return null;
  return (
    <>
      <div className="drawer-overlay" onClick={onClose} />
      <div className="drawer">
        <div className="drawer-head">
          <div>
            <div className="dp-kicker" style={{ color: `var(--${drill.sev}-text)` }}>
              Drill-down · {drill.rows.length} casos
            </div>
            <h2 className="drawer-title">{drill.title}</h2>
            <div className="drawer-meta">
              <div className="dm">Casos afetados<b>{drill.rows.length}</b></div>
              <div className="dm">Severidade
                <b style={{ color: `var(--${drill.sev}-text)`, fontFamily: "var(--sans)", fontSize: 14 }}>
                  {drill.sev === "crit" ? "Crítico" : drill.sev === "warn" ? "Atenção" : "Info"}
                </b>
              </div>
            </div>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn sm"><Icon name="external" size={14} />Exportar</button>
            <button className="icon-btn" onClick={onClose}><Icon name="close" size={18} /></button>
          </div>
        </div>
        <div className="drawer-body">
          <DataTable columns={drill.columns} rows={drill.rows} />
        </div>
      </div>
    </>
  );
}

/* ───────────────────────── Coverage donut ───────────────────────── */
function CoverageDonut({ pct, size = 72 }) {
  const r = size / 2 - 7, c = 2 * Math.PI * r;
  return (
    <svg width={size} height={size} style={{ transform: "rotate(-90deg)", flex: "none" }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="var(--surface-3)" strokeWidth="8" />
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="var(--accent)" strokeWidth="8"
        strokeLinecap="round" strokeDasharray={`${c * pct/100} ${c}`}
        style={{ transition: "stroke-dasharray .4s" }} />
      <text x={size/2} y={size/2} transform={`rotate(90 ${size/2} ${size/2})`}
        textAnchor="middle" dominantBaseline="central" fontSize="16" fontWeight="700"
        fontFamily="var(--mono)" fill="var(--text)">{pct}%</text>
    </svg>
  );
}

/* ───────────────────────── Subgraph builder ─────────────────────────
   Reconstrói o grafo a partir da união das variantes selecionadas.
   - node.cases  = casos que passam pelo nó (soma das variantes)
   - edge.cases  = casos que percorrem a transição
   - mantém coordenadas/labels dos nós e flags de curva das arestas originais
*/
function buildSubgraph(data, selectedIds) {
  const sel = data.variants.filter((v) => selectedIds.has(v.id));
  const totalCases = sel.reduce((s, v) => s + v.cases, 0);

  const nodeCases = {};
  const edgeCases = {};
  for (const v of sel) {
    const seenN = new Set();
    for (const nid of v.path) {
      if (!seenN.has(nid)) { nodeCases[nid] = (nodeCases[nid] || 0) + v.cases; seenN.add(nid); }
    }
    const seenE = new Set();
    for (let i = 0; i < v.path.length - 1; i++) {
      const id = v.path[i] + "->" + v.path[i + 1];
      if (!seenE.has(id)) { edgeCases[id] = (edgeCases[id] || 0) + v.cases; seenE.add(id); }
    }
  }

  const nodes = data.nodes
    .filter((n) => nodeCases[n.id] != null)
    .map((n) => ({ ...n, cases: n.type ? totalCases : (nodeCases[n.id] ?? 0) }));

  const edgeMeta = Object.fromEntries(data.edges.map((e) => [e.id, e]));
  const edges = Object.entries(edgeCases).map(([id, cases]) => {
    const meta = edgeMeta[id] || {};
    const [from, to] = id.split("->");
    return { ...meta, id, from, to, cases };
  });

  return { ...data, nodes, edges, totalCases };
}

/* default: marca variantes até cobrir ~80% dos casos (mínimo 1) */
function defaultSelection(variants) {
  const ids = new Set();
  let cum = 0;
  for (const v of variants) {
    ids.add(v.id);
    cum += v.pct;
    if (cum >= 80) break;
  }
  if (ids.size === 0 && variants[0]) ids.add(variants[0].id);
  return ids;
}

/* ───────────────────────── Detail panel ───────────────────────── */
function ExplorerDetail({ selected, data, nodeMap, onClose }) {
  if (selected.kind === "node") {
    const n = selected.item;
    const outgoing = data.edges.filter((e) => e.from === n.id && e.to !== n.id);
    const incoming = data.edges.filter((e) => e.to === n.id && e.from !== n.id);
    return (
      <aside className="detail-panel fade-in">
        <div className="dp-head">
          <div><div className="dp-kicker">Atividade</div><h3 className="dp-title">{n.label}</h3></div>
          <button className="icon-btn" onClick={onClose}><Icon name="close" size={18} /></button>
        </div>
        <div className="dp-body">
          <div className="dp-stat-grid">
            <div className="dp-stat"><div className="ds-label">Casos</div><div className="ds-val num">{n.cases.toLocaleString("pt-BR")}</div></div>
            <div className="dp-stat"><div className="ds-label">Frequência</div><div className="ds-val num">{Math.round((n.cases/data.totalCases)*100)}%</div></div>
            <div className="dp-stat"><div className="ds-label">Permanência média</div><div className="ds-val num">{n.avgDwell || "—"}</div></div>
            <div className="dp-stat"><div className="ds-label">Tipo</div><div className="ds-val" style={{ fontSize: 14 }}>{n.branch ? "Exceção" : "Padrão"}</div></div>
          </div>
          <div className="dp-section-title">Transições de saída</div>
          {outgoing.length ? outgoing.map((e) => (
            <div className="dp-list-row" key={e.id}>
              <span className="dlr-label"><Icon name="arrowDown" size={13} style={{ color: "var(--text-3)" }} />{nodeMap[e.to]?.label}</span>
              <span className="num" style={{ fontWeight: 600 }}>{e.cases.toLocaleString("pt-BR")} <span style={{ color: "var(--text-3)", fontWeight: 400 }}>· {e.time}</span></span>
            </div>
          )) : <div className="empty-hint" style={{ padding: 12 }}>Atividade final</div>}
          <div className="dp-section-title">Transições de entrada</div>
          {incoming.length ? incoming.map((e) => (
            <div className="dp-list-row" key={e.id}>
              <span className="dlr-label"><Icon name="arrowUp" size={13} style={{ color: "var(--text-3)" }} />{nodeMap[e.from]?.label}</span>
              <span className="num" style={{ fontWeight: 600 }}>{e.cases.toLocaleString("pt-BR")} <span style={{ color: "var(--text-3)", fontWeight: 400 }}>· {e.time}</span></span>
            </div>
          )) : <div className="empty-hint" style={{ padding: 12 }}>Atividade inicial</div>}
        </div>
      </aside>
    );
  }
  const e = selected.item;
  const from = nodeMap[e.from], to = nodeMap[e.to];
  const pct = ((e.cases / data.totalCases) * 100).toFixed(1);
  return (
    <aside className="detail-panel fade-in">
      <div className="dp-head">
        <div><div className="dp-kicker">Transição</div><h3 className="dp-title" style={{ fontSize: 15 }}>{from?.label} → {to?.label}</h3></div>
        <button className="icon-btn" onClick={onClose}><Icon name="close" size={18} /></button>
      </div>
      <div className="dp-body">
        <div className="dp-stat-grid">
          <div className="dp-stat"><div className="ds-label">Casos</div><div className="ds-val num">{e.cases.toLocaleString("pt-BR")}</div></div>
          <div className="dp-stat"><div className="ds-label">% do total</div><div className="ds-val num">{pct}%</div></div>
          <div className="dp-stat"><div className="ds-label">Tempo médio</div><div className="ds-val num">{e.time}</div></div>
          <div className="dp-stat"><div className="ds-label">Classificação</div><div className="ds-val" style={{ fontSize: 13.5, color: e.bottleneck ? "var(--crit-text)" : "var(--ok-text)" }}>{e.bottleneck ? "Gargalo" : "Normal"}</div></div>
        </div>
        {(e.bottleneck || e.rework || e.dup) && (
          <>
            <div className="dp-section-title">Sinais</div>
            {e.bottleneck && <div className="dp-list-row"><span className="dlr-label"><Icon name="clock" size={13} style={{ color: "var(--crit)" }} />Tempo de transição elevado</span><Sev sev="crit">Gargalo</Sev></div>}
            {e.rework && <div className="dp-list-row"><span className="dlr-label"><Icon name="loop" size={13} style={{ color: "var(--warn)" }} />Loop de retrabalho</span><Sev sev="warn">Retrabalho</Sev></div>}
            {e.dup && <div className="dp-list-row"><span className="dlr-label"><Icon name="alert" size={13} style={{ color: "var(--crit)" }} />Atividade repetida</span><Sev sev="crit">Duplicação</Sev></div>}
          </>
        )}
      </div>
    </aside>
  );
}

/* ───────────────────────── Explorer screen ───────────────────────── */
export function ExplorerScreen({ data, filters, onFiltersChange }) {
  const [selectedIds, setSelectedIds] = useState(() => defaultSelection(data.variants));
  const [flowOn,     setFlowOn]     = useState(true);
  const [showCounts, setShowCounts] = useState(false);
  const [selected,   setSelected]   = useState(null);
  const [showFilters, setShowFilters] = useState(false);

  // filtros (fornecedor / período)
  const [localForn, setLocalForn] = useState(filters?.fornecedores ?? []);
  const [startDate, setStartDate] = useState(filters?.startDate ?? "");
  const [endDate,   setEndDate]   = useState(filters?.endDate   ?? "");

  useEffect(() => {
    setSelectedIds(defaultSelection(data.variants));
    setSelected(null);
  }, [data]);

  const graphData = useMemo(() => buildSubgraph(data, selectedIds), [data, selectedIds]);
  const nodeMap = useMemo(() => Object.fromEntries(graphData.nodes.map((n) => [n.id, n])), [graphData]);

  const coveragePct = Math.round(
    data.variants.filter((v) => selectedIds.has(v.id)).reduce((s, v) => s + v.pct, 0)
  );
  const coveredCases = data.variants.filter((v) => selectedIds.has(v.id)).reduce((s, v) => s + v.cases, 0);
  const maxPct = Math.max(...data.variants.map((v) => v.pct), 1);
  const allSelected = selectedIds.size === data.variants.length;

  function toggleVariant(id) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }
  function toggleAll() {
    setSelectedIds(allSelected ? new Set() : new Set(data.variants.map((v) => v.id)));
  }

  // filtros
  function toggleForn(d) {
    const next = localForn.includes(d) ? localForn.filter((x) => x !== d) : [...localForn, d];
    setLocalForn(next);
    onFiltersChange({ fornecedores: next, startDate, endDate });
  }
  function clearFilters() {
    setLocalForn([]); setStartDate(""); setEndDate("");
    onFiltersChange({ fornecedores: [], startDate: "", endDate: "" });
  }
  function handleDateChange(field, value) {
    const next = field === "start"
      ? { fornecedores: localForn, startDate: value, endDate }
      : { fornecedores: localForn, startDate, endDate: value };
    if (field === "start") setStartDate(value); else setEndDate(value);
    if ((next.startDate && next.endDate) || (!next.startDate && !next.endDate)) onFiltersChange(next);
  }
  const hasFilters = localForn.length > 0 || startDate || endDate;

  return (
    <div className={"explorer" + (selected ? " with-detail" : "")}>
      {/* ── Variant Explorer panel ── */}
      <aside className="filters" style={{ display: "flex", flexDirection: "column" }}>
        <div className="filter-sec" style={{ paddingBottom: 12 }}>
          <div className="filter-head" style={{ marginBottom: 12 }}>
            <span><Icon name="variants" size={13} style={{ verticalAlign: -2, marginRight: 5 }} />Variant Explorer</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <CoverageDonut pct={coveragePct} />
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--text)" }}>casos cobertos</div>
              <div style={{ fontSize: 11.5, color: "var(--text-3)", marginTop: 2 }}>
                {selectedIds.size} de {data.variants.length} variantes
              </div>
              <div style={{ fontSize: 11.5, color: "var(--text-3)" }}>
                {coveredCases.toLocaleString("pt-BR")} de {data.totalCases.toLocaleString("pt-BR")} casos
              </div>
            </div>
          </div>
          <button className="btn sm" style={{ marginTop: 12, width: "100%" }}
            onClick={() => setShowFilters((s) => !s)}>
            <Icon name="filter" size={13} />Aplicar filtro
            <Icon name={showFilters ? "chevronD" : "chevronR"} size={13} style={{ marginLeft: "auto" }} />
          </button>
        </div>

        {/* filtros colapsáveis */}
        {showFilters && (
          <div className="filter-sec" style={{ background: "var(--surface-2)" }}>
            <div className="filter-head">
              <span>Filtros</span>
              {hasFilters && <button className="btn ghost sm" style={{ height: 22, padding: "0 6px", fontSize: 11 }} onClick={clearFilters}>Limpar</button>}
            </div>
            {data.filters.dims.length > 0 && (
              <>
                <label className="field-label">{data.filters.dimLabel}</label>
                <div className="chip-list" style={{ marginBottom: 12 }}>
                  {data.filters.dims.map((d) => (
                    <button key={d} className={"fchip" + (localForn.includes(d) ? " on" : "")} onClick={() => toggleForn(d)}>{d}</button>
                  ))}
                </div>
              </>
            )}
            <label className="field-label">Período</label>
            <div className="date-row">
              <input className="input" type="date" value={startDate} onChange={(e) => handleDateChange("start", e.target.value)} style={{ fontSize: 12 }} />
              <input className="input" type="date" value={endDate} onChange={(e) => handleDateChange("end", e.target.value)} style={{ fontSize: 12 }} />
            </div>
          </div>
        )}

        {/* tabela de variantes */}
        <div style={{ flex: 1, overflowY: "auto" }}>
          <div className="var-tbl-head">
            <button className={"cbox" + (allSelected ? " on" : "")} onClick={toggleAll}
              title={allSelected ? "Desmarcar todas" : "Marcar todas"}>
              {allSelected && <Icon name="check" size={11} strokeWidth={2.4} />}
            </button>
            <span>Variante</span>
            <span style={{ textAlign: "right" }}>Casos</span>
            <span>Cobertura</span>
            <span style={{ textAlign: "right" }}>Avg TPT</span>
          </div>
          {data.variants.map((v, i) => {
            const on = selectedIds.has(v.id);
            return (
              <div key={v.id} className={"var-row" + (on ? " on" : "")} onClick={() => toggleVariant(v.id)}>
                <span className={"cbox" + (on ? " on" : "")}>{on && <Icon name="check" size={11} strokeWidth={2.4} />}</span>
                <span className="vr-name num" title={v.name}>#{i + 1}</span>
                <span className="vr-count num">{v.cases.toLocaleString("pt-BR")}</span>
                <span className="vr-cov">
                  <span className="vr-bar"><i style={{ width: (v.pct / maxPct * 100) + "%" }} /></span>
                  <span className="vr-pct num">{v.pct}%</span>
                </span>
                <span className="vr-tpt num">{v.avgDur}</span>
              </div>
            );
          })}
        </div>
      </aside>

      {/* ── Graph ── */}
      <div className="graph-stage">
        <div className="graph-toolbar">
          <div className="gt-pill">
            <Icon name="layers" size={14} style={{ color: "var(--accent)" }} />
            {selectedIds.size === data.variants.length ? "Modelo completo" : `${selectedIds.size} variante(s)`} · <b>{coveredCases.toLocaleString("pt-BR")}</b> casos
          </div>
          <div style={{ flex: 1 }} />
          <div className="gt-pill" style={{ padding: 4, gap: 4 }}>
            <button className={"btn sm" + (flowOn ? " primary" : " ghost")} onClick={() => setFlowOn((f) => !f)}><Icon name="play" size={13} />Fluxo</button>
            <button className={"btn sm" + (showCounts ? " primary" : " ghost")} onClick={() => setShowCounts((c) => !c)}>123 Contagem</button>
          </div>
        </div>
        {selectedIds.size === 0 ? (
          <div className="empty-hint" style={{ paddingTop: 120 }}>Selecione ao menos uma variante para visualizar o processo.</div>
        ) : (
          <ProcessGraph data={graphData} selectedVariant={null} flowOn={flowOn} showCounts={showCounts}
            onSelectNode={(n) => setSelected({ kind: "node", item: n })}
            onSelectEdge={(e) => setSelected({ kind: "edge", item: e })}
            selected={selected} dimFilter={[]} />
        )}
      </div>

      {selected && <ExplorerDetail selected={selected} data={graphData} nodeMap={nodeMap} onClose={() => setSelected(null)} />}
    </div>
  );
}
