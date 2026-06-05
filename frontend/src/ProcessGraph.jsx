import { useState, useRef, useEffect, useMemo, useCallback } from "react";
import { Icon } from "./icons.jsx";

const GRAPH_W = 760, GRAPH_H = 1000;

function boxOf(n) {
  let w = 184, h = 52;
  if (n.type === "start" || n.type === "end") { w = 108; h = 34; }
  else if (n.branch) { w = 156; h = 48; }
  return { w, h, left: n.x - w / 2, right: n.x + w / 2, top: n.y - h / 2, bottom: n.y + h / 2 };
}

function cubicPoint(p0, c1, c2, p1, t) {
  const u = 1 - t;
  const x = u*u*u*p0[0] + 3*u*u*t*c1[0] + 3*u*t*t*c2[0] + t*t*t*p1[0];
  const y = u*u*u*p0[1] + 3*u*u*t*c1[1] + 3*u*t*t*c2[1] + t*t*t*p1[1];
  return [x, y];
}

function edgeGeom(from, to, edge) {
  const fb = boxOf(from), tb = boxOf(to);
  let sx, sy, ex, ey, c1, c2;
  if (edge.selfloop) {
    sx = fb.right - 6; sy = from.y - 9; ex = fb.right - 6; ey = from.y + 9;
    c1 = [sx + 78, sy - 20]; c2 = [ex + 78, ey + 20];
    const p0 = [sx, sy], p1 = [ex, ey];
    return { d: `M${sx} ${sy} C${c1[0]} ${c1[1]} ${c2[0]} ${c2[1]} ${ex} ${ey}`, p0, c1, c2, p1 };
  }
  const dy = to.y - from.y;
  if (dy > 30) {
    sx = from.x; sy = fb.bottom; ex = to.x; ey = tb.top;
    if (edge.skip || edge.curveSide) {
      const side = edge.side || -1, off = edge.off || 124;
      const my = sy + (ey - sy) * 0.5;
      c1 = [from.x + side * off, my * 0.7 + sy * 0.3];
      c2 = [to.x + side * off, my * 0.3 + ey * 0.7];
    } else {
      const my = (sy + ey) / 2;
      c1 = [sx, my]; c2 = [ex, my];
    }
  } else if (dy < -30) {
    const off = edge.off || 118;
    sx = fb.right - 8; sy = from.y - 2; ex = tb.right - 8; ey = to.y + 2;
    c1 = [Math.max(from.x, to.x) + off, from.y]; c2 = [Math.max(from.x, to.x) + off, to.y];
  } else {
    const forward = to.x > from.x;
    const av = edge.arc || 0, ao = edge.anchor || 0;
    if (forward) { sx = fb.right; sy = from.y + ao; ex = tb.left; ey = to.y + ao; }
    else { sx = fb.left; sy = from.y + ao; ex = tb.right; ey = to.y + ao; }
    const mx = (sx + ex) / 2;
    c1 = [mx, sy + av]; c2 = [mx, ey + av];
  }
  const p0 = [sx, sy], p1 = [ex, ey];
  return { d: `M${sx} ${sy} C${c1[0]} ${c1[1]} ${c2[0]} ${c2[1]} ${ex} ${ey}`, p0, c1, c2, p1 };
}

function freqColor(ratio) {
  const stops = ["--freq-0", "--freq-1", "--freq-2", "--freq-3", "--freq-4"];
  const i = Math.min(stops.length - 1, Math.floor(ratio * stops.length));
  return `var(${stops[i]})`;
}

function EdgeLabel({ time, count, accent, crit }) {
  const txt = count != null ? `${time} · ${count.toLocaleString("pt-BR")}` : time;
  const w = txt.length * 6.4 + 16;
  const bg = accent ? "var(--accent)" : crit ? "var(--crit-bg)" : "var(--surface)";
  const fg = accent ? "#fff" : crit ? "var(--crit-text)" : "var(--text-2)";
  const bd = accent ? "var(--accent)" : crit ? "var(--crit)" : "var(--border-strong)";
  return (
    <g>
      <rect x={-w/2} y={-9} width={w} height={18} rx={9} fill={bg} stroke={bd} strokeWidth="1" />
      <text x={0} y={4} textAnchor="middle" fontSize="10.5" fontWeight="600" fill={fg} fontFamily="var(--mono)">{txt}</text>
    </g>
  );
}

