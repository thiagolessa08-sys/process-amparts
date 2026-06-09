import { useState, useMemo } from "react";

const fmtInt = (n) => (Number(n) || 0).toLocaleString("pt-BR");

/* ───────── KPI card ───────── */
function Kpi({ label, value, unit, desc }) {
  return (
    <div className="up-kpi">
      <div className="up-kpi-label">{label}</div>
      <div className="up-kpi-value">{value} <span className="up-kpi-unit">{unit}</span></div>
      <div className="up-kpi-desc">{desc}</div>
    </div>
  );
}

/* ───────── área: usuários ativos por dia ───────── */
function AreaChart({ series }) {
  const W = 1180, H = 300, padL = 40, padR = 12, padT = 14, padB = 26;
  const cw = W - padL - padR, ch = H - padT - padB;
  if (!series.length) return <div className="up-empty">Sem dados</div>;
  const max = Math.max(5, ...series.map((s) => s.count));
  const xs = (i) => padL + (i / Math.max(1, series.length - 1)) * cw;
  const ys = (v) => padT + ch - (v / max) * ch;
  const line = series.map((s, i) => `${xs(i).toFixed(1)},${ys(s.count).toFixed(1)}`).join(" ");
  const area = `M ${padL},${padT + ch} L ${line.split(" ").join(" L ")} L ${(padL + cw)},${padT + ch} Z`;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => Math.round(t * max));
  // rótulos de ano no eixo X
  const years = [];
  let lastY = null;
  series.forEach((s, i) => { const y = s.date.slice(0, 4); if (y !== lastY) { years.push({ i, y }); lastY = y; } });
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="up-area-svg" preserveAspectRatio="none">
      <defs>
        <linearGradient id="upArea" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#5b8def" stopOpacity="0.45" />
          <stop offset="1" stopColor="#5b8def" stopOpacity="0.04" />
        </linearGradient>
      </defs>
      {ticks.map((t, i) => { const y = ys(t); return <g key={i}><line x1={padL} x2={W - padR} y1={y} y2={y} className="tm-grid" /><text x={padL - 6} y={y + 3} className="tm-axis" textAnchor="end">{t}</text></g>; })}
      <path d={area} fill="url(#upArea)" />
      <polyline points={line} fill="none" stroke="#4a82ea" strokeWidth="1.6" />
      {years.map((yr, k) => <text key={k} x={xs(yr.i)} y={H - 9} className="tm-axis" textAnchor="middle">{yr.y}</text>)}
    </svg>
  );
}

/* ───────── bubble chart (circle packing) ───────── */
function bubbleColor(t) {
  const c1 = [169, 194, 227], c2 = [224, 97, 124];
  const c = c1.map((a, i) => Math.round(a + (c2[i] - a) * t));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

function packBubbles(users, metric, W, H) {
  const vals = users.map((u) => Math.max(0.001, u[metric]));
  const min = Math.min(...vals), max = Math.max(...vals);
  const sMin = Math.sqrt(min), sMax = Math.sqrt(max);
  const rMin = 16, rMax = 54;
  const items = users.map((u) => {
    const v = Math.max(0.001, u[metric]);
    const t = sMax > sMin ? (Math.sqrt(v) - sMin) / (sMax - sMin) : 0.5;
    return { ...u, v, t, r: rMin + t * (rMax - rMin) };
  }).sort((a, b) => b.r - a.r);
  const placed = [], cx = W / 2, cy = H / 2;
  for (const it of items) {
    if (!placed.length) { placed.push({ ...it, x: cx, y: cy }); continue; }
    let pos = null;
    for (let a = 0; a < 8000; a++) {
      const ang = a * 0.35, rad = 2 + a * 0.45;
      const x = cx + rad * Math.cos(ang), y = cy + rad * Math.sin(ang);
      if (placed.every((p) => Math.hypot(p.x - x, p.y - y) >= p.r + it.r + 2)) { pos = { x, y }; break; }
    }
    placed.push({ ...it, x: (pos || { x: cx, y: cy }).x, y: (pos || { x: cx, y: cy }).y });
  }
  return placed;
}

function Bubbles({ users, metric }) {
  const W = 1180, H = 540;
  const placed = useMemo(() => packBubbles(users, metric, W, H), [users, metric]);
  const fmtV = (b) => metric === "throughput" ? `${b.v.toFixed(1)}d` : fmtInt(b.events);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="up-bubbles">
      {placed.map((b) => (
        <g key={b.user} transform={`translate(${b.x.toFixed(1)},${b.y.toFixed(1)})`}>
          <circle r={b.r} fill={bubbleColor(b.t)} fillOpacity="0.92">
            <title>{b.user}: {metric === "throughput" ? `${b.v.toFixed(1)} dias` : `${fmtInt(b.events)} eventos`}</title>
          </circle>
          {b.r >= 30 && <text y={-2} className="up-bub-name" textAnchor="middle">{b.user.length > 16 ? b.user.slice(0, 15) + "…" : b.user}</text>}
          <text y={b.r >= 30 ? 13 : 4} className="up-bub-val" textAnchor="middle" style={{ fontSize: Math.max(9, Math.min(15, b.r * 0.42)) }}>{fmtV(b)}</text>
        </g>
      ))}
    </svg>
  );
}

export function UserProdScreen({ data }) {
  const up = data.userProd || {};
  const [tab, setTab] = useState("events");
  const users = up.users || [];

  return (
    <div className="userprod">
      <div className="up-kpis">
        <Kpi label="Usuários ativos" value={up.activeUsersPerDay ?? 0} unit="por dia" desc="Média de usuários que executaram uma atividade no dia" />
        <Kpi label="Eventos por usuário" value={up.eventsPerUser ?? 0} unit="por dia" desc="Média diária de eventos por usuário" />
        <Kpi label="Casos por usuário" value={fmtInt(up.casesPerUser ?? 0)} unit="casos" desc="Média de casos por usuário" />
        <Kpi label="Usuários por caso" value={up.usersPerCase ?? 0} unit="usuários" desc="Média de usuários por caso" />
      </div>

      <div className="panel">
        <div className="panel-head"><span className="pt">Evolução de usuários ativos (por dia)</span></div>
        <div className="panel-body"><AreaChart series={up.series || []} /></div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <span className="pt">Usuários</span>
          <span className="ph-spacer" />
          <div className="seg up-seg">
            <button className={tab === "events" ? "on" : ""} onClick={() => setTab("events")}>Eventos</button>
            <button className={tab === "throughput" ? "on" : ""} onClick={() => setTab("throughput")}>Throughput</button>
          </div>
        </div>
        <div className="panel-body">
          <div className="up-scale"><span>Poucos</span><i /><span>Muitos</span></div>
          {users.length ? <Bubbles users={users} metric={tab} /> : <div className="up-empty">Sem dados de usuário</div>}
        </div>
      </div>
    </div>
  );
}
