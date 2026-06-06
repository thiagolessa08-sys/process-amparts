import { useState, useEffect, useRef, useCallback } from "react";
import { Icon } from "./icons.jsx";
import { ExplorerScreen, DrillDrawer } from "./ScreenExplorer.jsx";
import { VariantsScreen } from "./ScreenVariants.jsx";
import { DashboardScreen } from "./ScreenDashboard.jsx";
import { fetchModule, uploadCsv } from "./api.js";

const SCREENS = [
  { id: "explorer", label: "Explorador", icon: "explorer" },
  { id: "variants", label: "Variantes",  icon: "variants" },
  { id: "dashboard", label: "Dashboard", icon: "dashboard" },
];
const EMPTY_FILTERS = { fornecedores: [], startDate: "", endDate: "" };

function useTheme() {
  const [dark, setDark] = useState(() => localStorage.getItem("pm-theme") === "dark");
  useEffect(() => { localStorage.setItem("pm-theme", dark ? "dark" : "light"); }, [dark]);
  return [dark, setDark];
}

function Toast({ msg }) {
  if (!msg) return null;
  return (
    <div style={{
      position: "fixed", bottom: 22, left: "50%", transform: "translateX(-50%)", zIndex: 300,
      background: "var(--ink)", color: "var(--panel)", padding: "10px 16px", borderRadius: 10,
      fontSize: 13, fontWeight: 600, boxShadow: "var(--shadow-pop)", display: "flex", alignItems: "center", gap: 9,
    }}>
      <Icon name="check" size={15} strokeWidth={2.6} />{msg}
    </div>
  );
}

