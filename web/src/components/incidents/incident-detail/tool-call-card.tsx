import { useState, memo } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Wrench,
  Loader2,
  ChevronDown,
  ChevronRight,
  UserCheck,
  AlertTriangle,
  MessageSquarePlus,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ShellCodeBlock } from "@/components/ui/shell-code-block";
import { Markdown } from "@/components/ui/markdown";
import { TextDotsLoader } from "@/components/ui/loader";
import { cn } from "@/lib/utils";
import { decideApproval } from "@/api/approvals";
import { useIncidentStreamStore } from "@/stores/incident-stream";

interface ToolCallCardProps {
  name: string;
  args?: Record<string, unknown>;
  output?: string;
  isExecuting?: boolean;
  status?: "success" | "error";
  relativeTime?: string;
  serverInfo?: string;
  serviceInfo?: string;
  // Approval-related (optional)
  approvalId?: string;
  riskLevel?: string;
  explanation?: string;
  incidentStatus?: string;
}

const COMMAND_TOOLS = new Set(["ssh_bash", "bash", "service_exec"]);

function formatToolOutput(name: string, output: string): string {
  if (name !== "ssh_bash" && name !== "bash") return output;
  try {
    const parsed = JSON.parse(output);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return output;
    return parsed.stdout || parsed.stderr || parsed.error || output;
  } catch {
    return output;
  }
}

