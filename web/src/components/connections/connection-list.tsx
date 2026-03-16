import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Server, Trash2, Wifi, WifiOff } from "lucide-react";
import {
  deleteConnection,
  getConnections,
  testConnection,
} from "@/api/connections";
import { getProjects } from "@/api/projects";
import { cn } from "@/lib/utils";
import type { Connection, Project } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";

const statusConfig: Record<string, { color: string; icon: typeof Wifi }> = {
  online: { color: "text-green-500", icon: Wifi },
  offline: { color: "text-red-500", icon: WifiOff },
  unknown: { color: "text-gray-400", icon: WifiOff },
};

const statusBadgeColors: Record<string, string> = {
  online: "bg-green-100 text-green-800 border-transparent",
  offline: "bg-red-100 text-red-800 border-transparent",
  unknown: "bg-gray-100 text-gray-800 border-transparent",
};

const typeLabels: Record<string, string> = {
  ssh: "SSH",
  kubernetes: "K8s",
};

function ConnectionItem({
  conn,
  projectName,
}: {
  conn: Connection;
  projectName?: string;
}) {
  const queryClient = useQueryClient();

  const testMutation = useMutation({
    mutationFn: testConnection,
    onSuccess: () => {
      toast.success("Connection test completed");
      queryClient.invalidateQueries({ queryKey: ["connections"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteConnection,
    onSuccess: () => {
      toast.success("Connection deleted");
      queryClient.invalidateQueries({ queryKey: ["connections"] });
    },
  });

  const status = statusConfig[conn.status] ?? statusConfig.unknown;
  const StatusIcon = status.icon;
  const typeIcon = conn.type === "kubernetes" ? "☸️" : "🖥️";

  return (
    <div data-testid={`conn-item-${conn.id}`} className="border-b last:border-b-0">
      <div className="flex items-center gap-3 p-4">
        <span className="text-lg">{typeIcon}</span>
        <StatusIcon className={cn("h-4 w-4", status.color)} />
        <div className="flex-1 space-y-0.5">
          <p className="font-medium">{conn.name}</p>
          <p className="text-sm text-muted-foreground">
            {conn.type === "kubernetes"
              ? "Kubernetes Cluster"
              : `${conn.username}@${conn.host}:${conn.port}`}
          </p>
          {conn.description && (
            <p className="text-xs text-muted-foreground">{conn.description}</p>
          )}
        </div>
        <Badge data-testid="conn-type-badge" variant="outline" className="text-xs">
          {typeLabels[conn.type] ?? conn.type}
        </Badge>
        <Badge
          className={
            statusBadgeColors[conn.status] ?? statusBadgeColors.unknown
          }
        >
          {conn.status}
        </Badge>
        {projectName && (
          <Badge variant="secondary" className="text-xs">
            {projectName}
          </Badge>
        )}
        <Button
          data-testid={`conn-test-${conn.id}`}
          variant="outline"
          size="sm"
          onClick={() => testMutation.mutate(conn.id)}
          disabled={testMutation.isPending}
        >
          {testMutation.isPending ? "Testing..." : "Test"}
        </Button>
        <Button
          data-testid={`conn-delete-${conn.id}`}
          variant="ghost"
          size="sm"
          onClick={() => deleteMutation.mutate(conn.id)}
          disabled={deleteMutation.isPending}
        >
          <Trash2 className="h-4 w-4 text-destructive" />
        </Button>
      </div>
    </div>
  );
}

export function ConnectionList() {
  const { data: connections, isLoading } = useQuery({
    queryKey: ["connections"],
    queryFn: getConnections,
  });

  const { data: projects } = useQuery({
    queryKey: ["projects"],
    queryFn: getProjects,
  });

  const projectsById = (projects ?? []).reduce<Record<string, Project>>(
    (acc, p) => {
      acc[p.id] = p;
      return acc;
    },
    {},
  );

  if (isLoading) {
    return (
      <div className="divide-y">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 p-4">
            <Skeleton className="h-4 w-4 rounded-full" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-48" />
            </div>
            <Skeleton className="h-5 w-16 rounded-full" />
            <Skeleton className="h-8 w-16" />
            <Skeleton className="h-8 w-8" />
          </div>
        ))}
      </div>
    );
  }

  if (!connections?.length) {
    return (
      <Empty className="py-12">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <Server />
          </EmptyMedia>
          <EmptyTitle>No connections configured</EmptyTitle>
          <EmptyDescription>Add one to get started.</EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <div>
      {connections.map((conn) => (
        <ConnectionItem
          key={conn.id}
          conn={conn}
          projectName={conn.project_id ? projectsById[conn.project_id]?.name : undefined}
        />
      ))}
    </div>
  );
}
