import { useIncidentStreamStore } from "@/stores/incident-stream";
import { cn } from "@/lib/utils";
import { ShieldCheck, ShieldAlert, ShieldQuestion } from "lucide-react";

export function EvaluatorContent() {
  const result = useIncidentStreamStore((s) => s.evaluationResult);

  if (!result) return null;

  const passed = result.verification_passed;
  const confidence = result.confidence;

  const Icon = passed ? ShieldCheck : result.recommendation === "return_to_agent" ? ShieldAlert : ShieldQuestion;
  const iconColor = passed ? "text-green-500" : result.recommendation === "return_to_agent" ? "text-amber-500" : "text-muted-foreground";

  return (
    <div className="space-y-3">
      {/* Result card */}
      <div
        className={cn(
          "rounded-lg border p-3 space-y-2",
          passed ? "border-green-200 bg-green-50/30" : "border-amber-200 bg-amber-50/30",
        )}
      >
        <div className="flex items-center gap-2">
          <Icon className={cn("h-5 w-5", iconColor)} />
          <span
            className={cn(
              "text-sm font-medium",
              passed ? "text-green-800" : "text-amber-800",
            )}
          >
            {passed ? "验证通过" : "验证未通过"}
          </span>
          <span
            className={cn(
              "text-[10px] px-1.5 py-0.5 rounded font-medium",
              confidence === "high"
                ? "bg-green-100 text-green-700"
                : confidence === "medium"
                  ? "bg-amber-100 text-amber-700"
                  : "bg-gray-100 text-gray-600",
            )}
          >
            {confidence}
          </span>
        </div>

        {result.evidence_summary && (
          <p className="text-sm text-muted-foreground">{result.evidence_summary}</p>
        )}

        {result.concerns.length > 0 && (
          <div className="text-xs text-amber-700 space-y-0.5">
            {result.concerns.map((c, i) => (
              <p key={i}>- {c}</p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
