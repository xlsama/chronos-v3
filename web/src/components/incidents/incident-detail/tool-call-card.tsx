import { useState } from "react";
import { Wrench, Loader2, ChevronDown, ChevronRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ShellCodeBlock } from "@/components/ui/shell-code-block";
import { Markdown } from "@/components/ui/markdown";

interface ToolCallCardProps {
  name: string;
  args?: Record<string, unknown>;
  output?: string;
  isExecuting?: boolean;
  relativeTime?: string;
  serverInfo?: string;
  serviceInfo?: string;
}

const COMMAND_TOOLS = new Set(["ssh_bash", "bash", "service_exec"]);

export function ToolCallCard({
  name,
  args,
  output,
  isExecuting,
  relativeTime,
  serverInfo,
  serviceInfo,
}: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(isExecuting ?? false);

  const hasCommand = COMMAND_TOOLS.has(name);
  const command = hasCommand ? (args?.command as string | undefined) : undefined;
  const hasNonCommandArgs = !hasCommand && args && Object.keys(args).length > 0;

  // Badge info
  const badgeLabel =
    name === "ssh_bash" ? serverInfo :
    name === "bash" ? "本地" :
    name === "service_exec" ? serviceInfo :
    undefined;

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
        {badgeLabel && (
          <Badge variant="secondary" className="text-xs">
            {badgeLabel}
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
        <div className="flex flex-col gap-3 border-t border-blue-100 p-3 pt-2">
          {/* Command */}
          {command && (
            <ShellCodeBlock
              code={command}
              showPrompt
              className="overflow-x-auto rounded border-l-2 border-blue-400 bg-background p-2 pl-3 text-xs shadow-sm"
            />
          )}

          {/* Non-command args */}
          {hasNonCommandArgs && (
            <pre className="overflow-x-auto rounded border-l-2 border-blue-400 bg-background p-2 pl-3 text-xs shadow-sm">
              {JSON.stringify(args, null, 2)}
            </pre>
          )}

          {/* Result */}
          {output && (
            <div
              className="max-h-60 overflow-auto rounded border-l-2 border-green-400 bg-background p-2 pl-3 text-xs shadow-sm"
              data-testid="tool-output"
            >
              <Markdown content={output} variant="tiny" />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
