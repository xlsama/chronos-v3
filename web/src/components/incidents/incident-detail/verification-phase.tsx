import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, XCircle, AlertCircle, ShieldCheck } from "lucide-react";
import { useIncidentStreamStore } from "@/stores/incident-stream";
import { AgentCard } from "./agent-card";
import { getServers } from "@/api/servers";
import { getServices } from "@/api/services";

interface VerificationPhaseProps {
  incidentId: string;
  incidentStatus?: string;
}

const VERDICT_CONFIG = {
  pass: {
    icon: CheckCircle2,
    label: "验证通过",
    className: "border-green-200 bg-green-50/50 text-green-800",
    iconClass: "text-green-600",
  },
  fail: {
    icon: XCircle,
    label: "验证失败",
    className: "border-red-200 bg-red-50/50 text-red-800",
    iconClass: "text-red-600",
  },
  partial: {
    icon: AlertCircle,
    label: "部分验证",
    className: "border-amber-200 bg-amber-50/50 text-amber-800",
    iconClass: "text-amber-600",
  },
};

export function VerificationPhase({ incidentId: _incidentId, incidentStatus }: VerificationPhaseProps) {
  const verifyInvestigation = useIncidentStreamStore((s) =>
    s.investigations.find((i) => i.hypothesisId === "VERIFY"),
  );
  const activeIds = useIncidentStreamStore((s) => s.activeInvestigationIds);

  const { data: serversData } = useQuery({
    queryKey: ["servers", "all"],
    queryFn: () => getServers({ page_size: 200 }),
    staleTime: 5 * 60 * 1000,
  });
  const { data: servicesData } = useQuery({
    queryKey: ["services", "all"],
    queryFn: () => getServices({ page_size: 200 }),
    staleTime: 5 * 60 * 1000,
  });

  const serverMap = useMemo(() => {
    const map = new Map<string, string>();
    if (serversData?.items) {
      for (const s of serversData.items) map.set(s.id, s.name);
    }
    return map;
  }, [serversData]);

  const serviceMap = useMemo(() => {
    const map = new Map<string, string>();
    if (servicesData?.items) {
      for (const s of servicesData.items) map.set(s.id, `${s.name} (${s.type})`);
    }
    return map;
  }, [servicesData]);

  const verdict = useMemo(() => {
    if (!verifyInvestigation || verifyInvestigation.status === "running") return null;
    const status = verifyInvestigation.status;
    if (status === "confirmed") return "pass";
    if (status === "eliminated") return "fail";
    // Also check summary text
    const summary = verifyInvestigation.summary?.toLowerCase() || "";
    if (summary.includes("pass") || summary.includes("通过")) return "pass";
    if (summary.includes("fail") || summary.includes("失败")) return "fail";
    return "partial";
  }, [verifyInvestigation]);

  if (!verifyInvestigation) {
    return (
      <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
        <ShieldCheck className="h-4 w-4" />
        <span>等待验证启动...</span>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <AgentCard
        title="验证排查结论"
        events={verifyInvestigation.events}
        status={verifyInvestigation.status}
        isActive={activeIds.has("VERIFY")}
        isReporting={verifyInvestigation.isReporting}
        streamingContent={verifyInvestigation.thinkingContent}
        summary={verifyInvestigation.summary}
        serverMap={serverMap}
        serviceMap={serviceMap}
        incidentStatus={incidentStatus}
        forceExpanded={activeIds.has("VERIFY")}
      />

      {verdict && (
        <VerdictBanner verdict={verdict} summary={verifyInvestigation.summary} />
      )}
    </div>
  );
}

function VerdictBanner({ verdict, summary }: { verdict: string; summary?: string }) {
  const config = (verdict in VERDICT_CONFIG ? VERDICT_CONFIG[verdict as keyof typeof VERDICT_CONFIG] : null) || VERDICT_CONFIG.partial;
  const Icon = config.icon;

  return (
    <div className={`flex items-start gap-3 rounded-lg border p-4 ${config.className}`}>
      <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${config.iconClass}`} />
      <div className="min-w-0">
        <p className="text-sm font-medium">{config.label}</p>
        {summary && (
          <p className="mt-1 text-xs opacity-80">{summary}</p>
        )}
      </div>
    </div>
  );
}
