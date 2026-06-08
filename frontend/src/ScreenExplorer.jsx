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

// ordem ideal por módulo — usada para montar o caminho vertical do grafo
const IDEAL_BY_MODULE = {
  p2p: ["req", "po", "alter", "approve", "goods", "invoice", "pay"],
  o2c: ["order", "credit", "hold", "pick", "deliver", "invoice", "receive"],
};

/* ───────── subgrafo da união das variantes selecionadas ───────── */
export function buildSubgraph(data, selectedIds) {
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

export function defaultSelection(variants) {
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
export function Graph({ graphData, mode, zoom, pan, dragging, animKey, moduleKey, playingVariant, replayKey, onNodeClick }) {
  const graphRef = useRef(null);
  const nodeRefs = useRef({});
  const startRef = useRef(null);
  const endRef = useRef(null);
  const [bypasses, setBypasses] = useState([]);
  const [trace, setTrace] = useState(null);

  const primary = useMemo(() => {
    const order   = IDEAL_BY_MODULE[moduleKey] || IDEAL_BY_MODULE.p2p;
    const present = new Set(graphData.nodes.map((n) => n.id));
    return order.filter((id) => present.has(id));
  }, [graphData, moduleKey]);

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

  // traço do caminho da variante reproduzida: INÍCIO -> nós (na ordem) -> FIM
  useLayoutEffect(() => {
    if (!playingVariant) { setTrace(null); return; }
    const s = startRef.current, e = endRef.current;
    if (!s || !e) { setTrace(null); return; }
    // âncoras: cx = centro (linha vertical sobre as setas); lx = borda esquerda
    // (mesmo ponto de saída/entrada usado pelas curvas tracejadas de bypass)
    const anchor = (el) => ({
      cx: el.offsetLeft + el.offsetWidth / 2,
      lx: el.offsetLeft + 14,
      my: el.offsetTop + el.offsetHeight / 2,
    });
    const pathIds = playingVariant.path.filter((id) => nodeRefs.current[id]);
    if (pathIds.length === 0) { setTrace(null); return; }

    const sc = anchor(s);
    let d = `M ${sc.cx} ${sc.my}`;
    let prev = sc, prevOrd = -1;
    for (let i = 0; i < pathIds.length; i++) {
      const a = anchor(nodeRefs.current[pathIds[i]]);
      const ord = primary.indexOf(pathIds[i]);
      if (i === 0 || ord === prevOrd + 1) {
        d += ` L ${a.cx} ${a.my}`; // trecho reto, pelo centro
      } else {
        // desvio: reproduz exatamente a curva tracejada (borda esquerda, mesmo bow)
        const bow = Math.min(prev.lx, a.lx) - 66;
        d += ` L ${prev.lx} ${prev.my}`;                                  // conector (atrás do card)
        d += ` C ${bow} ${prev.my}, ${bow} ${a.my}, ${a.lx} ${a.my}`;     // curva = tracejada
        d += ` L ${a.cx} ${a.my}`;                                        // conector (atrás do card)
      }
      prev = a; prevOrd = ord;
    }
    const ec = anchor(e);
    d += ` L ${ec.cx} ${ec.my}`;
    setTrace(d);
  }, [playingVariant, replayKey, graphData, zoom, primary.join(",")]);

  return (
    <div className="graph" ref={graphRef}
      style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`, transition: dragging ? "none" : undefined }}>
      <svg className="bypass-svg">
        <defs>
          {/* máscara que cresce de cima p/ baixo, "desenhando" os desvios.
              key={animKey} remonta o rect ao trocar de variante -> SMIL replay */}
          <clipPath id="bypassReveal">
            <rect key={animKey} x="-600" y="-60" width="3000" height="0">
              <animate attributeName="height" from="0" to="1800" dur="0.9s"
                calcMode="spline" keySplines="0.2 0.7 0.3 1" keyTimes="0;1" fill="freeze" begin="0s" />
            </rect>
          </clipPath>
        </defs>
        <g clipPath="url(#bypassReveal)">
          {bypasses.map((b) => (
            <g key={b.id}>
              <path className="bypass-path" d={b.d} />
              <g transform={`translate(${b.lx}, ${b.ly})`}>
                <rect className="pill-bg" x="-30" y="-12" width="60" height="24" rx="7" />
                <text className="bypass-label" x="0" y="1" textAnchor="middle" dominantBaseline="middle" fill="#8b6fe8">{b.label}</text>
              </g>
            </g>
          ))}
        </g>
        {trace && (
          <path key={replayKey} className="variant-trace" pathLength="1" d={trace} />
        )}
      </svg>

      <div className="terminal" ref={startRef}><span className="tdot" style={{ background: "#16a34a" }} />INÍCIO</div>
      <div className="edge tiny"><div className="edge-track" style={{ "--flow": freqColor(0.85) }} /></div>

      {primary.map((id, i) => {
        const node = nodeById[id];
        const ratio = node.cases / graphData.totalCases;
        const nextId = primary[i + 1];
        const vEdge = nextId ? edgeById[`${id}->${nextId}`] : null;
        return (
          <div key={id} style={{ display: "contents" }}>
            <div className="node" ref={(el) => { nodeRefs.current[id] = el; }}
              onClick={(e) => onNodeClick?.(id, e.currentTarget.getBoundingClientRect())}>
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
      <div className="terminal end" ref={endRef}><span className="tdot" />FIM</div>
    </div>
  );
}

/* ───────── Popover de etapa (clique no nó) ───────── */
const fmtK = (n) => {
  n = Number(n) || 0;
  return n >= 1000 ? (n / 1000).toFixed(1).replace(".", ",") + "K" : String(n);
};

function MiniRing({ pct, size = 46 }) {
  const sw = 7, r = (size - sw) / 2, c = 2 * Math.PI * r, off = c * (1 - (pct || 0) / 100);
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--line-2)" strokeWidth={sw} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--violet)" strokeWidth={sw}
        strokeLinecap="round" strokeDasharray={c} strokeDashoffset={off}
        transform={`rotate(-90 ${size / 2} ${size / 2})`} />
    </svg>
  );
}

function NodePopover({ node, rect, total, active, onApply, onClose }) {
  const ref = useRef(null);
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    const onDown = (e) => { if (ref.current && !ref.current.contains(e.target)) onClose(); };
    window.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => { window.removeEventListener("keydown", onKey); document.removeEventListener("mousedown", onDown); };
  }, [onClose]);

  const W = 304, H = 372, M = 12;
  let left = rect.right + M;
  if (left + W > window.innerWidth - 8) left = rect.left - W - M;
  if (left < 8) left = 8;
  let top = Math.max(8, rect.top);
  if (top + H > window.innerHeight - 8) top = Math.max(8, window.innerHeight - H - 8);

  const pct = node.pct ?? 0;
  const pctOf = (n) => (total ? Math.round(100 * (n || 0) / total) : 0);
  const opt = (mode, label, count, p) => {
    const on = active && active.id === node.id && active.mode === mode;
    return (
      <button className={"np-opt" + (on ? " on" : "")} onClick={() => onApply(mode)}>
        <span className="np-opt-l">{label}</span>
        <span className="np-opt-r mono">{fmtK(count)} <span className="np-opt-pct">({Math.round(p)}%)</span></span>
      </button>
    );
  };

  return (
    <div className="node-pop" ref={ref} style={{ left, top }} onMouseDown={(e) => e.stopPropagation()}>
      <div className="np-head">
        <span className="np-ic"><Icon name="variants" size={15} /></span>
        <span className="np-title">{node.label}</span>
        <button className="np-x" onClick={onClose}><Icon name="close" size={16} /></button>
      </div>
      <div className="np-cov">
        <MiniRing pct={pct} />
        <div>
          <div className="np-cov-pct">{Math.round(pct)}% dos casos</div>
          <div className="np-cov-sub mono"># {fmt(node.casesWith)} de {fmt(total)}</div>
        </div>
      </div>
      <div className="np-freq">
        <div className="np-freq-n mono">{fmtK(node.freq)} vezes</div>
        <div className="np-freq-l">Frequência da atividade</div>
      </div>
      <div className="np-sel">Aplicar filtro</div>
      <div className="np-opts">
        {opt("with", "Com esta atividade", node.casesWith, pctOf(node.casesWith))}
        {opt("without", "Sem esta atividade", node.casesWithout, pctOf(node.casesWithout))}
        {opt("start", "Iniciando aqui", node.startCount, pctOf(node.startCount))}
        {opt("end", "Terminando aqui", node.endCount, pctOf(node.endCount))}
      </div>
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
  const [playingId, setPlayingId] = useState(null);
  const [replayKey, setReplayKey] = useState(0);
  const [mode, setMode] = useState("fluxo");
  const [zoom, setZoom] = useState(0.92);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const dragRef = useRef(null);
  const [showFilters, setShowFilters] = useState(false);
  const [popover, setPopover] = useState(null);

  function onPointerDown(e) {
    // não inicia pan ao clicar nos controles (zoom/legenda/toolbar) nem no popover
    if (e.target.closest("button, .zoom, .legend, .canvas-toolbar, .node-pop")) return;
    setPopover(null);
    dragRef.current = { sx: e.clientX, sy: e.clientY, ox: pan.x, oy: pan.y };
    setDragging(true);
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  function onPointerMove(e) {
    if (!dragRef.current) return;
    setPan({ x: dragRef.current.ox + (e.clientX - dragRef.current.sx), y: dragRef.current.oy + (e.clientY - dragRef.current.sy) });
  }
  function onPointerUp() { dragRef.current = null; setDragging(false); }
  function resetView() { setPan({ x: 0, y: 0 }); setZoom(0.92); setPopover(null); }

  const [localForn, setLocalForn] = useState(filters?.fornecedores ?? []);
  const [startDate, setStartDate] = useState(filters?.startDate ?? "");
  const [endDate, setEndDate]     = useState(filters?.endDate ?? "");

  useEffect(() => { setSelectedIds(defaultSelection(data.variants)); setPlayingId(null); setPopover(null); }, [data]);

  const nodeMeta = useMemo(() => Object.fromEntries(data.nodes.map((n) => [n.id, n])), [data]);
  function onNodeClick(id, rect) {
    const n = nodeMeta[id];
    if (!n || n.type) return; // terminais Início/Fim não abrem
    setPopover({ node: n, rect });
  }
  function applyActivity(mode) {
    const cur = filters?.activity;
    const same = cur && cur.id === popover.node.id && cur.mode === mode;
    onFiltersChange({ ...filters, activity: same ? null : { id: popover.node.id, mode, label: popover.node.label } });
    setPopover(null);
  }

  // a variante reproduzida entra no grafo mesmo que não esteja selecionada
  const effectiveIds = useMemo(() => {
    if (playingId == null) return selectedIds;
    const next = new Set(selectedIds); next.add(playingId); return next;
  }, [selectedIds, playingId]);
  const graphData = useMemo(() => buildSubgraph(data, effectiveIds), [data, effectiveIds]);
  const playingVariant = useMemo(() => data.variants.find((v) => v.id === playingId) || null, [data, playingId]);

  function playVariant(id) {
    if (playingId === id) { setPlayingId(null); return; } // ■ stop / limpa
    setPlayingId(id);
    setReplayKey((k) => k + 1);
  }
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
              <div key={v.id} className={"vrow" + (sel ? " sel" : "") + (playingId === v.id ? " playing" : "")} onClick={() => toggle(v.id)}>
                <div className="cbx"><Icon name="check" size={12} strokeWidth={3.5} /></div>
                <div className="vname"><span className="hash">#</span>{i + 1}</div>
                <div className="vcases mono">{fmt(v.cases)}</div>
                <div className="vcov">
                  <div className="num mono">{v.pct.toLocaleString("pt-BR", { minimumFractionDigits: 1 })}%</div>
                  <div className="bar"><i style={{ width: Math.min(100, v.pct / maxCov * 100) + "%" }} /></div>
                </div>
                <div className="vtpt mono">{v.avgDur}</div>
                <button className="vplay" title={playingId === v.id ? "Parar" : "Reproduzir caminho"}
                  onClick={(e) => { e.stopPropagation(); playVariant(v.id); }}>
                  <Icon name={playingId === v.id ? "stop" : "play"} size={12} />
                </button>
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
          <Graph graphData={graphData} mode={mode} zoom={zoom} pan={pan} dragging={dragging}
            animKey={[...selectedIds].sort().join(",")} moduleKey={data.key}
            playingVariant={playingVariant} replayKey={replayKey} onNodeClick={onNodeClick} />
        </div>

        <div className="legend">
          <div className="ttl">Frequência</div>
          <div className="grad" />
          <div className="scale"><span>baixa</span><span>alta</span></div>
          <div className="gargalo"><i />Gargalo / desvio</div>
        </div>

        <div className="zoom">
          <div className="zoom-stack">
            <button onClick={() => { setZoom((z) => Math.min(1.8, +(z + 0.12).toFixed(2))); setPopover(null); }}><Icon name="plus" size={16} /></button>
            <button onClick={() => { setZoom((z) => Math.max(0.4, +(z - 0.12).toFixed(2))); setPopover(null); }}><Icon name="minus" size={16} /></button>
            <button onClick={resetView}><Icon name="fit" size={16} /></button>
          </div>
          <div className="zoom-pct mono">{Math.round(zoom * 100)}%</div>
        </div>
      </div>

      {popover && (
        <NodePopover node={popover.node} rect={popover.rect} total={data.totalCases}
          active={filters?.activity} onApply={applyActivity} onClose={() => setPopover(null)} />
      )}
    </div>
  );
}
