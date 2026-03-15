import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { api } from "@/lib/api";
import type { Incident } from "@/lib/types";
import { cn } from "@/lib/utils";

const severityColors: Record<string, string> = {
  low: "bg-blue-100 text-blue-800",
  medium: "bg-yellow-100 text-yellow-800",
  high: "bg-orange-100 text-orange-800",
  critical: "bg-red-100 text-red-800",
};

const statusColors: Record<string, string> = {
  open: "bg-red-100 text-red-800",
  investigating: "bg-yellow-100 text-yellow-800",
  resolved: "bg-green-100 text-green-800",
  closed: "bg-gray-100 text-gray-800",
};

export function IncidentList() {
  const { data: incidents, isLoading } = useQuery({
    queryKey: ["incidents"],
    queryFn: () => api<Incident[]>("/incidents"),
  });

  if (isLoading) {
    return <div className="p-4 text-muted-foreground">Loading...</div>;
  }

  if (!incidents?.length) {
    return (
      <div className="p-8 text-center text-muted-foreground">
        No incidents yet. Create one to get started.
      </div>
    );
  }

  return (
    <div className="divide-y">
      {incidents.map((incident) => (
        <Link
          key={incident.id}
          to="/incidents/$incidentId"
          params={{ incidentId: incident.id }}
          className="flex items-center gap-4 p-4 transition-colors hover:bg-muted/50"
        >
          <div className="flex-1 space-y-1">
            <p className="font-medium">{incident.title}</p>
            <p className="text-sm text-muted-foreground line-clamp-1">
              {incident.description}
            </p>
          </div>
          <span
            className={cn(
              "rounded-full px-2 py-0.5 text-xs font-medium",
              severityColors[incident.severity] ?? "bg-gray-100",
            )}
          >
            {incident.severity}
          </span>
          <span
            className={cn(
              "rounded-full px-2 py-0.5 text-xs font-medium",
              statusColors[incident.status] ?? "bg-gray-100",
            )}
          >
            {incident.status}
          </span>
          <span className="text-xs text-muted-foreground">
            {new Date(incident.created_at).toLocaleString()}
          </span>
        </Link>
      ))}
    </div>
  );
}
