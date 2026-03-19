import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ArrowDown, ArrowLeft, Square } from "lucide-react";
import { getIncident, stopIncident } from "@/api/incidents";
import { useIncidentStream } from "@/hooks/use-incident-stream";
import { useAutoScroll } from "@/hooks/use-auto-scroll";
import { EventTimeline } from "@/components/incidents/incident-detail/event-timeline";
import { UserInputBar } from "@/components/incidents/incident-detail/user-input-bar";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { statusColors, statusLabels } from "@/lib/incident-constants";
import { Link } from "@tanstack/react-router";

export const Route = createFileRoute("/incidents/$incidentId")({
  component: IncidentDetailPage,
});

function IncidentDetailPage() {
  const { incidentId } = Route.useParams();
  const queryClient = useQueryClient();
  const { data: incident, isLoading, isError } = useQuery({
    queryKey: ["incident", incidentId],
    queryFn: () => getIncident(incidentId),
  });

  useIncidentStream(incidentId, incident?.status);

  const [stopDialogOpen, setStopDialogOpen] = useState(false);

  const isActive = incident?.status === "open" || incident?.status === "investigating";

  const { scrollRef, bottomRef, isAtBottom, scrollToBottom } = useAutoScroll({
    enabled: isActive,
    threshold: 100,
    smooth: true,
  });

  const stopMutation = useMutation({
    mutationFn: () => stopIncident(incidentId),
    onSuccess: () => {
      setStopDialogOpen(false);
      queryClient.invalidateQueries({ queryKey: ["incident", incidentId] });
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
    },
  });

  if (isLoading) {
    return (
      <div className="flex h-full flex-col">
        <div className="border-b px-6 py-4">
          <div className="flex items-center gap-3">
            <Skeleton className="h-5 w-48" />
            <Skeleton className="h-5 w-16 rounded-full" />
          </div>
          <Skeleton className="mt-2 h-4 w-72" />
        </div>
        <div className="flex-1 p-4 space-y-4">
          <Skeleton className="h-24 w-full rounded-lg" />
          <Skeleton className="h-16 w-full rounded-lg" />
          <Skeleton className="h-16 w-full rounded-lg" />
        </div>
      </div>
    );
  }

  if (isError || !incident) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4">
        <p className="text-sm text-muted-foreground">
          无法加载事件详情
        </p>
        <Button variant="outline" size="sm" nativeButton={false} render={<Link to="/incidents" />}>
          <ArrowLeft className="mr-1 h-4 w-4" />
          返回事件列表
        </Button>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Header */}
      <div className="border-b px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3 min-w-0">
            <h1 className="text-base font-medium truncate">
              {incident.summary_title || incident.description.slice(0, 30) + (incident.description.length > 30 ? "..." : "")}
            </h1>
            <Badge className={statusColors[incident.status]}>
              {statusLabels[incident.status] ?? incident.status}
            </Badge>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {isActive && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setStopDialogOpen(true)}
              >
                <Square className="mr-1 h-3.5 w-3.5" />
                停止
              </Button>
            )}
          </div>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          {incident.description}
        </p>
      </div>

      {/* Stop Dialog */}
      <AlertDialog open={stopDialogOpen} onOpenChange={setStopDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认停止</AlertDialogTitle>
            <AlertDialogDescription>
              停止后 Agent 将终止调查，此操作不可撤销。确定要停止吗？
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => stopMutation.mutate()}
              disabled={stopMutation.isPending}
            >
              确认停止
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Timeline */}
      <div
        ref={scrollRef}
        className="relative flex-1 min-h-0 overflow-auto"
      >
        <EventTimeline incidentId={incidentId} />
        <div ref={bottomRef} />

        {!isAtBottom && (
          <button
            className="sticky bottom-4 left-1/2 -translate-x-1/2 rounded-full border bg-background p-2 shadow-md transition-opacity hover:bg-accent"
            onClick={scrollToBottom}
          >
            <ArrowDown className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Input */}
      <UserInputBar incidentId={incidentId} incidentStatus={incident.status} />
    </div>
  );
}
