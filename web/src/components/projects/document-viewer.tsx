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
import { Markdown } from "@/components/ui/markdown";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";

interface DocumentViewerProps {
  documentId: string | null;
  onClose: () => void;
}

const EDITABLE_TYPES = new Set([
  "markdown",
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
  const isMarkdown = doc?.doc_type === "markdown";

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

    // PDF — iframe preview
    if (doc.doc_type === "pdf") {
      return (
        <iframe
          src={getDocumentFileUrl(doc.id)}
          className="h-full w-full border-0"
          title={doc.filename}
        />
      );
    }

    // Image — img preview
    if (doc.doc_type === "image") {
      return (
        <div className="flex items-center justify-center p-4">
          <img
            src={getDocumentFileUrl(doc.id)}
            alt={doc.filename}
            className="max-h-full max-w-full rounded object-contain"
          />
        </div>
      );
    }

    // Editing mode
    if (editing) {
      if (isMarkdown) {
        return (
          <Tabs defaultValue="edit" className="flex h-full flex-col">
            <TabsList className="mx-4 mt-2 w-fit">
              <TabsTrigger value="edit">编辑</TabsTrigger>
              <TabsTrigger value="preview">预览</TabsTrigger>
            </TabsList>
            <TabsContent value="edit" className="flex-1 overflow-hidden">
              <Textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                className="h-full resize-none rounded-none border-0 font-mono text-sm focus-visible:ring-0"
              />
            </TabsContent>
            <TabsContent value="preview" className="flex-1 overflow-auto p-4">
              <Markdown content={draft} />
            </TabsContent>
          </Tabs>
        );
      }

      // Other editable types — plain textarea
      return (
        <Textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="h-full resize-none rounded-none border-0 font-mono text-sm focus-visible:ring-0"
        />
      );
    }

    // Read-only: markdown rendered
    if (isMarkdown) {
      return (
        <ScrollArea className="h-full">
          <div className="p-4">
            <Markdown content={doc.content} />
          </div>
        </ScrollArea>
      );
    }

    // Read-only: word/excel/pptx — show extracted text as markdown
    if (["word", "excel", "pptx"].includes(doc.doc_type)) {
      return (
        <ScrollArea className="h-full">
          <div className="p-4">
            <Markdown content={doc.content} />
          </div>
        </ScrollArea>
      );
    }

    // Read-only: other text types — monospace
    return (
      <ScrollArea className="h-full">
        <pre className="whitespace-pre-wrap p-4 font-mono text-sm">
          {doc.content}
        </pre>
      </ScrollArea>
    );
  }

  return (
    <Sheet open={!!documentId} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="flex flex-col sm:max-w-3xl">
        <SheetHeader className="flex-row items-center justify-between gap-2 space-y-0">
          <SheetTitle className="truncate">
            {doc?.filename ?? "文档预览"}
          </SheetTitle>
          <div className="flex items-center gap-2">
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
        </SheetHeader>
        <div className="min-h-0 flex-1">{renderContent()}</div>
      </SheetContent>
    </Sheet>
  );
}
