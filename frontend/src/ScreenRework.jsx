import { useState, useRef } from "react";
import { Icon } from "./icons.jsx";
import { Graph, buildSubgraph, defaultSelection, useFitView, MIN_ZOOM } from "./ScreenExplorer.jsx";

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
const fmtMoney = (n) => (Number(n) || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });

/* ───────── Pizza (com/sem retrabalho) ───────── */
const PIE_COLORS = { "Com Retrabalho": "#e5484d", "Sem Retrabalho": "#16a34a" };

function Donut({ data, size = 172, thickness = 30 }) {
  const r = (size - thickness) / 2, c = 2 * Math.PI * r, cx = size / 2;
  let acc = 0;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <g transform={`rotate(-90 ${cx} ${cx})`}>
        <circle cx={cx} cy={cx} r={r} fill="none" stroke="var(--line-2)" strokeWidth={thickness} />
        {data.map((d) => {
          const len = c * (d.pct / 100);
          const el = (
            <circle key={d.nome} cx={cx} cy={cx} r={r} fill="none"
              stroke={PIE_COLORS[d.nome] || "#999"} strokeWidth={thickness} strokeLinecap="butt"
              strokeDasharray={`${len} ${c - len}`} strokeDashoffset={-acc}>
              <title>{d.nome}: {fmtPct(d.pct)}</title>
            </circle>
          );
          acc += len;
          return el;
        })}
      </g>
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
              <tr><th>Atividade</th><th># Itens</th><th>Valor</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.atividade}>
                  <td>{r.atividade}</td>
                  <td>{fmtInt(r.itens)}</td>
                  <td className="accent">{fmtMoney(r.valor)}</td>
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
        <div className="rwk-donut-wrap">
          <Donut data={rows} />
          <div className="rwk-legend">
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
        <div className="nf-wrap rwk-nf">
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

const RWK_ZOOM0 = 0.74;

export function ReworkScreen({ data }) {
  const rw = data.rework || {};
  const dim = data.filters?.dimLabel || data.dimension || "Cliente";
  const graphData = buildSubgraph(data, defaultSelection(data.variants));

  const [zoom, setZoom] = useState(RWK_ZOOM0);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const dragRef = useRef(null);
  // "Ajustar" e enquadramento automático ao abrir o fluxo
  const { viewportRef, fitView } = useFitView(setZoom, setPan, [data]);
  const onPointerDown = (e) => {
    if (e.target.closest("button, .zoom, .legend, .node, .node-pop")) return;
    setDragging(true);
    dragRef.current = { sx: e.clientX, sy: e.clientY, ox: pan.x, oy: pan.y };
  };
  const onPointerMove = (e) => {
    if (!dragRef.current) return;
    setPan({ x: dragRef.current.ox + (e.clientX - dragRef.current.sx), y: dragRef.current.oy + (e.clientY - dragRef.current.sy) });
  };
  const onPointerUp = () => { dragRef.current = null; setDragging(false); };

  return (
    <div className="rework">
      <div className="rwk-flow">
        <div className="viewport" ref={viewportRef} style={{ cursor: dragging ? "grabbing" : "grab", touchAction: "none" }}
          onPointerDown={onPointerDown} onPointerMove={onPointerMove}
          onPointerUp={onPointerUp} onPointerLeave={onPointerUp}>
          <Graph graphData={graphData} mode="contagem" zoom={zoom} pan={pan} dragging={dragging}
            animKey="rwk" moduleKey={data.key} playingVariant={null} replayKey={0} />
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
            <button onClick={() => setZoom((z) => Math.max(MIN_ZOOM, +(z - 0.12).toFixed(2)))}><Icon name="minus" size={16} /></button>
            <button onClick={fitView} title="Ajustar à tela"><Icon name="fit" size={16} /></button>
          </div>
          <div className="zoom-pct mono">{Math.round(zoom * 100)}%</div>
        </div>
      </div>
      <div className="rwk-col">
        <div className="rwk-kpi-row">
          <div className="rwk-kpi">
            <span className="rwk-kpi-ic"><Icon name="loop" size={20} /></span>
            <div className="rwk-kpi-txt">
              <div className="rwk-kpi-label">Retrabalho geral</div>
              <div className="rwk-kpi-desc">% de casos com ao menos uma atividade de retrabalho</div>
            </div>
            <span className="rwk-kpi-spacer" />
            <div className="rwk-kpi-value">{fmtPct(rw.pctComRetrabalho ?? 0)}</div>
          </div>
          <div className="rwk-kpi rwk-kpi-cost">
            <span className="rwk-kpi-ic"><Icon name="bolt" size={20} /></span>
            <div className="rwk-kpi-txt">
              <div className="rwk-kpi-label">Custo estimado de retrabalho</div>
              <div className="rwk-kpi-desc">
                {(rw.itensRetrabalho ?? 0).toLocaleString("pt-BR")} itens cancelados/alterados ·{" "}
                {rw.custoPremissa?.minutos ?? 10} min ·{" "}
                {fmtMoney(rw.custoPremissa?.valorHora ?? 50)}/h
              </div>
            </div>
            <span className="rwk-kpi-spacer" />
            <div className="rwk-kpi-value">{fmtMoney(rw.custoRetrabalho ?? 0)}</div>
          </div>
        </div>
        <AtividadesPanel rows={rw.atividades} />
        <div className="rwk-bottom">
          <ComSemPanel rows={rw.comSem} />
          <PorClientePanel rows={rw.porEntidade} dim={dim} />
        </div>
      </div>
    </div>
  );
}
