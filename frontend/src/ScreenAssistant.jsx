import { useState, useRef, useEffect } from "react";
import { Icon } from "./icons.jsx";
import { askAssistant } from "./api.js";

const SUGGESTIONS = [
  "Qual fornecedor tem o maior valor total?",
  "Quantos casos têm retrabalho?",
  "Qual o tempo médio entre criar e aprovar o pedido?",
  "Top 5 atividades mais frequentes",
];

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
              <div className="as-text">{m.text}</div>
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
