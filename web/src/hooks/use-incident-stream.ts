import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { useIncidentStreamStore } from "@/stores/incident-stream";
import { getIncidentEvents } from "@/api/incidents";
import { sseEventSchema } from "@/lib/schemas";
import type { SSEEvent } from "@/lib/types";

const MAX_RETRIES = 5;
const BASE_DELAY = 1000;

export function useIncidentStream(
  incidentId: string | undefined,
  status: string | undefined,
) {
  const eventSourceRef = useRef<EventSource | null>(null);
  const retriesRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  const lastTimestampRef = useRef("");
  const loadedForRef = useRef("");

  const {
    addEvent,
    appendThinking,
    clearThinking,
    appendSubAgentThinking,
    flushSubAgentThinking,
    addSubAgentEvent,
    updatePhase,
    setAskHumanQuestion,
    setApprovalDecided,
    setConnected,
    reset,
    loadHistory,
  } = useIncidentStreamStore();

  // Fetch persisted history events
  const { data: historyEvents } = useQuery({
    queryKey: ["incident-events", incidentId],
    queryFn: () => getIncidentEvents(incidentId!),
    enabled: !!incidentId,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (!incidentId) return;

    // Incident changed → reset
    if (loadedForRef.current && loadedForRef.current !== incidentId) {
      reset();
      lastTimestampRef.current = "";
      loadedForRef.current = "";
    }

    // Load history once per incident
    if (historyEvents && !loadedForRef.current) {
      loadHistory(historyEvents);
      loadedForRef.current = incidentId;
      if (historyEvents.length > 0) {
        lastTimestampRef.current =
          historyEvents[historyEvents.length - 1].timestamp;
      }
    }

    // Gate SSE on history being loaded
    if (loadedForRef.current !== incidentId) return;
    // No SSE for completed incidents
    if (status === "resolved" || status === "closed") return;

    retriesRef.current = 0;

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
          if (!result.success) return;

          const event = result.data as SSEEvent;

          // Dedup: skip events already covered by history
          if (
            lastTimestampRef.current &&
            event.timestamp <= lastTimestampRef.current
          ) {
            return;
          }

          const phase = (event.data.phase as string) || "";
          const agent = (event.data.agent as string) || "";

          if (phase === "discover_project" || phase === "gather_context") {
            updatePhase("gather_context");
          }

          if (phase === "discover_project") {
            if (event.event_type === "thinking") {
              appendSubAgentThinking(
                "discovery",
                event.data.content as string,
              );
            } else {
              flushSubAgentThinking("discovery", event.timestamp);
              addSubAgentEvent("discovery", event);
            }
          } else if (phase === "gather_context" && (agent === "history" || agent === "kb")) {
            if (event.event_type === "thinking") {
              appendSubAgentThinking(agent, event.data.content as string);
            } else {
              flushSubAgentThinking(agent, event.timestamp);
              addSubAgentEvent(agent, event);
            }
          } else if (event.event_type === "approval_decided") {
            setApprovalDecided(
              event.data.approval_id as string,
              event.data.decision as string,
            );
          } else if (event.event_type === "summary") {
            updatePhase("summarize");
            addEvent(event);
          } else if (event.event_type === "ask_human") {
            updatePhase("main");
            setAskHumanQuestion(event.data.question as string);
            addEvent(event);
          } else if (event.event_type === "thinking") {
            updatePhase("main");
            appendThinking(event.data.content as string);
          } else {
            updatePhase("main");
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
  }, [incidentId, historyEvents, status]);
}
