import { motion, AnimatePresence } from "motion/react";
import { useIncidentStreamStore } from "@/stores/incident-stream";
import { ThinkingBubble } from "./thinking-bubble";
import { ToolCallCard } from "./tool-call-card";
import { ApprovalCard } from "./approval-card";
import { SummarySection } from "./summary-section";
import { SubAgentCard } from "./sub-agent-card";
import { MessageCircleQuestion } from "lucide-react";

interface EventTimelineProps {
  incidentId?: string;
  savedToMemory?: boolean;
}

const itemVariants = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.3 } },
  exit: { opacity: 0, y: -8, transition: { duration: 0.2 } },
};

export function EventTimeline({ incidentId, savedToMemory }: EventTimelineProps) {
  const {
    events,
    historyAgentState,
    kbAgentState,
    thinkingContent,
  } = useIncidentStreamStore();

  const hasHistory =
    historyAgentState.events.length > 0 ||
    !!historyAgentState.thinkingContent;
  const hasKB =
    kbAgentState.events.length > 0 || !!kbAgentState.thinkingContent;
  const hasGatherContext = hasHistory || hasKB;

  return (
    <div className="space-y-3 p-4" data-testid="event-timeline">
      {/* Gather Context Phase — sub agent cards in grid */}
      {hasGatherContext && (
        <div className="grid gap-3 sm:grid-cols-2">
          {hasHistory && (
            <SubAgentCard
              agentName="history"
              events={historyAgentState.events}
              isStreaming={!!historyAgentState.thinkingContent}
              streamingContent={historyAgentState.thinkingContent}
            />
          )}
          {hasKB && (
            <SubAgentCard
              agentName="kb"
              events={kbAgentState.events}
              isStreaming={!!kbAgentState.thinkingContent}
              streamingContent={kbAgentState.thinkingContent}
            />
          )}
        </div>
      )}

      {/* Main Agent Events */}
      <AnimatePresence initial={false}>
        {events.map((event, i) => {
          switch (event.event_type) {
            case "thinking":
              return (
                <motion.div key={i} variants={itemVariants} initial="hidden" animate="visible" layout>
                  <ThinkingBubble
                    content={event.data.content as string}
                  />
                </motion.div>
              );
            case "tool_call":
              return (
                <motion.div key={i} variants={itemVariants} initial="hidden" animate="visible" layout>
                  <ToolCallCard
                    name={event.data.name as string}
                    args={event.data.args as Record<string, unknown>}
                  />
                </motion.div>
              );
            case "tool_result":
              return (
                <motion.div key={i} variants={itemVariants} initial="hidden" animate="visible" layout>
                  <ToolCallCard
                    name={event.data.name as string}
                    output={event.data.output as string}
                    isResult
                  />
                </motion.div>
              );
            case "approval_required":
              return (
                <motion.div key={i} variants={itemVariants} initial="hidden" animate="visible" layout>
                  <ApprovalCard
                    toolCall={event.data.tool_args as Record<string, unknown>}
                    approvalId={event.data.approval_id as string}
                  />
                </motion.div>
              );
            case "ask_human":
              return (
                <motion.div key={i} variants={itemVariants} initial="hidden" animate="visible" layout>
                  <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50/50 p-4">
                    <MessageCircleQuestion className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
                    <div>
                      <p className="text-sm font-medium text-amber-800">
                        Agent 需要更多信息
                      </p>
                      <p className="mt-1 text-sm text-amber-700">
                        {event.data.question as string}
                      </p>
                    </div>
                  </div>
                </motion.div>
              );
            case "summary":
              return (
                <motion.div key={i} variants={itemVariants} initial="hidden" animate="visible" layout>
                  <SummarySection
                    markdown={event.data.summary_md as string}
                    incidentId={incidentId}
                    savedToMemory={savedToMemory}
                  />
                </motion.div>
              );
            case "error":
              return (
                <motion.div key={i} variants={itemVariants} initial="hidden" animate="visible" layout>
                  <div className="rounded-md border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
                    Error: {event.data.message as string}
                  </div>
                </motion.div>
              );
            default:
              return null;
          }
        })}
      </AnimatePresence>

      {/* Live thinking stream */}
      <AnimatePresence>
        {thinkingContent && (
          <motion.div
            key="live-thinking"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
          >
            <ThinkingBubble content={thinkingContent} isStreaming />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