function GraphTooltip({ hover, data, maxCases }) {
  const style = { left: hover.x, top: hover.y };
  if (hover.kind === "edge") {
    const e = hover.item;
    const pct = ((e.cases / data.totalCases) * 100);
    return (
      <div className="gtooltip" style={style}>
        <div className="tt-title">
          {e.bottleneck && <Icon name="alert" size={13} style={{ color: "var(--crit)" }} />}
          {hover.from.label} <Icon name="chevronR" size={12} style={{ opacity: .5 }} /> {hover.to.label}
        </div>
        <div className="tt-row"><span>Casos</span><b className="num">{e.cases.toLocaleString("pt-BR")}</b></div>
        <div className="tt-row"><span>% do total</span><b className="num">{pct.toFixed(1)}%</b></div>
        <div className="tt-row"><span>Tempo médio</span><b className="num">{e.time}</b></div>
        {e.bottleneck && <div className="tt-row"><span style={{ color: "var(--crit-text)" }}>Gargalo identificado</span></div>}
        {e.rework && <div className="tt-row"><span style={{ color: "var(--warn-text)" }}>Transição de retrabalho</span></div>}
        {e.dup && <div className="tt-row"><span style={{ color: "var(--crit-text)" }}>Pagamento repetido</span></div>}
      </div>
    );
  }
  const n = hover.item;
  return (
    <div className="gtooltip" style={style}>
      <div className="tt-title">{n.label}</div>
      <div className="tt-row"><span>Casos</span><b className="num">{n.cases.toLocaleString("pt-BR")}</b></div>
      <div className="tt-row"><span>Frequência</span><b className="num">{Math.round((n.cases/data.totalCases)*100)}%</b></div>
      {n.avgDwell && <div className="tt-row"><span>Permanência média</span><b className="num">{n.avgDwell}</b></div>}
      {n.branch && <div className="tt-row"><span style={{ color: "var(--warn-text)" }}>Atividade de exceção</span></div>}
    </div>
  );
}

