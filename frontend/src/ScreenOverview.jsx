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

/* cinza p/ a fatia "Outros" */
const GREY = "#a9add0";

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
              <div className="dpl" title={r.produto}>{r.produto}</div>
              <div className="dpbar">
                <div className="dptrack">
                  <div className="dpfill" style={{ width: (r.itens / max) * 100 + "%" }} title={`${r.produto}: ${fmtInt(r.itens)} itens`} />
                </div>
                <div className="dpv">{fmtInt(r.itens)}</div>
              </div>
            </div>
          ))}
        </div>
        <div className="dpaxis">
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
  const max = Math.max(0.001, ...rows.map((r) => r.pct));
  const fmtPct = (p) => p.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + "%";
  return (
    <div className="panel">
      <div className="panel-head">
        <span className="pi"><Icon name="variants" size={15} /></span>
        <span className="pt">TOP 10 {dim}s</span>
        <span className="ph-spacer" />
        <span className="ph-meta">% do valor</span>
      </div>
      <div className="panel-body">
        <div className="dotplot green">
          {rows.map((r) => (
            <div className="dprow" key={r.nome}>
              <div className="dpl" title={r.nome}>{r.nome}</div>
              <div className="dpbar">
                <div className="dptrack">
                  <div className="dpfill" style={{ width: (r.pct / max) * 100 + "%", ...(r.nome === "Outros" ? { background: GREY } : {}) }} title={`${r.nome}: ${fmtPct(r.pct)}`} />
                </div>
                <div className="dpv">{fmtPct(r.pct)}</div>
              </div>
            </div>
          ))}
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
