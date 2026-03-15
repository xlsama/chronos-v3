import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { ShieldAlert } from "lucide-react";
import { decideApproval } from "@/api/approvals";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

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
  const decideMutation = useMutation({
    mutationFn: (decision: string) =>
      decideApproval(approvalId!, { decision, decided_by: "admin" }),
    onSuccess: (_, decision) => {
      toast.success(`Request ${decision}`);
    },
  });

  const riskLevel = toolCall?.risk_level as string | undefined;
  const explanation = toolCall?.explanation as string | undefined;
  const riskDetail = toolCall?.risk_detail as string | undefined;

  return (
    <div
      className="rounded-lg border-2 border-yellow-300 bg-yellow-50/50 p-4"
      data-testid="approval-card"
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

      {approvalId && (
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
    </div>
  );
}
