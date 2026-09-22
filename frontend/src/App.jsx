import { useState, useEffect, useRef, useCallback } from "react";
import { Icon } from "./icons.jsx";
import { ExplorerScreen, DrillDrawer } from "./ScreenExplorer.jsx";
import { VariantsScreen } from "./ScreenVariants.jsx";
import { DashboardScreen } from "./ScreenDashboard.jsx";
import { OverviewScreen } from "./ScreenOverview.jsx";
import { ReworkScreen } from "./ScreenRework.jsx";
import { CancelamentosScreen } from "./ScreenCancelamentos.jsx";
import { CaseExplorerScreen } from "./ScreenCaseExplorer.jsx";
import { DetailsScreen } from "./ScreenDetails.jsx";
import { AssistantScreen } from "./ScreenAssistant.jsx";
import { TwoMatchScreen } from "./ScreenTwoMatch.jsx";
import { UserProdScreen } from "./ScreenUserProd.jsx";
import { LoginScreen, readAuth, clearAuth } from "./ScreenLogin.jsx";
import { fetchModule, fetchModuleStatus, uploadCsv, refreshModule, setAuthToken } from "./api.js";

const SCREENS = [
  { id: "explorer", label: "Explorador", icon: "explorer" },
  { id: "variants", label: "Variantes",  icon: "variants" },
  { id: "dashboard", label: "Dashboard", icon: "activity" },
  { id: "rework", label: "Retrabalho", icon: "loop" },
  { id: "cancel", label: "Cancelamentos", icon: "close" },
  { id: "twomatch", label: "2 Way Match", icon: "shield" },
  { id: "userprod", label: "Produtividade", icon: "variants" },
  { id: "overview", label: "Visão Geral", icon: "dashboard" },
  { id: "cases", label: "Case Explorer", icon: "search" },
  { id: "details", label: "Detalhes", icon: "layers" },
  { id: "assistant", label: "Assistente IA", icon: "bolt" },
];
const EMPTY_FILTERS = { fornecedores: [], startDate: "", endDate: "", ano: "", mes: "", dias: [], produto: "", activity: null, variantKeys: [], variantMode: "include" };

const MODULES = [
  { key: "amparts", label: "AM Parts-O2C", color: "#d4145a" },
];

const ACT_MODE_LABEL = { with: "Com", without: "Sem", start: "Inicia em", end: "Termina em" };

/* Módulo a abrir: o 1º do usuário que AINDA existe em MODULES.
   Sem o cruzamento, uma sessão salva antes de um módulo ser removido continua
   mandando a tela pedir /api/modules/<removido>, que responde 403 "Sem acesso a
   este módulo" — com a barra exibindo só o módulo certo, o que esconde a causa.
   Nunca leia `modules[0]` do localStorage direto. */
function firstModule(user) {
  const permitidos = user?.modules || [];
  const valido = MODULES.find((m) => permitidos.includes(m.key));
  return (valido || MODULES[0]).key;
}

