import { useState, useEffect } from "react";
import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { motion } from "motion/react";
import { AlertCircle, Archive, EllipsisVertical, FileText, Square } from "lucide-react";
import { listVariants, listItemVariants } from "@/lib/motion";
import dayjs from "@/lib/dayjs";
import { archiveIncident, getIncidents, stopIncident } from "@/api/incidents";
import { getAttachmentUrl } from "@/api/attachments";
import type { Attachment } from "@/lib/types";
import { PhotoView } from "react-photo-view";
import { isImageType } from "@/lib/file-utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConstrainedPhotoProvider } from "@/components/ui/constrained-photo-provider";
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { QueryContent } from "@/components/query-content";
import { AttachmentPreviewDialog } from "@/components/incidents/attachment-preview-dialog";
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import { severityColors, statusColors, statusLabels } from "@/lib/incident-constants";

export const STATUS_OPTIONS = [
  { value: "all", label: "全部" },
  { value: "open", label: "待处理" },
  { value: "investigating", label: "调查中" },
  { value: "resolved", label: "已解决" },
  { value: "interrupted", label: "已中断" },
  { value: "stopped", label: "已停止" },
] as const;

export const SEVERITY_OPTIONS = [
  { value: "all", label: "全部" },
  { value: "P0", label: "P0" },
  { value: "P1", label: "P1" },
  { value: "P2", label: "P2" },
  { value: "P3", label: "P3" },
] as const;

export const STATUS_LABELS = Object.fromEntries(STATUS_OPTIONS.map((o) => [o.value, o.label])) as Record<string, string>;
export const SEVERITY_LABELS = Object.fromEntries(SEVERITY_OPTIONS.map((o) => [o.value, o.label])) as Record<string, string>;

function generatePageNumbers(currentPage: number, totalPages: number): (number | "ellipsis")[] {
  const pages: (number | "ellipsis")[] = [];
  const delta = 1;
  const rangeStart = Math.max(2, currentPage - delta);
  const rangeEnd = Math.min(totalPages - 1, currentPage + delta);

  pages.push(1);
  if (rangeStart > 2) pages.push("ellipsis");
  for (let i = rangeStart; i <= rangeEnd; i++) pages.push(i);
  if (rangeEnd < totalPages - 1) pages.push("ellipsis");
  if (totalPages > 1) pages.push(totalPages);

  return pages;
}

interface IncidentListProps {
  statusFilter: string;
  severityFilter: string;
}

