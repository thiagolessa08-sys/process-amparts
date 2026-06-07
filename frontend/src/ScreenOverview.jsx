import { Icon } from "./icons.jsx";

/* ───────── formatadores compactos ───────── */
function fmtCompact(n) {
  n = Number(n) || 0;
  if (n >= 1e9) return (n / 1e9).toFixed(2).replace(".", ",") + "B";
  if (n >= 1e6) return (n / 1e6).toFixed(1).replace(".", ",") + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1).replace(".", ",") + "K";
  return String(Math.round(n));
}
const fmtBRL = (n) => fmtCompact(n) + " R$";
const fmtInt = (n) => (Number(n) || 0).toLocaleString("pt-BR");

/* paleta verde (do mais escuro ao mais claro) + cinza p/ "Outros" */
const GREENS = ["#166534", "#15803d", "#16a34a", "#22c55e", "#4ade80",
                "#86efac", "#bbf7d0", "#0e7a5f", "#3aa17e", "#7fc8ad"];
const GREY = "#a9add0";

/* ───────── Donut (TOP clientes) ───────── */
function Donut({ data, size = 150, sw = 22 }) {
  const r = (size - sw) / 2, c = 2 * Math.PI * r;
  let acc = 0;
  return (
    <svg className="clients-donut" width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <g transform={`rotate(-90 ${size / 2} ${size / 2})`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--line-2)" strokeWidth={sw} />
        {data.map((d, i) => {
          const len = c * (d.pct / 100);
          const el = (
            <circle key={i} cx={size / 2} cy={size / 2} r={r} fill="none"
              stroke={d.color} strokeWidth={sw}
              strokeDasharray={`${len} ${c - len}`} strokeDashoffset={-acc}>
              <title>{d.nome}: {d.pct}%</title>
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
function ProdutosPanel({ rows = [] }) {
  const max = Math.max(1, ...rows.map((r) => r.itens));
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => fmtCompact(t * max));
  return (
    <div className="panel">
      <div className="panel-head">
        <span className="pi"><Icon name="layers" size={15} /></span>
        <span className="pt">TOP 10 Produtos</span>
        <span className="ph-spacer" />
        <span className="ph-meta">por qtd itens</span>
      </div>
      <div className="panel-body">
        <div className="dotplot">
          {rows.map((r) => (
            <div className="dprow" key={r.produto}>
              <div className="dpl">{r.produto}</div>
              <div className="dptrack">
                <span className="dpdot" style={{ left: (r.itens / max) * 100 + "%" }} title={`${r.produto}: ${fmtInt(r.itens)} itens`} />
              </div>
            </div>
          ))}
        </div>
        <div className="dpaxis">
          <span />
          <div className="dpticks">{ticks.map((t, i) => <span key={i}>{t}</span>)}</div>
        </div>
      </div>
    </div>
  );
}

function CanceladosPanel({ rows = [] }) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => Math.round(t * max));
  return (
    <div className="panel">
      <div className="panel-head">
        <span className="pi"><Icon name="loop" size={15} /></span>
        <span className="pt">Pedidos Cancelados por Mês</span>
        <span className="ph-spacer" />
        <span className="ph-meta">{rows.length} meses</span>
      </div>
      <div className="panel-body">
        <div className="hbars">
          {rows.map((r) => (
            <div className="hbrow" key={r.mes}>
              <div className="hbl">{r.mes}</div>
              <div className="hbtrack"><div className="hbfill" style={{ width: (r.count / max) * 100 + "%" }} /></div>
              <div className="hbv">{r.count}</div>
            </div>
          ))}
        </div>
        <div className="hbaxis">
          <span />
          <div className="hbticks">{ticks.map((t, i) => <span key={i}>{t}</span>)}</div>
          <span />
        </div>
      </div>
    </div>
  );
}

function ClientesPanel({ rows = [], dim }) {
  const data = rows.map((r, i) => ({
    ...r,
    color: r.nome === "Outros" ? GREY : GREENS[i % GREENS.length],
  }));
  return (
    <div className="panel">
      <div className="panel-head">
        <span className="pi"><Icon name="variants" size={15} /></span>
        <span className="pt">TOP 10 {dim}s</span>
        <span className="ph-spacer" />
        <span className="ph-meta">% do valor</span>
      </div>
      <div className="panel-body">
        <div className="clients">
          <Donut data={data} />
          <div className="clients-legend">
            {data.map((d) => (
              <div className={"lchip" + (d.nome === "Outros" ? " more" : "")} key={d.nome}>
                <span className="sw" style={{ background: d.color }} />
                <span className="lc">{d.nome}</span>
                <span className="lp">{d.pct.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function NfPanel({ rows = [], dim }) {
  return (
    <div className="panel">
      <div className="panel-head">
        <span className="pi"><Icon name="dashboard" size={15} /></span>
        <span className="pt">Pedidos × Nota Fiscal</span>
        <span className="ph-spacer" />
        <span className="ph-meta">Top {dim.toLowerCase()}s</span>
      </div>
      <div className="panel-body">
        <div className="nf-wrap">
          <table className="nf-table">
            <thead>
              <tr>
                <th>{dim}</th><th>Pedido</th><th>Qtde unid.</th><th>Itens ped.</th>
                <th>Total pedido</th><th>Fatura</th><th>Itens fat.</th><th>Total fatura</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.entidade}>
                  <td>{r.entidade}</td>
                  <td>{fmtInt(r.pedidos)}</td>
                  <td>{fmtCompact(r.qtdUnid)}</td>
                  <td>{fmtInt(r.itensPed)}</td>
                  <td className="accent">{fmtBRL(r.totalPedido)}</td>
                  <td>{fmtInt(r.faturas)}</td>
                  <td>{fmtInt(r.itensFat)}</td>
                  <td className="accent">{fmtBRL(r.totalFatura)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export function OverviewScreen({ data }) {
  const ov = data.overview || {};
  const dim = data.filters?.dimLabel || data.dimension || "Cliente";
  return (
    <div className="overview">
      <div className="ov-grid">
        <ProdutosPanel rows={ov.topProdutos} />
        <CanceladosPanel rows={ov.canceladosPorMes} />
        <ClientesPanel rows={ov.topClientes} dim={dim} />
        <NfPanel rows={ov.pedidosNf} dim={dim} />
      </div>
    </div>
  );
}
