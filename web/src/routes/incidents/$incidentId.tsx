import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useRef, useEffect, useCallback, useState } from "react";
import { ArrowDown } from "lucide-react";
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
  const { isConnected, events, thinkingContent } = useIncidentStreamStore();

  const { data: incident } = useQuery({
    queryKey: ["incident", incidentId],
    queryFn: () => getIncident(incidentId),
  });

  useIncidentStream(incidentId, incident?.status);

  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const shouldAutoScroll = useRef(true);
  const [isAtBottom, setIsAtBottom] = useState(true);

  const checkIsAtBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const threshold = 100;
    const atBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
    shouldAutoScroll.current = atBottom;
    setIsAtBottom(atBottom);
  }, []);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    if (shouldAutoScroll.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [events.length, thinkingContent]);

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
      <div
        ref={scrollRef}
        className="relative flex-1 overflow-auto"
        onScroll={checkIsAtBottom}
      >
        <EventTimeline
          incidentId={incidentId}
          savedToMemory={incident?.saved_to_memory}
          summaryMarkdown={incident?.summary_md}
        />
        <div ref={bottomRef} />

        {!isAtBottom && (
          <button
            className="sticky bottom-4 left-full -translate-x-8 rounded-full border bg-background p-2 shadow-md transition-opacity hover:bg-accent"
            onClick={scrollToBottom}
          >
            <ArrowDown className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Input */}
      <UserInputBar incidentId={incidentId} />
    </div>
  );
}
