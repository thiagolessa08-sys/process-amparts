import { useState, useMemo, useEffect } from "react";
import { Icon } from "./icons.jsx";
import { fetchUser } from "./api.js";

const fmtInt = (n) => (Number(n) || 0).toLocaleString("pt-BR");
function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso), p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

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
    <svg viewBox={`0 0 ${W} ${H}`} className="up-area-svg">
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
  const rMin = 26, rMax = 86;
  const items = users.map((u) => {
    const v = Math.max(0.001, u[metric]);
    const t = sMax > sMin ? (Math.sqrt(v) - sMin) / (sMax - sMin) : 0.5;
    return { ...u, v, t, r: rMin + t * (rMax - rMin) };
  }).sort((a, b) => b.r - a.r);
  const placed = [], cx = W / 2, cy = H / 2;
  for (const it of items) {
    if (!placed.length) { placed.push({ ...it, x: cx, y: cy }); continue; }
    let pos = null;
    for (let a = 0; a < 12000; a++) {
      const ang = a * 0.3, rad = 2 + a * 0.55;
      const x = cx + rad * Math.cos(ang), y = cy + rad * Math.sin(ang);
      if (placed.every((p) => Math.hypot(p.x - x, p.y - y) >= p.r + it.r + 4)) { pos = { x, y }; break; }
    }
    placed.push({ ...it, x: (pos || { x: cx, y: cy }).x, y: (pos || { x: cx, y: cy }).y });
  }
  return placed;
}

function Bubbles({ users, metric, onSelect }) {
  const W = 1180, H = 580;
  const placed = useMemo(() => packBubbles(users, metric, W, H), [users, metric]);
  const fmtV = (b) => metric === "throughput" ? `${b.v.toFixed(1)}d` : fmtInt(b.events);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="up-bubbles">
      <defs>
        <filter id="bubShadow" x="-40%" y="-40%" width="180%" height="180%">
          <feDropShadow dx="0" dy="3" stdDeviation="5" floodColor="#5b6b9e" floodOpacity="0.30" />
        </filter>
        <radialGradient id="bubGloss" cx="35%" cy="26%" r="78%">
          <stop offset="0" stopColor="#fff" stopOpacity="0.5" />
          <stop offset="0.45" stopColor="#fff" stopOpacity="0.08" />
          <stop offset="1" stopColor="#fff" stopOpacity="0" />
        </radialGradient>
      </defs>
      {placed.map((b) => (
        <g key={b.user} transform={`translate(${b.x.toFixed(1)},${b.y.toFixed(1)})`}
          className="up-bub" onClick={() => onSelect?.(b.user)}>
          <title>{b.user}: {metric === "throughput" ? `${b.v.toFixed(1)} dias` : `${fmtInt(b.events)} eventos`}</title>
          <circle className="up-bub-fill" r={b.r} fill={bubbleColor(b.t)} filter="url(#bubShadow)" />
          <circle r={b.r} fill="url(#bubGloss)" pointerEvents="none" />
          <circle r={b.r} fill="none" stroke="#fff" strokeOpacity="0.6" strokeWidth="1.5" pointerEvents="none" />
          {b.r >= 30 && <text y={-3} className="up-bub-name" textAnchor="middle"
            style={{ fontSize: Math.max(8.5, Math.min(12.5, b.r * 0.24)) }}>
            {b.user.length > 16 ? b.user.slice(0, 15) + "…" : b.user}</text>}
          <text y={b.r >= 30 ? 14 : 4} className="up-bub-val" textAnchor="middle"
            style={{ fontSize: Math.max(10, Math.min(19, b.r * 0.4)) }}>{fmtV(b)}</text>
        </g>
      ))}
    </svg>
  );
}

