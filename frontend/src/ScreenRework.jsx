import { Icon } from "./icons.jsx";
import { Graph, buildSubgraph, defaultSelection } from "./ScreenExplorer.jsx";

/* formatadores compactos */
function fmtCompact(n) {
  n = Number(n) || 0;
  if (n >= 1e9) return (n / 1e9).toFixed(2).replace(".", ",") + "B";
  if (n >= 1e6) return (n / 1e6).toFixed(1).replace(".", ",") + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1).replace(".", ",") + "K";
  return String(Math.round(n));
}
const fmtInt = (n) => (Number(n) || 0).toLocaleString("pt-BR");
const fmtPct = (n) => (Number(n) || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " %";

/* ───────── Pizza (com/sem retrabalho) ───────── */
const PIE_COLORS = { "Com Retrabalho": "#e5484d", "Sem Retrabalho": "#16a34a" };

function Pie({ data, size = 168 }) {
  const r = size / 2, cx = r, cy = r;
  let acc = 0;
  const pt = (frac) => {
    const a = 2 * Math.PI * frac - Math.PI / 2;
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  };
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {data.map((d) => {
        const start = acc, end = acc + d.pct / 100;
        acc = end;
        if (d.pct <= 0) return null;
        if (d.pct >= 99.999) {
          return <circle key={d.nome} cx={cx} cy={cy} r={r} fill={PIE_COLORS[d.nome] || "#999"} />;
        }
        const [x1, y1] = pt(start), [x2, y2] = pt(end);
        const large = end - start > 0.5 ? 1 : 0;
        return (
          <path key={d.nome} d={`M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`}
            fill={PIE_COLORS[d.nome] || "#999"}>
            <title>{d.nome}: {fmtPct(d.pct)}</title>
          </path>
        );
      })}
    </svg>
  );
}

/* ───────── Painéis ───────── */
function AtividadesPanel({ rows = [] }) {
  return (
    <div className="panel">
      <div className="panel-head">
        <span className="pi"><Icon name="loop" size={15} /></span>
        <span className="pt">Atividades de Retrabalho</span>
        <span className="ph-spacer" />
        <span className="ph-meta">{rows.length} atividades</span>
      </div>
      <div className="panel-body">
        <div className="nf-wrap">
          <table className="nf-table">
            <thead>
              <tr><th>Atividade</th><th># Itens</th><th># Atividade</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.atividade}>
                  <td>{r.atividade}</td>
                  <td>{fmtInt(r.itens)}</td>
                  <td className="accent">{fmtInt(r.ocorrencias)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function ComSemPanel({ rows = [] }) {
  return (
    <div className="panel">
      <div className="panel-head">
        <span className="pi"><Icon name="shield" size={15} /></span>
        <span className="pt">Com ou Sem Retrabalho</span>
      </div>
      <div className="panel-body">
        <div className="clients" style={{ justifyContent: "center" }}>
          <Pie data={rows} />
          <div className="clients-legend" style={{ gridTemplateColumns: "1fr" }}>
            {rows.map((d) => (
              <div className="lchip" key={d.nome}>
                <span className="sw" style={{ background: PIE_COLORS[d.nome] || "#999" }} />
                <span className="lc" style={{ fontFamily: "inherit" }}>{d.nome}</span>
                <span className="lp">{fmtPct(d.pct)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function PorClientePanel({ rows = [], dim }) {
  return (
    <div className="panel">
      <div className="panel-head">
        <span className="pi"><Icon name="variants" size={15} /></span>
        <span className="pt">Retrabalho por {dim}</span>
        <span className="ph-spacer" />
        <span className="ph-meta">{dim}</span>
      </div>
      <div className="panel-body">
        <div className="nf-wrap">
          <table className="nf-table rwk-table">
            <thead>
              <tr><th>{dim}</th><th>Qtde Unidades</th><th>Itens Venda</th><th>% Retrabalho</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.entidade}>
                  <td>{r.entidade}</td>
                  <td>{fmtCompact(r.qtdUnidades)}</td>
                  <td>{fmtInt(r.itensVenda)}</td>
                  <td className="rwk-pct-cell">
                    <span className="rwk-pct-bar" style={{ width: Math.min(100, r.pctRetrabalho) + "%" }} />
                    <span className="rwk-pct-val">{fmtPct(r.pctRetrabalho)}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export function ReworkScreen({ data }) {
  const rw = data.rework || {};
  const dim = data.filters?.dimLabel || data.dimension || "Cliente";
  const graphData = buildSubgraph(data, defaultSelection(data.variants));
  return (
    <div className="rework">
      <div className="rwk-flow">
        <div className="rwk-graph-scroll">
          <Graph graphData={graphData} mode="contagem" zoom={0.74} pan={{ x: 0, y: 0 }}
            dragging={false} animKey="rwk" moduleKey={data.key} playingVariant={null} replayKey={0} />
        </div>
      </div>
      <div className="rwk-col">
        <AtividadesPanel rows={rw.atividades} />
        <div className="rwk-bottom">
          <ComSemPanel rows={rw.comSem} />
          <PorClientePanel rows={rw.porEntidade} dim={dim} />
        </div>
      </div>
    </div>
  );
}
