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

function Markdown({ text }) {
  const lines = String(text ?? "").replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let list = null;
  const flush = () => { if (list) { blocks.push(list); list = null; } };
  for (const raw of lines) {
    const line = raw.replace(/\s+$/, "");
    const ul = line.match(/^\s*[-•*]\s+(.*)$/);
    const ol = line.match(/^\s*\d+[.)]\s+(.*)$/);
    const h  = line.match(/^(#{1,3})\s+(.*)$/);
    if (ul) {
      if (!list || list.type !== "ul") { flush(); list = { type: "ul", items: [] }; }
      list.items.push(ul[1]);
    } else if (ol) {
      if (!list || list.type !== "ol") { flush(); list = { type: "ol", items: [] }; }
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
      setMessages((m) => [...m, { role: "assistant", text: res.answer, steps: res.steps }]);
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
          <div key={i} className={"as-msg " + m.role}>
            {m.role === "assistant" && <div className="as-av"><Icon name="activity" size={15} /></div>}
            <div className={"as-bubble" + (m.error ? " err" : "")}>
              {m.role === "assistant"
                ? <div className="as-text as-md"><Markdown text={m.text} /></div>
                : <div className="as-text">{m.text}</div>}
              {m.role === "assistant" && <Steps steps={m.steps} />}
            </div>
          </div>
        ))}

        {loading && (
          <div className="as-msg assistant">
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
