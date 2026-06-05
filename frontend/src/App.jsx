import { useState, useEffect, useRef } from "react";
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

function useTheme() {
  const [theme, setTheme] = useState(() => localStorage.getItem("pm-theme") || "light");
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("pm-theme", theme);
  }, [theme]);
  return [theme, setTheme];
}

function Toast({ msg }) {
  if (!msg) return null;
  return (
    <div style={{ position: "fixed", bottom: 22, left: "50%", transform: "translateX(-50%)", zIndex: 300,
      background: "var(--text)", color: "var(--surface)", padding: "10px 16px", borderRadius: 9,
      fontSize: 13, fontWeight: 550, boxShadow: "var(--shadow-lg)", display: "flex", alignItems: "center", gap: 9 }}
      className="fade-in">
      <Icon name="check" size={15} strokeWidth={2.4} />{msg}
    </div>
  );
}

export default function App() {
  const [moduleKey, setModuleKey] = useState("p2p");
  const [screen, setScreen] = useState("explorer");
  const [theme, setTheme] = useTheme();
  const [drill, setDrill] = useState(null);
  const [toast, setToast] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const fileRef = useRef(null);

  const flash = (m) => { setToast(m); setTimeout(() => setToast(""), 2200); };
  const openDrill = (key) => setDrill(data?.drill?.[key] || null);

  async function load(key) {
    setLoading(true);
    setError(null);
    try {
      const d = await fetchModule(key);
      setData(d);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(moduleKey); }, [moduleKey]);
  useEffect(() => { setDrill(null); }, [moduleKey, screen]);

  async function onUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    flash(`Processando "${file.name}"…`);
    try {
      await uploadCsv(file);
      await load(moduleKey);
      flash(`"${file.name}" carregado com sucesso`);
    } catch (err) {
      flash(`Erro: ${err.message}`);
    }
    e.target.value = "";
  }

  const alertCount = data?.kpis?.filter((k) => k.icon === "alert").length ?? 0;

  const headInfo = !data ? { title: "Carregando…", sub: "" } : {
    explorer:  { title: "Explorador de Processo",   sub: `Modelo descoberto · ${data.totalCases.toLocaleString("pt-BR")} casos · ${data.avgVariants} variantes` },
    variants:  { title: "Variantes do Processo",    sub: `${data.avgVariants} caminhos distintos do início ao fim` },
    dashboard: { title: "Dashboard de KPIs & Alertas", sub: `Visão financeira — ${data.name}` },
  }[screen];

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark"><Icon name="activity" size={17} strokeWidth={2.2} /></div>
          <div className="brand-name">Fluxo<span>·mining</span></div>
        </div>

        <div className="module-switch">
          <button className={moduleKey === "p2p" ? "active" : ""} onClick={() => setModuleKey("p2p")}>
            <span className="dot" style={{ background: "#4F46E5" }} />P2P
          </button>
          <button className={moduleKey === "o2c" ? "active" : ""} onClick={() => setModuleKey("o2c")}>
            <span className="dot" style={{ background: "#16B3A6" }} />O2C
          </button>
        </div>

        <div className="topbar-spacer" />

        <input ref={fileRef} type="file" accept=".csv" style={{ display: "none" }} onChange={onUpload} />
        <button className="btn" onClick={() => fileRef.current.click()}><Icon name="upload" size={15} />Importar CSV</button>
        <button className="btn primary" onClick={() => { setModuleKey(moduleKey); load(moduleKey); flash("Dataset demo carregado"); }}>
          <Icon name="database" size={15} />Carregar dataset demo
        </button>
        <button className="icon-btn" onClick={() => setTheme(theme === "light" ? "dark" : "light")} title="Alternar tema">
          <Icon name={theme === "light" ? "moon" : "sun"} size={18} />
        </button>
      </header>

      <div className="body">
        <nav className="sidebar">
          <div className="nav-label">Análise</div>
          {SCREENS.map((s) => (
            <button key={s.id} className={"nav-item" + (screen === s.id ? " active" : "")} onClick={() => setScreen(s.id)}>
              <Icon name={s.icon} size={17} className="ni-icon" />{s.label}
              {s.id === "dashboard" && alertCount > 0 && <span className="ni-badge">{alertCount}</span>}
              {s.id === "variants" && data && <span className="ni-badge">{data.avgVariants}</span>}
            </button>
          ))}

          <div className="nav-label" style={{ marginTop: 14 }}>Processo</div>
          {data && (
            <div style={{ padding: "2px 4px" }}>
              {data.kpis.filter(k => k.id === "lead" || k.id === "conf").map(k => (
                <div key={k.id} className="metric-mini" style={{ padding: "5px 6px" }}>
                  <span className="mm-label">{k.label}</span>
                  <span className="mm-val num" style={{ color: k.sev === "warn" ? "var(--warn-text)" : "var(--text)" }}>{k.value}{k.unit ? " " + k.unit : ""}</span>
                </div>
              ))}
            </div>
          )}

          <div className="sidebar-foot">
            <div className="dataset-chip">
              <div className="kpi-ico" style={{ width: 30, height: 30, background: "var(--accent-weak)", color: "var(--accent-text)" }}><Icon name="database" size={15} /></div>
              <div style={{ minWidth: 0 }}>
                <div className="ds-name">demo_{moduleKey}_2026.csv</div>
                {data && <div className="ds-sub">{data.totalCases.toLocaleString("pt-BR")} casos</div>}
              </div>
            </div>
          </div>
        </nav>

        <main className="main">
          <div className="page-head">
            <div>
              <h1 className="page-title">{headInfo.title}
                {data && <span className="badge accent" style={{ fontSize: 11 }}>{data.short}</span>}
              </h1>
              <p className="page-sub">{headInfo.sub}</p>
            </div>
            <div className="page-actions">
              <button className="btn"><Icon name="external" size={15} />Exportar</button>
            </div>
          </div>

          <div className="screen-host">
            {loading && (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", color: "var(--text-3)", fontSize: 14 }}>
                <Icon name="activity" size={20} className="spin" style={{ marginRight: 10 }} />Carregando…
              </div>
            )}
            {error && (
              <div style={{ padding: 40, color: "var(--crit-text)", fontSize: 13 }}>
                <Icon name="alert" size={16} style={{ marginRight: 8 }} />Erro ao carregar: {error}
              </div>
            )}
            {!loading && !error && data && (
              <>
                {screen === "explorer"  && <ExplorerScreen  key={moduleKey} data={data} />}
                {screen === "variants"  && <VariantsScreen  key={moduleKey} data={data} />}
                {screen === "dashboard" && <DashboardScreen key={moduleKey} data={data} onDrill={openDrill} />}
              </>
            )}
          </div>
        </main>
      </div>

      {drill && <DrillDrawer drill={drill} onClose={() => setDrill(null)} />}
      <Toast msg={toast} />
    </div>
  );
}
