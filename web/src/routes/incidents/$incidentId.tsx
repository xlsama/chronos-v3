import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useEffect, useCallback, useState } from "react";
import { ArrowDown, Square } from "lucide-react";
import { getIncident, stopIncident } from "@/api/incidents";
import { useIncidentStream } from "@/hooks/use-incident-stream";
import { EventTimeline } from "@/components/incidents/incident-detail/event-timeline";
import { UserInputBar } from "@/components/incidents/incident-detail/user-input-bar";
import { useIncidentStreamStore } from "@/stores/incident-stream";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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

export const Route = createFileRoute("/incidents/$incidentId")({
  component: IncidentDetailPage,
});

function IncidentDetailPage() {
  const { incidentId } = Route.useParams();
  const queryClient = useQueryClient();
  const { events, thinkingContent, phaseState } = useIncidentStreamStore();

  const { data: incident } = useQuery({
    queryKey: ["incident", incidentId],
    queryFn: () => getIncident(incidentId),
  });

  useIncidentStream(incidentId, incident?.status);

  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const shouldAutoScroll = useRef(true);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const [stopDialogOpen, setStopDialogOpen] = useState(false);

  const isActive = incident?.status === "open" || incident?.status === "investigating";

  const stopMutation = useMutation({
    mutationFn: () => stopIncident(incidentId),
    onSuccess: () => {
      setStopDialogOpen(false);
      queryClient.invalidateQueries({ queryKey: ["incident", incidentId] });
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
    },
  });

  const checkIsAtBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const threshold = 100;
    const atBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
    shouldAutoScroll.current = atBottom;
    setIsAtBottom(atBottom);
  }, []);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    if (phaseState.contextGathering === "active") return;
    if (shouldAutoScroll.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [events.length, thinkingContent, phaseState.contextGathering]);

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3 min-w-0">
            <h1 className="text-base font-medium truncate">
              {incident?.summary_title || (incident ? incident.description.slice(0, 30) + (incident.description.length > 30 ? "..." : "") : "Loading...")}
            </h1>
            {incident && (
              <Badge className={statusColors[incident.status]}>
                {statusLabels[incident.status] ?? incident.status}
              </Badge>
            )}
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
        {incident && (
          <p className="mt-1 text-sm text-muted-foreground">
            {incident.description}
          </p>
        )}
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
        className="relative flex-1 overflow-auto"
        onScroll={checkIsAtBottom}
      >
        <EventTimeline
          summaryMarkdown={incident?.summary_md}
        />
        <div ref={bottomRef} />

        {!isAtBottom && (
          <button
            className="sticky bottom-4 left-full -translate-x-8 rounded-full border bg-background p-2 shadow-md transition-opacity hover:bg-accent"
            onClick={scrollToBottom}
          >
            <ArrowDown className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Input */}
      <UserInputBar incidentId={incidentId} incidentStatus={incident?.status} />
    </div>
  );
}
