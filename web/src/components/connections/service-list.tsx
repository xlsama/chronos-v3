import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Trash2 } from "lucide-react";
import { deleteService, getServicesByConnection } from "@/api/services";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

export function ServiceList({ connectionId }: { connectionId: string }) {
  const queryClient = useQueryClient();

  const { data: services, isLoading } = useQuery({
    queryKey: ["services", connectionId],
    queryFn: () => getServicesByConnection(connectionId),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteService,
    onSuccess: () => {
      toast.success("Service deleted");
      queryClient.invalidateQueries({ queryKey: ["services", connectionId] });
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
    <div data-testid={`service-list-${connectionId}`} className="space-y-0.5">
      {services.map((svc, index) => {
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
            <span className="font-medium text-sm">{svc.name}</span>
            <span className="text-xs text-muted-foreground">
              {svc.service_type}
            </span>
            {svc.source && (
              <span className="text-xs text-muted-foreground">
                {svc.source}
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
