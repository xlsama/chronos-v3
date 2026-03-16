import { useEffect } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Markdown } from "@tiptap/markdown";
import Placeholder from "@tiptap/extension-placeholder";
import Link from "@tiptap/extension-link";
import { cn } from "@/lib/utils";

interface MarkdownEditorProps {
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  placeholder?: string;
  minHeight?: number | string;
  maxHeight?: number | string;
  className?: string;
  disabled?: boolean;
  autoFocus?: boolean;
}

export function MarkdownEditor({
  value,
  onChange,
  onBlur,
  placeholder,
  minHeight,
  maxHeight,
  className,
  disabled,
  autoFocus,
}: MarkdownEditorProps) {
  const editor = useEditor({
    extensions: [
      StarterKit,
      Markdown,
      Placeholder.configure({ placeholder }),
      Link.configure({ autolink: true, openOnClick: false }),
    ],
    content: value,
    contentType: "markdown",
    immediatelyRender: false,
    autofocus: autoFocus ?? false,
    editable: !disabled,
    onUpdate: ({ editor }) => {
      onChange(editor.getMarkdown());
    },
    onBlur: () => onBlur?.(),
  });

  // Sync external value changes (e.g. form reset)
  useEffect(() => {
    if (!editor) return;
    const current = editor.getMarkdown();
    if (value !== current) {
      editor.commands.setContent(value, {
        emitUpdate: false,
        contentType: "markdown",
      });
    }
  }, [value, editor]);

  // Sync disabled state
  useEffect(() => {
    if (!editor) return;
    editor.setEditable(!disabled);
  }, [disabled, editor]);

  return (
    <div
      data-slot="markdown-editor"
      className={cn(
        "rounded-lg border border-input bg-transparent transition-colors",
        "has-[.tiptap.ProseMirror-focused]:border-ring has-[.tiptap.ProseMirror-focused]:ring-3 has-[.tiptap.ProseMirror-focused]:ring-ring/50",
        "dark:bg-input/30",
        disabled && "cursor-not-allowed opacity-50",
        className,
      )}
    >
      <EditorContent
        editor={editor}
        className={cn(
          "prose prose-sm max-w-none dark:prose-invert px-3 py-2",
          "[&_.tiptap.ProseMirror]:outline-none",
          "[&_.tiptap.ProseMirror_p.is-editor-empty:first-child::before]:text-muted-foreground [&_.tiptap.ProseMirror_p.is-editor-empty:first-child::before]:content-[attr(data-placeholder)] [&_.tiptap.ProseMirror_p.is-editor-empty:first-child::before]:float-left [&_.tiptap.ProseMirror_p.is-editor-empty:first-child::before]:pointer-events-none [&_.tiptap.ProseMirror_p.is-editor-empty:first-child::before]:h-0",
        )}
        style={{
          minHeight,
          maxHeight,
          overflowY: maxHeight ? "auto" : undefined,
        }}
      />
    </div>
  );
}
