import { useState } from "react";
import { Terminal, Loader2, ChevronDown, ChevronRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";

interface ToolCallCardProps {
  name: string;
  args?: Record<string, unknown>;
  output?: string;
  isExecuting?: boolean;
  relativeTime?: string;
  connectionInfo?: string;
}

export function ToolCallCard({
  name,
  args,
  output,
  isExecuting,
  relativeTime,
  connectionInfo,
}: ToolCallCardProps) {
  const [argsExpanded, setArgsExpanded] = useState(false);

  return (
    <div
      className="rounded-lg border border-blue-200 bg-blue-50/50 p-3"
      data-testid="tool-call-card"
    >
      {/* Header */}
      <div className="flex items-center gap-2 text-sm">
        <Terminal className="h-4 w-4 shrink-0 text-blue-700" />
        <span className="font-medium text-blue-900" data-testid="tool-name">{name}</span>
        {connectionInfo && (
          <Badge variant="secondary" className="text-xs">
            {connectionInfo}
          </Badge>
        )}
        {relativeTime && (
          <span className="ml-auto text-xs text-muted-foreground">{relativeTime}</span>
        )}
      </div>

      {/* Args — collapsible */}
      {args && Object.keys(args).length > 0 && (
        <div className="mt-2">
          <button
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            onClick={() => setArgsExpanded(!argsExpanded)}
          >
            {argsExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            参数
          </button>
          {argsExpanded && (
            <pre className="mt-1 overflow-x-auto rounded bg-background p-2 text-xs">
              {JSON.stringify(args, null, 2)}
            </pre>
          )}
        </div>
      )}

      {/* Executing state */}
      {isExecuting && (
        <div className="mt-2 flex items-center gap-2 text-xs text-blue-600">
          <Loader2 className="h-3 w-3 animate-spin" />
          执行中...
        </div>
      )}

      {/* Result */}
      {output && (
        <pre
          className="mt-2 max-h-60 overflow-auto rounded border-l-2 border-green-400 bg-background p-2 text-xs"
          data-testid="tool-output"
        >
          {output}
        </pre>
      )}
    </div>
  );
}
