import { useState, useMemo } from "react";
import { Icon } from "./icons.jsx";

export function Sparkline({ data, color, w = 96, h = 30, fill = true, strokeW = 1.6 }) {
  const min = Math.min(...data), max = Math.max(...data);
  const span = max - min || 1;
  const stepX = w / (data.length - 1);
  const pts = data.map((v, i) => [i * stepX, h - 4 - ((v - min) / span) * (h - 8)]);
  const line = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
  const area = line + ` L ${w} ${h} L 0 ${h} Z`;
  const gid = useMemo(() => "sp" + Math.random().toString(36).slice(2, 8), []);
  return (
    <svg width={w} height={h} style={{ display: "block", overflow: "visible" }}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.22" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {fill && <path d={area} fill={`url(#${gid})`} />}
      <path d={line} fill="none" stroke={color} strokeWidth={strokeW} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r="2.4" fill={color} />
    </svg>
  );
}

export function MiniPath({ path, nodes, color = "var(--accent)", conformant = true }) {
  const nodeMap = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes]);
  const steps = path.filter((id) => id !== "start" && id !== "end");
  const w = 168, h = 26, n = steps.length;
  const gap = n > 1 ? (w - 12) / (n - 1) : 0;
  return (
    <svg width={w} height={h} style={{ display: "block" }}>
      {steps.slice(0, -1).map((_, i) => (
        <line key={i} x1={6 + i * gap} y1={h / 2} x2={6 + (i + 1) * gap} y2={h / 2}
          stroke={conformant ? color : "var(--warn)"} strokeWidth="2" opacity="0.45" />
      ))}
      {steps.map((id, i) => {
        const isEnd = i === 0 || i === steps.length - 1;
        return <circle key={id + i} cx={6 + i * gap} cy={h / 2} r={isEnd ? 4 : 3}
          fill={conformant ? color : "var(--warn)"}
          stroke="var(--surface)" strokeWidth="1.5" />;
      })}
    </svg>
  );
}

export function Sev({ sev, children }) {
  return <span className={"badge " + sev}><span className="bdot" style={{ background: "currentColor" }} />{children}</span>;
}

export function KpiCard({ kpi, color, onDrill }) {
  const clickable = !!kpi.drill;
  const sevColor = { ok: "var(--ok)", warn: "var(--warn)", crit: "var(--crit)", info: "var(--info)" }[kpi.sev];
  const isAlert = kpi.icon === "alert";
  return (
    <div className={"kpi-card" + (isAlert ? " alert" : "") + (clickable ? " clickable" : "")}
      data-sev={kpi.sev}
      onClick={clickable ? () => onDrill(kpi.drill) : undefined}>
      <div className="kpi-top">
        <div className="kpi-ico" style={{ background: isAlert ? "var(--" + kpi.sev + "-bg)" : "var(--surface-2)", color: sevColor }}>
          <Icon name={kpi.icon} size={16} />
        </div>
        <div className="kpi-label">{kpi.label}</div>
        {clickable && <Icon name="chevronR" size={15} className="kpi-arrow" />}
      </div>
      <div className="kpi-mid">
        <div className="kpi-value num">{kpi.value}{kpi.unit && <span className="kpi-unit">{kpi.unit}</span>}</div>
        <Sparkline data={kpi.trend} color={isAlert ? sevColor : color} w={92} h={34} />
      </div>
      <div className="kpi-sub">
        {kpi.trendDir && (() => {
          const goodDir = kpi.good;
          const isGood = goodDir ? kpi.trendDir === goodDir : null;
          const cls = isGood === null ? "neutral" : isGood ? "up-good" : "up-bad";
          return <span className={"kpi-delta " + cls}><Icon name={kpi.trendDir === "up" ? "arrowUp" : "arrowDown"} size={12} /></span>;
        })()}
        <span>{kpi.sub}</span>
      </div>
    </div>
  );
}

export function DataTable({ columns, rows }) {
  return (
    <div className="tbl-wrap">
      <table className="tbl">
        <thead>
          <tr>{columns.map((c, i) => <th key={i}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r, ri) => (
            <tr key={ri}>
              {r.map((cell, ci) => {
                if (cell && typeof cell === "object" && cell.badge) {
                  return <td key={ci}><Sev sev={cell.badge}>{cell.text}</Sev></td>;
                }
                const isId = ci === 0;
                const isNum = typeof cell === "string" && /^R\$|\d/.test(cell) && ci > 0;
                return <td key={ci} className={isNum ? "num" : ""} style={isId ? { fontWeight: 600, fontFamily: "var(--mono)", fontSize: "12px" } : null}>{cell}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