/* mini-gráfico do KPI */
function Spark({ data }) {
  if (!data?.length) return null;
  const w = 56, h = 32, min = Math.min(...data), max = Math.max(...data), rng = max - min || 1;
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / rng) * (h - 5) - 2.5;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return (
    <svg className="kpi-spark" viewBox={`0 0 ${w} ${h}`} fill="none" preserveAspectRatio="none">
      <polyline points={pts} style={{ stroke: "var(--kpi-line)" }} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/* dropdown de múltiplos dias (checkboxes) — filtro "Dia do <periodo>" */
function DayMultiSelect({ days, value, onChange, periodo = "Pedido" }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);
  const toggle = (d) => {
    const set = new Set(value);
    set.has(d) ? set.delete(d) : set.add(d);
    onChange([...set].sort((a, b) => a - b));
  };
  const label = value.length === 0 ? `Dia do ${periodo}`
    : value.length === 1 ? `Dia ${value[0]}` : `${value.length} dias`;
  return (
    <div className={"selectwrap daysel" + (value.length ? " active" : "")} ref={ref}>
      <span className="lead"><Icon name="calendar" size={14} /></span>
      <button type="button" className="daysel-btn" onClick={() => setOpen((o) => !o)}>{label}</button>
      <span className="caret"><Icon name="chevronD" size={14} /></span>
      {open && (
        <div className="daysel-pop">
          <div className="daysel-head">
            <span>{value.length} selecionado(s)</span>
            {value.length > 0 && <button type="button" onClick={() => onChange([])}>Limpar</button>}
          </div>
          <div className="daysel-grid">
            {days.map((d) => (
              <label key={d} className={"daysel-item" + (value.includes(d) ? " on" : "")}>
                <input type="checkbox" checked={value.includes(d)} onChange={() => toggle(d)} />{d}
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* uma faixa: título + filtros + KPIs + exportar */
function Ribbon({ data, headInfo, filters, setFilter }) {
  const f = data.filters || {};
  // o backend diz se o período recorta pela data do pedido ou pelo início do
  // caso — o rótulo tem de acompanhar, senão a tela promete o filtro errado
  const per = f.periodoLabel || "Pedido";
  const fornVal = filters.fornecedores?.[0] ?? "";
  return (
    <header className="ribbon">
      <div className="title-block">
        <div className="title-row">
          <h1>{headInfo.title}</h1>
        </div>
        {headInfo.sub && <span className="subtitle">{headInfo.sub}</span>}
      </div>
      <div className="ribbon-rule" />

      <div className="filter-col">
        <div className="filter-group">
          <div className="selectwrap">
            <span className="lead"><Icon name="calendar" size={14} /></span>
            <select value={filters.ano} onChange={(e) => setFilter({ ano: e.target.value ? Number(e.target.value) : "" })}>
              <option value="">Ano do {per}</option>
              {(f.years || []).map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
            <span className="caret"><Icon name="chevronD" size={14} /></span>
          </div>
          <div className="selectwrap">
            <span className="lead"><Icon name="calendar" size={14} /></span>
            <select value={filters.mes} onChange={(e) => setFilter({ mes: e.target.value ? Number(e.target.value) : "" })}>
              <option value="">Mês do {per}</option>
              {(f.months || []).map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
            <span className="caret"><Icon name="chevronD" size={14} /></span>
          </div>
          {(f.dias?.length > 0) && (
            <DayMultiSelect days={f.dias} value={filters.dias || []} onChange={(dias) => setFilter({ dias })} periodo={per} />
          )}
          <div className="selectwrap supplier">
            <span className="lead"><Icon name="truck" size={14} /></span>
            <select value={fornVal} onChange={(e) => setFilter({ fornecedores: e.target.value ? [e.target.value] : [] })}>
              <option value="">{data.dimension || f.dimLabel || "Fornecedor"}</option>
              {(f.dims || []).map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
            <span className="caret"><Icon name="chevronD" size={14} /></span>
          </div>
          {(f.produtos?.length > 0) && (
            <div className="selectwrap supplier">
              <span className="lead"><Icon name="layers" size={14} /></span>
              <select value={filters.produto ?? ""} onChange={(e) => setFilter({ produto: e.target.value || "" })}>
                <option value="">Produto</option>
                {(f.produtos || []).map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
              <span className="caret"><Icon name="chevronD" size={14} /></span>
            </div>
          )}
        </div>

        {filters.activity && (
          <button className="act-chip" onClick={() => setFilter({ activity: null })} title="Remover filtro de atividade">
            <Icon name="filter" size={13} />
            {ACT_MODE_LABEL[filters.activity.mode]}: <b>{filters.activity.label}</b>
            <Icon name="close" size={13} />
          </button>
        )}
        {filters.variantKeys?.length > 0 && (
          <button className="act-chip" onClick={() => setFilter({ variantKeys: [], variantMode: "include" })} title="Remover filtro de variante">
            <Icon name="variants" size={13} />
            {filters.variantMode === "exclude" ? "Variantes excluídas" : "Filtrado por variante"}: <b>{filters.variantKeys.length}</b>
            <Icon name="close" size={13} />
          </button>
        )}
      </div>

      <div className="ribbon-spacer" />
      <div className="ribbon-rule" />

      <div className="ribbon-kpis">
        {(data.headlineKpis || []).map((k) => (
          <div key={k.id} className={"kpi " + k.accent}>
            <div className="kpi-top">
              <span className="kpi-chip"><Icon name={k.icon} size={15} /></span>
              <span className="kpi-label">{k.label}</span>
              {k.delta && (
                <span className={"kpi-delta" + (k.accent === "itens" ? " muted" : "")}>
                  <Icon name="trendUp" size={12} />{k.delta}
                </span>
              )}
            </div>
            <div className="kpi-bottom">
              <div className="kpi-value">{k.value}{k.unit && <span className="unit"> {k.unit}</span>}</div>
              <Spark data={k.spark} />
            </div>
          </div>
        ))}
      </div>

    </header>
  );
}

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
  const [auth, setAuth]       = useState(() => readAuth());
  const [moduleKey, setModuleKey] = useState(() => firstModule(readAuth()));
  const [screen, setScreen]   = useState(() => {
    const s = readAuth()?.screens;
    return s?.length ? s[0] : "explorer";   // usuário restrito cai na 1ª tela liberada
  });
  const [dark, setDark]       = useTheme();
  const [drill, setDrill]     = useState(null);
  const [toast, setToast]     = useState("");
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  const [polling, setPolling] = useState(false);   // fonte real carregando
  const [progress, setProgress] = useState(0);
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const fileRef = useRef(null);
  const yearDefaulted = useRef(null);   // controla o auto-set do último ano por módulo

  const flash = (m) => { setToast(m); setTimeout(() => setToast(""), 2400); };
  const openDrill = (key) => setDrill(data?.drill?.[key] || null);

  // usuário só-chat (screens = ["assistant"]): vê apenas o chat e NÃO carrega o
  // payload pesado do módulo (o chat só precisa da chave do módulo)
  const chatOnly = auth?.screens?.length === 1 && auth.screens[0] === "assistant";

  const load = useCallback(async (key, f) => {
    setLoading(true); setError(null);
    try {
      setData(await fetchModule(key, f));
      setPolling(false);
    } catch (e) {
      if (e.status === 503) { setData(null); setProgress((p) => p || 0); setPolling(true); }
      else { setPolling(false); setError(e.message); }
    } finally { setLoading(false); }
  }, []);

  // enquanto a fonte real carrega: faz polling do status e atualiza sozinho ao concluir
  useEffect(() => {
    if (!polling) return;
    let alive = true;
    const tick = async () => {
      try {
        const s = await fetchModuleStatus(moduleKey);
        if (!alive) return;
        setProgress(s.progress || 0);
        if (s.status === "ready") { setPolling(false); load(moduleKey, filters); }
        else if (s.status === "error") { setPolling(false); setError(s.error || "Falha ao carregar do banco"); }
      } catch { /* mantém o polling */ }
    };
    tick();
    const id = setInterval(tick, 2000);
    return () => { alive = false; clearInterval(id); };
  }, [polling, moduleKey, filters, load]);

  useEffect(() => {
    if (!auth?.token) return;   // só carrega depois de autenticado (evita 401 no mount)
    if (chatOnly) { setLoading(false); return; }   // só-chat: sem carga do payload
    // a marca vive no estado (não só nesta chamada) para sobreviver ao retry do
    // polling em 503, que relança `load` com `filters`
    const inicial = { ...EMPTY_FILTERS, defaultPeriod: true };
    yearDefaulted.current = null; setFilters(inicial); load(moduleKey, inicial);
  }, [moduleKey, load, auth, chatOnly]);
  useEffect(() => { setDrill(null); }, [moduleKey, screen]);

  // telas liberadas p/ o usuário (allow-list opcional; vazio = todas). Se a tela
  // atual não estiver na lista, cai na 1ª liberada (ex.: usuário só-chat).
  const allowedScreens = (auth?.screens?.length)
    ? SCREENS.filter((s) => auth.screens.includes(s.id))
    : SCREENS;
  useEffect(() => {
    if (allowedScreens.length && !allowedScreens.some((s) => s.id === screen)) {
      setScreen(allowedScreens[0].id);
    }
  }, [allowedScreens, screen]);

  const onFiltersChange = useCallback((f) => { setFilters(f); load(moduleKey, f); }, [moduleKey, load]);
  const setFilter = useCallback((patch) => { onFiltersChange({ ...filters, ...patch }); }, [filters, onFiltersChange]);

  // ano sempre no último: ao carregar um módulo, pré-seleciona o ano mais
  // recente disponível (uma vez por módulo; o usuário pode trocar/limpar depois)
  useEffect(() => {
    if (!data || data.key !== moduleKey || yearDefaulted.current === moduleKey) return;
    const years = data.filters?.years || [];
    yearDefaulted.current = moduleKey;
    // a marca sai aqui: daqui em diante, limpar o ano volta a pedir o log inteiro
    const semMarca = { ...filters, defaultPeriod: false };
    if (years.length && !filters.ano) onFiltersChange({ ...semMarca, ano: Math.max(...years) });
    else setFilters(semMarca);
  }, [data, moduleKey, filters, onFiltersChange]);

  async function onRefresh() {
    flash("Recarregando dados do banco… (~1–2 min). Recarregue em instantes.");
    try {
      await refreshModule(moduleKey);
      setTimeout(() => load(moduleKey, filters), 1500);
    } catch (err) { flash(`Erro: ${err.message}`); }
  }

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

  const headInfo = !data ? { title: chatOnly ? "Assistente IA" : "Carregando…", sub: null } : {
    overview:  { title: "Visão Geral", sub: <>Dashboard · <b>{data.totalCases.toLocaleString("pt-BR")}</b> casos · <b>4</b> indicadores</> },
    explorer:  { title: "Explorador de Processo", sub: <>Modelo descoberto · <b>{data.totalCases.toLocaleString("pt-BR")}</b> casos · <b>{data.avgVariants}</b> variantes</> },
    variants:  { title: "Variantes do Processo",  sub: <><b>{data.avgVariants}</b> caminhos distintos do início ao fim</> },
    dashboard: { title: "Dashboard de KPIs & Alertas", sub: <>Visão financeira — <b>{data.name}</b></> },
    rework:    { title: "Análise de Retrabalho", sub: <><b>{data.rework?.pctComRetrabalho ?? 0}%</b> dos casos com retrabalho</> },
    cancel:    { title: "Análise de Cancelamentos", sub: <><b>{data.cancelamentos?.pctCancel ?? 0}%</b> dos casos com cancelamento</> },
    twomatch:  { title: "2 Way Match", sub: <>Pedido × Faturamento</> },
    userprod:  { title: "Produtividade de Usuário", sub: <>Atividade por usuário (recurso)</> },
    cases:     { title: "Case Explorer", sub: <>Explore casos individuais — <b>{data.totalCases.toLocaleString("pt-BR")}</b> casos</> },
    details:   { title: "Detalhes", sub: <>Pedidos por item (orçamento · pedido · nota fiscal)</> },
    assistant: { title: "Assistente IA", sub: <>Pergunte sobre o processo em linguagem natural</> },
  }[screen];

  if (!auth || !auth.token) {   // sessão antiga sem token → força re-login
    return (
      <LoginScreen
        dark={dark}
        onToggleTheme={() => setDark((d) => !d)}
        onLogin={(user) => {
          setAuth(user);
          setModuleKey(firstModule(user));
          setScreen(user.screens?.length ? user.screens[0] : "explorer");
        }}
      />
    );
  }

  return (
    <div className={"shell" + (dark ? " dark" : "")}>
      {/* TOPBAR */}
      <header className="topbar">
        <div className="brand">
          <span className="logo"><Icon name="activity" size={17} strokeWidth={2.4} /></span>
          <span className="name">Process<span className="dim"> Intelligence</span></span>
        </div>
        <div className="tabs">
          {MODULES.filter((m) => (auth.modules || []).includes(m.key)).map((m) => (
            <button key={m.key} className={moduleKey === m.key ? "on" : ""} onClick={() => setModuleKey(m.key)}>
              <span className="pdot" style={{ background: m.color }} />{m.label}
            </button>
          ))}
        </div>
        <span className="spacer" />
        <input ref={fileRef} type="file" accept=".csv" style={{ display: "none" }} onChange={onUpload} />
        {!chatOnly && (
          <button className="btn" onClick={onRefresh} title="Recarregar os dados do banco">
            <Icon name="loop" size={15} />Atualizar dados
          </button>
        )}
        <button className="icon-btn" onClick={() => setDark(d => !d)} title="Alternar tema">
          <Icon name={dark ? "sun" : "moon"} size={17} />
        </button>
        <div className="user-chip" title={auth.email}>
          <span className="user-avatar">{(auth.name || auth.email || "?").charAt(0).toUpperCase()}</span>
          <span className="user-name">{auth.name}</span>
        </div>
        <button
          className="icon-btn"
          onClick={() => { setAuthToken(""); clearAuth(); setAuth(null); }}
          title="Sair"
        >
          <Icon name="logout" size={17} />
        </button>
      </header>

      <div className="main-row">
        {/* RAIL */}
        <nav className="rail">
          <div className="rail-eyebrow">Análise</div>
          {allowedScreens.map((s) => (
            <div key={s.id} className={"nav-item" + (screen === s.id ? " on" : "")} onClick={() => setScreen(s.id)}>
              <Icon name={s.icon} size={17} />{s.label}
              {s.id === "variants" && data && <span className="nbadge">{data.avgVariants}</span>}
              {s.id === "dashboard" && alertCount > 0 && <span className="nbadge">{alertCount}</span>}
            </div>
          ))}
          {!chatOnly && <>
            <div className="rail-eyebrow">Processo</div>
            <div className="metric"><span className="k">Lead time médio</span><span className="v good">{leadKpi ? `${leadKpi.value} ${leadKpi.unit || ""}` : "—"}</span></div>
            <div className="metric"><span className="k">Conformidade do processo</span><span className="v">{conformPct}%</span></div>
            <div className="rail-spacer" />
            <div className="file-card">
              <span className="fi"><Icon name="database" size={16} /></span>
              <div>
                <div className="fn">{data?.short || "AM Parts-O2C"} · arquivo</div>
                <div className="fs">{data ? `${data.totalCases.toLocaleString("pt-BR")} casos` : "—"}</div>
              </div>
            </div>
          </>}
        </nav>

        {/* APP */}
        <div className="app">
          {data && !chatOnly ? (
            <Ribbon data={data} headInfo={headInfo} filters={filters} setFilter={setFilter} />
          ) : (
            <header className="ribbon">
              <div className="title-block"><div className="title-row"><h1>{headInfo.title}</h1></div></div>
            </header>
          )}

          {chatOnly && (
            <div className="screen-fill"><AssistantScreen key={moduleKey} data={{ key: moduleKey }} filters={filters} /></div>
          )}
          {!chatOnly && polling && (
            <div className="real-loading">
              <div className="rl-spin"><Icon name="activity" size={30} className="spin" /></div>
              <div className="rl-title">Carregando dados do banco…</div>
              <div className="rl-sub">Pode levar ~1–2 min. A tela atualiza sozinha ao concluir.</div>
              <div className="rl-bar"><i style={{ width: `${Math.max(4, progress)}%` }} /></div>
              <div className="rl-pct mono">{Math.round(progress)}%</div>
            </div>
          )}
          {!chatOnly && loading && !polling && (
            <div style={{ display: "grid", placeItems: "center", color: "var(--muted)", fontSize: 14 }}>
              <span><Icon name="activity" size={18} className="spin" style={{ marginRight: 8, verticalAlign: -3 }} />Carregando…</span>
            </div>
          )}
          {!chatOnly && error && !loading && !polling && (
            <div style={{ padding: 40, color: "var(--crit)", fontSize: 13 }}>
              <Icon name="alert" size={16} style={{ marginRight: 8, verticalAlign: -3 }} />Erro ao carregar: {error}
            </div>
          )}
          {!loading && !error && !polling && data && (
            <>
              {screen === "overview" && <div className="screen-fill" style={{ overflowY: "auto" }}><OverviewScreen key={moduleKey} data={data} /></div>}
              {screen === "rework" && <div className="screen-fill"><ReworkScreen key={moduleKey} data={data} /></div>}
              {screen === "cancel" && <div className="screen-fill" style={{ overflowY: "auto" }}><CancelamentosScreen key={moduleKey} data={data} /></div>}
              {screen === "twomatch" && <div className="screen-fill" style={{ overflowY: "auto" }}><TwoMatchScreen key={moduleKey} data={data} /></div>}
              {screen === "userprod" && <div className="screen-fill" style={{ overflowY: "auto" }}><UserProdScreen key={moduleKey} data={data} filters={filters} /></div>}
              {screen === "cases" && <div className="screen-fill"><CaseExplorerScreen key={moduleKey} data={data} filters={filters} /></div>}
              {screen === "details" && <div className="screen-fill"><DetailsScreen key={moduleKey} data={data} filters={filters} /></div>}
              {screen === "assistant" && <div className="screen-fill"><AssistantScreen key={moduleKey} data={data} filters={filters} /></div>}
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
