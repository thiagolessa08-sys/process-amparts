import { useState, useRef, useEffect } from "react";
import { Icon } from "./icons.jsx";
import { askAssistant } from "./api.js";

const SUGGESTIONS = [
  "Qual fornecedor tem o maior valor total?",
  "Quantos casos têm retrabalho?",
  "Qual o tempo médio entre criar e aprovar o pedido?",
  "Top 5 atividades mais frequentes",
];

/* ───────── markdown leve (negrito, itálico, código, listas) ───────── */
function renderInline(text) {
  // tokeniza: **negrito** · __negrito__ · `código` · *itálico*
  const parts = String(text).split(/(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\*[^*\n]+\*)/g);
  return parts.map((p, i) => {
    if (!p) return null;
    if ((p.startsWith("**") && p.endsWith("**")) || (p.startsWith("__") && p.endsWith("__")))
      return <strong key={i}>{p.slice(2, -2)}</strong>;
    if (p.startsWith("`") && p.endsWith("`")) return <code key={i} className="md-code">{p.slice(1, -1)}</code>;
    if (p.startsWith("*") && p.endsWith("*")) return <em key={i}>{p.slice(1, -1)}</em>;
    return p;
  });
}

/* pt-BR: "R$ 1.477.898,11" -> 1477898.11 · "55%" -> 55 */
function parseNum(s) {
  const raw = String(s).replace(/[^\d,.-]/g, "");
  if (!raw) return null;
  const n = parseFloat(raw.replace(/\./g, "").replace(",", "."));
  return Number.isNaN(n) ? null : n;
}

