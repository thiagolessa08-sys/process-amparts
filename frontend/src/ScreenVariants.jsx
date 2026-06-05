import { useState, useEffect } from "react";
import { Icon } from "./icons.jsx";
import { Sev, MiniPath } from "./components.jsx";
import { ProcessGraph } from "./ProcessGraph.jsx";

export const TAG_META = {
  happy: { color: "var(--accent)", badge: "accent", label: "Caminho feliz" },
  risk:  { color: "var(--warn)",   badge: "warn",   label: "Risco" },
  rework:{ color: "var(--warn)",   badge: "warn",   label: "Retrabalho" },
  crit:  { color: "var(--crit)",   badge: "crit",   label: "Crítico" },
  other: { color: "var(--text-3)", badge: "neutral", label: "Outras" },
};

export function VariantsScreen({ data }) {
  const [sel, setSel] = useState(data.variants[0]?.id);
  useEffect(() => { setSel(data.variants[0]?.id); }, [data]);
  const selectedVariant = data.variants.find((v) => v.id === sel);
  const maxPct = Math.max(...data.variants.map((v) => v.pct));
  const conformPct = data.variants.filter(v => v.conformant).reduce((s, v) => s + v.pct, 0);

  return (
    <div className="variants-layout">
      <div className="variants-main">
        <div className="var-summary">
          <div className="var-sum-card"><div className="vsc-val num">{data.avgVariants}</div><div className="vsc-label">Variantes distintas</div></div>
          <div className="var-sum-card"><div className="vsc-val num">{data.variants[0]?.pct}%</div><div className="vsc-label">Cobertura do caminho feliz</div></div>
          <div className="var-sum-card"><div className="vsc-val num" style={{ color: "var(--warn-text)" }}>{Math.round(100 - conformPct)}%</div><div className="vsc-label">Casos não conformes</div></div>
          <div className="var-sum-card"><div className="vsc-val num">{data.totalCases.toLocaleString("pt-BR")}</div><div className="vsc-label">Casos analisados</div></div>
        </div>

        <div className="var-list">
          {data.variants.map((v, i) => {
            const m = TAG_META[v.tag] || TAG_META.other;
            return (
              <div key={v.id} className={"var-item" + (sel === v.id ? " active" : "")} onClick={() => setSel(v.id)}>
                <div className="var-rank">{String(i + 1).padStart(2, "0")}</div>
                <div className="var-mid">
                  <div className="var-name">
                    {v.name}
                    {v.conformant ? <Sev sev="ok">Conforme</Sev> : <span className={"badge " + m.badge}>{m.label}</span>}
                  </div>
                  <div style={{ marginBottom: 9 }}><MiniPath path={v.path} nodes={data.nodes} color={m.color} conformant={v.conformant} /></div>
                  <div className="var-bar-row">
                    <div className="var-bar"><i style={{ width: (v.pct / maxPct * 100) + "%", background: m.color }} /></div>
                    <span className="var-pct num">{v.pct}%</span>
                  </div>
                </div>
                <div className="var-right">
                  <div className="var-cases num">{v.cases.toLocaleString("pt-BR")}</div>
                  <div className="var-cases-label">casos</div>
                  <div className="var-dur"><Icon name="clock" size={11} />{v.avgDur}</div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <aside className="variants-side">
        <div className="vs-head">
          <div>
            <div className="dp-kicker" style={{ marginBottom: 2 }}>Caminho destacado</div>
            <div style={{ fontWeight: 650, fontSize: 14.5 }}>{selectedVariant?.name}</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div className="num" style={{ fontWeight: 700, fontSize: 16 }}>{selectedVariant?.pct}%</div>
            <div style={{ fontSize: 11, color: "var(--text-3)" }}>{selectedVariant?.cases.toLocaleString("pt-BR")} casos</div>
          </div>
        </div>
        <div className="vs-graph graph-stage">
          {selectedVariant && (
            <ProcessGraph data={data} selectedVariant={selectedVariant} flowOn={true} showCounts={false}
              onSelectNode={() => {}} onSelectEdge={() => {}} selected={null} dimFilter={[]} />
          )}
        </div>
      </aside>
    </div>
  );
}
