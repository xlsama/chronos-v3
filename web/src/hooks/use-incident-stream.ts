import { useEffect, useRef } from "react";
import { useIncidentStreamStore } from "@/stores/incident-stream";
import type { SSEEvent } from "@/lib/types";

export function useIncidentStream(incidentId: string | undefined) {
  const eventSourceRef = useRef<EventSource | null>(null);
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

    const es = new EventSource(`/api/incidents/${incidentId}/stream`);
    eventSourceRef.current = es;

    es.onopen = () => {
      setConnected(true);
    };

    es.onmessage = (e) => {
      try {
        const event: SSEEvent = JSON.parse(e.data);
        const phase = (event.data.phase as string) || "";
        const agent = (event.data.agent as string) || "history";

        if (phase === "gather_context") {
          // Sub agent events — dispatch by agent name
          if (event.event_type === "thinking") {
            appendSubAgentThinking(agent, event.data.content as string);
          } else {
            // Flush accumulated thinking before non-thinking event
            flushSubAgentThinking(agent, event.timestamp);
            addSubAgentEvent(agent, event);
          }
        } else if (event.event_type === "ask_human") {
          // Agent is asking the human a question
          setAskHumanQuestion(event.data.question as string);
          addEvent(event);
        } else if (event.event_type === "thinking") {
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
