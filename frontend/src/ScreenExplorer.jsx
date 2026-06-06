import { useState, useMemo, useEffect, useRef, useLayoutEffect } from "react";
import { Icon } from "./icons.jsx";
import { Sev, DataTable } from "./components.jsx";

const fmt = (n) => Math.round(n).toLocaleString("pt-BR");

// frequência -> roxo (baixo = lavanda, alto = violeta profundo)
function freqColor(t) {
  t = Math.max(0, Math.min(1, t));
  const L = 0.74 - t * 0.32;
  const C = 0.10 + t * 0.10;
  return `oklch(${L} ${C} 295)`;
}

const IDEAL_ORDER = ["req", "po", "approve", "goods", "invoice", "pay"];

/* ───────── subgrafo da união das variantes selecionadas ───────── */
function buildSubgraph(data, selectedIds) {
  const sel = data.variants.filter((v) => selectedIds.has(v.id));
  const totalCases = sel.reduce((s, v) => s + v.cases, 0);
  const nodeCases = {}, edgeCases = {};
  for (const v of sel) {
    const seenN = new Set();
    for (const nid of v.path) if (!seenN.has(nid)) { nodeCases[nid] = (nodeCases[nid] || 0) + v.cases; seenN.add(nid); }
    const seenE = new Set();
    for (let i = 0; i < v.path.length - 1; i++) {
      const id = v.path[i] + "->" + v.path[i + 1];
      if (!seenE.has(id)) { edgeCases[id] = (edgeCases[id] || 0) + v.cases; seenE.add(id); }
    }
  }
  const nodeMeta = Object.fromEntries(data.nodes.map((n) => [n.id, n]));
  const edgeMeta = Object.fromEntries(data.edges.map((e) => [e.id, e]));
  const nodes = Object.keys(nodeCases).map((id) => ({ ...nodeMeta[id], id, cases: nodeMeta[id]?.type ? totalCases : nodeCases[id] }));
  const edges = Object.entries(edgeCases).map(([id, cases]) => {
    const [from, to] = id.split("->");
    return { ...edgeMeta[id], id, from, to, cases };
  });
  return { ...data, nodes, edges, totalCases };
}

function defaultSelection(variants) {
  const ids = new Set(); let cum = 0;
  for (const v of variants) { ids.add(v.id); cum += v.pct; if (cum >= 80) break; }
  if (ids.size === 0 && variants[0]) ids.add(variants[0].id);
  return ids;
}

/* ───────── Donut ───────── */
function Donut({ pct }) {
  const r = 30, c = 2 * Math.PI * r, off = c * (1 - pct / 100);
  return (
    <svg width="74" height="74" viewBox="0 0 74 74">
      <defs><linearGradient id="dg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#7b54ee" /><stop offset="1" stopColor="#5a2fe0" /></linearGradient></defs>
      <circle cx="37" cy="37" r={r} fill="none" className="donut-track" strokeWidth="7" />
      <circle cx="37" cy="37" r={r} fill="none" stroke="url(#dg)" strokeWidth="7" strokeLinecap="round"
        strokeDasharray={c} strokeDashoffset={off} transform="rotate(-90 37 37)"
        style={{ transition: "stroke-dashoffset .5s cubic-bezier(.2,.7,.3,1)" }} />
      <text x="37" y="38" textAnchor="middle" dominantBaseline="middle" className="donut-num mono" fontSize="16" fontWeight="600">{Math.round(pct)}%</text>
    </svg>
  );
}

