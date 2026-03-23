import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { ShieldAlert, AlertTriangle, Loader2, Terminal } from "lucide-react";
import { decideApproval } from "@/api/approvals";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { ShellCodeBlock } from "@/components/ui/shell-code-block";
import { useIncidentStreamStore } from "@/stores/incident-stream";

const TOOL_LABELS: Record<string, string> = {
  ssh_bash: "SSH 远程命令",
  bash: "本地命令",
  service_exec: "服务命令",
};

interface ApprovalCardProps {
  toolCall: Record<string, unknown> | null;
  approvalId?: string;
  toolName?: string;
  serverInfo?: string;
  serviceInfo?: string;
}

export function ApprovalCard({ toolCall, approvalId, toolName, serverInfo, serviceInfo }: ApprovalCardProps) {
  const decidedApprovals = useIncidentStreamStore((s) => s.decidedApprovals);
  const setApprovalDecided = useIncidentStreamStore(
    (s) => s.setApprovalDecided,
  );
  const resolvedDecision = approvalId
    ? (decidedApprovals[approvalId] ?? null)
    : null;

  const decideMutation = useMutation({
    mutationFn: (decision: string) =>
      decideApproval(approvalId!, {
        decision,
        decided_by: "admin",
        silent: true,
      }),
    onSuccess: (_, decision) => {
      setApprovalDecided(approvalId!, decision);
    },
    onError: (error: unknown) => {
      // 409 Conflict → approval already decided, parse actual decision from detail
      const apiErr = error as { status?: number; detail?: string };
      if (apiErr.status === 409) {
        const decision = apiErr.detail?.includes("rejected") ? "rejected" : "approved";
        setApprovalDecided(approvalId!, decision);
        return;
      }
      toast.error("审批操作失败");
    },
  });

  const riskLevel = toolCall?.risk_level as string | undefined;
  const explanation = toolCall?.explanation as string | undefined;
  const command = toolCall?.command as string | undefined;
  const isHigh = riskLevel === "HIGH";

  return (
    <div
      className={cn(
        "rounded-lg border-2 p-4",
        isHigh
          ? "border-red-300 bg-red-50/50"
          : "border-yellow-300 bg-yellow-50/50",
      )}
      data-testid="approval-card"
      data-approval-id={approvalId}
    >
      <div
        className={cn(
          "flex items-center gap-2 text-sm font-semibold",
          isHigh ? "text-red-800" : "text-yellow-800",
        )}
      >
        {isHigh ? (
          <AlertTriangle className="h-5 w-5" />
        ) : (
          <ShieldAlert className="h-5 w-5" />
        )}
        {isHigh ? "高危操作审批" : "操作审批"}
        {riskLevel && (
          <span
            className={cn(
              "ml-2 inline-block rounded px-2 py-0.5 text-xs font-medium",
              isHigh
                ? "bg-red-100 text-red-800"
                : "bg-yellow-100 text-yellow-800",
            )}
            data-testid="risk-level"
          >
            {riskLevel}
          </span>
        )}
      </div>

      {toolName && (
        <div className="mt-2 flex items-center gap-2 text-sm text-muted-foreground">
          <Terminal className="h-3.5 w-3.5" />
          <span>{TOOL_LABELS[toolName] ?? toolName}</span>
          {toolName === "ssh_bash" && serverInfo && (
            <Badge variant="secondary" className="text-xs">{serverInfo}</Badge>
          )}
          {toolName === "bash" && (
            <Badge variant="secondary" className="text-xs">本地</Badge>
          )}
          {toolName === "service_exec" && serviceInfo && (
            <Badge variant="secondary" className="text-xs">{serviceInfo}</Badge>
          )}
        </div>
      )}

      {isHigh && (
        <div className="mt-2 rounded border border-red-200 bg-red-100/50 px-3 py-2 text-xs text-red-700">
          此命令被识别为高危操作，请仔细确认后再审批
        </div>
      )}

      {toolCall && (
        <div className="mt-3 space-y-2">
          {command && (
            <div>
              <span className="text-sm font-medium">命令:</span>
              <ShellCodeBlock
                code={command}
                showPrompt={false}
                className="mt-1 overflow-x-auto rounded bg-background p-2 text-xs"
              />
            </div>
          )}

          {explanation && (
            <p className="text-sm">
              <span className="font-medium">说明:</span> {explanation}
            </p>
          )}
        </div>
      )}

      {approvalId && !resolvedDecision && (
        <div className="mt-3 flex gap-2">
          <Button
            size="sm"
            onClick={() => decideMutation.mutate("approved")}
            disabled={decideMutation.isPending}
            data-testid="approve-button"
          >
            {decideMutation.isPending && decideMutation.variables === "approved" && (
              <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
            )}
            批准
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => decideMutation.mutate("rejected")}
            disabled={decideMutation.isPending}
            data-testid="reject-button"
          >
            {decideMutation.isPending && decideMutation.variables === "rejected" && (
              <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
            )}
            拒绝
          </Button>
        </div>
      )}

      {resolvedDecision && (
        <div className="mt-3">
          <span
            className={cn(
              "inline-flex rounded-full px-2.5 py-1 text-xs font-medium",
              resolvedDecision === "approved"
                ? "bg-green-100 text-green-800"
                : "bg-red-100 text-red-800",
            )}
            data-testid="approval-decision"
          >
            {resolvedDecision === "approved" ? "已批准" : "已拒绝"}
          </span>
        </div>
      )}
    </div>
  );
}
