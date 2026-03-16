import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { Service } from "@/lib/types";
import { Badge } from "@/components/ui/badge";

const SERVICE_TYPE_ICONS: Record<string, string> = {
  frontend: "🌐",
  backend_api: "🔧",
  worker: "⚙️",
  etl_job: "🔄",
  cron_job: "⏰",
  database: "🗄️",
  cache: "💾",
  message_queue: "📨",
  custom: "📦",
};

type ServiceNodeData = { service: Service };

export const ServiceNode = memo(function ServiceNode({
  data,
  selected,
}: NodeProps & { data: ServiceNodeData }) {
  const { service } = data;
  const icon = SERVICE_TYPE_ICONS[service.service_type] ?? "📦";

  return (
    <>
      <Handle type="target" position={Position.Left} className="!w-2 !h-2" />
      <div
        className={`rounded-lg border-2 bg-background px-4 py-3 shadow-sm min-w-[180px] transition-colors ${
          selected ? "border-primary" : "border-border"
        }`}
      >
        <div className="flex items-center gap-2">
          <span className="text-base">{icon}</span>
          <span className="font-medium text-sm">{service.name}</span>
        </div>
        <div className="mt-1 flex items-center gap-1">
          <Badge variant="outline" className="text-[10px] px-1 py-0">
            {service.service_type}
          </Badge>
          {service.source !== "manual" && (
            <Badge variant="secondary" className="text-[10px] px-1 py-0">
              {service.source}
            </Badge>
          )}
        </div>
        {service.description && (
          <p className="mt-1 text-xs text-muted-foreground line-clamp-2 max-w-[200px]">
            {service.description}
          </p>
        )}
      </div>
      <Handle type="source" position={Position.Right} className="!w-2 !h-2" />
    </>
  );
});
