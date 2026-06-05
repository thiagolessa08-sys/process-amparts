import { useState, useMemo, useEffect } from "react";
import { Icon } from "./icons.jsx";
import { Sev, DataTable } from "./components.jsx";
import { ProcessGraph } from "./ProcessGraph.jsx";

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
            <div className="dp-kicker" style={{ color: "var(--" + drill.sev + "-text)" }}>Drill-down · {drill.rows.length} casos</div>
            <h2 className="drawer-title">{drill.title}</h2>
            <div className="drawer-meta">
              <div className="dm">Casos afetados<b>{drill.rows.length}</b></div>
              <div className="dm">Severidade<b style={{ color: "var(--" + drill.sev + "-text)", fontFamily: "var(--sans)", fontSize: 14 }}>{drill.sev === "crit" ? "Crítico" : drill.sev === "warn" ? "Atenção" : "Info"}</b></div>
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
        <div className="dp-section-title">Impacto estimado</div>
        <p style={{ fontSize: 12.5, color: "var(--text-2)", lineHeight: 1.5, margin: 0 }}>
          {e.bottleneck ? "Esta transição concentra parte relevante do lead time. Reduzir o tempo aqui melhora o indicador geral do processo." : "Transição dentro do comportamento esperado do processo."}
        </p>
      </div>
    </aside>
  );
}

export function ExplorerScreen({ data }) {
  const [variantId, setVariantId] = useState("");
  const [dimFilter, setDimFilter] = useState([]);
  const [flowOn, setFlowOn] = useState(true);
  const [showCounts, setShowCounts] = useState(false);
  const [selected, setSelected] = useState(null);
  const [actLevel, setActLevel] = useState(100);
  const [pathLevel, setPathLevel] = useState(80);

  useEffect(() => { setSelected(null); setVariantId(""); setDimFilter([]); }, [data]);

  const selectedVariant = useMemo(() => data.variants.find((v) => v.id === variantId) || null, [variantId, data]);
  const toggleDim = (d) => setDimFilter((f) => f.includes(d) ? f.filter((x) => x !== d) : [...f, d]);
  const nodeMap = useMemo(() => Object.fromEntries(data.nodes.map((n) => [n.id, n])), [data]);

  return (
    <div className={"explorer" + (selected ? " with-detail" : "")}>
      <aside className="filters">
        <div className="filter-sec">
          <div className="filter-head">
            <span><Icon name="filter" size={12} style={{ verticalAlign: -1, marginRight: 5 }} />Filtros</span>
            {(dimFilter.length > 0 || variantId) && <button className="btn ghost sm" style={{ height: 22, padding: "0 6px", fontSize: 11 }} onClick={() => { setDimFilter([]); setVariantId(""); }}>Limpar</button>}
          </div>
          <label className="field-label">Variante</label>
          <select className="select" value={variantId} onChange={(e) => setVariantId(e.target.value)}>
            <option value="">Todas as variantes ({data.avgVariants})</option>
            {data.variants.map((v) => <option key={v.id} value={v.id}>{v.name} — {v.pct}%</option>)}
          </select>
        </div>

        {data.filters.dims.length > 0 && (
          <div className="filter-sec">
            <div className="filter-head"><span>{data.filters.dimLabel}</span>{dimFilter.length > 0 && <span className="fh-count">{dimFilter.length}</span>}</div>
            <div className="chip-list">
              {data.filters.dims.map((d) => (
                <button key={d} className={"fchip" + (dimFilter.includes(d) ? " on" : "")} onClick={() => toggleDim(d)}>{d}</button>
              ))}
            </div>
          </div>
        )}

        <div className="filter-sec">
          <div className="filter-head"><span>Detalhe do modelo</span></div>
          <label className="field-label" style={{ display: "flex", justifyContent: "space-between" }}>Atividades <b className="num" style={{ color: "var(--text)" }}>{actLevel}%</b></label>
          <input className="slider" type="range" min="20" max="100" value={actLevel} onChange={(e) => setActLevel(+e.target.value)} />
          <label className="field-label" style={{ display: "flex", justifyContent: "space-between", marginTop: 10 }}>Conexões <b className="num" style={{ color: "var(--text)" }}>{pathLevel}%</b></label>
          <input className="slider" type="range" min="20" max="100" value={pathLevel} onChange={(e) => setPathLevel(+e.target.value)} />
        </div>

        <div className="filter-sec">
          <div className="filter-head"><span>Resumo</span></div>
          <div className="metric-mini"><span className="mm-label">Total de casos</span><span className="mm-val num">{data.totalCases.toLocaleString("pt-BR")}</span></div>
          <div className="metric-mini"><span className="mm-label">Variantes</span><span className="mm-val num">{data.avgVariants}</span></div>
          <div className="metric-mini"><span className="mm-label">Atividades</span><span className="mm-val num">{data.nodes.filter(n => !n.type).length}</span></div>
        </div>
      </aside>

      <div className="graph-stage">
        <div className="graph-toolbar">
          <div className="gt-pill"><Icon name="layers" size={14} style={{ color: "var(--accent)" }} />{selectedVariant ? selectedVariant.name : "Modelo completo"} · <b>{(selectedVariant ? selectedVariant.cases : data.totalCases).toLocaleString("pt-BR")}</b> casos</div>
          <div style={{ flex: 1 }} />
          <div className="gt-pill" style={{ padding: 4, gap: 4 }}>
            <button className={"btn sm" + (flowOn ? " primary" : " ghost")} onClick={() => setFlowOn((f) => !f)}><Icon name="play" size={13} />Fluxo</button>
            <button className={"btn sm" + (showCounts ? " primary" : " ghost")} onClick={() => setShowCounts((c) => !c)}>123 Contagem</button>
          </div>
        </div>
        <ProcessGraph data={data} selectedVariant={selectedVariant} flowOn={flowOn} showCounts={showCounts}
          onSelectNode={(n) => setSelected({ kind: "node", item: n })}
          onSelectEdge={(e) => setSelected({ kind: "edge", item: e })}
          selected={selected} dimFilter={dimFilter} />
      </div>

      {selected && <ExplorerDetail selected={selected} data={data} nodeMap={nodeMap} onClose={() => setSelected(null)} />}
    </div>
  );
}
