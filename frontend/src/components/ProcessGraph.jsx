import ReactFlow, { Background, Controls } from "reactflow";
import "reactflow/dist/style.css";

// Converte o grafo da API + um caminho destacado em nos/arestas do React Flow.
function toFlow(graph, highlightPath) {
  const onPath = new Set(highlightPath || []);
  // pares consecutivos do caminho destacado
  const pathPairs = new Set();
  if (highlightPath) {
    for (let i = 0; i < highlightPath.length - 1; i++) {
      pathPairs.add(`${highlightPath[i]}->${highlightPath[i + 1]}`);
    }
  }
  const hasHighlight = onPath.size > 0;

  const nodes = graph.nodes.map((n, i) => {
    const active = onPath.has(n.id);
    return {
      id: n.id,
      data: { label: `${n.id}  (${n.count})` },
      position: { x: 250, y: i * 110 },
      style: {
        padding: 10,
        borderRadius: 8,
        border: active ? "2px solid #4f46e5" : "1px solid #c7d2fe",
        background: active ? "#eef2ff" : "#fff",
        opacity: hasHighlight && !active ? 0.35 : 1,
        width: 220,
      },
    };
  });

  const maxCount = Math.max(...graph.edges.map((e) => e.count), 1);
  const edges = graph.edges.map((e) => {
    const active = pathPairs.has(`${e.source}->${e.target}`);
    return {
      id: `${e.source}->${e.target}`,
      source: e.source,
      target: e.target,
      label: `${e.count}`,
      style: {
        strokeWidth: 1 + (e.count / maxCount) * 6,
        stroke: active ? "#4f46e5" : "#a5b4fc",
        opacity: hasHighlight && !active ? 0.2 : 1,
      },
    };
  });

  return { nodes, edges };
}

export default function ProcessGraph({ graph, highlightPath }) {
  if (!graph) return null;
  const { nodes, edges } = toFlow(graph, highlightPath);
  return (
    <div style={{ flex: 1, height: "100%" }}>
      <ReactFlow nodes={nodes} edges={edges} fitView>
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
