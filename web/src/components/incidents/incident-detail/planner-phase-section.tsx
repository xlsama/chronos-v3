import { useIncidentStreamStore, type InvestigationPlan } from "@/stores/incident-stream";
import { cn } from "@/lib/utils";
import { Search, CheckCircle2, XCircle, Circle, Loader2 } from "lucide-react";

function HypothesisStatusIcon({ status }: { status: string }) {
  switch (status) {
    case "confirmed":
      return <CheckCircle2 className="h-4 w-4 text-green-500 shrink-0" />;
    case "eliminated":
      return <XCircle className="h-4 w-4 text-red-400 shrink-0" />;
    case "investigating":
      return <Loader2 className="h-4 w-4 text-blue-500 shrink-0 animate-spin" />;
    default:
      return <Circle className="h-4 w-4 text-muted-foreground/40 shrink-0" />;
  }
}

function HypothesisItem({
  hypothesis,
}: {
  hypothesis: InvestigationPlan["hypotheses"][number];
}) {
  const isDone = hypothesis.status === "confirmed" || hypothesis.status === "eliminated";
  const isActive = hypothesis.status === "investigating";

  return (
    <div
      className={cn(
        "flex items-start gap-2.5 rounded-md px-2.5 py-1.5 transition-colors",
        isActive && "bg-blue-50/60",
        isDone && "opacity-70",
      )}
    >
      <div className="mt-0.5">
        <HypothesisStatusIcon status={hypothesis.status} />
      </div>
      <div className="min-w-0 flex-1">
        <p
          className={cn(
            "text-sm leading-snug",
            isDone && "line-through text-muted-foreground",
            isActive && "font-medium text-blue-900",
          )}
        >
          <span className="text-muted-foreground mr-1">{hypothesis.id}</span>
          {hypothesis.description}
        </p>
        {hypothesis.evidence_for.length > 0 && (
          <p className="text-xs text-green-700 mt-0.5">
            {hypothesis.evidence_for.join("; ")}
          </p>
        )}
        {hypothesis.evidence_against.length > 0 && (
          <p className="text-xs text-red-600 mt-0.5">
            {hypothesis.evidence_against.join("; ")}
          </p>
        )}
      </div>
      <div className="shrink-0">
        {hypothesis.status === "confirmed" && (
          <span className="text-[10px] font-medium text-green-600 bg-green-50 px-1.5 py-0.5 rounded">
            confirmed
          </span>
        )}
        {hypothesis.status === "eliminated" && (
          <span className="text-[10px] font-medium text-red-500 bg-red-50 px-1.5 py-0.5 rounded">
            eliminated
          </span>
        )}
      </div>
    </div>
  );
}

export function PlannerContent() {
  const plan = useIncidentStreamStore((s) => s.plannerPlan);

  if (!plan) return null;

  const sortedHypotheses = [...plan.hypotheses].sort((a, b) => a.priority - b.priority);

  return (
    <div className="space-y-3">
      {/* Header info */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        <span>
          <span className="font-medium text-foreground">{plan.symptom_category}</span>
        </span>
        {plan.target_scope && (
          <span>{plan.target_scope}</span>
        )}
      </div>

      {/* Hypothesis list */}
      <div className="space-y-0.5">
        {sortedHypotheses.map((h) => (
          <HypothesisItem key={h.id} hypothesis={h} />
        ))}
      </div>

      {/* Null hypothesis */}
      {plan.null_hypothesis && (
        <div className="text-xs text-muted-foreground bg-muted/30 rounded-md px-3 py-2">
          <span className="font-medium">H0:</span> {plan.null_hypothesis}
        </div>
      )}

      {/* Next action */}
      {plan.next_action && (
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Search className="h-3 w-3" />
          <span>{plan.next_action}</span>
        </div>
      )}
    </div>
  );
}
