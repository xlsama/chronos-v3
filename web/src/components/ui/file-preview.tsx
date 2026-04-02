import { cn } from "@/lib/utils";
import { ImagePreview } from "@/components/ui/image-preview";
import { Markdown } from "@/components/ui/markdown";
import { ScrollArea } from "@/components/ui/scroll-area";

export type FileType =
  | "markdown"
  | "memory_config"
  | "text"
  | "log"
  | "json"
  | "yaml"
  | "csv"
  | "html"
  | "word"
  | "excel"
  | "pptx"
  | "pdf"
  | "image";

export interface FilePreviewProps {
  content: string;
  fileType: FileType;
  /** pdf / image 类型需要提供文件 URL */
  fileUrl?: string;
  filename?: string;
  className?: string;
}

/** 以 markdown 渲染的类型 */
const MARKDOWN_TYPES = new Set<FileType>([
  "markdown",
  "memory_config",
  "word",
  "excel",
  "pptx",
]);

export function FilePreview({
  content,
  fileType,
  fileUrl,
  filename,
  className,
}: FilePreviewProps) {
  // PDF — iframe
  if (fileType === "pdf") {
    return (
      <iframe
        src={fileUrl}
        className={cn("h-full w-full border-0", className)}
        title={filename}
      />
    );
  }

  // Image
  if (fileType === "image") {
    return (
      <ImagePreview
        src={fileUrl!}
        alt={filename}
        className={cn("h-full w-full p-4", className)}
      />
    );
  }

  // Markdown / Word / Excel / PPTX — 渲染为 markdown
  if (MARKDOWN_TYPES.has(fileType)) {
    return (
      <ScrollArea className={cn("h-full", className)}>
        <div className="p-4">
          <Markdown content={content} />
        </div>
      </ScrollArea>
    );
  }

  // 其他文本类型 — monospace
  return (
    <ScrollArea className={cn("h-full", className)}>
      <pre className="whitespace-pre-wrap p-4 font-mono text-sm">
        {content}
      </pre>
    </ScrollArea>
  );
}