export default function App() {
  const [moduleKey, setModuleKey] = useState("p2p");
  const [screen, setScreen]   = useState("explorer");
  const [dark, setDark]       = useTheme();
  const [drill, setDrill]     = useState(null);
  const [toast, setToast]     = useState("");
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const fileRef = useRef(null);

  const flash = (m) => { setToast(m); setTimeout(() => setToast(""), 2400); };
  const openDrill = (key) => setDrill(data?.drill?.[key] || null);

  const load = useCallback(async (key, f) => {
    setLoading(true); setError(null);
    try { setData(await fetchModule(key, f)); }
    catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { setFilters(EMPTY_FILTERS); load(moduleKey, EMPTY_FILTERS); }, [moduleKey, load]);
  useEffect(() => { setDrill(null); }, [moduleKey, screen]);

  const onFiltersChange = useCallback((f) => { setFilters(f); load(moduleKey, f); }, [moduleKey, load]);

  async function onUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    flash(`Processando "${file.name}"…`);
    try { await uploadCsv(file); await load(moduleKey, filters); flash(`"${file.name}" carregado`); }
    catch (err) { flash(`Erro: ${err.message}`); }
    e.target.value = "";
  }

  const alertCount = data?.kpis?.filter((k) => k.icon === "alert").length ?? 0;
  const conformPct = data ? Math.round(data.variants.filter(v => v.conformant).reduce((s, v) => s + v.pct, 0)) : 0;
  const leadKpi = data?.kpis?.find(k => k.id === "lead");

  const headInfo = !data ? { title: "Carregando…", sub: null } : {
    explorer:  { title: "Explorador de Processo", sub: <>Modelo descoberto · <b>{data.totalCases.toLocaleString("pt-BR")}</b> casos · <b>{data.avgVariants}</b> variantes</> },
    variants:  { title: "Variantes do Processo",  sub: <><b>{data.avgVariants}</b> caminhos distintos do início ao fim</> },
    dashboard: { title: "Dashboard de KPIs & Alertas", sub: <>Visão financeira — <b>{data.name}</b></> },
  }[screen];

  return (
    <div className={"shell" + (dark ? " dark" : "")}>
      {/* TOPBAR */}
      <header className="topbar">
        <div className="brand">
          <span className="logo"><Icon name="activity" size={17} strokeWidth={2.4} /></span>
          <span className="name">Fluxo<span className="dim">·mining</span></span>
        </div>
        <div className="tabs">
          <button className={moduleKey === "p2p" ? "on" : ""} onClick={() => setModuleKey("p2p")}>
            <span className="pdot" style={{ background: "#5a2fe0" }} />P2P
          </button>
          <button className={moduleKey === "o2c" ? "on" : ""} onClick={() => setModuleKey("o2c")}>
            <span className="pdot" style={{ background: "#16a34a" }} />O2C
          </button>
        </div>
        <span className="spacer" />
        <input ref={fileRef} type="file" accept=".csv" style={{ display: "none" }} onChange={onUpload} />
        <button className="btn" onClick={() => fileRef.current.click()}><Icon name="upload" size={15} />Importar CSV</button>
        <button className="btn primary" onClick={() => { load(moduleKey, EMPTY_FILTERS); setFilters(EMPTY_FILTERS); flash("Dataset demo carregado"); }}>
          <Icon name="database" size={15} />Carregar dataset demo
        </button>
        <button className="icon-btn" onClick={() => setDark(d => !d)} title="Alternar tema">
          <Icon name={dark ? "sun" : "moon"} size={17} />
        </button>
      </header>

      <div className="main-row">
        {/* RAIL */}
        <nav className="rail">
          <div className="rail-eyebrow">Análise</div>
          {SCREENS.map((s) => (
            <div key={s.id} className={"nav-item" + (screen === s.id ? " on" : "")} onClick={() => setScreen(s.id)}>
              <Icon name={s.icon} size={17} />{s.label}
              {s.id === "variants" && data && <span className="nbadge">{data.avgVariants}</span>}
              {s.id === "dashboard" && alertCount > 0 && <span className="nbadge">{alertCount}</span>}
            </div>
          ))}
          <div className="rail-eyebrow">Processo</div>
          <div className="metric"><span className="k">Lead time médio</span><span className="v good">{leadKpi ? `${leadKpi.value} ${leadKpi.unit || ""}` : "—"}</span></div>
          <div className="metric"><span className="k">Conformidade do processo</span><span className="v">{conformPct}%</span></div>
          <div className="rail-spacer" />
          <div className="file-card">
            <span className="fi"><Icon name="database" size={16} /></span>
            <div>
              <div className="fn">demo_{moduleKey}_2026.csv</div>
              <div className="fs">{data ? `${data.totalCases.toLocaleString("pt-BR")} casos` : "—"}</div>
            </div>
          </div>
        </nav>

        {/* APP */}
        <div className="app">
          <header className="header">
            <h1>{headInfo.title}</h1>
            {data && <span className="badge">{data.short}</span>}
            {headInfo.sub && <span className="subtitle">{headInfo.sub}</span>}
            <span className="spacer" />
            <button className="btn"><Icon name="external" size={15} />Exportar</button>
          </header>

          {loading && (
            <div style={{ display: "grid", placeItems: "center", color: "var(--muted)", fontSize: 14 }}>
              <span><Icon name="activity" size={18} className="spin" style={{ marginRight: 8, verticalAlign: -3 }} />Carregando…</span>
            </div>
          )}
          {error && !loading && (
            <div style={{ padding: 40, color: "var(--crit)", fontSize: 13 }}>
              <Icon name="alert" size={16} style={{ marginRight: 8, verticalAlign: -3 }} />Erro ao carregar: {error}
            </div>
          )}
          {!loading && !error && data && (
            <>
              {screen === "explorer" && <ExplorerScreen key={moduleKey} data={data} filters={filters} onFiltersChange={onFiltersChange} />}
              {screen === "variants" && <div className="screen-fill"><VariantsScreen key={moduleKey} data={data} /></div>}
              {screen === "dashboard" && <div className="screen-fill" style={{ overflowY: "auto" }}><DashboardScreen key={moduleKey} data={data} onDrill={openDrill} /></div>}
            </>
          )}
        </div>
      </div>

      {drill && <DrillDrawer drill={drill} onClose={() => setDrill(null)} />}
      <Toast msg={toast} />
    </div>
  );
}