export const ToolCallCard = memo(function ToolCallCard({
  name,
  args,
  output,
  isExecuting,
  status,
  relativeTime,
  serverInfo,
  serviceInfo,
  approvalId,
  riskLevel,
  explanation,
  incidentStatus,
}: ToolCallCardProps) {
  const isApproval = !!approvalId;
  const isHigh = riskLevel === "HIGH";

  const [expanded, setExpanded] = useState(isApproval ? true : (isExecuting ?? false));

  // Approval state from store
  const decidedApprovals = useIncidentStreamStore((s) => s.decidedApprovals);
  const setApprovalDecided = useIncidentStreamStore((s) => s.setApprovalDecided);
  const pendingSupplement = useIncidentStreamStore((s) => s.pendingSupplement);
  const setPendingSupplement = useIncidentStreamStore((s) => s.setPendingSupplement);
  const triggerScrollToBottom = useIncidentStreamStore((s) => s.triggerScrollToBottom);

  const approvalEntry = approvalId ? (decidedApprovals[approvalId] ?? null) : null;
  const resolvedDecision = approvalEntry?.decision ?? null;
  const supplementText = approvalEntry?.supplementText;
  const isSupplementing = pendingSupplement?.approvalId === approvalId;
  const isExpired =
    incidentStatus === "stopped" ||
    incidentStatus === "resolved" ||
    incidentStatus === "interrupted";

  const decideMutation = useMutation({
    mutationFn: (vars: { decision: string }) =>
      decideApproval(approvalId!, {
        decision: vars.decision,
        decided_by: "admin",
        silent: true,
      }),
    onSuccess: (_, vars) => {
      setApprovalDecided(approvalId!, vars.decision);
      triggerScrollToBottom();
    },
    onError: (error: unknown) => {
      const apiErr = error as { status?: number; detail?: string };
      if (apiErr.status === 409) {
        const decision = apiErr.detail?.includes("rejected") ? "rejected" : "approved";
        setApprovalDecided(approvalId!, decision);
        triggerScrollToBottom();
        return;
      }
      toast.error("审批操作失败");
    },
  });

  const hasCommand = COMMAND_TOOLS.has(name);
  const command = hasCommand ? (args?.command as string | undefined) : undefined;
  const hasNonCommandArgs = !hasCommand && args && Object.keys(args).length > 0;

  const badgeLabel =
    name === "ssh_bash"
      ? serverInfo
      : name === "bash"
        ? "本地"
        : name === "service_exec"
          ? serviceInfo
          : undefined;

  // Color theme
  const colors = isApproval
    ? isHigh
      ? {
          border: "border-red-300 dark:border-red-700",
          bg: "bg-red-50/50 dark:bg-red-950/30",
          chevron: "text-red-400",
          icon: "text-red-700 dark:text-red-300",
          name: "text-red-900 dark:text-red-100",
          spinner: "text-red-500",
          divider: "border-red-100 dark:border-red-800",
          borderWidth: "border-2",
        }
      : {
          border: "border-yellow-300 dark:border-yellow-700",
          bg: "bg-yellow-50/50 dark:bg-yellow-950/30",
          chevron: "text-yellow-400",
          icon: "text-yellow-700 dark:text-yellow-300",
          name: "text-yellow-900 dark:text-yellow-100",
          spinner: "text-yellow-500",
          divider: "border-yellow-100 dark:border-yellow-800",
          borderWidth: "border-2",
        }
    : {
        border: "border-blue-200 dark:border-blue-500/15",
        bg: "bg-blue-50/50 dark:bg-blue-500/[0.06]",
        chevron: "text-blue-400 dark:text-blue-400/60",
        icon: "text-blue-700 dark:text-blue-400",
        name: "text-blue-900 dark:text-blue-200",
        spinner: "text-blue-500",
        divider: "border-blue-100 dark:border-blue-500/10",
        borderWidth: "border",
      };

  // Decision badge component
  const baseBadge = resolvedDecision ? (
    <span
      className={cn(
        "inline-flex rounded-full px-2 py-0.5 text-xs font-medium",
        resolvedDecision === "approved"
          ? "bg-green-100 text-green-800 dark:bg-green-900/50 dark:text-green-200"
          : resolvedDecision === "supplemented"
            ? "bg-blue-100 text-blue-800 dark:bg-blue-900/50 dark:text-blue-200"
            : "bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200",
      )}
      data-testid="approval-decision"
    >
      {resolvedDecision === "approved"
        ? "已批准"
        : resolvedDecision === "supplemented"
          ? "已补充"
          : "已拒绝"}
    </span>
  ) : null;

  const decisionBadge = baseBadge;

  return (
    <div
      className={cn("rounded-lg", colors.borderWidth, colors.border, colors.bg)}
      data-testid={isApproval ? "approval-card" : "tool-call-card"}
      data-approval-id={approvalId}
    >
      {/* Header */}
      <button
        className="flex w-full items-center gap-2 p-3 text-left text-sm"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? (
          <ChevronDown className={cn("h-3.5 w-3.5 shrink-0", colors.chevron)} />
        ) : (
          <ChevronRight className={cn("h-3.5 w-3.5 shrink-0", colors.chevron)} />
        )}

        {/* Icon: spinner when executing, error/normal icon otherwise */}
        {isExecuting ? (
          <Loader2 className={cn("h-4 w-4 shrink-0 animate-spin", colors.spinner)} />
        ) : isApproval ? (
          isHigh ? (
            <AlertTriangle className={cn("h-4 w-4 shrink-0", colors.icon)} />
          ) : (
            <UserCheck className={cn("h-4 w-4 shrink-0", colors.icon)} />
          )
        ) : (
          <Wrench className={cn("h-4 w-4 shrink-0", status === "error" ? "text-orange-500 dark:text-orange-400" : colors.icon)} />
        )}

        <span className={cn("font-medium", colors.name)} data-testid="tool-name">
          {name}
        </span>

        {badgeLabel && (
          <Badge variant="secondary" className="text-xs">
            {badgeLabel}
          </Badge>
        )}

        {/* Risk level badge */}
        {isApproval && riskLevel && (
          <span
            className={cn(
              "inline-block rounded px-2 py-0.5 text-xs font-medium",
              isHigh ? "bg-red-100 text-red-800 dark:bg-red-900/50 dark:text-red-200" : "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-200",
            )}
            data-testid="risk-level"
          >
            {riskLevel}
          </span>
        )}

        {!isExecuting && status === "error" && (
          <span className="inline-block rounded px-1.5 py-0.5 text-xs font-medium bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300">
            失败
          </span>
        )}

        {/* Right side: decision badge + relative time */}
        <span className="ml-auto flex items-center gap-2">
          {isExecuting && (
            <TextDotsLoader text="执行中" size="sm" className="text-muted-foreground" />
          )}
          {decisionBadge}
          {relativeTime && (
            <span className="text-xs text-muted-foreground">{relativeTime}</span>
          )}
        </span>
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className={cn("flex flex-col gap-3 border-t p-3 pt-2", colors.divider)}>
          {/* High-risk warning */}
          {isApproval && isHigh && (
            <div className="rounded border border-red-200 bg-red-100/50 px-3 py-2 text-xs text-red-700 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300">
              此命令被识别为高危操作，请仔细确认后再审批
            </div>
          )}

          {/* Input */}
          {command && (
            <div>
              <p className="mb-1 text-xs font-medium text-muted-foreground">Input</p>
              <ShellCodeBlock
                code={command}
                showPrompt={!isApproval || !!output}
                className="overflow-x-auto rounded-md border border-border/50 bg-background px-4 py-2 text-xs"
              />
            </div>
          )}

          {hasNonCommandArgs && (
            <div>
              <p className="mb-1 text-xs font-medium text-muted-foreground">Input</p>
              <pre className="overflow-x-auto rounded-md border border-border/50 bg-background px-4 py-2 text-xs">
                {JSON.stringify(args, null, 2)}
              </pre>
            </div>
          )}

          {/* Explanation */}
          {isApproval && explanation && (
            <p className="text-sm">
              <span className="font-medium">说明:</span> {explanation}
            </p>
          )}

          {/* Output */}
          {output && (
            <div data-testid="tool-output">
              <p className="mb-1 text-xs font-medium text-muted-foreground">Output</p>
              <div className="max-h-60 overflow-auto rounded-md border border-border/50 bg-background px-4 py-2 text-xs">
                <Markdown content={formatToolOutput(name, output)} variant="tiny" />
              </div>
            </div>
          )}

          {/* Supplement content */}
          {resolvedDecision === "supplemented" && supplementText && (
            <div>
              <p className="mb-1 text-xs font-medium text-muted-foreground">补充内容</p>
              <div className="rounded-md border border-border/50 bg-background p-2 text-sm">
                <Markdown content={supplementText} variant="compact" />
              </div>
            </div>
          )}

          {/* Approval action buttons */}
          {isApproval &&
            approvalId &&
            !resolvedDecision &&
            (isExpired ? (
              <div>
                <span
                  className="inline-flex rounded-full px-2.5 py-1 text-xs font-medium bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"
                  data-testid="approval-decision"
                >
                  已过期
                </span>
              </div>
            ) : isSupplementing ? (
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-blue-600">补充说明中...</span>
                <button
                  className="text-xs text-muted-foreground underline hover:text-foreground"
                  onClick={() => setPendingSupplement(null)}
                >
                  取消
                </button>
              </div>
            ) : (
              <div className="flex gap-2">
                <Button
                  size="sm"
                  onClick={() => decideMutation.mutate({ decision: "approved" })}
                  disabled={decideMutation.isPending}
                  data-testid="approve-button"
                >
                  {decideMutation.isPending &&
                    decideMutation.variables?.decision === "approved" && (
                      <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                    )}
                  批准
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => decideMutation.mutate({ decision: "rejected" })}
                  disabled={decideMutation.isPending}
                  data-testid="reject-button"
                >
                  {decideMutation.isPending &&
                    decideMutation.variables?.decision === "rejected" && (
                      <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                    )}
                  拒绝
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setPendingSupplement({ approvalId: approvalId! })}
                  disabled={decideMutation.isPending}
                  data-testid="supplement-button"
                >
                  <MessageSquarePlus className="mr-1 h-3.5 w-3.5" />
                  补充说明
                </Button>
              </div>
            ))}
        </div>
      )}
    </div>
  );
});
