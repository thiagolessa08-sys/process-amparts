import ProcessGraph from "./components/ProcessGraph";

export default function App() {
  return (
    <div>
      <header style={{ padding: "12px 20px", borderBottom: "1px solid #e5e7eb" }}>
        <strong>Process Mining</strong> — Modulo Financeiro · P2P
      </header>
      <ProcessGraph />
    </div>
  );
}
