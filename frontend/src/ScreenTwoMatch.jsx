import { Icon } from "./icons.jsx";

/* ───────── formatadores ───────── */
function fmtVal(n) {
  n = Number(n) || 0;
  if (n >= 1e9) return (n / 1e9).toFixed(1).replace(".", ",") + "B";
  if (n >= 1e6) return Math.round(n / 1e6) + "M";
  if (n >= 1e3) return Math.round(n / 1e3) + "K";
  return String(Math.round(n));
}
const fmtInt = (n) => (Number(n) || 0).toLocaleString("pt-BR");
const mesLbl = (m) => m;

function niceMax(v) {
  if (v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  const f = v / p;
  const nf = f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10;
  return nf * p;
}

/* ───────── 1. Pedidos × Faturamento (barras agrupadas) ───────── */
function GroupedBars({ data }) {
  const W = 720, H = 360, padL = 46, padB = 30, padT = 16, padR = 8;
  const cw = W - padL - padR, ch = H - padT - padB;
  const max = niceMax(Math.max(1, ...data.flatMap((d) => [d.pedidoValor, d.faturadoValor])));
  const n = Math.max(1, data.length), group = cw / n, bw = Math.min(15, group / 3);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => t * max);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" className="tm-svg">
      {ticks.map((t, i) => {
        const y = padT + ch - (t / max) * ch;
        return <g key={i}>
          <line x1={padL} x2={W - padR} y1={y} y2={y} className="tm-grid" />
          <text x={padL - 6} y={y + 3} className="tm-axis" textAnchor="end">{fmtVal(t)}</text>
        </g>;
      })}
      {data.map((d, i) => {
        const gx = padL + i * group + group / 2;
        const ph = (d.pedidoValor / max) * ch, fh = (d.faturadoValor / max) * ch;
        return <g key={i}>
          <rect x={gx - bw - 1} y={padT + ch - ph} width={bw} height={Math.max(0, ph)} rx="2" fill="#f59e2b" />
          <rect x={gx + 1} y={padT + ch - fh} width={bw} height={Math.max(0, fh)} rx="2" fill="#16a34a" />
          <text x={gx} y={H - 11} className="tm-axis" textAnchor="middle">{mesLbl(d.mes)}</text>
        </g>;
      })}
    </svg>
  );
}

/* ───────── 2. % de pedidos efetivados (barras + rótulo) ───────── */
function PctBars({ data }) {
  const W = 720, H = 360, padL = 36, padB = 30, padT = 26, padR = 8;
  const cw = W - padL - padR, ch = H - padT - padB;
  const n = Math.max(1, data.length), group = cw / n, bw = Math.min(34, group * 0.6);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" className="tm-svg">
      <line x1={padL} x2={W - padR} y1={padT + ch} y2={padT + ch} className="tm-grid" />
      {data.map((d, i) => {
        const gx = padL + i * group + group / 2;
        const h = (Math.min(100, d.pct) / 100) * ch;
        return <g key={i}>
          <rect x={gx - bw / 2} y={padT + ch - h} width={bw} height={Math.max(0, h)} rx="3" fill="#2f5fe0" />
          <text x={gx} y={padT + ch - h - 6} className="tm-pctlbl" textAnchor="middle">{d.pct.toFixed(2)}%</text>
          <text x={gx} y={H - 11} className="tm-axis" textAnchor="middle">{mesLbl(d.mes)}</text>
        </g>;
      })}
    </svg>
  );
}

