import { useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useIncidentStreamStore } from "@/stores/incident-stream";
import { getIncidentEvents } from "@/api/incidents";
import { sseEventSchema } from "@/lib/schemas";
import type { SSEEvent } from "@/lib/types";

const BASE_DELAY = 1000;
const MAX_BACKOFF = 30_000;
const HEARTBEAT_TIMEOUT = 120_000;
const MAX_RETRIES = 15;

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
  const heartbeatTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  const lastTimestampRef = useRef("");
  const seenEventIdsRef = useRef<Set<string>>(new Set());
  const loadedForRef = useRef("");
  const loadedEventsRef = useRef<SSEEvent[] | null>(null);
  const statusRef = useRef(status);
  const hasInvalidatedIncidentRef = useRef(false);

  const {
    addEvent,
    appendThinking,
    clearThinking,
    appendAnswer,
    clearAnswer,
    appendAskHuman,
    clearAskHumanStream,
    appendSubAgentThinking,
    flushSubAgentThinking,
    addSubAgentEvent,
    setSubAgentStatus,
    updatePhase,
    setAskHumanQuestion,
    setResolutionConfirmRequired,
    setResolutionConfirmResolved,
    setWaitingForAgent,
    setApprovalDecided,
    setPlannerPlanMd,
    appendPlannerThinking,
    setPlannerProgress,
    endRound,
    setConnected,
    reset,
    loadHistory,
  } = useIncidentStreamStore();

  // Keep statusRef in sync
  useEffect(() => {
    statusRef.current = status;
  }, [status]);

  // Close SSE when incident reaches terminal state
  useEffect(() => {
    if (status === "resolved" || status === "stopped") {
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
      clearTimeout(retryTimerRef.current);
      clearTimeout(heartbeatTimerRef.current);
      setConnected(false);
    }
    // oxlint-disable-next-line react/exhaustive-deps -- setConnected is a stable zustand action
  }, [status]);

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
      seenEventIdsRef.current = new Set();
      hasInvalidatedIncidentRef.current = false;
    };
    // oxlint-disable-next-line react/exhaustive-deps -- reset is a stable zustand action
  }, [incidentId]);

  useEffect(() => {
    if (!incidentId) return;

    // Incident changed → reset
    if (loadedForRef.current && loadedForRef.current !== incidentId) {
      reset();
      lastTimestampRef.current = "";
      seenEventIdsRef.current = new Set();
      loadedForRef.current = "";
      loadedEventsRef.current = null;
      hasInvalidatedIncidentRef.current = false;
    }

    // Load history once per incident
    if (historyEvents && !loadedForRef.current) {
      loadHistory(historyEvents);
      loadedForRef.current = incidentId;
      loadedEventsRef.current = historyEvents;
      // Populate seenEventIds from history
      for (const e of historyEvents) {
        if (e.event_id) seenEventIdsRef.current.add(e.event_id);
      }
      if (historyEvents.length > 0) {
        lastTimestampRef.current =
          historyEvents[historyEvents.length - 1].timestamp;
      }
    } else if (
      historyEvents &&
      loadedForRef.current === incidentId &&
      loadedEventsRef.current !== historyEvents &&
      (
        statusRef.current === "resolved" || statusRef.current === "stopped" ||
        (historyEvents.length > 0 && (!loadedEventsRef.current || loadedEventsRef.current.length === 0))
      )
    ) {
      // Reload history when:
      // - Terminal incidents: React Query refetches newer data
      // - Active incidents: initial load was empty but refetch returned actual data
      loadHistory(historyEvents);
      loadedEventsRef.current = historyEvents;
      // Repopulate seenEventIds
      for (const e of historyEvents) {
        if (e.event_id) seenEventIdsRef.current.add(e.event_id);
      }
      if (historyEvents.length > 0) {
        lastTimestampRef.current =
          historyEvents[historyEvents.length - 1].timestamp;
      }
    }

    // Gate SSE on history being loaded
    if (loadedForRef.current !== incidentId) return;
    // No SSE for terminal incidents
    if (statusRef.current === "resolved" || statusRef.current === "stopped") return;

    retriesRef.current = 0;

    function resetHeartbeat() {
      clearTimeout(heartbeatTimerRef.current);
      heartbeatTimerRef.current = setTimeout(() => {
        // Heartbeat timeout — force reconnect
        eventSourceRef.current?.close();
        eventSourceRef.current = null;
        setConnected(false);
        const delay = Math.min(BASE_DELAY * Math.pow(2, retriesRef.current), MAX_BACKOFF);
        retriesRef.current++;
        retryTimerRef.current = setTimeout(connect, delay);
      }, HEARTBEAT_TIMEOUT);
    }

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
        resetHeartbeat();
      };

      es.onmessage = (e) => {
        resetHeartbeat();

        try {
          const raw = JSON.parse(e.data);
          const result = sseEventSchema.safeParse(raw);
          if (!result.success) return;

          const event = result.data as SSEEvent;
          const isReplay = event.replay === true;

          // Dedup by event_id
          if (!isReplay && event.event_id) {
            if (seenEventIdsRef.current.has(event.event_id)) return;
            seenEventIdsRef.current.add(event.event_id);
          } else if (
            !isReplay &&
            !event.event_id &&
            lastTimestampRef.current &&
            event.timestamp <= lastTimestampRef.current
          ) {
            // Fallback: timestamp-based dedup when no event_id
            return;
          }

          // Update lastTimestamp for reconnection
          lastTimestampRef.current = event.timestamp;

          const phase = (event.data.phase as string) || "";
          const agent = (event.data.agent as string) || "";

          // Replay events: DB records with complete content, route like loadHistory
          if (isReplay) {
            if (event.event_id) {
              seenEventIdsRef.current.add(event.event_id);
            }
            if (event.event_type === "approval_decided") {
              setApprovalDecided(
                event.data.approval_id as string,
                event.data.decision as string,
                event.data.supplement_text as string | undefined,
              );
            } else if (event.event_type === "thinking_done" || event.event_type === "answer_done" || event.event_type === "ask_human_done") {
              // DB boundary marker, skip
            } else if (event.event_type === "confirm_resolution_required") {
              // Replay: restore resolution confirm state
              setResolutionConfirmRequired(true);
            } else if (event.event_type === "resolution_confirmed") {
              setResolutionConfirmResolved(true);
            } else if (event.event_type === "plan_generated" || event.event_type === "plan_updated") {
              setPlannerPlanMd((event.data.plan_md as string) || "");
              if (event.event_type === "plan_updated" && phase === "investigation") {
                addEvent(event);
              }
            } else if (event.event_type === "planner_started" || event.event_type === "planner_progress") {
              // skip — phase update handled below
            } else if (event.event_type === "agent_status") {
              if (phase === "gather_context" && (agent === "history" || agent === "kb")) {
                setSubAgentStatus(agent, event.data.status as "started" | "completed" | "failed");
              }
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
            } else if (event.event_type === "done") {
              updatePhase("summary_complete");
            } else if (phase) {
              updatePhase(phase);
            } else {
              updatePhase("investigation");
            }
            return;
          }

          // Invalidate incident query once on first real-time event
          // so the status badge updates (e.g. open → investigating)
          // Delay 500ms to ensure backend DB commit has completed
          if (!hasInvalidatedIncidentRef.current) {
            hasInvalidatedIncidentRef.current = true;
            setTimeout(() => {
              queryClient.invalidateQueries({ queryKey: ["incident", incidentId] });
            }, 500);
          }

          // Real-time events
          if (phase === "gather_context") {
            updatePhase("gather_context");
          }

          if (phase === "gather_context" && (agent === "history" || agent === "kb")) {
            if (event.event_type === "agent_status") {
              setSubAgentStatus(agent, event.data.status as "started" | "completed" | "failed");
            } else if (event.event_type === "thinking_done") {
              flushSubAgentThinking(agent, event.timestamp);
            } else if (event.event_type === "thinking") {
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
              event.data.supplement_text as string | undefined,
            );
          } else if (event.event_type === "done") {
            setWaitingForAgent(false);
            // Add done event to timeline (renders "Agent 排查完成" separator)
            addEvent(event);
            // Agent completed; invalidate queries + close SSE
            updatePhase("summary_complete");
            setResolutionConfirmResolved(true);
            queryClient.invalidateQueries({ queryKey: ["incident", incidentId] });
            queryClient.invalidateQueries({ queryKey: ["incidents"] });
            queryClient.invalidateQueries({ queryKey: ["incident-events", incidentId] });
          } else if (event.event_type === "confirm_resolution_required") {
            setResolutionConfirmRequired(true);
            setResolutionConfirmResolved(false);
          } else if (event.event_type === "resolution_confirmed") {
            setResolutionConfirmResolved(true);
          } else if (event.event_type === "agent_interrupted") {
            // Flush thinking buffer
            const { thinkingContent: intThk } = useIncidentStreamStore.getState();
            if (intThk) {
              addEvent({
                event_type: "thinking",
                data: { content: intThk },
                timestamp: event.timestamp,
              });
              clearThinking();
            }
            // Flush answer buffer
            const { answerContent: intAns } = useIncidentStreamStore.getState();
            if (intAns) {
              addEvent({
                event_type: "answer",
                data: { content: intAns },
                timestamp: event.timestamp,
              });
              clearAnswer();
            }
            // Add interrupted event to timeline (renders "已中断" separator)
            addEvent(event);
            setWaitingForAgent(false);
            // Don't close SSE — interrupted is not terminal. Refresh incident status.
            queryClient.invalidateQueries({ queryKey: ["incident", incidentId] });
          } else if (event.event_type === "incident_stopped") {
            addEvent(event);
            // Close SSE and invalidate queries to refresh status
            es.close();
            eventSourceRef.current = null;
            setConnected(false);
            clearTimeout(heartbeatTimerRef.current);
            queryClient.invalidateQueries({ queryKey: ["incident", incidentId] });
            queryClient.invalidateQueries({ queryKey: ["incidents"] });
            queryClient.invalidateQueries({ queryKey: ["incident-events", incidentId] });
          } else if (event.event_type === "ask_human") {
            setWaitingForAgent(false);
            updatePhase("investigation");
            // Flush residual thinking
            const { thinkingContent: thk } = useIncidentStreamStore.getState();
            if (thk) {
              addEvent({
                event_type: "thinking",
                data: { content: thk },
                timestamp: event.timestamp,
              });
              clearThinking();
            }
            // Accumulate incremental question
            appendAskHuman(event.data.question as string);
          } else if (event.event_type === "ask_human_done") {
            const { askHumanStreamContent } = useIncidentStreamStore.getState();
            if (askHumanStreamContent) {
              addEvent({
                event_type: "ask_human",
                data: { question: askHumanStreamContent },
                timestamp: event.timestamp,
              });
              setAskHumanQuestion(askHumanStreamContent);
              clearAskHumanStream();
            }
          } else if (event.event_type === "planner_started") {
            updatePhase("planning");
          } else if (event.event_type === "planner_progress") {
            setPlannerProgress(event.data.status as string);
            updatePhase("planning");
          } else if (event.event_type === "thinking") {
            setWaitingForAgent(false);
            if (phase === "planning") {
              updatePhase("planning");
              appendPlannerThinking(event.data.content as string);
            } else {
              updatePhase("investigation");
              appendThinking(event.data.content as string);
            }
          } else if (event.event_type === "thinking_done") {
            if (phase === "planning") {
              // Planner thinking done — structured result event will follow
            } else {
              const { thinkingContent } =
                useIncidentStreamStore.getState();
              if (thinkingContent) {
                addEvent({
                  event_type: "thinking",
                  data: { content: thinkingContent },
                  timestamp: event.timestamp,
                });
                clearThinking();
              }
            }
          } else if (event.event_type === "answer") {
            setWaitingForAgent(false);
            updatePhase("investigation");
            // Flush any residual thinking
            const { thinkingContent } = useIncidentStreamStore.getState();
            if (thinkingContent) {
              addEvent({
                event_type: "thinking",
                data: { content: thinkingContent },
                timestamp: event.timestamp,
              });
              clearThinking();
            }
            // Stream accumulate
            appendAnswer(event.data.content as string);
          } else if (event.event_type === "answer_done") {
            // Flush answer buffer → add as complete event
            const { answerContent } = useIncidentStreamStore.getState();
            if (answerContent) {
              addEvent({
                event_type: "answer",
                data: { content: answerContent },
                timestamp: event.timestamp,
              });
              clearAnswer();
            }
          } else if (event.event_type === "plan_generated" || event.event_type === "plan_updated") {
            setPlannerPlanMd((event.data.plan_md as string) || "");
            // plan_updated during investigation → also add to timeline for inline indicator
            if (event.event_type === "plan_updated" && phase === "investigation") {
              addEvent(event);
            }
            updatePhase(phase || "planning");
          } else if (event.event_type === "round_started") {
            addEvent(event);
          } else if (event.event_type === "round_ended") {
            endRound(event.data.round as number, (event.data.summary as string) || "");
            addEvent(event);
          } else if (event.event_type === "agent_status") {
            // main-phase agent_status: ignore (only relevant for gather_context)
          } else {
            updatePhase("investigation");
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
            setWaitingForAgent(event.event_type === "tool_result");
          }
        } catch {
          // ignore unparseable JSON
        }
      };

      es.onerror = () => {
        es.close();
        eventSourceRef.current = null;
        setConnected(false);
        clearTimeout(heartbeatTimerRef.current);

        // Stop retrying after MAX_RETRIES
        if (retriesRef.current >= MAX_RETRIES) {
          return;
        }

        // Reconnect with exponential backoff capped at MAX_BACKOFF
        const delay = Math.min(BASE_DELAY * Math.pow(2, retriesRef.current), MAX_BACKOFF);
        retriesRef.current++;
        retryTimerRef.current = setTimeout(connect, delay);
      };
    }

    connect();

    return () => {
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
      clearTimeout(retryTimerRef.current);
      clearTimeout(heartbeatTimerRef.current);
      setConnected(false);
    };
    // oxlint-disable-next-line react/exhaustive-deps -- store actions are stable zustand references
  }, [incidentId, historyEvents]);
}
