export default function VariantsPanel({ variants, selectedId, onSelect }) {
  return (
    <aside
      style={{
        width: 320,
        borderLeft: "1px solid #e5e7eb",
        overflowY: "auto",
        padding: 12,
      }}
    >
      <h3 style={{ margin: "4px 8px 12px" }}>Variantes</h3>
      {variants.map((v) => {
        const active = v.variant_id === selectedId;
        return (
          <button
            key={v.variant_id}
            onClick={() => onSelect(active ? null : v.variant_id)}
            style={{
              display: "block",
              width: "100%",
              textAlign: "left",
              marginBottom: 8,
              padding: 10,
              borderRadius: 8,
              cursor: "pointer",
              border: active ? "2px solid #4f46e5" : "1px solid #e5e7eb",
              background: active ? "#eef2ff" : "#fff",
            }}
          >
            <div style={{ fontWeight: 600 }}>
              Variante {v.variant_id} — {v.percentage}%
            </div>
            <div style={{ fontSize: 12, color: "#6b7280" }}>
              {v.count.toLocaleString("pt-BR")} casos
            </div>
            <div style={{ fontSize: 12, marginTop: 4 }}>
              {v.activities.join(" → ")}
            </div>
          </button>
        );
      })}
    </aside>
  );
}
