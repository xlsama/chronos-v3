import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Server, Trash2, Wifi, WifiOff } from "lucide-react";
import {
  deleteInfrastructure,
  getInfrastructures,
  testInfrastructure,
} from "@/api/infrastructures";
import { cn } from "@/lib/utils";
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

export function InfrastructureList() {
  const queryClient = useQueryClient();

  const { data: infrastructures, isLoading } = useQuery({
    queryKey: ["infrastructures"],
    queryFn: getInfrastructures,
  });

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
    <div className="divide-y">
      {infrastructures.map((infra) => {
        const status = statusConfig[infra.status] ?? statusConfig.unknown;
        const StatusIcon = status.icon;

        return (
          <div key={infra.id} className="flex items-center gap-4 p-4">
            <StatusIcon className={cn("h-4 w-4", status.color)} />
            <div className="flex-1 space-y-0.5">
              <p className="font-medium">{infra.name}</p>
              <p className="text-sm text-muted-foreground">
                {infra.username}@{infra.host}:{infra.port}
              </p>
            </div>
            <Badge
              className={
                statusBadgeColors[infra.status] ?? statusBadgeColors.unknown
              }
            >
              {infra.status}
            </Badge>
            <Button
              variant="outline"
              size="sm"
              onClick={() => testMutation.mutate(infra.id)}
              disabled={testMutation.isPending}
            >
              {testMutation.isPending ? "Testing..." : "Test"}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => deleteMutation.mutate(infra.id)}
              disabled={deleteMutation.isPending}
            >
              <Trash2 className="h-4 w-4 text-destructive" />
            </Button>
          </div>
        );
      })}
    </div>
  );
}