export function IncidentList({ statusFilter, severityFilter }: IncidentListProps) {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const pageSize = 10;

  useEffect(() => {
    // oxlint-disable-next-line react/set-state-in-effect -- reset pagination when filters change
    setPage(1);
  }, [statusFilter, severityFilter]);

  const { data, isLoading, isPlaceholderData } = useQuery({
    queryKey: ["incidents", statusFilter, severityFilter, page],
    queryFn: () =>
      getIncidents({
        status: statusFilter === "all" ? undefined : statusFilter,
        severity: severityFilter === "all" ? undefined : severityFilter,
        page,
        page_size: pageSize,
      }),
    placeholderData: keepPreviousData,
    refetchInterval: 5000,
  });

  const incidents = data?.items;
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / pageSize);

  const [stopDialogId, setStopDialogId] = useState<string | null>(null);
  const [archiveDialogId, setArchiveDialogId] = useState<string | null>(null);
  const [previewAttachment, setPreviewAttachment] = useState<Attachment | null>(null);

  const stopMutation = useMutation({
    mutationFn: (id: string) => stopIncident(id),
    onSuccess: () => {
      setStopDialogId(null);
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
    },
  });

  const archiveMutation = useMutation({
    mutationFn: (id: string) => archiveIncident(id),
    onSuccess: () => {
      setArchiveDialogId(null);
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
    },
  });

  const isActive = (status: string) => status === "open" || status === "investigating";

  return (
    <>
      <div className="flex flex-1 flex-col min-h-0">
        <div className="flex-1 overflow-y-auto min-h-0">
          <QueryContent
            isLoading={isLoading}
            data={data}
            isEmpty={(d) => !d.items?.length}
            skeleton={
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
            }
            empty={
              <Empty className="pt-[20vh]">
                <EmptyHeader>
                  <EmptyMedia variant="icon">
                    <AlertCircle />
                  </EmptyMedia>
                  <EmptyTitle>暂无事件</EmptyTitle>
                  <EmptyDescription>快让你的 Agent 帮你排查问题吧。</EmptyDescription>
                </EmptyHeader>
              </Empty>
            }
          >
            {() => (
              <div className={isPlaceholderData ? "opacity-60 transition-opacity" : "transition-opacity"}>
                <motion.div variants={listVariants} initial="initial" animate="animate">
                  {incidents!.map((incident) => (
                    <motion.div
                      key={incident.id}
                      variants={listItemVariants}
                    >
                      <div className="group relative">
                        <Link
                          to="/incidents/$incidentId"
                          params={{ incidentId: incident.id }}
                          className="flex items-center gap-4 border-l-2 border-l-transparent p-4 pr-12 transition-colors hover:bg-muted/50 hover:border-l-primary/60"
                        >
                          <div className="flex-1 space-y-1">
                            <p className="text-sm">{incident.summary_title || incident.description.slice(0, 80) + (incident.description.length > 80 ? "..." : "")}</p>
                            <p className="text-xs text-muted-foreground line-clamp-1">
                              {incident.description}
                            </p>
                            {incident.attachments && incident.attachments.length > 0 && (
                              <div
                                className="mt-1.5 flex items-center gap-1.5"
                                onClick={(e) => { e.preventDefault(); e.stopPropagation(); }}
                              >
                                <ConstrainedPhotoProvider>
                                  {incident.attachments
                                    .slice(0, 4)
                                    .filter((att) => isImageType(att.content_type))
                                    .map((att) => (
                                      <PhotoView key={att.id} src={getAttachmentUrl(att.id)}>
                                        <button
                                          type="button"
                                          className="shrink-0 overflow-hidden rounded border transition-opacity hover:opacity-80"
                                        >
                                          <img
                                            src={getAttachmentUrl(att.id)}
                                            alt={att.filename}
                                            className="size-8 rounded object-cover"
                                          />
                                        </button>
                                      </PhotoView>
                                    ))}
                                </ConstrainedPhotoProvider>
                                {incident.attachments
                                  .slice(0, 4)
                                  .filter((att) => !isImageType(att.content_type))
                                  .map((att) => (
                                    <button
                                      key={att.id}
                                      type="button"
                                      onClick={() => setPreviewAttachment(att)}
                                      className="shrink-0 overflow-hidden rounded border transition-opacity hover:opacity-80"
                                    >
                                      <div className="flex size-8 items-center justify-center bg-muted text-muted-foreground">
                                        <FileText className="size-3.5" />
                                      </div>
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
                          <Badge className={`w-fit justify-center ${statusColors[incident.status]}`}>
                            {statusLabels[incident.status] ?? incident.status}
                          </Badge>
                          <Badge className={`justify-center ${severityColors[incident.severity]}`}>
                            {incident.severity}
                          </Badge>
                          <span className="w-14 shrink-0 text-right text-xs text-muted-foreground">
                            {dayjs(incident.created_at).fromNow()}
                          </span>
                        </Link>
                        <div className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity">
                          <DropdownMenu>
                            <DropdownMenuTrigger render={<Button variant="ghost" size="icon-sm" />}>
                              <EllipsisVertical className="h-4 w-4" />
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem onClick={() => setArchiveDialogId(incident.id)}>
                                <Archive className="mr-2 h-4 w-4" />
                                归档
                              </DropdownMenuItem>
                              {isActive(incident.status) && (
                                <DropdownMenuItem
                                  variant="destructive"
                                  onClick={() => setStopDialogId(incident.id)}
                                >
                                  <Square className="mr-2 h-4 w-4" />
                                  终止
                                </DropdownMenuItem>
                              )}
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </div>
                      </div>
                    </motion.div>
                  ))}
                </motion.div>
              </div>
            )}
          </QueryContent>
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-center px-4 py-6 shrink-0">
            <Pagination>
              <PaginationContent>
                <PaginationItem>
                  <PaginationPrevious
                    text="上一页"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    aria-disabled={page <= 1}
                    className={page <= 1 ? "pointer-events-none opacity-50" : "cursor-pointer"}
                  />
                </PaginationItem>
                {generatePageNumbers(page, totalPages).map((pageNum, idx) =>
                  pageNum === "ellipsis" ? (
                    <PaginationItem key={`ellipsis-${idx}`}>
                      <PaginationEllipsis />
                    </PaginationItem>
                  ) : (
                    <PaginationItem key={pageNum}>
                      <PaginationLink
                        isActive={pageNum === page}
                        onClick={() => setPage(pageNum as number)}
                        className="cursor-pointer"
                      >
                        {pageNum}
                      </PaginationLink>
                    </PaginationItem>
                  ),
                )}
                <PaginationItem>
                  <PaginationNext
                    text="下一页"
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    aria-disabled={page >= totalPages}
                    className={page >= totalPages ? "pointer-events-none opacity-50" : "cursor-pointer"}
                  />
                </PaginationItem>
              </PaginationContent>
            </Pagination>
          </div>
        )}
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

      <AlertDialog open={!!archiveDialogId} onOpenChange={(open) => !open && setArchiveDialogId(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认归档</AlertDialogTitle>
            <AlertDialogDescription>
              归档后事件将从列表中移除。确定要归档吗？
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => archiveDialogId && archiveMutation.mutate(archiveDialogId)}
              disabled={archiveMutation.isPending}
            >
              确认归档
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