/* ───────── área mensal empilhada por atividade (estilo Celonis) ───────── */
function MonthlyArea({ data, legend }) {
  const acts = legend && legend.length ? legend : ["Eventos"];
  const colorOf = (a) => a === "Outras" ? "#a9a9a9" : DP_COLORS[acts.indexOf(a) % DP_COLORS.length];

  const W = 1180, H = 320, padL = 44, padR = 14, padT = 16, padB = 40;
  const cw = W - padL - padR, ch = H - padT - padB;
  const [hover, setHover] = useState(null);
  if (!data.length) return <div className="up-empty">Sem dados</div>;

  const valOf = (d, a) => d.acts ? (d.acts[a] || 0) : d.events;
  const max = Math.max(5, ...data.map((d) => d.events));
  const xs = (i) => padL + (data.length === 1 ? cw / 2 : (i / (data.length - 1)) * cw);
  const ys = (v) => padT + ch - (v / max) * ch;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => Math.round(t * max));

  // áreas empilhadas: para cada atividade, polígono entre acumulado anterior e atual
  const cum = data.map(() => 0);
  const bands = acts.map((a) => {
    const lower = cum.slice();
    data.forEach((d, i) => { cum[i] += valOf(d, a); });
    const upper = cum.slice();
    const top = data.map((_, i) => `${xs(i).toFixed(1)},${ys(upper[i]).toFixed(1)}`).join(" L ");
    const bot = data.map((_, i) => `${xs(data.length - 1 - i).toFixed(1)},${ys(lower[data.length - 1 - i]).toFixed(1)}`).join(" L ");
    return { a, d: `M ${top} L ${bot} Z` };
  });

  return (
    <div className="up-dp">
      <div className="up-dp-legend">
        {acts.map((a) => <span key={a} className="up-dp-leg"><i style={{ background: colorOf(a) }} />{a}</span>)}
      </div>
      <div className="up-dp-chart">
        <svg viewBox={`0 0 ${W} ${H}`} className="up-area-svg">
          {ticks.map((t, i) => { const y = ys(t); return <g key={i}><line x1={padL} x2={W - padR} y1={y} y2={y} className="tm-grid" /><text x={padL - 6} y={y + 3} className="tm-axis" textAnchor="end">{t}</text></g>; })}
          {bands.map((b) => <path key={b.a} d={b.d} fill={colorOf(b.a)} fillOpacity="0.88" />)}
          {data.map((d, i) => (i % 3 === 0 || i === data.length - 1) && <text key={"t" + i} x={xs(i)} y={H - 12} className="tm-axis" textAnchor="middle">{d.mes}</text>)}
          {data.map((d, i) => {
            const w = data.length > 1 ? cw / (data.length - 1) : cw;
            return <rect key={"h" + i} x={xs(i) - w / 2} y={padT} width={w} height={ch} fill="transparent"
              onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover((p) => p === i ? null : p)} />;
          })}
          {hover != null && <line x1={xs(hover)} x2={xs(hover)} y1={padT} y2={padT + ch} className="tm-grid" stroke="#9aa" />}
        </svg>
        {hover != null && data[hover] && (
          <div className="up-dp-tip" style={{ left: `${xs(hover) / W * 100}%` }}>
            <div className="up-dp-tip-head">{data[hover].mes}</div>
            {acts.map((a) => { const v = valOf(data[hover], a); return v > 0 && (
              <div key={a} className="up-dp-tip-row"><i style={{ background: colorOf(a) }} />{a}: <b>{fmtInt(v)}</b></div>
            ); })}
          </div>
        )}
      </div>
    </div>
  );
}

/* ───────── perfil diário (barras empilhadas por atividade, estilo Celonis) ───────── */
const DP_COLORS = ["#e6607c", "#c77da6", "#8f8fd0", "#7fc6da", "#6fae87", "#e3b34b", "#a9a9a9"];

