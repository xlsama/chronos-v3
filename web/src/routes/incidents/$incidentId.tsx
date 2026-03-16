import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { getIncident } from "@/api/incidents";
import { useIncidentStream } from "@/hooks/use-incident-stream";
import { EventTimeline } from "@/components/incidents/incident-detail/event-timeline";
import { UserInputBar } from "@/components/incidents/incident-detail/user-input-bar";
import { useIncidentStreamStore } from "@/stores/incident-stream";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/incidents/$incidentId")({
  component: IncidentDetailPage,
});

function IncidentDetailPage() {
  const { incidentId } = Route.useParams();
  const { isConnected } = useIncidentStreamStore();

  const { data: incident } = useQuery({
    queryKey: ["incident", incidentId],
    queryFn: () => getIncident(incidentId),
  });

  useIncidentStream(incidentId, incident?.status);

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="border-b px-6 py-4">
        <div className="flex items-center gap-3">
          <h1 className="text-base font-medium">
            {incident?.title ?? "Loading..."}
          </h1>
          <span
            className={cn(
              "h-2 w-2 rounded-full",
              isConnected ? "bg-green-500" : "bg-gray-300",
            )}
          />
        </div>
        {incident && (
          <p className="mt-1 text-sm text-muted-foreground">
            {incident.description}
          </p>
        )}
      </div>

      {/* Timeline */}
      <div className="flex-1 overflow-auto">
        <EventTimeline
          incidentId={incidentId}
          savedToMemory={incident?.saved_to_memory}
          summaryMarkdown={incident?.summary_md}
        />
      </div>

      {/* Input */}
      <UserInputBar incidentId={incidentId} />
    </div>
  );
}
