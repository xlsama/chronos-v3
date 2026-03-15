import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { ShieldAlert } from "lucide-react";

interface ApprovalCardProps {
  toolCall: Record<string, unknown> | null;
  approvalId?: string;
}

export function ApprovalCard({ toolCall, approvalId }: ApprovalCardProps) {
  const decideMutation = useMutation({
    mutationFn: (decision: string) =>
      api(`/approvals/${approvalId}/decide`, {
        method: "POST",
        body: { decision, decided_by: "admin" },
      }),
  });

  return (
    <div className="rounded-lg border-2 border-yellow-300 bg-yellow-50/50 p-4">
      <div className="flex items-center gap-2 text-sm font-semibold text-yellow-800">
        <ShieldAlert className="h-5 w-5" />
        Approval Required
      </div>

      {toolCall && (
        <div className="mt-3 space-y-2">
          <p className="text-sm">
            <span className="font-medium">Command:</span>{" "}
            {(toolCall.args as Record<string, string>)?.command ?? "N/A"}
          </p>
          <pre className="rounded bg-background p-2 text-xs">
            {JSON.stringify(toolCall, null, 2)}
          </pre>
        </div>
      )}

      {approvalId && (
        <div className="mt-3 flex gap-2">
          <Button
            size="sm"
            onClick={() => decideMutation.mutate("approved")}
            disabled={decideMutation.isPending}
          >
            Approve
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => decideMutation.mutate("rejected")}
            disabled={decideMutation.isPending}
          >
            Reject
          </Button>
        </div>
      )}
    </div>
  );
}
