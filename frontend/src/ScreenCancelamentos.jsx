import { Icon } from "./icons.jsx";

const fmtPct = (n) => (Number(n) || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " %";
const fmtMoney = (n) => (Number(n) || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
const fmtInt = (n) => (Number(n) || 0).toLocaleString("pt-BR");

const STAGE_COLOR = { "Orçamento": "#0e9f93", "Pedido": "#e0820e", "Fatura": "#e5484d", "Pagamento": "#7b54ee", "Outro": "#9aa0b4" };

function Kpi({ icon, label, value, sub, tone }) {
  return (
    <div className={"cnc-kpi" + (tone ? " " + tone : "")}>
      <span className="cnc-kpi-ic"><Icon name={icon} size={19} /></span>
      <div className="cnc-kpi-txt">
        <div className="cnc-kpi-label">{label}</div>
        <div className="cnc-kpi-value">{value}</div>
        {sub && <div className="cnc-kpi-sub">{sub}</div>}
      </div>
    </div>
  );
}

function Panel({ title, sub, icon, children, meta }) {
  return (
    <div className="panel cnc-panel">
      <div className="panel-head">
        {icon && <span className="pi"><Icon name={icon} size={15} /></span>}
        <span className="pt">{title}</span>
        {sub && <span className="cnc-psub">{sub}</span>}
        {meta && <><span className="ph-spacer" /><span className="ph-meta">{meta}</span></>}
      </div>
      <div className="panel-body cnc-body">{children}</div>
    </div>
  );
}

function Bars({ items, labelKey = "nome", byKey = "valor", fmt = fmtMoney, sub, color = "#7b54ee", colorBy }) {
  if (!items?.length) return <div className="cnc-empty">Sem dados</div>;
  const max = Math.max(...items.map((i) => Math.abs(Number(i[byKey]) || 0)), 1);
  return (
    <div className="cnc-bars">
      {items.map((it, i) => (
        <div className="cnc-barrow" key={i}>
          <span className="cnc-barlab" title={it[labelKey]}>{it[labelKey]}</span>
          <span className="cnc-bartrack">
            <i style={{ width: (100 * Math.abs(Number(it[byKey]) || 0) / max) + "%", background: colorBy ? colorBy(it) : color }} />
          </span>
          <span className="cnc-barval">{fmt(it[byKey])}{sub && <em>{sub(it)}</em>}</span>
        </div>
      ))}
    </div>
  );
}

export function CancelamentosScreen({ data }) {
  const c = data.cancelamentos || {};
  const dim = data.dimension || "Cliente";
  const meses = c.porMes || [];
  const maxMes = Math.max(...meses.map((m) => m.qtd || 0), 1);

  return (
    <div className="cnc">
      <div className="cnc-kpis">
        <Kpi icon="loop" label="Taxa de cancelamento" value={fmtPct(c.pctCancel)} sub={`${fmtInt(c.casosCancelados)} casos cancelados`} tone="red" />
        <Kpi icon="dollar" label="Valor cancelado" value={fmtMoney(c.valorCancelado)} sub={`${fmtInt(c.numCancel)} cancelamentos`} />
        <Kpi icon="alert" label="Valor perdido (pós-fatura)" value={fmtMoney(c.valorPerdido)} sub="cancelado depois de faturar" tone="red" />
        <Kpi icon="clock" label="Tempo médio até cancelar" value={`${(Number(c.tempoMedioDias) || 0).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} d`} sub="do início ao cancelamento" />
      </div>

      <div className="cnc-grid2">
        <Panel title="Onde no fluxo cancela" sub="por etapa — barra pelo valor" icon="variants">
          <Bars items={c.porEtapa || []} labelKey="etapa" byKey="valor" fmt={fmtMoney}
            colorBy={(it) => STAGE_COLOR[it.etapa] || "#7b54ee"}
            sub={(it) => ` · ${fmtInt(it.casos)} casos`} />
        </Panel>
        <Panel title="Por tipo de cancelamento" icon="loop">
          <Bars items={c.porTipo || []} labelKey="tipo" byKey="casos" fmt={fmtInt} color="#e5484d"
            sub={(it) => ` · ${fmtMoney(it.valor)}`} />
        </Panel>
      </div>

      <Panel title="Evolução por mês" sub="quantidade de cancelamentos" icon="activity">
        <div className="cnc-months">
          {meses.length === 0 && <div className="cnc-empty">Sem dados</div>}
          {meses.map((m, i) => (
            <div className="cnc-mcol" key={i} title={`${m.mes}: ${fmtInt(m.qtd)}`}>
              <span className="cnc-mval">{fmtInt(m.qtd)}</span>
              <span className="cnc-mbarwrap"><i className="cnc-mbar" style={{ height: Math.max(3, 100 * m.qtd / maxMes) + "%" }} /></span>
              <span className="cnc-mlab">{m.mes?.slice(5)}/{m.mes?.slice(2, 4)}</span>
            </div>
          ))}
        </div>
      </Panel>

      <div className="cnc-grid2">
        <Panel title={`Top ${dim.toLowerCase()} que mais cancela`} sub="por nº de casos cancelados" icon="variants" meta={dim}>
          <Bars items={c.topClientes || []} labelKey="nome" byKey="casos" fmt={fmtInt} color="#e5484d"
            sub={(it) => ` · ${fmtMoney(it.valor)}`} />
        </Panel>
        <Panel title="Top produtos cancelados" sub="por nº de casos" icon="layers" meta="Produto">
          <Bars items={c.topProdutos || []} labelKey="nome" byKey="casos" fmt={fmtInt} color="#e0820e"
            sub={(it) => ` · ${fmtMoney(it.valor)}`} />
        </Panel>
      </div>
    </div>
  );
}