/* tabela renderizada + toggle Tabela/Gráfico (barras horizontais) */
function MdTable({ rows }) {
  const [chart, setChart] = useState(false);
  if (!rows.length) return null;
  const header = rows[0];
  const body = rows.slice(1);
  const ncols = header.length;
  const isNumCol = (c) => body.length && body.filter((r) => parseNum(r[c]) != null).length > body.length / 2;
  let valCol = ncols - 1;
  for (let c = ncols - 1; c >= 0; c--) { if (isNumCol(c)) { valCol = c; break; } }
  let labCol = 0;
  for (let c = 0; c < ncols; c++) { if (!isNumCol(c)) { labCol = c; break; } }
  const data = body
    .map((r) => ({ label: r[labCol], raw: r[valCol], val: parseNum(r[valCol]) }))
    .filter((d) => d.val != null);
  const canChart = data.length >= 2;
  const max = Math.max(...data.map((d) => Math.abs(d.val)), 1);

  return (
    <div className="md-tablewrap">
      {canChart && (
        <div className="md-tabtoggle">
          <button type="button" className={chart ? "" : "on"} onClick={() => setChart(false)}>
            <Icon name="variants" size={13} /> Tabela
          </button>
          <button type="button" className={chart ? "on" : ""} onClick={() => setChart(true)}>
            <Icon name="hbars" size={13} /> Gráfico
          </button>
        </div>
      )}
      {chart ? (
        <div className="md-chart">
          {data.map((d, i) => (
            <div className="md-chrow" key={i}>
              <span className="md-chlab" title={d.label}>{d.label}</span>
              <span className="md-chtrack"><i style={{ width: (100 * Math.abs(d.val) / max) + "%" }} /></span>
              <span className="md-chval">{d.raw}</span>
            </div>
          ))}
        </div>
      ) : (
        <table className="md-table">
          <thead><tr>{header.map((c, i) => <th key={i}>{renderInline(c)}</th>)}</tr></thead>
          <tbody>
            {body.map((r, ri) => (
              <tr key={ri}>{r.map((c, ci) => <td key={ci} className={isNumCol(ci) ? "num" : ""}>{renderInline(c)}</td>)}</tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

const _isTableRow = (l) => /^\s*\|.*\|\s*$/.test(l);
const _cellsOf = (l) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
const _isSep = (cells) => cells.length > 0 && cells.every((c) => /^:?-{2,}:?$/.test(c) || c === "");

function Markdown({ text }) {
  const lines = String(text ?? "").replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let list = null, table = null;
  const flush = () => {
    if (list) { blocks.push(list); list = null; }
    if (table) { blocks.push(table); table = null; }
  };
  for (const raw of lines) {
    const line = raw.replace(/\s+$/, "");
    if (_isTableRow(line)) {
      const cells = _cellsOf(line);
      if (list) { blocks.push(list); list = null; }
      if (!table) table = { type: "table", rows: [] };
      if (!_isSep(cells)) table.rows.push(cells);
      continue;
    }
    const ul = line.match(/^\s*[-•*]\s+(.*)$/);
    const ol = line.match(/^\s*\d+[.)]\s+(.*)$/);
    const h  = line.match(/^(#{1,3})\s+(.*)$/);
    if (ul) {
      if (table) { blocks.push(table); table = null; }
      if (!list || list.type !== "ul") { if (list) blocks.push(list); list = { type: "ul", items: [] }; }
      list.items.push(ul[1]);
    } else if (ol) {
      if (table) { blocks.push(table); table = null; }
      if (!list || list.type !== "ol") { if (list) blocks.push(list); list = { type: "ol", items: [] }; }
      list.items.push(ol[1]);
    } else if (h) {
      flush(); blocks.push({ type: "h", level: h[1].length, text: h[2] });
    } else if (line.trim() === "") {
      flush();
    } else {
      flush(); blocks.push({ type: "p", text: line });
    }
  }
  flush();
  return (
    <div className="md">
      {blocks.map((b, i) => {
        if (b.type === "table") return <MdTable key={i} rows={b.rows} />;
        if (b.type === "ul") return <ul key={i} className="md-ul">{b.items.map((it, j) => <li key={j}>{renderInline(it)}</li>)}</ul>;
        if (b.type === "ol") return <ol key={i} className="md-ol">{b.items.map((it, j) => <li key={j}>{renderInline(it)}</li>)}</ol>;
        if (b.type === "h")  return <div key={i} className={"md-h md-h" + b.level}>{renderInline(b.text)}</div>;
        return <p key={i} className="md-p">{renderInline(b.text)}</p>;
      })}
    </div>
  );
}

function QueryResult({ table }) {
  if (!table) return null;
  return (
    <div className="as-table-wrap">
      <table className="as-table">
        <thead><tr>{table.columns.map((c, i) => <th key={i}>{c}</th>)}</tr></thead>
        <tbody>
          {table.rows.slice(0, 12).map((row, ri) => (
            <tr key={ri}>{row.map((v, ci) => <td key={ci}>{String(v)}</td>)}</tr>
          ))}
        </tbody>
      </table>
      {table.rows.length > 12 && <div className="as-table-more">+{table.rows.length - 12} linhas</div>}
    </div>
  );
}

function PdfDownload({ b64, name }) {
  if (!b64) return null;
  function download() {
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], { type: "application/pdf" }));
    const a = document.createElement("a");
    a.href = url; a.download = name || "relatorio.pdf";
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }
  return (
    <button className="as-pdf" onClick={download}>
      <Icon name="arrowDown" size={15} /> Baixar PDF
    </button>
  );
}

function Steps({ steps }) {
  const [open, setOpen] = useState(false);
  if (!steps?.length) return null;
  return (
    <div className="as-steps">
      <button className="as-steps-toggle" onClick={() => setOpen((o) => !o)}>
        <Icon name="hash" size={13} /> {steps.length} consulta{steps.length > 1 ? "s" : ""} executada{steps.length > 1 ? "s" : ""}
        <Icon name="chevronD" size={13} style={{ transform: open ? "rotate(180deg)" : "none", transition: "transform .15s", marginLeft: "auto" }} />
      </button>
      {open && steps.map((s, i) => (
        <div className="as-step" key={i}>
          <pre className="as-code">{s.code}</pre>
          {s.error ? <div className="as-err">{s.error}</div> : <QueryResult table={s.table} />}
        </div>
      ))}
    </div>
  );
}

export function AssistantScreen({ data, filters }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef(null);
  const taRef = useRef(null);

  useEffect(() => { scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight); }, [messages, loading]);

  async function send(text) {
    const q = (text ?? input).trim();
    if (!q || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: q }]);
    setLoading(true);
    try {
      const res = await askAssistant(data.key, q, filters);
      setMessages((m) => [...m, { role: "assistant", text: res.answer, steps: res.steps, pdf: res.pdf, pdfName: res.pdfName }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", text: `⚠️ ${e.message}`, error: true }]);
    } finally {
      setLoading(false);
    }
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  }

  return (
    <div className="assistant">
      <div className="as-scroll" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="as-empty">
            <div className="as-empty-logo"><Icon name="activity" size={26} strokeWidth={2.2} /></div>
            <div className="as-empty-title">Assistente de Processos</div>
            <div className="as-empty-sub">Pergunte sobre os dados em linguagem natural. A IA escreve e executa a consulta, e responde com os números.</div>
            <div className="as-suggest">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="as-chip" onClick={() => send(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={"as-msg as-" + m.role}>
            {m.role === "assistant" && <div className="as-av"><Icon name="activity" size={15} /></div>}
            <div className={"as-bubble" + (m.error ? " err" : "")}>
              {m.role === "assistant"
                ? <div className="as-text as-md"><Markdown text={m.text} /></div>
                : <div className="as-text">{m.text}</div>}
              {m.role === "assistant" && <Steps steps={m.steps} />}
              {m.role === "assistant" && <PdfDownload b64={m.pdf} name={m.pdfName} />}
            </div>
          </div>
        ))}

        {loading && (
          <div className="as-msg as-assistant">
            <div className="as-av"><Icon name="activity" size={15} /></div>
            <div className="as-bubble"><div className="as-typing"><span /><span /><span /></div></div>
          </div>
        )}
      </div>

      <div className="as-input-bar">
        <textarea ref={taRef} className="as-input" rows={1} placeholder="Pergunte algo sobre o processo…"
          value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={onKeyDown} disabled={loading} />
        <button className="as-send" onClick={() => send()} disabled={loading || !input.trim()}>
          <Icon name="arrowUp" size={18} strokeWidth={2.4} />
        </button>
      </div>
    </div>
  );
}
