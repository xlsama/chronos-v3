import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ChevronRight, Server, Trash2, Wifi, WifiOff } from "lucide-react";
import {
  deleteInfrastructure,
  getInfrastructures,
  testInfrastructure,
} from "@/api/infrastructures";
import { cn } from "@/lib/utils";
import type { Infrastructure } from "@/lib/types";
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
import { ServiceList } from "./service-list";
import { CreateServiceDialog } from "./create-service-dialog";
import { DiscoverServicesDialog } from "./discover-services-dialog";

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

function InfrastructureItem({ infra }: { infra: Infrastructure }) {
  const [expanded, setExpanded] = useState(false);
  const queryClient = useQueryClient();

  const testMutation = useMutation({
    mutationFn: testInfrastructure,
    onSuccess: () => {
      toast.success("Connection test completed");
      queryClient.invalidateQueries({ queryKey: ["infrastructures"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteInfrastructure,
    onSuccess: () => {
      toast.success("Infrastructure deleted");
      queryClient.invalidateQueries({ queryKey: ["infrastructures"] });
    },
  });

  const status = statusConfig[infra.status] ?? statusConfig.unknown;
  const StatusIcon = status.icon;
  const typeIcon = infra.type === "kubernetes" ? "☸️" : "🖥️";

  return (
    <div data-testid={`infra-item-${infra.id}`} className="border-b last:border-b-0">
      <div className="flex items-center gap-3 p-4">
        <button
          data-testid={`infra-expand-${infra.id}`}
          onClick={() => setExpanded(!expanded)}
          className="text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronRight
            className={cn(
              "h-4 w-4 transition-transform",
              expanded && "rotate-90",
            )}
          />
        </button>
        <span className="text-lg">{typeIcon}</span>
        <StatusIcon className={cn("h-4 w-4", status.color)} />
        <div className="flex-1 space-y-0.5">
          <p className="font-medium">{infra.name}</p>
          <p className="text-sm text-muted-foreground">
            {infra.type === "kubernetes"
              ? "Kubernetes Cluster"
              : `${infra.username}@${infra.host}:${infra.port}`}
          </p>
        </div>
        <Badge data-testid="infra-type-badge" variant="outline" className="text-xs">
          {typeLabels[infra.type] ?? infra.type}
        </Badge>
        <Badge
          className={
            statusBadgeColors[infra.status] ?? statusBadgeColors.unknown
          }
        >
          {infra.status}
        </Badge>
        <Button
          data-testid={`infra-test-${infra.id}`}
          variant="outline"
          size="sm"
          onClick={() => testMutation.mutate(infra.id)}
          disabled={testMutation.isPending}
        >
          {testMutation.isPending ? "Testing..." : "Test"}
        </Button>
        <Button
          data-testid={`infra-delete-${infra.id}`}
          variant="ghost"
          size="sm"
          onClick={() => deleteMutation.mutate(infra.id)}
          disabled={deleteMutation.isPending}
        >
          <Trash2 className="h-4 w-4 text-destructive" />
        </Button>
      </div>

      {expanded && (
        <div className="pb-3">
          <div className="flex items-center gap-2 pl-12 pb-2">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Services
            </span>
            <CreateServiceDialog infraId={infra.id} />
            <DiscoverServicesDialog infraId={infra.id} />
          </div>
          <ServiceList infraId={infra.id} />
        </div>
      )}
    </div>
  );
}

export function InfrastructureList() {
  const { data: infrastructures, isLoading } = useQuery({
    queryKey: ["infrastructures"],
    queryFn: getInfrastructures,
  });

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

  if (!infrastructures?.length) {
    return (
      <Empty className="py-12">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <Server />
          </EmptyMedia>
          <EmptyTitle>No infrastructure configured</EmptyTitle>
          <EmptyDescription>Add one to get started.</EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <div>
      {infrastructures.map((infra) => (
        <InfrastructureItem key={infra.id} infra={infra} />
      ))}
    </div>
  );
}