/* ───────── Graph (fluxo vertical) ───────── */
function Graph({ graphData, mode, zoom, pan, dragging }) {
  const graphRef = useRef(null);
  const nodeRefs = useRef({});
  const [bypasses, setBypasses] = useState([]);

  const primary = useMemo(() => {
    const present = new Set(graphData.nodes.map((n) => n.id));
    return IDEAL_ORDER.filter((id) => present.has(id));
  }, [graphData]);

  const nodeById = useMemo(() => Object.fromEntries(graphData.nodes.map((n) => [n.id, n])), [graphData]);
  const edgeById = useMemo(() => Object.fromEntries(graphData.edges.map((e) => [e.id, e])), [graphData]);

  // arestas verticais (consecutivas no caminho ideal) vs bypass (resto)
  const verticalIds = new Set();
  for (let i = 0; i < primary.length - 1; i++) verticalIds.add(`${primary[i]}->${primary[i + 1]}`);

  const bypassEdges = graphData.edges.filter((e) => {
    if (verticalIds.has(e.id)) return false;
    if (e.from === "start" || e.to === "end") return false;
    // só desenha se ambos os nós estão no caminho principal (medíveis)
    return primary.includes(e.from) && primary.includes(e.to) && e.from !== e.to;
  });

  useLayoutEffect(() => {
    const g = graphRef.current;
    if (!g) return;
    const out = [];
    for (const e of bypassEdges) {
      const s = nodeRefs.current[e.from], t = nodeRefs.current[e.to];
      if (!s || !t) continue;
      const sx = s.offsetLeft + 14, sy = s.offsetTop + s.offsetHeight / 2;
      const tx = t.offsetLeft + 14, ty = t.offsetTop + t.offsetHeight / 2;
      const bowX = Math.min(sx, tx) - 66;
      out.push({
        id: e.id,
        d: `M ${sx} ${sy} C ${bowX} ${sy}, ${bowX} ${ty}, ${tx} ${ty}`,
        lx: bowX - 4, ly: (sy + ty) / 2,
        label: mode === "fluxo" ? e.time : fmt(e.cases),
      });
    }
    setBypasses(out);
  }, [graphData, mode, zoom, primary.join(",")]);

  return (
    <div className="graph" ref={graphRef} style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`, transition: dragging ? "none" : undefined }}>
      <svg className="bypass-svg">
        {bypasses.map((b) => (
          <g key={b.id}>
            <path className="bypass-path" d={b.d} />
            <g transform={`translate(${b.lx}, ${b.ly})`}>
              <rect className="pill-bg" x="-30" y="-12" width="60" height="24" rx="7" />
              <text className="bypass-label" x="0" y="1" textAnchor="middle" dominantBaseline="middle" fill="#8b6fe8">{b.label}</text>
            </g>
          </g>
        ))}
      </svg>

      <div className="terminal"><span className="tdot" style={{ background: "#16a34a" }} />INÍCIO</div>
      <div className="edge tiny"><div className="edge-track" style={{ "--flow": freqColor(0.85) }} /></div>

      {primary.map((id, i) => {
        const node = nodeById[id];
        const ratio = node.cases / graphData.totalCases;
        const nextId = primary[i + 1];
        const vEdge = nextId ? edgeById[`${id}->${nextId}`] : null;
        return (
          <div key={id} style={{ display: "contents" }}>
            <div className="node" ref={(el) => { nodeRefs.current[id] = el; }}>
              <div className="node-accent" style={{ background: freqColor(ratio) }} />
              <div className="node-body">
                <div className="node-title">{node.label}</div>
                <div className="node-stats">
                  <span className="node-count mono">{fmt(node.cases)}</span>
                  <span className={"node-pct" + (ratio < 0.999 ? " dim" : "")}>{Math.round(ratio * 100)}%</span>
                </div>
              </div>
            </div>
            {nextId && (
              <div className={"edge" + (vEdge?.bottleneck ? " bottleneck" : "")}>
                <div className="edge-track" style={{ "--flow": vEdge?.bottleneck ? "#e5484d" : freqColor(0.6 + (vEdge ? vEdge.cases / graphData.totalCases : 0) * 0.4) }} />
                <span className="edge-label">{vEdge ? (mode === "fluxo" ? vEdge.time : fmt(vEdge.cases)) : "—"}</span>
              </div>
            )}
          </div>
        );
      })}

      <div className="edge tiny"><div className="edge-track" style={{ "--flow": freqColor(0.85) }} /></div>
      <div className="terminal end"><span className="tdot" />FIM</div>
    </div>
  );
}

/* ───────── Drill drawer (usado pelo Dashboard) ───────── */
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
            <div className="dp-kicker" style={{ color: `var(--${drill.sev}-text)` }}>Drill-down · {drill.rows.length} casos</div>
            <h2 className="drawer-title">{drill.title}</h2>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn"><Icon name="external" size={14} />Exportar</button>
            <button className="icon-btn" onClick={onClose}><Icon name="close" size={18} /></button>
          </div>
        </div>
        <div className="drawer-body"><DataTable columns={drill.columns} rows={drill.rows} /></div>
      </div>
    </>
  );
}

/* ───────── Explorer screen ───────── */
export function ExplorerScreen({ data, filters, onFiltersChange }) {
  const [selectedIds, setSelectedIds] = useState(() => defaultSelection(data.variants));
  const [mode, setMode] = useState("fluxo");
  const [zoom, setZoom] = useState(0.92);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const dragRef = useRef(null);
  const [showFilters, setShowFilters] = useState(false);

  function onPointerDown(e) {
    // não inicia pan ao clicar nos controles (zoom/legenda/toolbar)
    if (e.target.closest("button, .zoom, .legend, .canvas-toolbar")) return;
    dragRef.current = { sx: e.clientX, sy: e.clientY, ox: pan.x, oy: pan.y };
    setDragging(true);
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  function onPointerMove(e) {
    if (!dragRef.current) return;
    setPan({ x: dragRef.current.ox + (e.clientX - dragRef.current.sx), y: dragRef.current.oy + (e.clientY - dragRef.current.sy) });
  }
  function onPointerUp() { dragRef.current = null; setDragging(false); }
  function resetView() { setPan({ x: 0, y: 0 }); setZoom(0.92); }

  const [localForn, setLocalForn] = useState(filters?.fornecedores ?? []);
  const [startDate, setStartDate] = useState(filters?.startDate ?? "");
  const [endDate, setEndDate]     = useState(filters?.endDate ?? "");

  useEffect(() => { setSelectedIds(defaultSelection(data.variants)); }, [data]);

  const graphData = useMemo(() => buildSubgraph(data, selectedIds), [data, selectedIds]);
  const selVars = data.variants.filter((v) => selectedIds.has(v.id));
  const selCases = selVars.reduce((s, v) => s + v.cases, 0);
  const coveragePct = (selCases / data.totalCases) * 100;
  const maxCov = Math.max(...data.variants.map((v) => v.pct), 1);

  function toggle(id) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) { if (next.size > 1) next.delete(id); } else next.add(id);
      return next;
    });
  }

  function toggleForn(d) {
    const next = localForn.includes(d) ? localForn.filter((x) => x !== d) : [...localForn, d];
    setLocalForn(next); onFiltersChange({ fornecedores: next, startDate, endDate });
  }
  function handleDate(field, value) {
    const next = field === "start" ? { fornecedores: localForn, startDate: value, endDate } : { fornecedores: localForn, startDate, endDate: value };
    if (field === "start") setStartDate(value); else setEndDate(value);
    if ((next.startDate && next.endDate) || (!next.startDate && !next.endDate)) onFiltersChange(next);
  }

  return (
    <div className="body">
      {/* SIDEBAR */}
      <aside className="sidebar">
        <div className="eyebrow"><Icon name="variants" size={14} /> Variant Explorer</div>

        <div className="coverage">
          <Donut pct={coveragePct} />
          <div className="coverage-meta">
            <div className="big">casos cobertos</div>
            <div className="small">
              <b>{selectedIds.size}</b> de {data.variants.length} variantes<br />
              <b>{fmt(selCases)}</b> de {fmt(data.totalCases)} casos
            </div>
          </div>
        </div>

        <button className="filter" onClick={() => setShowFilters((s) => !s)}>
          <Icon name="filter" size={15} /> Aplicar filtro
          <span className="chev" style={{ marginLeft: "auto", transform: showFilters ? "rotate(90deg)" : "none", transition: "transform .15s" }}><Icon name="chevronR" size={15} /></span>
        </button>

        {showFilters && (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {data.filters.dims.length > 0 && (
              <div>
                <div className="eyebrow" style={{ marginBottom: 8 }}>{data.filters.dimLabel}</div>
                <div className="chip-list">
                  {data.filters.dims.map((d) => (
                    <button key={d} className={"fchip" + (localForn.includes(d) ? " on" : "")} onClick={() => toggleForn(d)}>{d}</button>
                  ))}
                </div>
              </div>
            )}
            <div>
              <div className="eyebrow" style={{ marginBottom: 8 }}>Período</div>
              <div className="date-row">
                <input className="input" type="date" value={startDate} onChange={(e) => handleDate("start", e.target.value)} />
                <input className="input" type="date" value={endDate} onChange={(e) => handleDate("end", e.target.value)} />
              </div>
            </div>
          </div>
        )}

        <div>
          <div className="vt-head">
            <span></span><span>Variante</span><span className="r">Casos</span><span className="r">Cobertura</span><span className="r">Avg TPT</span>
          </div>
          {data.variants.map((v, i) => {
            const sel = selectedIds.has(v.id);
            return (
              <div key={v.id} className={"vrow" + (sel ? " sel" : "")} onClick={() => toggle(v.id)}>
                <div className="cbx"><Icon name="check" size={12} strokeWidth={3.5} /></div>
                <div className="vname"><span className="hash">#</span>{i + 1}</div>
                <div className="vcases mono">{fmt(v.cases)}</div>
                <div className="vcov">
                  <div className="num mono">{v.pct.toLocaleString("pt-BR", { minimumFractionDigits: 1 })}%</div>
                  <div className="bar"><i style={{ width: Math.min(100, v.pct / maxCov * 100) + "%" }} /></div>
                </div>
                <div className="vtpt mono">{v.avgDur}</div>
              </div>
            );
          })}
        </div>
      </aside>

      {/* CANVAS */}
      <div className="canvas-wrap">
        <div className="canvas-toolbar">
          <div className="scope-pill">
            <Icon name="layers" size={15} />
            <span><b>{selectedIds.size}</b> variante(s)</span>
            <span className="dot" />
            <span><b>{fmt(selCases)}</b> casos</span>
          </div>
          <span style={{ flex: 1 }} />
          <div className="seg">
            <button className={mode === "fluxo" ? "on" : ""} onClick={() => setMode("fluxo")}><Icon name="play" size={14} /> Fluxo</button>
            <button className={mode === "contagem" ? "on" : ""} onClick={() => setMode("contagem")}><Icon name="hash" size={14} /> Contagem</button>
          </div>
        </div>

        <div className="viewport"
          style={{ cursor: dragging ? "grabbing" : "grab", touchAction: "none" }}
          onPointerDown={onPointerDown} onPointerMove={onPointerMove}
          onPointerUp={onPointerUp} onPointerLeave={onPointerUp}>
          <Graph graphData={graphData} mode={mode} zoom={zoom} pan={pan} dragging={dragging} />
        </div>

        <div className="legend">
          <div className="ttl">Frequência</div>
          <div className="grad" />
          <div className="scale"><span>baixa</span><span>alta</span></div>
          <div className="gargalo"><i />Gargalo / desvio</div>
        </div>

        <div className="zoom">
          <div className="zoom-stack">
            <button onClick={() => setZoom((z) => Math.min(1.8, +(z + 0.12).toFixed(2)))}><Icon name="plus" size={16} /></button>
            <button onClick={() => setZoom((z) => Math.max(0.4, +(z - 0.12).toFixed(2)))}><Icon name="minus" size={16} /></button>
            <button onClick={resetView}><Icon name="fit" size={16} /></button>
          </div>
          <div className="zoom-pct mono">{Math.round(zoom * 100)}%</div>
        </div>
      </div>
    </div>
  );
}
