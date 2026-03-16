import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Trash2 } from "lucide-react";
import { deleteService, getServicesByInfra } from "@/api/services";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

const typeIcons: Record<string, string> = {
  docker: "🐳",
  systemd: "⚙️",
  process: "📦",
  database: "🐬",
  cache: "🔴",
  queue: "📨",
  cron_job: "⏰",
  k8s_deployment: "📦",
  k8s_statefulset: "📦",
  k8s_service: "🔗",
};

export function ServiceList({ infraId }: { infraId: string }) {
  const queryClient = useQueryClient();

  const { data: services, isLoading } = useQuery({
    queryKey: ["services", infraId],
    queryFn: () => getServicesByInfra(infraId),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteService,
    onSuccess: () => {
      toast.success("Service deleted");
      queryClient.invalidateQueries({ queryKey: ["services", infraId] });
    },
  });

  if (isLoading) {
    return (
      <div className="space-y-1 pl-8">
        {Array.from({ length: 2 }).map((_, i) => (
          <Skeleton key={i} className="h-6 w-48" />
        ))}
      </div>
    );
  }

  if (!services?.length) {
    return (
      <p className="pl-8 text-xs text-muted-foreground py-1">
        No services discovered
      </p>
    );
  }

  return (
    <div data-testid={`service-list-${infraId}`} className="space-y-0.5">
      {services.map((svc, index) => {
        const icon = typeIcons[svc.service_type] ?? "📦";
        const isLast = index === services.length - 1;

        return (
          <div
            key={svc.id}
            data-testid={`service-item-${svc.id}`}
            className="group flex items-center gap-2 pl-6 pr-4 py-0.5 text-sm"
          >
            <span className="text-muted-foreground text-xs">
              {isLast ? "└──" : "├──"}
            </span>
            <span>{icon}</span>
            <span className="font-medium text-sm">{svc.name}</span>
            <Badge variant="outline" className="text-xs px-1.5 py-0">
              {svc.service_type}
            </Badge>
            {svc.port && (
              <span className="text-xs text-muted-foreground">:{svc.port}</span>
            )}
            {svc.namespace && (
              <span className="text-xs text-muted-foreground">
                ({svc.namespace})
              </span>
            )}
            <Button
              variant="ghost"
              size="sm"
              className="ml-auto h-6 w-6 p-0 opacity-0 group-hover:opacity-100 transition-opacity"
              onClick={() => deleteMutation.mutate(svc.id)}
              disabled={deleteMutation.isPending}
            >
              <Trash2 className="h-3 w-3 text-destructive" />
            </Button>
          </div>
        );
      })}
    </div>
  );
}
