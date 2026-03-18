import { useRef, useEffect, useCallback } from "react";
import { Markdown } from "@/components/ui/markdown";
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
  previewTransform?: (value: string) => string;
  variant?: "default" | "compact";
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
  previewTransform,
  variant = "default",
}: MarkdownEditorProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  const isSyncing = useRef(false);

  useEffect(() => {
    if (autoFocus && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [autoFocus]);

  const syncScroll = useCallback(
    (source: HTMLElement, target: HTMLElement) => {
      if (isSyncing.current) {
        isSyncing.current = false;
        return;
      }
      const maxScroll = source.scrollHeight - source.clientHeight;
      const ratio = maxScroll > 0 ? source.scrollTop / maxScroll : 0;
      isSyncing.current = true;
      target.scrollTop = ratio * (target.scrollHeight - target.clientHeight);
    },
    [],
  );

  return (
    <div
      data-slot="markdown-editor"
      className={cn(
        "grid grid-cols-2 overflow-hidden rounded-lg border border-input",
        disabled && "cursor-not-allowed opacity-50",
        className,
      )}
      style={{ minHeight, maxHeight }}
    >
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        placeholder={placeholder}
        disabled={disabled}
        className="resize-none border-r border-input bg-transparent p-3 font-mono text-sm outline-none placeholder:text-muted-foreground dark:bg-input/30"
        style={{ minHeight, maxHeight }}
        onScroll={() => {
          if (textareaRef.current && previewRef.current) {
            syncScroll(textareaRef.current, previewRef.current);
          }
        }}
      />
      <div
        ref={previewRef}
        className="overflow-y-auto p-3"
        style={{ minHeight, maxHeight }}
        onScroll={() => {
          if (previewRef.current && textareaRef.current) {
            syncScroll(previewRef.current, textareaRef.current);
          }
        }}
      >
        {value ? (
          <Markdown content={previewTransform ? previewTransform(value) : value} variant={variant} />
        ) : (
          <p className="text-sm text-muted-foreground">预览</p>
        )}
      </div>
    </div>
  );
}
