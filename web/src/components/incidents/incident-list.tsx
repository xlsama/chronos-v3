import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { motion } from "motion/react";
import { AlertCircle, FileText, Square } from "lucide-react";
import dayjs from "@/lib/dayjs";
import { getIncidents, stopIncident } from "@/api/incidents";
import { getAttachmentUrl } from "@/api/attachments";
import type { Attachment } from "@/lib/types";
import { isImageType } from "@/lib/file-utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { AttachmentPreviewDialog } from "@/components/incidents/attachment-preview-dialog";
import { severityColors, statusColors, statusLabels } from "@/lib/incident-constants";

export function IncidentList() {
  const queryClient = useQueryClient();
  const { data: incidents, isLoading } = useQuery({
    queryKey: ["incidents"],
    queryFn: getIncidents,
  });

  const [stopDialogId, setStopDialogId] = useState<string | null>(null);
  const [previewAttachment, setPreviewAttachment] = useState<Attachment | null>(null);

  const stopMutation = useMutation({
    mutationFn: (id: string) => stopIncident(id),
    onSuccess: () => {
      setStopDialogId(null);
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
    },
  });

  if (isLoading) {
    return (
      <div className="divide-y">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 p-4">
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-48" />
              <Skeleton className="h-3 w-72" />
            </div>
            <Skeleton className="h-5 w-16 rounded-full" />
            <Skeleton className="h-5 w-16 rounded-full" />
          </div>
        ))}
      </div>
    );
  }

  if (!incidents?.length) {
    return (
      <Empty className="py-12">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <AlertCircle />
          </EmptyMedia>
          <EmptyTitle>暂无事件</EmptyTitle>
          <EmptyDescription>创建一个以开始使用。</EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  const isActive = (status: string) => status === "open" || status === "investigating";

  return (
    <>
      <div className="divide-y">
        {incidents.map((incident, i) => (
          <motion.div
            key={incident.id}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25, delay: i * 0.05 }}
          >
            <Link
              to="/incidents/$incidentId"
              params={{ incidentId: incident.id }}
              className="flex items-center gap-4 p-4 transition-colors hover:bg-muted/50"
            >
              <div className="flex-1 space-y-1">
                <p className="text-sm font-medium">{incident.summary_title || incident.description.slice(0, 80) + (incident.description.length > 80 ? "..." : "")}</p>
                <p className="text-xs text-muted-foreground line-clamp-1">
                  {incident.description}
                </p>
                {incident.attachments && incident.attachments.length > 0 && (
                  <div className="mt-1.5 flex items-center gap-1.5">
                    {incident.attachments.slice(0, 4).map((att) => (
                      <button
                        key={att.id}
                        type="button"
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setPreviewAttachment(att);
                        }}
                        className="shrink-0 overflow-hidden rounded border transition-opacity hover:opacity-80"
                      >
                        {isImageType(att.content_type) ? (
                          <img
                            src={getAttachmentUrl(att.id)}
                            alt={att.filename}
                            className="size-8 rounded object-cover"
                          />
                        ) : (
                          <div className="flex size-8 items-center justify-center bg-muted text-muted-foreground">
                            <FileText className="size-3.5" />
                          </div>
                        )}
                      </button>
                    ))}
                    {incident.attachments.length > 4 && (
                      <span className="text-xs text-muted-foreground">
                        +{incident.attachments.length - 4}
                      </span>
                    )}
                  </div>
                )}
              </div>
              <Badge className={severityColors[incident.severity]}>
                {incident.severity}
              </Badge>
              <Badge className={statusColors[incident.status]}>
                {statusLabels[incident.status] ?? incident.status}
              </Badge>
              <span className="text-xs text-muted-foreground">
                {dayjs(incident.created_at).fromNow()}
              </span>
              {isActive(incident.status) && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 shrink-0 text-muted-foreground hover:text-destructive"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    setStopDialogId(incident.id);
                  }}
                >
                  <Square className="h-4 w-4" />
                </Button>
              )}
            </Link>
          </motion.div>
        ))}
      </div>

      <AlertDialog open={!!stopDialogId} onOpenChange={(open) => !open && setStopDialogId(null)}>
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
              onClick={() => stopDialogId && stopMutation.mutate(stopDialogId)}
              disabled={stopMutation.isPending}
            >
              确认停止
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AttachmentPreviewDialog
        attachment={previewAttachment}
        open={!!previewAttachment}
        onOpenChange={(open) => !open && setPreviewAttachment(null)}
      />
    </>
  );
}
