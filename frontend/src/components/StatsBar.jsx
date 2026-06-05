function fmtDays(seconds) {
  const days = seconds / 86400;
  return `${days.toFixed(1)} dias`;
}

function Card({ label, value }) {
  return (
    <div
      style={{
        padding: "10px 16px",
        background: "#f9fafb",
        border: "1px solid #e5e7eb",
        borderRadius: 8,
        minWidth: 120,
      }}
    >
      <div style={{ fontSize: 12, color: "#6b7280" }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 600 }}>{value}</div>
    </div>
  );
}

export default function StatsBar({ stats }) {
  if (!stats) return null;
  return (
    <div style={{ display: "flex", gap: 12, padding: "12px 20px" }}>
      <Card label="Casos" value={stats.num_cases.toLocaleString("pt-BR")} />
      <Card label="Eventos" value={stats.num_events.toLocaleString("pt-BR")} />
      <Card label="Variantes" value={stats.num_variants} />
      <Card label="Tempo medio" value={fmtDays(stats.mean_throughput_seconds)} />
      <Card label="Tempo mediano" value={fmtDays(stats.median_throughput_seconds)} />
    </div>
  );
}
