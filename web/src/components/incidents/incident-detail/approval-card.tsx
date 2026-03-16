import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { motion } from "motion/react";
import { ShieldAlert } from "lucide-react";
import { decideApproval } from "@/api/approvals";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useIncidentStreamStore } from "@/stores/incident-stream";

interface ApprovalCardProps {
  toolCall: Record<string, unknown> | null;
  approvalId?: string;
}

const riskColors: Record<string, string> = {
  LOW: "bg-green-100 text-green-800",
  MEDIUM: "bg-yellow-100 text-yellow-800",
  HIGH: "bg-red-100 text-red-800",
};

export function ApprovalCard({ toolCall, approvalId }: ApprovalCardProps) {
  const decidedApprovals = useIncidentStreamStore((s) => s.decidedApprovals);
  const setApprovalDecided = useIncidentStreamStore(
    (s) => s.setApprovalDecided,
  );
  const resolvedDecision = approvalId
    ? (decidedApprovals.get(approvalId) ?? null)
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
      toast.success(`Request ${decision}`);
    },
    onError: (error: unknown) => {
      // 409 Conflict → approval already decided, silently mark as decided
      const status = (error as { status?: number })?.status;
      if (status === 409) {
        setApprovalDecided(approvalId!, "approved");
        return;
      }
      toast.error("Failed to decide approval");
    },
  });

  const riskLevel = toolCall?.risk_level as string | undefined;
  const explanation = toolCall?.explanation as string | undefined;
  const riskDetail = toolCall?.risk_detail as string | undefined;

  return (
    <motion.div
      className="rounded-lg border-2 border-yellow-300 bg-yellow-50/50 p-4"
      data-testid="approval-card"
      data-approval-id={approvalId}
      initial={{ scale: 0.95, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ type: "spring", stiffness: 300, damping: 20 }}
    >
      <div className="flex items-center gap-2 text-sm font-semibold text-yellow-800">
        <ShieldAlert className="h-5 w-5" />
        Approval Required
      </div>

      {toolCall && (
        <div className="mt-3 space-y-2">
          <p className="text-sm">
            <span className="font-medium">Command:</span>{" "}
            {(toolCall as Record<string, string>)?.command ?? "N/A"}
          </p>

          {explanation && (
            <p className="text-sm">
              <span className="font-medium">Explanation:</span> {explanation}
            </p>
          )}

          {riskLevel && (
            <p className="text-sm">
              <span className="font-medium">Risk Level:</span>{" "}
              <span
                className={cn(
                  "ml-1 inline-block rounded px-2 py-0.5 text-xs font-medium",
                  riskColors[riskLevel] ?? "bg-gray-100 text-gray-800",
                )}
                data-testid="risk-level"
              >
                {riskLevel}
              </span>
            </p>
          )}

          {riskDetail && (
            <p className="text-sm">
              <span className="font-medium">Risk Detail:</span> {riskDetail}
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
            Approve
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => decideMutation.mutate("rejected")}
            disabled={decideMutation.isPending}
            data-testid="reject-button"
          >
            Reject
          </Button>
        </div>
      )}

      {resolvedDecision && (
        <div className="mt-3">
          <span
            className="inline-flex rounded-full bg-green-100 px-2.5 py-1 text-xs font-medium text-green-800"
            data-testid="approval-decision"
          >
            {resolvedDecision === "approved" ? "Approved" : "Rejected"}
          </span>
        </div>
      )}
    </motion.div>
  );
}
