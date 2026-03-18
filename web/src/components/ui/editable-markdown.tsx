import { useState } from "react";
import { Eye, Loader2, Pencil, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Markdown } from "@/components/ui/markdown";
import { MarkdownEditor } from "@/components/ui/markdown-editor";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

interface EditableMarkdownProps {
  content: string;
  onSave: (content: string) => Promise<void>;
  variant?: "default" | "compact";
  className?: string;
}

export function EditableMarkdown({
  content,
  onSave,
  variant = "default",
  className,
}: EditableMarkdownProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [isPending, setIsPending] = useState(false);

  function startEditing() {
    setDraft(content);
    setEditing(true);
  }

  async function save() {
    setIsPending(true);
    try {
      await onSave(draft);
      setEditing(false);
    } finally {
      setIsPending(false);
    }
  }

  return (
    <div className={cn("flex h-full flex-col", className)}>
      <div className="flex justify-end px-4 py-2">
        {!editing ? (
          <Button variant="outline" size="sm" onClick={startEditing}>
            <Pencil className="mr-1.5 h-3.5 w-3.5" />
            编辑
          </Button>
        ) : (
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setEditing(false)}
            >
              <Eye className="mr-1.5 h-3.5 w-3.5" />
              取消
            </Button>
            <Button size="sm" onClick={save} disabled={isPending}>
              {isPending ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Save className="mr-1.5 h-3.5 w-3.5" />
              )}
              保存
            </Button>
          </div>
        )}
      </div>
      <div className="min-h-0 flex-1">
        {editing ? (
          <div className="h-full px-4 pb-4">
            <MarkdownEditor
              value={draft}
              onChange={setDraft}
              className="h-full"
              autoFocus
            />
          </div>
        ) : (
          <ScrollArea className="h-full">
            <div className="p-4">
              <Markdown content={content} variant={variant} />
            </div>
          </ScrollArea>
        )}
      </div>
    </div>
  );
}
