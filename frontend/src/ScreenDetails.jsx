import { useState, useEffect } from "react";
import { Icon } from "./icons.jsx";
import { fetchDetails } from "./api.js";

const PAGE_LIMIT = 500;
const fmtInt = (n) => (Number(n) || 0).toLocaleString("pt-BR");
const fmtVal = (n) => (Number(n) || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const isNum = (fmt) => fmt === "money" || fmt === "int" || fmt === "id";

export function DetailsScreen({ data, filters }) {
  const [res, setRes] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState("");

  // busca server-side (Nr. PED / cliente / produto); debounce 300ms
  useEffect(() => {
    let alive = true;
    setLoading(true); setError(null);
    const t = setTimeout(() => {
      fetchDetails(data.key, filters, { q: query, limit: PAGE_LIMIT })
        .then((r) => { if (alive) setRes(r); })
        .catch((e) => { if (alive) setError(e.message); })
        .finally(() => { if (alive) setLoading(false); });
    }, 300);
    return () => { alive = false; clearTimeout(t); };
  }, [data.key, filters, query]);

  const cols = res?.columns || [];
  const rows = res?.rows || [];
  const total = res?.total ?? 0;
  const capped = total > rows.length;
  const fmtCell = (fmt, v) => v == null ? "—"
    : fmt === "money" ? fmtVal(v) : fmt === "int" ? fmtInt(v)
    : fmt === "id" ? (v !== "" && !isNaN(v) ? String(Number(v)) : String(v))
    : String(v);

  return (
    <div className="details">
      <div className="det-toolbar">
        <div className="cex-search inline">
          <Icon name="search" size={15} />
          <input placeholder="Buscar Nr. PED, cliente ou produto…" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <span className="cex-count mono" title={capped ? `Mostrando ${rows.length} de ${total} — refine a busca` : ""}>
          {loading ? "…" : capped
            ? `${fmtInt(rows.length)} de ${fmtInt(total)} registros`
            : `${fmtInt(total)} registros`}
        </span>
      </div>
      <div className="det-table-wrap">
        <table className="nf-table det-table">
          <thead>
            <tr>{cols.map((c) => <th key={c.key} className={isNum(c.fmt) ? "r" : ""}>{c.label}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>
                {cols.map((c) => (
                  <td key={c.key} className={isNum(c.fmt) ? "r mono" : ""}>{fmtCell(c.fmt, row[c.key])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {loading && <div className="cex-empty">Carregando…</div>}
        {error && !loading && <div className="cex-empty">Erro: {error}</div>}
        {!loading && !error && rows.length === 0 && <div className="cex-empty">Nenhum registro</div>}
      </div>
    </div>
  );
}
