import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { FileText, Trash2 } from "lucide-react";
import dayjs from "@/lib/dayjs";
import { deleteDocument, getDocuments } from "@/api/documents";
import { CreateDocumentButton, UploadDocumentButton } from "./document-upload";
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
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { DocumentViewer } from "./document-viewer";

interface DocumentListProps {
  projectId: string;
}

const statusColors: Record<string, string> = {
  indexed: "bg-green-100 text-green-800 border-transparent",
  indexing: "bg-blue-100 text-blue-800 border-transparent",
  pending: "bg-yellow-100 text-yellow-800 border-transparent",
  error: "bg-red-100 text-red-800 border-transparent",
};

const statusLabels: Record<string, string> = {
  indexed: "已索引",
  indexing: "索引中",
  pending: "等待索引",
  error: "失败",
};

export function DocumentList({ projectId }: DocumentListProps) {
  const queryClient = useQueryClient();
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{
    id: string;
    filename: string;
  } | null>(null);

  const { data: documents, isLoading } = useQuery({
    queryKey: ["documents", projectId],
    queryFn: () => getDocuments(projectId),
    refetchInterval: (query) => {
      const docs = query.state.data;
      if (!docs) return false;
      const hasInProgress = docs.some(
        (d) => d.status === "pending" || d.status === "indexing",
      );
      return hasInProgress ? 2000 : false;
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteDocument,
    onSuccess: () => {
      toast.success("文档已删除");
      queryClient.invalidateQueries({ queryKey: ["documents", projectId] });
    },
  });

  if (isLoading) {
    return (
      <div className="divide-y rounded-lg border">
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3 p-3">
            <Skeleton className="h-4 w-4" />
            <div className="flex-1 space-y-1.5">
              <Skeleton className="h-3.5 w-32" />
              <Skeleton className="h-3 w-48" />
            </div>
            <Skeleton className="h-5 w-14 rounded-full" />
            <Skeleton className="h-8 w-8" />
          </div>
        ))}
      </div>
    );
  }

  if (!documents?.length) {
    return (
      <Empty className="rounded-lg border py-12">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <FileText />
          </EmptyMedia>
          <EmptyTitle>暂无文档</EmptyTitle>
          <EmptyDescription>
            上传或新建文档以开始构建知识库。
          </EmptyDescription>
        </EmptyHeader>
        <div className="mt-4 flex items-center justify-center gap-2">
          <UploadDocumentButton projectId={projectId} />
          <CreateDocumentButton projectId={projectId} />
        </div>
      </Empty>
    );
  }

  const sortedDocuments = [...documents].sort((a, b) => {
    if (a.doc_type === "service_map" && b.doc_type !== "service_map") return -1;
    if (a.doc_type !== "service_map" && b.doc_type === "service_map") return 1;
    return 0;
  });

  return (
    <>
      <div className="divide-y rounded-lg border">
        {sortedDocuments.map((doc) => (
          <div
            key={doc.id}
            className="flex cursor-pointer items-center gap-3 p-3 hover:bg-muted/50"
            onClick={() => setSelectedDocId(doc.id)}
          >
            <FileText className="h-4 w-4 text-muted-foreground" />
            <div className="flex-1">
              <p className="text-sm font-medium">{doc.filename}</p>
              <p className="text-xs text-muted-foreground">
                {doc.doc_type} &middot;{" "}
                {dayjs(doc.created_at).fromNow()}
              </p>
            </div>
            {doc.doc_type === "service_map" && (
              <Badge className="bg-blue-100 text-blue-800 border-transparent">
                内置
              </Badge>
            )}
            {doc.status === "error" && doc.error_message ? (
              <Tooltip>
                <TooltipTrigger render={<Badge className={statusColors.error} />}>
                    {statusLabels.error}
                </TooltipTrigger>
                <TooltipContent side="top" className="max-w-xs">
                  {doc.error_message}
                </TooltipContent>
              </Tooltip>
            ) : (
              <Badge
                className={
                  statusColors[doc.status] ??
                  "bg-gray-100 text-gray-800 border-transparent"
                }
              >
                {statusLabels[doc.status] ?? doc.status}
              </Badge>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                setDeleteTarget({ id: doc.id, filename: doc.filename });
              }}
              disabled={deleteMutation.isPending}
            >
              <Trash2 className="h-4 w-4 text-destructive" />
            </Button>
          </div>
        ))}
      </div>
      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除文档</AlertDialogTitle>
            <AlertDialogDescription>
              确定要删除 <strong>{deleteTarget?.filename}</strong>{" "}
              吗？该操作将同时清除向量数据库中的相关数据，且无法撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => {
                if (deleteTarget) deleteMutation.mutate(deleteTarget.id);
                setDeleteTarget(null);
              }}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? "删除中..." : "删除"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <DocumentViewer
        documentId={selectedDocId}
        onClose={() => setSelectedDocId(null)}
      />
    </>
  );
}
