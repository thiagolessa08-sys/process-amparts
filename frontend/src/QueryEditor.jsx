import { useState, useEffect } from "react";
import { Icon } from "./icons.jsx";
import {
  fetchCordeiroQueries, validateCordeiroQuery, previewCordeiroQuery,
  saveCordeiroQueries, resetCordeiroQueries,
} from "./api.js";

/* Modal: edita as 4 queries-base do Cordeiro (tabela / colunas / where),
   valida cada uma (determinístico + Claude) e salva → recarrega o event log. */
export function QueryEditor({ onClose, onApplied }) {
  const [meta, setMeta] = useState(null);     // {order, labels, required, defaults, aiConfigured}
  const [edits, setEdits] = useState({});      // {source: {table, columns, where}}
  const [active, setActive] = useState(null);
  const [results, setResults] = useState({});  // {source: {ok, columns, missing, error, ai}}
  const [previews, setPreviews] = useState({}); // {source: {ok, columns, rows, error}}
  const [validating, setValidating] = useState(false);
  const [running, setRunning] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let alive = true;
    fetchCordeiroQueries()
      .then((d) => { if (!alive) return; setMeta(d); setEdits(d.sources); setActive(d.order[0]); })
      .catch((e) => alive && setErr(e.message));
    return () => { alive = false; };
  }, []);

  function setField(f, v) {
    setEdits((e) => ({ ...e, [active]: { ...e[active], [f]: v } }));
    setResults((r) => ({ ...r, [active]: undefined }));   // edição invalida resultado
    setPreviews((p) => ({ ...p, [active]: undefined }));
  }

  async function validate() {
    setValidating(true);
    const cur = edits[active];
    try {
      const r = await validateCordeiroQuery(active, cur.table, cur.columns, cur.where || "");
      setResults((rs) => ({ ...rs, [active]: r }));
    } catch (e) {
      setResults((rs) => ({ ...rs, [active]: { ok: false, error: e.message, missing: [], columns: [] } }));
    } finally { setValidating(false); }
  }

  async function run() {
    setRunning(true);
    const cur = edits[active];
    try {
      const r = await previewCordeiroQuery(active, cur.table, cur.columns, cur.where || "");
      setPreviews((ps) => ({ ...ps, [active]: r }));
    } catch (e) {
      setPreviews((ps) => ({ ...ps, [active]: { ok: false, error: e.message, columns: [], rows: [] } }));
    } finally { setRunning(false); }
  }

  async function save() {
    setSaving(true);
    try { await saveCordeiroQueries(edits); onApplied(); }
    catch (e) { setErr(e.message); setSaving(false); }
  }

  async function reset() {
    if (!window.confirm("Restaurar as 4 queries para o padrão e recarregar o Cordeiro?")) return;
    setSaving(true);
    try { await resetCordeiroQueries(); onApplied(); }
    catch (e) { setErr(e.message); setSaving(false); }
  }

  if (err) {
    return <div className="qe-overlay" onMouseDown={onClose}>
      <div className="qe-modal sm" onMouseDown={(e) => e.stopPropagation()}>
        <div className="qe-result bad"><div className="qe-result-head"><Icon name="alert" size={15} />Erro: {err}</div></div>
        <div className="qe-foot"><span style={{ flex: 1 }} /><button className="btn" onClick={onClose}>Fechar</button></div>
      </div></div>;
  }
  if (!meta) {
    return <div className="qe-overlay" onMouseDown={onClose}>
      <div className="qe-modal sm" onMouseDown={(e) => e.stopPropagation()}>
        <div className="qe-loading"><Icon name="activity" size={16} className="spin" /> Carregando queries…</div>
      </div></div>;
  }

  const cur = edits[active] || { table: "", columns: "", where: "" };
  const res = results[active];
  const prev = previews[active];
  const anyBroken = meta.order.some((s) => results[s] && results[s].ok === false);

  return (
    <div className="qe-overlay" onMouseDown={onClose}>
      <div className="qe-modal" onMouseDown={(e) => e.stopPropagation()}>
        <div className="qe-head">
          <div>
            <div className="qe-title"><Icon name="database" size={16} /> Fonte de dados — Cordeiro</div>
            <div className="qe-sub">Edite as queries-base. Chaves de paginação, junções e o modelo são fixos.</div>
          </div>
          <button className="qe-x" onClick={onClose}><Icon name="close" size={18} /></button>
        </div>

        <div className="qe-tabs">
          {meta.order.map((s) => {
            const st = results[s];
            return (
              <button key={s} className={"qe-tab" + (active === s ? " on" : "")} onClick={() => setActive(s)}>
                {meta.labels[s]}
                {st && <span className={"qe-tdot " + (st.ok ? "ok" : "bad")} />}
              </button>
            );
          })}
        </div>

        <div className="qe-body">
          <label className="qe-label">Tabela (FROM)</label>
          <input className="qe-input mono" value={cur.table} spellCheck={false}
            onChange={(e) => setField("table", e.target.value)} />

          <label className="qe-label">Colunas (SELECT)</label>
          <textarea className="qe-area mono" rows={5} value={cur.columns} spellCheck={false}
            onChange={(e) => setField("columns", e.target.value)} />

          <label className="qe-label">Filtro (WHERE) <span className="qe-opt">opcional</span></label>
          <textarea className="qe-area mono" rows={2} value={cur.where || ""} spellCheck={false}
            placeholder="ex.: QuotationDocCreationDate >= '2025-01-01'"
            onChange={(e) => setField("where", e.target.value)} />

          <div className="qe-required">
            <span className="qe-req-l">Colunas obrigatórias</span>
            {meta.required[active].map((c) => {
              const miss = res?.missing?.some((m) => m.toLowerCase() === c.toLowerCase());
              return <span key={c} className={"qe-chip" + (miss ? " miss" : "")}>{c}</span>;
            })}
          </div>

          <div className="qe-runbar">
            <button className="btn" onClick={validate} disabled={validating || running}>
              {validating
                ? <><Icon name="activity" size={14} className="spin" /> Validando…</>
                : <><Icon name="check" size={14} /> Validar query</>}
            </button>
            <button className="btn" onClick={run} disabled={validating || running}>
              {running
                ? <><Icon name="activity" size={14} className="spin" /> Rodando…</>
                : <><Icon name="play" size={13} /> Rodar (top 100)</>}
            </button>
            {!meta.aiConfigured && <span className="qe-hint">IA não configurada — só validação básica</span>}
          </div>

          {res && (
            <div className={"qe-result " + (res.ok ? "ok" : "bad")}>
              <div className="qe-result-head">
                <Icon name={res.ok ? "check" : "alert"} size={15} />
                {res.ok ? "Query válida — todas as colunas obrigatórias presentes."
                  : (res.error ? "Erro ao executar a query." : "Faltam colunas obrigatórias.")}
              </div>
              {res.error && <pre className="qe-code err">{res.error}</pre>}
              {res.missing?.length > 0 && <div className="qe-miss">Faltando: {res.missing.join(", ")}</div>}
              {res.ai?.summary && (
                <div className="qe-ai">
                  <div className="qe-ai-l"><Icon name="activity" size={13} /> Claude</div>
                  <div className="qe-ai-txt">{res.ai.summary}</div>
                  {res.ai.suggestion && <pre className="qe-code">{res.ai.suggestion}</pre>}
                </div>
              )}
            </div>
          )}

          {prev && (
            prev.error
              ? <div className="qe-result bad"><div className="qe-result-head"><Icon name="alert" size={15} /> Erro ao rodar a query.</div><pre className="qe-code err">{prev.error}</pre></div>
              : (
                <div className="qe-preview">
                  <div className="qe-preview-head">
                    <Icon name="check" size={14} /> {prev.rows.length} linha{prev.rows.length === 1 ? "" : "s"} (top 100) · {prev.columns.length} colunas
                  </div>
                  <div className="qe-table-wrap">
                    <table className="qe-table">
                      <thead><tr>{prev.columns.map((c, i) => <th key={i}>{c}</th>)}</tr></thead>
                      <tbody>
                        {prev.rows.map((row, ri) => (
                          <tr key={ri}>{row.map((v, ci) => <td key={ci} title={v == null ? "" : String(v)}>{v == null ? "—" : String(v)}</td>)}</tr>
                        ))}
                      </tbody>
                    </table>
                    {prev.rows.length === 0 && <div className="qe-preview-empty">A query não retornou linhas.</div>}
                  </div>
                </div>
              )
          )}
        </div>

        <div className="qe-foot">
          <button className="btn ghost" onClick={reset} disabled={saving}>Restaurar padrão</button>
          <span style={{ flex: 1 }} />
          {anyBroken && <span className="qe-warn"><Icon name="alert" size={13} /> Há query com falha</span>}
          <button className="btn" onClick={onClose} disabled={saving}>Cancelar</button>
          <button className="btn primary" onClick={save} disabled={saving}>
            {saving ? "Salvando…" : "Salvar e recarregar"}
          </button>
        </div>
      </div>
    </div>
  );
}
