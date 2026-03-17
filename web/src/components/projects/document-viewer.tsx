import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Eye, Save, Loader2 } from "lucide-react";
import { toast } from "sonner";
import {
  getDocument,
  getDocumentFileUrl,
  updateDocument,
} from "@/api/documents";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { FilePreview, type FileType } from "@/components/ui/file-preview";
import { MarkdownEditor } from "@/components/ui/markdown-editor";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";

interface DocumentViewerProps {
  documentId: string | null;
  onClose: () => void;
}

const EDITABLE_TYPES = new Set([
  "markdown",
  "service_map",
  "text",
  "log",
  "json",
  "yaml",
  "csv",
  "html",
]);

export function DocumentViewer({ documentId, onClose }: DocumentViewerProps) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");

  const { data: doc, isLoading } = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => getDocument(documentId!),
    enabled: !!documentId,
  });

  const saveMutation = useMutation({
    mutationFn: () => updateDocument(documentId!, draft),
    onSuccess: () => {
      toast.success("文档已保存");
      setEditing(false);
      queryClient.invalidateQueries({ queryKey: ["document", documentId] });
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const isEditable = doc ? EDITABLE_TYPES.has(doc.doc_type) : false;
  const isMarkdown = doc?.doc_type === "markdown" || doc?.doc_type === "service_map";

  function startEditing() {
    if (doc) {
      setDraft(doc.content);
      setEditing(true);
    }
  }

  function renderContent() {
    if (isLoading) {
      return (
        <div className="space-y-3 p-4">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      );
    }

    if (!doc) return null;

    // 编辑模式
    if (editing) {
      if (isMarkdown) {
        return (
          <div className="h-full p-4">
            <MarkdownEditor
              value={draft}
              onChange={setDraft}
              className="h-full border-0"
            />
          </div>
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

    // 只读模式 — 委托给通用 FilePreview
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
    <Dialog open={!!documentId} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="flex h-[90vh] flex-col sm:max-w-[80vw]">
        <DialogHeader className="flex-row items-center justify-between gap-2 space-y-0">
          <DialogTitle className="truncate">
            {doc?.filename ?? "文档预览"}
          </DialogTitle>
          <div className="mr-6 flex items-center gap-2">
            {isEditable && !editing && (
              <Button variant="outline" size="sm" onClick={startEditing}>
                <Pencil className="mr-1.5 h-3.5 w-3.5" />
                编辑
              </Button>
            )}
            {editing && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setEditing(false)}
                >
                  <Eye className="mr-1.5 h-3.5 w-3.5" />
                  取消
                </Button>
                <Button
                  size="sm"
                  onClick={() => saveMutation.mutate()}
                  disabled={saveMutation.isPending}
                >
                  {saveMutation.isPending ? (
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Save className="mr-1.5 h-3.5 w-3.5" />
                  )}
                  保存
                </Button>
              </>
            )}
          </div>
        </DialogHeader>
        <div className="min-h-0 flex-1">{renderContent()}</div>
      </DialogContent>
    </Dialog>
  );
}