function DailyProfile({ data, legend }) {
  const acts = legend && legend.length ? legend : ["Eventos"];
  const colorOf = (a) => a === "Outras" ? "#a9a9a9" : DP_COLORS[acts.indexOf(a) % DP_COLORS.length];

  const W = 1180, H = 300, padL = 44, padR = 14, padT = 16, padB = 32;
  const cw = W - padL - padR, ch = H - padT - padB;
  const max = Math.max(1, ...data.map((d) => d.count));
  const n = data.length, group = cw / n, bw = Math.min(54, group * 0.6);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => Math.round(t * max));
  const [hover, setHover] = useState(null);

  return (
    <div className="up-dp">
      <div className="up-dp-legend">
        {acts.map((a) => (
          <span key={a} className="up-dp-leg"><i style={{ background: colorOf(a) }} />{a}</span>
        ))}
      </div>
      <div className="up-dp-chart">
        <svg viewBox={`0 0 ${W} ${H}`} className="up-area-svg">
          {ticks.map((t, i) => { const y = padT + ch - (t / max) * ch; return <g key={i}><line x1={padL} x2={W - padR} y1={y} y2={y} className="tm-grid" /><text x={padL - 6} y={y + 3} className="tm-axis" textAnchor="end">{t}</text></g>; })}
          {data.map((d, i) => {
            const gx = padL + i * group + group / 2;
            let yTop = padT + ch;
            const segs = acts.map((a) => {
              const v = d.acts ? (d.acts[a] || 0) : d.count;
              const h = (v / max) * ch;
              yTop -= h;
              return { a, v, y: yTop, h };
            });
            return <g key={i} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover((p) => p === i ? null : p)}>
              {segs.map((s) => s.h > 0 && (
                <rect key={s.a} x={gx - bw / 2} y={s.y} width={bw} height={Math.max(0, s.h)} fill={colorOf(s.a)} />
              ))}
              <text x={gx} y={H - 10} className="tm-axis" textAnchor="middle">{d.bucket.replace(/:00/g, "").replace(" - ", "–") + "h"}</text>
            </g>;
          })}
        </svg>
        {hover != null && data[hover] && data[hover].count > 0 && (
          <div className="up-dp-tip" style={{ left: `${(padL + hover * group + group / 2) / W * 100}%` }}>
            <div className="up-dp-tip-head">Faixa de hora: {data[hover].bucket}</div>
            {acts.map((a) => {
              const v = data[hover].acts ? (data[hover].acts[a] || 0) : data[hover].count;
              return v > 0 && (
                <div key={a} className="up-dp-tip-row">
                  <i style={{ background: colorOf(a) }} />{a}: <b>{fmtInt(v)}</b>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function UserDrill({ moduleKey, name, filters, onBack }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    let alive = true;
    setD(null); setErr(null);
    fetchUser(moduleKey, name, filters)
      .then((res) => alive && setD(res))
      .catch((e) => alive && setErr(e.message));
    return () => { alive = false; };
  }, [moduleKey, name, filters]);

  return (
    <div className="userprod">
      <button className="up-back" onClick={onBack}><Icon name="chevronR" size={15} style={{ transform: "rotate(180deg)" }} />Voltar para usuários</button>
      <div className="up-drill-title"><b>{name}</b></div>

      {!d && !err && <div className="up-empty">Carregando…</div>}
      {err && <div className="up-empty">Erro: {err}</div>}
      {d && d.found === false && <div className="up-empty">Sem eventos para este usuário no filtro atual.</div>}
      {d && d.found && (
        <>
          <div className="up-kpis up-kpis-6">
            <Kpi label="Eventos" value={d.eventsPerDay} unit="por dia" desc="Média de eventos por dia" />
            <Kpi label="Atividades" value={d.activitiesPerDay} unit="por dia" desc="Média de atividades diferentes por dia" />
            <Kpi label="Throughput" value={d.throughputHours.toFixed(1)} unit="horas" desc="Tempo médio ponta a ponta dos casos do usuário" />
            <Kpi label="Última atividade" value={fmtDate(d.lastActive).split(" ")[0]} unit="" desc={`Última atividade em ${fmtDate(d.lastActive)}`} />
            <div className="up-kpi">
              <div className="up-kpi-label">Casos vêm de</div>
              <div className="up-kpi-names">{d.comeFrom.names.join(", ") || "—"}</div>
              <div className="up-kpi-desc">em {d.comeFrom.pct}%</div>
            </div>
            <div className="up-kpi">
              <div className="up-kpi-label">Casos vão para</div>
              <div className="up-kpi-names">{d.goesTo.names.join(", ") || "—"}</div>
              <div className="up-kpi-desc">em {d.goesTo.pct}%</div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-head"><span className="pt"><b>{name}</b> — atividades por mês</span></div>
            <div className="panel-body"><MonthlyArea data={d.monthly} legend={d.dailyLegend} /></div>
          </div>

          <div className="panel">
            <div className="panel-head"><span className="pt"><b>{name}</b> — perfil diário</span></div>
            <div className="panel-body"><DailyProfile data={d.dailyProfile} legend={d.dailyLegend} /></div>
          </div>
        </>
      )}
    </div>
  );
}

export function UserProdScreen({ data, filters }) {
  const up = data.userProd || {};
  const [tab, setTab] = useState("events");
  const [sel, setSel] = useState(null);
  const users = up.users || [];
  // só os 30 maiores pela métrica ativa (evita centenas de bolhas poluindo)
  const topUsers = useMemo(
    () => [...users].sort((a, b) => (b[tab] || 0) - (a[tab] || 0)).slice(0, 30),
    [users, tab]
  );
  // todos os usuários (ordem alfabética) para o seletor — ver alguém além dos 30
  const allUsers = useMemo(
    () => [...users].sort((a, b) => a.user.localeCompare(b.user)),
    [users]
  );

  if (sel) return <UserDrill moduleKey={data.key} name={sel} filters={filters} onBack={() => setSel(null)} />;

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
          {users.length > 30 && <span className="ph-meta">top 30 de {fmtInt(users.length)}</span>}
          <span className="ph-spacer" />
          <div className="selectwrap up-userpick">
            <span className="lead"><Icon name="search" size={14} /></span>
            <select value="" onChange={(e) => e.target.value && setSel(e.target.value)}>
              <option value="">Ver usuário…</option>
              {allUsers.map((u) => <option key={u.user} value={u.user}>{u.user}</option>)}
            </select>
            <span className="caret"><Icon name="chevronD" size={14} /></span>
          </div>
          <div className="seg up-seg">
            <button className={tab === "events" ? "on" : ""} onClick={() => setTab("events")}>Eventos</button>
            <button className={tab === "throughput" ? "on" : ""} onClick={() => setTab("throughput")}>Throughput</button>
          </div>
        </div>
        <div className="panel-body">
          <div className="up-scale"><span>Poucos</span><i /><span>Muitos</span></div>
          {topUsers.length ? <Bubbles users={topUsers} metric={tab} onSelect={setSel} /> : <div className="up-empty">Sem dados de usuário</div>}
        </div>
      </div>
    </div>
  );
}
