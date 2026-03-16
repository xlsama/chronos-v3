import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { Connection } from "@/lib/types";

type ConnectionNodeData = { connection: Connection };

export const ConnectionNode = memo(function ConnectionNode({
  data,
  selected,
}: NodeProps & { data: ConnectionNodeData }) {
  const { connection } = data;
  const icon = connection.type === "kubernetes" ? "☸️" : "🖥️";
  const statusColor =
    connection.status === "online"
      ? "bg-green-500"
      : connection.status === "offline"
        ? "bg-red-500"
        : "bg-gray-400";

  return (
    <>
      <Handle type="target" position={Position.Left} className="!w-2 !h-2" />
      <div
        className={`rounded-lg border-2 border-dashed bg-muted/50 px-4 py-3 shadow-sm min-w-[180px] transition-colors ${
          selected ? "border-primary" : "border-border"
        }`}
      >
        <div className="flex items-center gap-2">
          <span className="text-base">{icon}</span>
          <span className="font-medium text-sm">{connection.name}</span>
          <span className={`h-2 w-2 rounded-full ${statusColor}`} />
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          {connection.type === "kubernetes"
            ? "Kubernetes Cluster"
            : `${connection.type.toUpperCase()} · ${connection.username}@${connection.host}`}
        </p>
      </div>
      <Handle type="source" position={Position.Right} className="!w-2 !h-2" />
    </>
  );
});