/* ───────── 3. Evolução Faturamento (barras + linha, eixo duplo) ───────── */
function ComboChart({ data }) {
  const W = 720, H = 360, padL = 46, padB = 30, padT = 16, padR = 44;
  const cw = W - padL - padR, ch = H - padT - padB;
  const maxV = niceMax(Math.max(1, ...data.map((d) => d.faturadoValor)));
  const maxC = niceMax(Math.max(1, ...data.map((d) => d.faturadoCount)));
  const n = Math.max(1, data.length), group = cw / n, bw = Math.min(26, group * 0.5);
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  const pts = data.map((d, i) => {
    const gx = padL + i * group + group / 2;
    const y = padT + ch - (d.faturadoCount / maxC) * ch;
    return [gx, y];
  });
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" className="tm-svg">
      {ticks.map((t, i) => {
        const y = padT + ch - t * ch;
        return <g key={i}>
          <line x1={padL} x2={W - padR} y1={y} y2={y} className="tm-grid" />
          <text x={padL - 6} y={y + 3} className="tm-axis" textAnchor="end">{fmtVal(t * maxV)}</text>
          <text x={W - padR + 6} y={y + 3} className="tm-axis" textAnchor="start" fill="#e0820e">{fmtVal(t * maxC)}</text>
        </g>;
      })}
      {data.map((d, i) => {
        const gx = padL + i * group + group / 2;
        const h = (d.faturadoValor / maxV) * ch;
        return <g key={i}>
          <rect x={gx - bw / 2} y={padT + ch - h} width={bw} height={Math.max(0, h)} rx="2" fill="#16a34a" />
          <text x={gx} y={H - 11} className="tm-axis" textAnchor="middle">{mesLbl(d.mes)}</text>
        </g>;
      })}
      <polyline points={pts.map((p) => p.join(",")).join(" ")} fill="none" stroke="#e0820e" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
      {pts.map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r="3.2" fill="#e0820e" />)}
    </svg>
  );
}

/* cor da célula Pedidos: vermelho (alto) → verde (baixo) */
function pedColor(v, max) {
  const t = max ? v / max : 0; // 1 = alto (vermelho), 0 = baixo (verde)
  const hue = 130 - t * 130;   // 130 verde → 0 vermelho
  return `hsl(${hue}, 62%, 47%)`;
}

function Panel({ title, meta, icon, children }) {
  return (
    <div className="panel">
      <div className="panel-head">
        <span className="pi"><Icon name={icon} size={15} /></span>
        <span className="pt">{title}</span>
        <span className="ph-spacer" />
        {meta && <span className="ph-meta">{meta}</span>}
      </div>
      <div className="panel-body">{children}</div>
    </div>
  );
}

export function TwoMatchScreen({ data }) {
  const tm = data.twoMatch || { monthly: [], pendentes: [] };
  const dim = data.filters?.dimLabel || data.dimension || "Cliente";
  const months = tm.monthly;
  const maxPed = Math.max(1, ...tm.pendentes.map((p) => p.pedidos));

  return (
    <div className="overview">
      <div className="ov-grid">
        <Panel title="Evolução Pedidos × Faturamento" icon="dashboard" meta="por mês">
          {months.length ? <GroupedBars data={months} /> : <div className="tm-empty">Sem dados</div>}
          <div className="tm-legend">
            <span className="tm-li"><i style={{ background: "#f59e2b" }} />Pedido</span>
            <span className="tm-li"><i style={{ background: "#16a34a" }} />Faturado</span>
          </div>
        </Panel>

        <Panel title="% de pedidos efetivados" icon="shield" meta="por mês">
          {months.length ? <PctBars data={months} /> : <div className="tm-empty">Sem dados</div>}
          <div className="tm-legend">
            <span className="tm-li"><i style={{ background: "#2f5fe0" }} />% Pedidos Efetivados por mês</span>
          </div>
        </Panel>

        <Panel title="Evolução Faturamento" icon="activity" meta="valor + qtde">
          {months.length ? <ComboChart data={months} /> : <div className="tm-empty">Sem dados</div>}
          <div className="tm-legend">
            <span className="tm-li"><i style={{ background: "#16a34a" }} />Faturado</span>
            <span className="tm-li"><i className="line" style={{ background: "#e0820e" }} />Qtde Faturado</span>
          </div>
        </Panel>

        <Panel title="Pedidos Pendentes por Cliente" icon="variants" meta={dim}>
          <div className="nf-wrap rwk-nf tm-pend-wrap">
            <table className="nf-table tm-table">
              <thead>
                <tr><th>{dim}</th><th>Qtde Unidades</th><th>Itens Venda</th><th>Pedidos</th></tr>
              </thead>
              <tbody>
                {tm.pendentes.map((p) => (
                  <tr key={p.entidade}>
                    <td>{p.entidade}</td>
                    <td>{fmtVal(p.qtdUnidades)}</td>
                    <td>{fmtInt(p.itensVenda)}</td>
                    <td className="tm-ped" style={{ background: pedColor(p.pedidos, maxPed) }}>{fmtInt(p.pedidos)}</td>
                  </tr>
                ))}
                {tm.pendentes.length === 0 && (
                  <tr><td colSpan={4} className="tm-empty">Nenhum pedido pendente (todos faturados)</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
    </div>
  );
}
