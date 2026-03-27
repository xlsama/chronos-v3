import { useState } from "react";
import { Copy, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { Markdown } from "@/components/ui/markdown";

interface AnswerCardProps {
  content: string;
  isStreaming?: boolean;
}

export function AnswerCard({ content, isStreaming }: AnswerCardProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      className={cn(
        "rounded-lg border border-violet-200 bg-violet-50/50 p-4 text-sm dark:border-blue-500/15 dark:bg-blue-500/[0.06]",
        isStreaming && "border-l-2 border-l-violet-400",
      )}
    >
      <div className="mb-1 flex items-center justify-between">
        <div className="text-xs font-medium text-muted-foreground">
          排查结论{isStreaming && "..."}
        </div>
        {!isStreaming && content && (
          <button
            onClick={handleCopy}
            className="rounded p-0.5 text-muted-foreground hover:text-foreground"
          >
            {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
          </button>
        )}
      </div>
      <Markdown content={content} streaming={isStreaming} variant="compact" />
    </div>
  );
}
