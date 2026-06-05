import { useEffect, useState } from "react";
import ReactFlow, { Background, Controls } from "reactflow";
import "reactflow/dist/style.css";
import { fetchProcessGraph } from "../api";

// Layout vertical simples: empilha as atividades na ordem em que chegam.
function toFlow(graph) {
  const nodes = graph.nodes.map((n, i) => ({
    id: n.id,
    data: { label: `${n.id}  (${n.count})` },
    position: { x: 250, y: i * 110 },
    style: {
      padding: 10,
      borderRadius: 8,
      border: "1px solid #4f46e5",
      background: "#eef2ff",
      width: 220,
    },
  }));

  const maxCount = Math.max(...graph.edges.map((e) => e.count), 1);
  const edges = graph.edges.map((e) => ({
    id: `${e.source}->${e.target}`,
    source: e.source,
    target: e.target,
    label: `${e.count}`,
    style: { strokeWidth: 1 + (e.count / maxCount) * 6, stroke: "#6366f1" },
  }));

  return { nodes, edges };
}

export default function ProcessGraph() {
  const [flow, setFlow] = useState({ nodes: [], edges: [] });
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchProcessGraph()
      .then((graph) => setFlow(toFlow(graph)))
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <p style={{ color: "crimson" }}>Falha: {error}</p>;

  return (
    <div style={{ width: "100%", height: "100vh" }}>
      <ReactFlow nodes={flow.nodes} edges={flow.edges} fitView>
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
