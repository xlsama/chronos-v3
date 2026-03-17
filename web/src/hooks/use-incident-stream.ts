import { useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
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
  const queryClient = useQueryClient();
  const eventSourceRef = useRef<EventSource | null>(null);
  const retriesRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  const lastTimestampRef = useRef("");
  const loadedForRef = useRef("");
  const loadedEventsRef = useRef<SSEEvent[] | null>(null);

  const {
    addEvent,
    appendThinking,
    clearThinking,
    appendReportStream,
    clearReportStream,
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

  // Reset store when navigating away (unmount) or switching incidents
  useEffect(() => {
    return () => {
      reset();
      loadedForRef.current = "";
      loadedEventsRef.current = null;
      lastTimestampRef.current = "";
    };
  }, [incidentId]);

  useEffect(() => {
    if (!incidentId) return;

    // Incident changed → reset
    if (loadedForRef.current && loadedForRef.current !== incidentId) {
      reset();
      lastTimestampRef.current = "";
      loadedForRef.current = "";
      loadedEventsRef.current = null;
    }

    // Load history once per incident
    if (historyEvents && !loadedForRef.current) {
      loadHistory(historyEvents);
      loadedForRef.current = incidentId;
      loadedEventsRef.current = historyEvents;
      if (historyEvents.length > 0) {
        lastTimestampRef.current =
          historyEvents[historyEvents.length - 1].timestamp;
      }
    } else if (
      historyEvents &&
      loadedForRef.current === incidentId &&
      loadedEventsRef.current !== historyEvents &&
      (status === "resolved" || status === "closed" || status === "stopped")
    ) {
      // Terminal incidents: reload when React Query refetches newer data
      loadHistory(historyEvents);
      loadedEventsRef.current = historyEvents;
      if (historyEvents.length > 0) {
        lastTimestampRef.current =
          historyEvents[historyEvents.length - 1].timestamp;
      }
    }

    // Gate SSE on history being loaded
    if (loadedForRef.current !== incidentId) return;
    // No SSE for terminal incidents
    if (status === "resolved" || status === "closed" || status === "stopped") return;

    retriesRef.current = 0;

    function connect() {
      let url = `/api/incidents/${incidentId}/stream`;
      if (lastTimestampRef.current) {
        url += `?since=${encodeURIComponent(lastTimestampRef.current)}`;
      }
      const es = new EventSource(url);
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
          const isReplay = event.replay === true;

          // Dedup: skip events already covered by history (only for non-replay)
          if (
            !isReplay &&
            lastTimestampRef.current &&
            event.timestamp <= lastTimestampRef.current
          ) {
            return;
          }

          // Update lastTimestamp for reconnection
          lastTimestampRef.current = event.timestamp;

          const phase = (event.data.phase as string) || "";
          const agent = (event.data.agent as string) || "";

          // Replay events: DB records with complete content, route like loadHistory
          if (isReplay) {
            if (event.event_type === "approval_decided") {
              setApprovalDecided(
                event.data.approval_id as string,
                event.data.decision as string,
              );
            } else if (
              phase === "gather_context" &&
              (agent === "history" || agent === "kb")
            ) {
              addSubAgentEvent(agent, event);
            } else {
              addEvent(event);
            }
            // Update phase state
            if (phase === "gather_context") {
              updatePhase("gather_context");
            } else if (event.event_type === "summary") {
              updatePhase("summary_complete");
            } else if (phase) {
              updatePhase(phase);
            } else {
              updatePhase("main");
            }
            return;
          }

          // Real-time events
          if (phase === "gather_context") {
            updatePhase("gather_context");
          }

          if (phase === "gather_context" && (agent === "history" || agent === "kb")) {
            if (event.event_type === "thinking") {
              appendSubAgentThinking(agent, event.data.content as string);
            } else {
              flushSubAgentThinking(agent, event.timestamp);
              addSubAgentEvent(agent, event);
            }
          } else if (event.event_type === "user_message") {
            addEvent(event);
          } else if (event.event_type === "approval_decided") {
            setApprovalDecided(
              event.data.approval_id as string,
              event.data.decision as string,
            );
          } else if (phase === "summarize" && event.event_type === "thinking") {
            appendReportStream(event.data.content as string);
          } else if (event.event_type === "summary") {
            clearReportStream();
            updatePhase("summary_complete");
            addEvent(event);
            queryClient.invalidateQueries({ queryKey: ["incident", incidentId] });
            queryClient.invalidateQueries({ queryKey: ["incidents"] });
            queryClient.invalidateQueries({ queryKey: ["incident-events", incidentId] });
          } else if (event.event_type === "incident_stopped") {
            addEvent(event);
            // Close SSE and invalidate queries to refresh status
            es.close();
            eventSourceRef.current = null;
            setConnected(false);
            queryClient.invalidateQueries({ queryKey: ["incident", incidentId] });
            queryClient.invalidateQueries({ queryKey: ["incidents"] });
            queryClient.invalidateQueries({ queryKey: ["incident-events", incidentId] });
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
