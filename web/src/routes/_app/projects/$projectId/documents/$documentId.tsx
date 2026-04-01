import { useState } from "react";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import { ArrowLeft, History, Loader2, Pencil, Save, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { pageVariants, pageTransition } from "@/lib/motion";
import {
  deleteDocument,
  getDocument,
  getDocumentFileUrl,
  updateDocument,
} from "@/api/documents";
import { VersionHistoryDialog } from "@/components/version-history/version-history-dialog";
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
import { Button } from "@/components/ui/button";
import { FilePreview, type FileType } from "@/components/ui/file-preview";
import { Markdown } from "@/components/ui/markdown";
import { MarkdownEditor } from "@/components/ui/markdown-editor";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { QueryContent } from "@/components/query-content";

export const Route = createFileRoute(
  "/_app/projects/$projectId/documents/$documentId",
)({
  component: DocumentDetailPage,
});

const EDITABLE_TYPES = new Set([
  "markdown",
  "agents_config",
  "text",
  "log",
  "json",
  "yaml",
  "csv",
  "html",
]);

function DocumentDetailPage() {
  const { projectId, documentId } = Route.useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string | null>(null);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  const { data: doc, isLoading } = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => getDocument(documentId),
  });

  const isEditable = doc ? EDITABLE_TYPES.has(doc.doc_type) : false;
  const isMarkdown =
    doc?.doc_type === "markdown" || doc?.doc_type === "agents_config";
  const canDelete = doc ? doc.doc_type !== "agents_config" : false;

  function startEditing() {
    if (doc) {
      setDraft(doc.content);
      setEditing(true);
    }
  }

  function cancelEditing() {
    setEditing(false);
    setDraft(null);
  }

  const saveMutation = useMutation({
    mutationFn: () => updateDocument(documentId, draft!),
    onSuccess: () => {
      toast.success("文档已保存");
      setEditing(false);
      setDraft(null);
      queryClient.invalidateQueries({ queryKey: ["document", documentId] });
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteDocument(documentId),
    onSuccess: () => {
      toast.success("文档已删除");
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      navigate({ to: "/projects/$projectId", params: { projectId } });
    },
  });

  function renderDocContent(doc: NonNullable<typeof doc>) {
    // Editing mode
    if (editing && draft !== null) {
      if (isMarkdown) {
        return (
          <MarkdownEditor
            value={draft}
            onChange={setDraft}
            className="h-full"
            autoFocus
            variant="default"
          />
        );
      }
      return (
        <Textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="h-full resize-none rounded-none border-0 font-mono text-sm focus-visible:ring-0"
        />
      );
    }

    // View mode: markdown preview
    if (isMarkdown) {
      return (
        <ScrollArea className="h-full" scrollToTop>
          <div className="px-10 py-4">
            <Markdown content={doc.content} />
          </div>
        </ScrollArea>
      );
    }

    // View mode: editable text types (read-only display)
    if (isEditable) {
      return (
        <ScrollArea className="h-full" scrollToTop>
          <pre className="whitespace-pre-wrap p-4 font-mono text-sm">
            {doc.content}
          </pre>
        </ScrollArea>
      );
    }

    // Non-editable: file preview
    return (
      <FilePreview
        content={doc.content}
        fileType={doc.doc_type as FileType}
        fileUrl={getDocumentFileUrl(doc.id)}
        filename={doc.filename}
      />
    );
  }

  return (
    <motion.div
      className="flex h-full flex-col"
      variants={pageVariants}
      initial="initial"
      animate="animate"
      transition={pageTransition}
    >
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div className="flex items-center gap-3 min-w-0">
          <Link to="/projects/$projectId" params={{ projectId }}>
            <Button variant="ghost" size="icon-sm">
              <ArrowLeft className="h-4 w-4" />
            </Button>
          </Link>
          <h1 className="text-base font-medium truncate">
            {doc?.filename ?? "文档"}
          </h1>
        </div>
        <div className="flex items-center gap-2">
          {editing ? (
            <>
              <Button size="sm" variant="outline" onClick={cancelEditing}>
                取消
              </Button>
              <Button
                size="sm"
                onClick={() => saveMutation.mutate()}
                disabled={saveMutation.isPending || draft === null}
              >
                {saveMutation.isPending ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Save className="mr-1.5 h-3.5 w-3.5" />
                )}
                保存
              </Button>
            </>
          ) : (
            <>
              {isEditable && (
                <Button size="sm" variant="outline" onClick={startEditing}>
                  <Pencil className="mr-1.5 h-3.5 w-3.5" />
                  编辑
                </Button>
              )}
              {doc?.doc_type === "agents_config" && (
                <Button size="sm" variant="outline" onClick={() => setShowHistory(true)}>
                  <History className="mr-1.5 h-3.5 w-3.5" />
                  更新历史
                </Button>
              )}
            </>
          )}
          {canDelete && (
            <Button
              size="sm"
              variant="destructive"
              onClick={() => setShowDeleteDialog(true)}
            >
              <Trash2 className="mr-1.5 h-3.5 w-3.5" />
              删除
            </Button>
          )}
        </div>
      </div>
      {doc?.doc_type === "agents_config" && (
        <p className="px-6 py-2 text-xs text-muted-foreground">
          此文档会在事件解决后自动更新 ——
          系统从排查对话中提取架构拓扑、服务配置和排查经验等运维知识，增量补充到文档中。
        </p>
      )}
      <div className="min-h-0 flex-1">
        <QueryContent
          isLoading={isLoading}
          data={doc}
          className="h-full"
          skeleton={
            <div className="space-y-3 p-4">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          }
          empty={<div />}
        >
          {(doc) => renderDocContent(doc)}
        </QueryContent>
      </div>

      <AlertDialog
        open={showDeleteDialog}
        onOpenChange={(open) => !open && setShowDeleteDialog(false)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除文档</AlertDialogTitle>
            <AlertDialogDescription>
              确定要删除 <strong>{doc?.filename}</strong>{" "}
              吗？该操作将同时清除向量数据库中的相关数据，且无法撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => deleteMutation.mutate()}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? "删除中..." : "删除"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <VersionHistoryDialog
        open={showHistory}
        onOpenChange={setShowHistory}
        entityType="agents_md"
        entityId={documentId}
        title="AGENTS.md 更新历史"
      />
    </motion.div>
  );
}
