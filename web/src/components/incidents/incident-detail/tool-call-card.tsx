import { useState } from "react";
import { Wrench, Loader2, ChevronDown, ChevronRight } from "lucide-react";
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
  const [expanded, setExpanded] = useState(isExecuting ?? false);

  const isBash = name === "bash";
  const command = isBash ? (args?.command as string | undefined) : undefined;
  const hasNonBashArgs = !isBash && args && Object.keys(args).length > 0;

  return (
    <div
      className="rounded-lg border border-blue-200 bg-blue-50/50"
      data-testid="tool-call-card"
    >
      {/* Header — always visible, clickable to toggle */}
      <button
        className="flex w-full items-center gap-2 p-3 text-left text-sm"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-blue-400" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-blue-400" />
        )}
        <Wrench className="h-4 w-4 shrink-0 text-blue-700" />
        <span className="font-medium text-blue-900" data-testid="tool-name">{name}</span>
        {serverInfo && (
          <Badge variant="secondary" className="text-xs">
            {serverInfo}
          </Badge>
        )}
        {isExecuting && (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-500" />
        )}
        {relativeTime && (
          <span className="ml-auto text-xs text-muted-foreground">{relativeTime}</span>
        )}
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="space-y-2 border-t border-blue-100 p-3 pt-2">
          {/* Bash command */}
          {command && (
            <ShellCodeBlock
              code={command}
              showPrompt
              className="overflow-x-auto rounded bg-background p-2 text-xs"
            />
          )}

          {/* Non-bash args */}
          {hasNonBashArgs && (
            <pre className="overflow-x-auto rounded bg-background p-2 text-xs">
              {JSON.stringify(args, null, 2)}
            </pre>
          )}

          {/* Result */}
          {output && (
            <pre
              className="max-h-60 overflow-auto whitespace-pre-wrap rounded border-l-2 border-green-400 bg-background p-2 text-xs"
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
