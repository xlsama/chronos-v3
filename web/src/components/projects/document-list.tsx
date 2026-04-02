import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { motion } from "motion/react";
import { toast } from "sonner";
import { FileText, Trash2 } from "lucide-react";
import { listVariants, listItemVariants } from "@/lib/motion";
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
import { QueryContent } from "@/components/query-content";

interface DocumentListProps {
  projectId: string;
}

const statusColors: Record<string, string> = {
  indexed: "bg-emerald-50 text-emerald-700 border-transparent dark:bg-emerald-950/40 dark:text-emerald-400",
  indexing: "bg-sky-50 text-sky-700 border-transparent dark:bg-sky-950/40 dark:text-sky-400",
  pending: "bg-amber-50 text-amber-700 border-transparent dark:bg-amber-950/40 dark:text-amber-400",
  index_failed: "bg-red-50 text-red-700 border-transparent dark:bg-red-950/40 dark:text-red-400",
};

const statusLabels: Record<string, string> = {
  indexed: "已索引",
  indexing: "索引中",
  pending: "等待索引",
  index_failed: "索引失败",
};

export function DocumentList({ projectId }: DocumentListProps) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
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

  return (
    <>
      <QueryContent
        isLoading={isLoading}
        data={documents}
        isEmpty={(d) => !d.length}
        skeleton={
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
        }
        empty={
          <Empty className="pt-[20vh]">
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
        }
      >
        {(documents) => {
          const sortedDocuments = [...documents].sort((a, b) => {
            if (a.doc_type === "memory_config" && b.doc_type !== "memory_config") return -1;
            if (a.doc_type !== "memory_config" && b.doc_type === "memory_config") return 1;
            return 0;
          });

          return (
            <motion.div className="divide-y rounded-lg border" variants={listVariants} initial="initial" animate="animate">
              {sortedDocuments.map((doc) => (
                <motion.div
                  key={doc.id}
                  variants={listItemVariants}
                  className="flex cursor-pointer items-center gap-3 p-3 hover:bg-muted/50"
                  onClick={() =>
                    navigate({
                      to: "/projects/$projectId/documents/$documentId",
                      params: { projectId, documentId: doc.id },
                    })
                  }
                >
                  <FileText className="h-4 w-4 text-muted-foreground" />
                  <div className="flex-1">
                    <p className="text-sm font-medium">{doc.filename}</p>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                      {dayjs(doc.updated_at).fromNow()}
                    </p>
                  </div>
                  {doc.doc_type === "memory_config" && (
                    <Badge className="bg-slate-50 text-slate-600 border-transparent dark:bg-slate-800/40 dark:text-slate-400">
                      概要
                    </Badge>
                  )}
                  {doc.doc_type !== "memory_config" &&
                    (doc.status === "index_failed" && doc.error_message ? (
                      <Tooltip>
                        <TooltipTrigger render={<Badge className={statusColors.index_failed} />}>
                            {statusLabels.index_failed}
                        </TooltipTrigger>
                        <TooltipContent side="top" className="max-w-xs">
                          {doc.error_message}
                        </TooltipContent>
                      </Tooltip>
                    ) : (
                      <Badge
                        className={
                          statusColors[doc.status] ??
                          "bg-slate-50 text-slate-600 border-transparent dark:bg-slate-800/40 dark:text-slate-400"
                        }
                      >
                        {statusLabels[doc.status] ?? doc.status}
                      </Badge>
                    ))}
                  {doc.doc_type !== "memory_config" && (
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
                  )}
                </motion.div>
              ))}
            </motion.div>
          );
        }}
      </QueryContent>
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
    </>
  );
}
