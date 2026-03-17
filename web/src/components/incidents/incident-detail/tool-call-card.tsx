import { useState } from "react";
import { Terminal, Loader2, ChevronDown, ChevronRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ShellCodeBlock } from "@/components/ui/shell-code-block";

interface ToolCallCardProps {
  name: string;
  args?: Record<string, unknown>;
  output?: string;
  isExecuting?: boolean;
  relativeTime?: string;
  serverInfo?: string;
}

export function ToolCallCard({
  name,
  args,
  output,
  isExecuting,
  relativeTime,
  serverInfo,
}: ToolCallCardProps) {
  const [outputExpanded, setOutputExpanded] = useState(true);

  const isBash = name === "bash";
  const command = isBash ? (args?.command as string | undefined) : undefined;

  return (
    <div
      className="rounded-lg border border-blue-200 bg-blue-50/50 p-3"
      data-testid="tool-call-card"
    >
      {/* Header */}
      <div className="flex items-center gap-2 text-sm">
        <Terminal className="h-4 w-4 shrink-0 text-blue-700" />
        <span className="font-medium text-blue-900" data-testid="tool-name">{name}</span>
        {serverInfo && (
          <Badge variant="secondary" className="text-xs">
            {serverInfo}
          </Badge>
        )}
        {relativeTime && (
          <span className="ml-auto text-xs text-muted-foreground">{relativeTime}</span>
        )}
      </div>

      {/* Bash command — show inline */}
      {command && (
        <ShellCodeBlock
          code={command}
          showPrompt
          className="mt-2 overflow-x-auto rounded bg-background p-2 text-xs"
        />
      )}

      {/* Non-bash args — collapsible */}
      {!isBash && args && Object.keys(args).length > 0 && (
        <div className="mt-2">
          <pre className="overflow-x-auto rounded bg-background p-2 text-xs">
            {JSON.stringify(args, null, 2)}
          </pre>
        </div>
      )}

      {/* Executing state */}
      {isExecuting && (
        <div className="mt-2 flex items-center gap-2 text-xs text-blue-600">
          <Loader2 className="h-3 w-3 animate-spin" />
          执行中...
        </div>
      )}

      {/* Result — collapsible for long output */}
      {output && (
        <div className="mt-2">
          {output.length > 500 && (
            <button
              className="mb-1 flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
              onClick={() => setOutputExpanded(!outputExpanded)}
            >
              {outputExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              输出 ({output.length} chars)
            </button>
          )}
          {(output.length <= 500 || outputExpanded) && (
            <pre
              className="max-h-60 overflow-auto rounded border-l-2 border-green-400 bg-background p-2 text-xs"
              data-testid="tool-output"
            >
              {output}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