export function ProcessGraph({ data, selectedVariant, flowOn, showCounts, onSelectNode, onSelectEdge, selected, dimFilter }) {
  const wrapRef = useRef(null);
  const [vp, setVp] = useState({ k: 1, x: 0, y: 0 });
  const [size, setSize] = useState({ w: 900, h: 600 });
  const [hover, setHover] = useState(null);
  const drag = useRef(null);

  const nodeMap = useMemo(() => Object.fromEntries(data.nodes.map((n) => [n.id, n])), [data]);
  const maxCases = useMemo(() => Math.max(...data.edges.map((e) => e.cases)), [data]);

  const pathEdges = useMemo(() => {
    if (!selectedVariant) return null;
    const set = new Set();
    const p = selectedVariant.path;
    for (let i = 0; i < p.length - 1; i++) set.add(p[i] + "->" + p[i + 1]);
    return set;
  }, [selectedVariant]);
  const pathNodes = useMemo(() => selectedVariant ? new Set(selectedVariant.path) : null, [selectedVariant]);

  const fit = useCallback(() => {
    const el = wrapRef.current; if (!el) return;
    const W = el.clientWidth, H = el.clientHeight;
    const pad = 56;
    const widthK = (W - pad) / GRAPH_W, heightK = (H - pad) / GRAPH_H;
    let k = Math.min(widthK, heightK);
    k = Math.max(k, Math.min(widthK, 0.66));
    k = Math.min(k, 1.4);
    const x = (W - GRAPH_W * k) / 2;
    const fits = GRAPH_H * k + pad <= H;
    const y = fits ? (H - GRAPH_H * k) / 2 : 28;
    setVp({ k, x, y });
  }, []);

  useEffect(() => {
    const el = wrapRef.current; if (!el) return;
    const ro = new ResizeObserver(() => { setSize({ w: el.clientWidth, h: el.clientHeight }); });
    ro.observe(el);
    setSize({ w: el.clientWidth, h: el.clientHeight });
    fit();
    return () => ro.disconnect();
  }, [fit]);

  useEffect(() => { fit(); }, [data, fit]);

  useEffect(() => {
    const el = wrapRef.current; if (!el) return;
    const onWheel = (e) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      setVp((v) => {
        const factor = Math.exp(-e.deltaY * 0.0014);
        const k = Math.min(2.4, Math.max(0.3, v.k * factor));
        const r = k / v.k;
        return { k, x: mx - (mx - v.x) * r, y: my - (my - v.y) * r };
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const onPointerDown = (e) => {
    if (e.target.closest("[data-node]") || e.target.closest("[data-edge]")) return;
    drag.current = { sx: e.clientX, sy: e.clientY, ox: vp.x, oy: vp.y };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e) => {
    if (!drag.current) return;
    setVp((v) => ({ ...v, x: drag.current.ox + (e.clientX - drag.current.sx), y: drag.current.oy + (e.clientY - drag.current.sy) }));
  };
  const onPointerUp = () => { drag.current = null; };

  const zoom = (dir) => {
    const el = wrapRef.current; const W = el.clientWidth, H = el.clientHeight;
    setVp((v) => {
      const k = Math.min(2.4, Math.max(0.3, v.k * (dir > 0 ? 1.25 : 0.8)));
      const r = k / v.k;
      return { k, x: W/2 - (W/2 - v.x) * r, y: H/2 - (H/2 - v.y) * r };
    });
  };

  return (
    <div className="graph-wrap" ref={wrapRef}
      onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerLeave={onPointerUp}
      style={{ cursor: drag.current ? "grabbing" : "grab" }}>
      <svg width={size.w} height={size.h} style={{ display: "block" }}>
        <defs>
          {["m-low","m-mid","m-high","m-crit","m-accent","m-dim"].map((id) => {
            const col = { "m-low":"var(--freq-1)","m-mid":"var(--freq-2)","m-high":"var(--freq-4)","m-crit":"var(--crit)","m-accent":"var(--accent)","m-dim":"var(--border-strong)" }[id];
            return (
              <marker key={id} id={id} viewBox="0 0 10 10" refX="6.5" refY="5" markerUnits="userSpaceOnUse" markerWidth="8.5" markerHeight="8.5" orient="auto-start-reverse">
                <path d="M0 1 L9 5 L0 9 z" fill={col} />
              </marker>
            );
          })}
        </defs>
        <g transform={`translate(${vp.x} ${vp.y}) scale(${vp.k})`}>
          <g>
            {data.edges.map((edge) => {
              const from = nodeMap[edge.from], to = nodeMap[edge.to];
              if (!from || !to) return null;
              const g = edgeGeom(from, to, edge);
              const ratio = edge.cases / maxCases;
              const inPath = pathEdges && pathEdges.has(edge.id);
              const dimmed = pathEdges && !inPath;
              const isHover = hover && hover.kind === "edge" && hover.item.id === edge.id;
              const isSel = selected && selected.kind === "edge" && selected.item.id === edge.id;
              let color, marker, width, op = 1, animate = false;
              const baseW = 1.6 + ratio * 9;
              if (inPath) { color = "var(--accent)"; marker = "m-accent"; width = Math.max(3, baseW); animate = flowOn; }
              else if (dimmed) { color = "var(--border-strong)"; marker = "m-dim"; width = Math.max(1.4, baseW * 0.6); op = 0.3; }
              else if (edge.bottleneck) { color = "var(--crit)"; marker = "m-crit"; width = Math.max(2, baseW); animate = flowOn; }
              else { color = freqColor(ratio); marker = ratio > 0.6 ? "m-high" : ratio > 0.25 ? "m-mid" : "m-low"; width = baseW; animate = flowOn && ratio > 0.3; }
              if (isHover || isSel) { width += 1.5; op = 1; }
              const mid = cubicPoint(g.p0, g.c1, g.c2, g.p1, 0.5);
              const showLabel = !dimmed && (edge.time !== "—") && (ratio > 0.04 || inPath || edge.bottleneck);
              return (
                <g key={edge.id} data-edge style={{ cursor: "pointer" }}
                  onMouseEnter={(e) => setHover({ kind: "edge", item: edge, from, to, x: e.clientX, y: e.clientY })}
                  onMouseMove={(e) => setHover((h) => h ? { ...h, x: e.clientX, y: e.clientY } : h)}
                  onMouseLeave={() => setHover(null)}
                  onClick={() => onSelectEdge(edge)}>
                  <path d={g.d} fill="none" stroke="transparent" strokeWidth={Math.max(14, width + 12)} />
                  <path d={g.d} fill="none" stroke={color} strokeWidth={width} strokeLinecap="round"
                    markerEnd={`url(#${marker})`} opacity={op}
                    style={isSel ? { filter: "drop-shadow(0 0 4px var(--accent-ring))" } : null} />
                  {animate && (
                    <path className="eflow" d={g.d} fill="none" stroke="rgba(255,255,255,0.85)" strokeWidth={Math.max(1.2, width * 0.42)}
                      strokeLinecap="round" strokeDasharray="1 13" opacity={inPath ? 0.9 : 0.55} />
                  )}
                  {showLabel && (
                    <g transform={`translate(${mid[0]} ${mid[1]})`} style={{ pointerEvents: "none" }}>
                      <EdgeLabel time={edge.time} count={showCounts ? edge.cases : null} accent={inPath} crit={edge.bottleneck && !inPath} />
                    </g>
                  )}
                </g>
              );
            })}
          </g>
          <g>
            {data.nodes.map((n) => {
              const b = boxOf(n);
              const inPath = pathNodes && pathNodes.has(n.id);
              const offPath = pathNodes && !inPath;
              const isHover = hover && hover.kind === "node" && hover.item.id === n.id;
              const isSel = selected && selected.kind === "node" && selected.item.id === n.id;
              const ratio = n.cases / data.totalCases;
              if (n.type === "start" || n.type === "end") {
                return (
                  <g key={n.id} data-node transform={`translate(${b.left} ${b.top})`} style={{ cursor: "pointer", opacity: offPath ? 0.4 : 1 }}
                    onClick={() => onSelectNode(n)}>
                    <rect width={b.w} height={b.h} rx={b.h/2} fill="var(--surface-3)" stroke={inPath ? "var(--accent)" : "var(--border-strong)"} strokeWidth={inPath ? 2 : 1.2} />
                    <circle cx={20} cy={b.h/2} r={5} fill={n.type === "start" ? "var(--ok)" : "var(--text-3)"} />
                    <text x={b.w/2 + 8} y={b.h/2 + 4} textAnchor="middle" fontSize="12" fontWeight="650" fill="var(--text-2)" style={{ letterSpacing: ".04em", textTransform: "uppercase" }}>{n.label}</text>
                  </g>
                );
              }
              const stroke = isSel ? "var(--accent)" : inPath ? "var(--accent)" : isHover ? "var(--accent)" : "var(--border-strong)";
              return (
                <g key={n.id} data-node transform={`translate(${b.left} ${b.top})`} style={{ cursor: "pointer", opacity: offPath ? 0.4 : 1 }}
                  onMouseEnter={(e) => setHover({ kind: "node", item: n, x: e.clientX, y: e.clientY })}
                  onMouseMove={(e) => setHover((h) => h ? { ...h, x: e.clientX, y: e.clientY } : h)}
                  onMouseLeave={() => setHover(null)}
                  onClick={() => onSelectNode(n)}>
                  <rect width={b.w} height={b.h} rx={11} fill="var(--surface)" stroke={stroke}
                    strokeWidth={isSel || inPath ? 2 : 1.2}
                    style={(isSel || isHover) ? { filter: "drop-shadow(0 4px 10px rgba(16,24,40,0.14))" } : null} />
                  <rect x={0} y={0} width={4} height={b.h} rx={2} fill={n.branch ? "var(--warn)" : freqColor(ratio)} />
                  <text x={b.w/2 + 2} y={21} textAnchor="middle" fontSize="12.5" fontWeight="600" fill="var(--text)">{n.label}</text>
                  <text x={14} y={38} fontSize="10.5" fontWeight="600" fill="var(--text-3)" fontFamily="var(--mono)">{n.cases.toLocaleString("pt-BR")}</text>
                  <text x={b.w - 14} y={38} textAnchor="end" fontSize="10.5" fill="var(--text-3)" fontFamily="var(--mono)">{Math.round(ratio*100)}%</text>
                  <rect x={14} y={b.h-7} width={b.w-28} height={3} rx={1.5} fill="var(--surface-3)" />
                  <rect x={14} y={b.h-7} width={(b.w-28)*Math.min(1,ratio)} height={3} rx={1.5} fill={n.branch ? "var(--warn)" : freqColor(ratio)} />
                </g>
              );
            })}
          </g>
        </g>
      </svg>

      <div className="graph-controls">
        <button className="icon-btn gc" onClick={() => zoom(1)} title="Aproximar"><Icon name="zoomIn" size={17} /></button>
        <button className="icon-btn gc" onClick={() => zoom(-1)} title="Afastar"><Icon name="zoomOut" size={17} /></button>
        <button className="icon-btn gc" onClick={fit} title="Ajustar"><Icon name="fit" size={16} /></button>
        <div className="gc-zoom num">{Math.round(vp.k * 100)}%</div>
      </div>

      <div className="graph-legend">
        <div className="gl-row"><span className="gl-title">Frequência</span></div>
        <div className="gl-ramp">
          <span style={{ background: "var(--freq-0)" }} /><span style={{ background: "var(--freq-1)" }} /><span style={{ background: "var(--freq-2)" }} /><span style={{ background: "var(--freq-3)" }} /><span style={{ background: "var(--freq-4)" }} />
        </div>
        <div className="gl-scale"><span>baixa</span><span>alta</span></div>
        <div className="gl-item"><span className="gl-line crit" /> Gargalo / desvio</div>
      </div>

      {hover && <GraphTooltip hover={hover} data={data} maxCases={maxCases} />}
    </div>
  );
}
