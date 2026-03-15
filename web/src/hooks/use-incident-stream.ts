import { useEffect, useRef } from "react";
import { useIncidentStreamStore } from "@/stores/incident-stream";
import type { SSEEvent } from "@/lib/types";

export function useIncidentStream(incidentId: string | undefined) {
  const eventSourceRef = useRef<EventSource | null>(null);
  const { addEvent, appendThinking, clearThinking, setConnected, reset } =
    useIncidentStreamStore();

  useEffect(() => {
    if (!incidentId) return;

    reset();

    const es = new EventSource(`/api/incidents/${incidentId}/stream`);
    eventSourceRef.current = es;

    es.onopen = () => {
      setConnected(true);
    };

    es.onmessage = (e) => {
      try {
        const event: SSEEvent = JSON.parse(e.data);

        if (event.event_type === "thinking") {
          appendThinking(event.data.content as string);
        } else {
          // When a non-thinking event arrives, flush thinking content
          const { thinkingContent } = useIncidentStreamStore.getState();
          if (thinkingContent) {
            addEvent({
              event_type: "thinking",
              data: { content: thinkingContent },
              timestamp: event.timestamp,
            });
            clearThinking();
          }
          addEvent(event);
        }
      } catch {
        // ignore malformed events
      }
    };

    es.onerror = () => {
      setConnected(false);
    };

    return () => {
      es.close();
      eventSourceRef.current = null;
      setConnected(false);
    };
  }, [incidentId]);
}
