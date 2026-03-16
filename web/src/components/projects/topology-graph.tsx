import { useCallback, useMemo, useRef, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MarkerType,
  useEdgesState,
  useNodesState,
  type Connection as FlowConnection,
  type Edge,
  type Node,
  type NodeTypes,
} from "@xyflow/react";
import dagre from "dagre";
import "@xyflow/react/dist/style.css";

import type { ProjectTopology } from "@/lib/types";
import { ServiceNode } from "./nodes/service-node";
import { ConnectionNode } from "./nodes/connection-node";

const nodeTypes: NodeTypes = {
  serviceNode: ServiceNode,
  connectionNode: ConnectionNode,
} as unknown as NodeTypes;

const NODE_WIDTH = 220;
const NODE_HEIGHT = 80;

function applyDagreLayout(nodes: Node[], edges: Edge[]): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 60, ranksep: 120 });

  for (const node of nodes) {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const edge of edges) {
    g.setEdge(edge.source, edge.target);
  }

  dagre.layout(g);

  const layoutedNodes = nodes.map((node) => {
    const dagNode = g.node(node.id);
    return {
      ...node,
      position: {
        x: dagNode.x - NODE_WIDTH / 2,
        y: dagNode.y - NODE_HEIGHT / 2,
      },
    };
  });

  return { nodes: layoutedNodes, edges };
}

function buildGraphData(topology: ProjectTopology) {
  const nodes: Node[] = [
    ...topology.services.map((s) => ({
      id: `svc-${s.id}`,
      type: "serviceNode" as const,
      data: { service: s },
      position: { x: 0, y: 0 },
    })),
    ...topology.connections.map((c) => ({
      id: `conn-${c.id}`,
      type: "connectionNode" as const,
      data: { connection: c },
      position: { x: 0, y: 0 },
    })),
  ];

  const edges: Edge[] = [
    ...topology.dependencies.map((d) => ({
      id: `dep-${d.id}`,
      source: `svc-${d.from_service_id}`,
      target: `svc-${d.to_service_id}`,
      label: d.dependency_type,
      type: "smoothstep",
      animated: true,
      markerEnd: { type: MarkerType.ArrowClosed },
      style: { stroke: "var(--color-primary)" },
      data: { entityType: "dependency" as const, entityId: d.id },
    })),
    ...topology.bindings.map((b) => ({
      id: `bind-${b.id}`,
      source: `svc-${b.service_id}`,
      target: `conn-${b.connection_id}`,
      type: "smoothstep",
      style: { strokeDasharray: "5,5", stroke: "var(--color-muted-foreground)" },
      data: { entityType: "binding" as const, entityId: b.id },
    })),
  ];

  return applyDagreLayout(nodes, edges);
}

export type TopologyGraphRef = {
  autoLayout: () => void;
};

export function TopologyGraph({
  topology,
  onConnect,
  onNodeContextMenu,
  onEdgeContextMenu,
}: {
  topology: ProjectTopology;
  onConnect?: (params: FlowConnection) => void;
  onNodeContextMenu?: (event: React.MouseEvent, node: Node) => void;
  onEdgeContextMenu?: (event: React.MouseEvent, edge: Edge) => void;
}) {
  const graphData = useMemo(() => buildGraphData(topology), [topology]);
  const [nodes, setNodes, onNodesChange] = useNodesState(graphData.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(graphData.edges);
  const prevTopologyRef = useRef(topology);

  // Update nodes/edges when topology data changes
  if (topology !== prevTopologyRef.current) {
    prevTopologyRef.current = topology;
    const newData = buildGraphData(topology);
    setNodes(newData.nodes);
    setEdges(newData.edges);
  }

  const handleConnect = useCallback(
    (params: FlowConnection) => {
      onConnect?.(params);
    },
    [onConnect],
  );

  const handleNodeContextMenu = useCallback(
    (event: React.MouseEvent, node: Node) => {
      event.preventDefault();
      onNodeContextMenu?.(event, node);
    },
    [onNodeContextMenu],
  );

  const handleEdgeContextMenu = useCallback(
    (event: React.MouseEvent, edge: Edge) => {
      event.preventDefault();
      onEdgeContextMenu?.(event, edge);
    },
    [onEdgeContextMenu],
  );

  const [autoLayoutKey, setAutoLayoutKey] = useState(0);

  const autoLayout = useCallback(() => {
    const newData = buildGraphData(topology);
    setNodes(newData.nodes);
    setEdges(newData.edges);
    setAutoLayoutKey((k) => k + 1);
  }, [topology, setNodes, setEdges]);

  return (
    <TopologyGraphContext.Provider value={{ autoLayout }}>
      <ReactFlow
        key={autoLayoutKey}
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={handleConnect}
        onNodeContextMenu={handleNodeContextMenu}
        onEdgeContextMenu={handleEdgeContextMenu}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.3}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={16} size={1} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </TopologyGraphContext.Provider>
  );
}

import { createContext, useContext } from "react";

const TopologyGraphContext = createContext<{ autoLayout: () => void }>({
  autoLayout: () => {},
});

export function useTopologyGraph() {
  return useContext(TopologyGraphContext);
}
