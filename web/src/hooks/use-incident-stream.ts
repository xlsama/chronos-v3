import { useEffect, useRef } from "react";
import { useIncidentStreamStore } from "@/stores/incident-stream";
import { sseEventSchema } from "@/lib/schemas";
import type { SSEEvent } from "@/lib/types";

const MAX_RETRIES = 5;
const BASE_DELAY = 1000;

export function useIncidentStream(incidentId: string | undefined) {
  const eventSourceRef = useRef<EventSource | null>(null);
  const retriesRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const {
    addEvent,
    appendThinking,
    clearThinking,
    appendSubAgentThinking,
    flushSubAgentThinking,
    addSubAgentEvent,
    setAskHumanQuestion,
    setConnected,
    reset,
  } = useIncidentStreamStore();

  useEffect(() => {
    if (!incidentId) return;

    reset();

    function connect() {
      const es = new EventSource(`/api/incidents/${incidentId}/stream`);
      eventSourceRef.current = es;

      es.onopen = () => {
        retriesRef.current = 0;
        setConnected(true);
      };

      es.onmessage = (e) => {
        try {
          const raw = JSON.parse(e.data);
          const result = sseEventSchema.safeParse(raw);

          if (!result.success) {
            console.warn("[SSE] Malformed event:", result.error.issues, raw);
            return;
          }

          const event = result.data as SSEEvent;
          const phase = (event.data.phase as string) || "";
          const agent = (event.data.agent as string) || "history";

          if (phase === "discover_project") {
            if (event.event_type === "thinking") {
              appendSubAgentThinking("discovery", event.data.content as string);
            } else {
              flushSubAgentThinking("discovery", event.timestamp);
              addSubAgentEvent("discovery", event);
            }
          } else if (phase === "gather_context") {
            if (event.event_type === "thinking") {
              appendSubAgentThinking(agent, event.data.content as string);
            } else {
              flushSubAgentThinking(agent, event.timestamp);
              addSubAgentEvent(agent, event);
            }
          } else if (event.event_type === "ask_human") {
            setAskHumanQuestion(event.data.question as string);
            addEvent(event);
          } else if (event.event_type === "thinking") {
            appendThinking(event.data.content as string);
          } else {
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
          // ignore unparseable JSON
        }
      };

      es.onerror = () => {
        es.close();
        eventSourceRef.current = null;
        setConnected(false);

        if (retriesRef.current < MAX_RETRIES) {
          const delay = BASE_DELAY * Math.pow(2, retriesRef.current);
          retriesRef.current++;
          retryTimerRef.current = setTimeout(connect, delay);
        }
      };
    }

    connect();

    return () => {
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
      clearTimeout(retryTimerRef.current);
      setConnected(false);
    };
  }, [incidentId]);
}
