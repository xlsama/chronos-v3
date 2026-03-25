import { createFileRoute } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { motion, AnimatePresence } from "motion/react";
import { ArrowDown, ArrowLeft, Info, Square } from "lucide-react";
import { getIncident, stopIncident } from "@/api/incidents";
import { pageVariants, pageTransition } from "@/lib/motion";
import { useIncidentStream } from "@/hooks/use-incident-stream";
import { useIncidentStreamStore } from "@/stores/incident-stream";
import { useAutoScroll } from "@/hooks/use-auto-scroll";
import { EventTimeline } from "@/components/incidents/incident-detail/event-timeline";
import { UserInputBar } from "@/components/incidents/incident-detail/user-input-bar";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import { QueryContent } from "@/components/query-content";
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

  const isConnected = useIncidentStreamStore((s) => s.isConnected);
  const [stopDialogOpen, setStopDialogOpen] = useState(false);

  const isActive = incident?.status === "open" || incident?.status === "investigating" || incident?.status === "interrupted";

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

  if (isError) {
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
    <motion.div
      className="h-full"
      variants={pageVariants}
      initial="initial"
      animate="animate"
      transition={pageTransition}
    >
    <QueryContent
      isLoading={isLoading}
      data={incident}
      className="h-full"
      skeleton={
        <div className="flex h-full flex-col">
          <div className="border-b px-6 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Skeleton className="h-5 w-48" />
              </div>
              <Skeleton className="h-5 w-16 rounded-full" />
            </div>
          </div>
          <div className="flex-1 p-4 space-y-4">
            <Skeleton className="h-24 w-full rounded-lg" />
            <Skeleton className="h-16 w-full rounded-lg" />
            <Skeleton className="h-16 w-full rounded-lg" />
          </div>
        </div>
      }
      empty={
        <div className="flex h-full flex-col items-center justify-center gap-4">
          <p className="text-sm text-muted-foreground">
            无法加载事件详情
          </p>
          <Button variant="outline" size="sm" nativeButton={false} render={<Link to="/incidents" />}>
            <ArrowLeft className="mr-1 h-4 w-4" />
            返回事件列表
          </Button>
        </div>
      }
    >
      {(incident) => (
    <div className="flex h-full min-h-0 flex-col">
      {/* Header */}
      <div className="border-b px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3 min-w-0">
            <Link to="/incidents">
              <Button variant="ghost" size="icon-sm">
                <ArrowLeft className="h-4 w-4" />
              </Button>
            </Link>
            <h1 className="text-base font-medium truncate">
              {incident.summary_title || incident.description.slice(0, 30) + (incident.description.length > 30 ? "..." : "")}
            </h1>
            <Popover>
              <PopoverTrigger openOnHover delay={0} render={<Button variant="ghost" size="icon-sm" />}>
                <Info className="h-4 w-4 text-muted-foreground" />
              </PopoverTrigger>
              <PopoverContent side="bottom" align="start" className="max-w-sm">
                <p className="text-sm whitespace-pre-wrap">{incident.description}</p>
              </PopoverContent>
            </Popover>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {isActive && (
              isConnected ? (
                <span className="h-2 w-2 rounded-full bg-green-500" title="已连接" />
              ) : (
                <span className="flex items-center gap-1.5" title="连接中断">
                  <span className="relative flex h-2 w-2">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75" />
                    <span className="relative inline-flex h-2 w-2 rounded-full bg-amber-500" />
                  </span>
                  <span className="text-xs text-amber-600">连接中断</span>
                </span>
              )
            )}
            <AnimatePresence mode="wait">
              <motion.span
                key={incident.status}
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.8 }}
                transition={{ duration: 0.2 }}
              >
                <Badge className={statusColors[incident.status]}>
                  {statusLabels[incident.status] ?? incident.status}
                </Badge>
              </motion.span>
            </AnimatePresence>
            {isActive && (
              <Button
                variant="outline"
                size="sm"
                className="hover:text-destructive hover:bg-destructive/10 hover:border-transparent"
                onClick={() => setStopDialogOpen(true)}
              >
                <Square className="mr-1 h-3.5 w-3.5" />
                终止事件
              </Button>
            )}
          </div>
        </div>
      </div>

      {/* Stop Dialog */}
      <AlertDialog open={stopDialogOpen} onOpenChange={setStopDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认终止事件</AlertDialogTitle>
            <AlertDialogDescription>
              终止后 Agent 将永久停止调查，此操作不可撤销。确定要终止吗？
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => stopMutation.mutate()}
              disabled={stopMutation.isPending}
            >
              确认终止
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Timeline */}
      <div
        ref={scrollRef}
        className="relative flex-1 min-h-0 overflow-auto"
      >
        <EventTimeline incidentId={incidentId} incidentStatus={incident.status} />
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
      )}
    </QueryContent>
    </motion.div>
  );
}
