import { Icon } from "./icons.jsx";
import { Sparkline, KpiCard } from "./components.jsx";
import { TAG_META } from "./ScreenVariants.jsx";

function AlertCard({ kpi, color, onDrill }) {
  const sevColor = { ok: "var(--ok)", warn: "var(--warn)", crit: "var(--crit)", info: "var(--info)" }[kpi.sev];
  return (
    <div className="kpi-card alert clickable" data-sev={kpi.sev} onClick={() => kpi.drill && onDrill(kpi.drill)} style={{ gap: 13 }}>
      <div className="kpi-top">
        <div className="kpi-ico" style={{ background: "var(--" + kpi.sev + "-bg)", color: sevColor }}><Icon name="alert" size={16} /></div>
        <div><div style={{ fontSize: 13, fontWeight: 600 }}>{kpi.label}</div></div>
        <span className={"badge " + kpi.sev} style={{ marginLeft: "auto" }}><span className="bdot" style={{ background: "currentColor" }} />{kpi.sev === "crit" ? "Crítico" : "Atenção"}</span>
      </div>
      <div className="kpi-mid" style={{ alignItems: "flex-end" }}>
        <div>
          <div className="kpi-value num" style={{ fontSize: 30, color: sevColor }}>{kpi.value}{kpi.unit && <span className="kpi-unit">{kpi.unit}</span>}</div>
          <div className="kpi-sub" style={{ marginTop: 6 }}>{kpi.sub}</div>
        </div>
        <Sparkline data={kpi.trend} color={sevColor} w={104} h={40} />
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--accent-text)", fontSize: 12.5, fontWeight: 600, paddingTop: 4, borderTop: "1px solid var(--border)", marginTop: 2 }}>
        Ver casos afetados <Icon name="chevronR" size={14} />
      </div>
    </div>
  );
}

function Donut({ pct, color, size = 120 }) {
  const r = size / 2 - 11, c = 2 * Math.PI * r;
  return (
    <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="var(--surface-3)" strokeWidth="13" />
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth="13" strokeLinecap="round"
        strokeDasharray={`${c * pct/100} ${c}`} style={{ transition: "stroke-dasharray .5s" }} />
      <text x={size/2} y={size/2} transform={`rotate(90 ${size/2} ${size/2})`} textAnchor="middle" dominantBaseline="central"
        fontSize="22" fontWeight="700" fontFamily="var(--mono)" fill="var(--text)">{pct}%</text>
    </svg>
  );
}

export function DashboardScreen({ data, onDrill }) {
  const alerts = data.kpis.filter((k) => k.icon === "alert");
  const indicators = data.kpis.filter((k) => k.icon !== "alert");
  const maxPct = Math.max(...data.variants.map((v) => v.pct));
  const conformPct = Math.round(data.variants.filter(v => v.conformant).reduce((s, v) => s + v.pct, 0));

  return (
    <div className="dash">
      {alerts.length > 0 && (
        <>
          <div className="dash-section-title"><Icon name="alert" size={15} style={{ color: "var(--crit)" }} />Alertas acionáveis<span className="dst-line" /></div>
          <div className="alert-row">
            {alerts.map((k) => <AlertCard key={k.id} kpi={k} color={data.color} onDrill={onDrill} />)}
          </div>
        </>
      )}

      <div className="dash-section-title"><Icon name="activity" size={15} style={{ color: "var(--accent)" }} />Indicadores-chave<span className="dst-line" /></div>
      <div className="kpi-grid">
        {indicators.map((k) => <KpiCard key={k.id} kpi={k} color={data.color} onDrill={onDrill} />)}
      </div>

      <div className="dash-section-title"><Icon name="layers" size={15} style={{ color: "var(--accent)" }} />Distribuição & conformidade<span className="dst-line" /></div>
      <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr", gap: 14 }}>
        <div className="chart-card">
          <div className="cc-head"><div><div className="cc-title">Distribuição de variantes</div><div className="cc-sub">% de casos por caminho</div></div></div>
          <div className="bars">
            {data.variants.map((v) => {
              const m = TAG_META[v.tag] || TAG_META.other;
              return (
                <div className="bar-col" key={v.id} title={v.name}>
                  <div className="bar-val num">{v.pct}%</div>
                  <div className="bar" style={{ height: (v.pct / maxPct * 92) + "%", background: m.color }} />
                  <div className="bar-label">{String(v.pct).padStart(2, "0")}</div>
                </div>
              );
            })}
          </div>
          <div style={{ display: "flex", gap: 14, marginTop: 12, flexWrap: "wrap" }}>
            {data.variants.slice(0, 5).map((v) => {
              const m = TAG_META[v.tag] || TAG_META.other;
              return <div key={v.id} className="dl-item" style={{ fontSize: 11.5 }}><span className="dl-dot" style={{ background: m.color }} />{v.name}</div>;
            })}
          </div>
        </div>

        <div className="chart-card">
          <div className="cc-head"><div><div className="cc-title">Conformidade do processo</div><div className="cc-sub">aderência ao fluxo padrão</div></div></div>
          <div className="donut-row" style={{ justifyContent: "center", paddingTop: 6 }}>
            <Donut pct={conformPct} color={conformPct >= 85 ? "var(--ok)" : "var(--warn)"} size={132} />
            <div className="donut-legend">
              <div className="dl-item"><span className="dl-dot" style={{ background: conformPct >= 85 ? "var(--ok)" : "var(--warn)" }} />Conforme<span className="dl-val num">{conformPct}%</span></div>
              <div className="dl-item"><span className="dl-dot" style={{ background: "var(--surface-3)", border: "1px solid var(--border-strong)" }} />Desvios<span className="dl-val num">{100 - conformPct}%</span></div>
              <div style={{ fontSize: 11.5, color: "var(--text-3)", marginTop: 6, maxWidth: 150, lineHeight: 1.4 }}>
                {Math.round(data.totalCases * (100 - conformPct) / 100).toLocaleString("pt-BR")} casos seguem caminhos fora do padrão definido.
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
