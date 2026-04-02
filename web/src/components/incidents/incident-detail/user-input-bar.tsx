import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { X } from "lucide-react";
import { uploadFiles } from "@/api/attachments";
import { decideApproval } from "@/api/approvals";
import { interruptIncident, sendIncidentMessage } from "@/api/incidents";
import { PromptComposer } from "@/components/prompt-composer";
import { useIncidentStreamStore } from "@/stores/incident-stream";

interface UserInputBarProps {
  incidentId: string;
  incidentStatus?: string;
}

const TERMINAL_STATUSES = ["resolved", "stopped"];

export function UserInputBar({ incidentId, incidentStatus }: UserInputBarProps) {
  const queryClient = useQueryClient();
  const {
    askHumanQuestion,
    setAskHumanQuestion,
    resolutionConfirmRequired,
    resolutionConfirmResolved,
    setResolutionConfirmRequired,
    pendingSupplement,
    setPendingSupplement,
    setApprovalDecided,
    triggerScrollToBottom,
    addEvent,
    setWaitingForAgent,
  } = useIncidentStreamStore();

  const isTerminal = !!incidentStatus && TERMINAL_STATUSES.includes(incidentStatus);
  const isWaitingForInput = !!askHumanQuestion || (resolutionConfirmRequired && !resolutionConfirmResolved);
  const isAgentWorking = incidentStatus === "investigating" && !isWaitingForInput && !pendingSupplement;
  const isInputDisabled = isTerminal;

  const [isInterrupting, setIsInterrupting] = useState(false);
  const interruptTimeoutRef = useRef<ReturnType<typeof setTimeout>>();

  useEffect(() => {
    if (isInterrupting && !isAgentWorking) {
      setIsInterrupting(false);
      clearTimeout(interruptTimeoutRef.current);
    }
  }, [isInterrupting, isAgentWorking]);

  useEffect(() => {
    return () => clearTimeout(interruptTimeoutRef.current);
  }, []);
  const isSupplementMode = !!pendingSupplement;

  // Normal message mutation
  const mutation = useMutation({
    mutationFn: async ({
      content,
      files,
    }: {
      content: string;
      files: File[];
    }) => {
      let attachmentIds: string[] | undefined;
      if (files.length > 0) {
        const attachments = await uploadFiles(files);
        attachmentIds = attachments.map((a) => a.id);
      }
      return sendIncidentMessage(incidentId, content, attachmentIds);
    },
    onMutate: ({ content, files }) => {
      const optimisticAttachments = files.map((f) => ({
        filename: f.name,
        content_type: f.type,
        size: f.size,
        preview_url: f.type.startsWith("image/")
          ? URL.createObjectURL(f)
          : null,
      }));

      addEvent({
        event_id: `optimistic-${Date.now()}`,
        event_type: "user_message",
        data: {
          content,
          ...(optimisticAttachments.length > 0 && {
            attachments: optimisticAttachments,
          }),
        },
        timestamp: new Date().toISOString(),
      });
      setAskHumanQuestion(null);
      if (resolutionConfirmRequired) setResolutionConfirmRequired(false);
      setWaitingForAgent(true);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["incidents", incidentId] });
    },
    onError: () => {
      toast.error("消息发送失败，请重试");
    },
  });

  // Supplement mutation
  const supplementMutation = useMutation({
    mutationFn: async ({
      content,
      files,
    }: {
      content: string;
      files: File[];
    }) => {
      let fullContent = content;
      if (files.length > 0) {
        const attachments = await uploadFiles(files);
        const fileNames = attachments.map((a) => a.filename).join(", ");
        fullContent += `\n\n[附件: ${fileNames}]`;
      }
      await decideApproval(pendingSupplement!.approvalId, {
        decision: "supplemented",
        supplement_text: fullContent,
        silent: true,
      });
      return fullContent;
    },
    onSuccess: (fullContent) => {
      setApprovalDecided(pendingSupplement!.approvalId, "supplemented", fullContent);
      setPendingSupplement(null);
      triggerScrollToBottom();
    },
    onError: () => {
      toast.error("补充说明发送失败，请重试");
    },
  });

  const interruptMutation = useMutation({
    mutationFn: () => interruptIncident(incidentId),
    onMutate: () => {
      setIsInterrupting(true);
      clearTimeout(interruptTimeoutRef.current);
      interruptTimeoutRef.current = setTimeout(() => setIsInterrupting(false), 10_000);
    },
    onError: () => {
      setIsInterrupting(false);
      clearTimeout(interruptTimeoutRef.current);
      toast.error("打断失败，请重试");
    },
  });

  const handleSubmit = useCallback(
    (text: string, files: File[]) => {
      if (isSupplementMode) {
        supplementMutation.mutate({ content: text, files });
      } else {
        mutation.mutate({ content: text, files });
      }
    },
    [isSupplementMode, mutation, supplementMutation],
  );

  const activeMutation = isSupplementMode ? supplementMutation : mutation;

  const placeholder = isTerminal
    ? ""
    : isSupplementMode
      ? "输入补充说明后发送，Agent 将重新思考方案..."
      : incidentStatus === "error"
        ? "发送消息以重试排查..."
        : incidentStatus === "interrupted"
          ? "输入内容后发送以继续排查..."
          : isAgentWorking
            ? "输入内容，点击停止后发送..."
            : resolutionConfirmRequired && !resolutionConfirmResolved
              ? "输入新问题继续排查，或点击「已解决」..."
              : askHumanQuestion
                  ? "回复 Agent 的问题..."
                  : "向 Agent 发送消息...";

  return (
    <div className="px-14 py-4">
      {isSupplementMode && (
        <div className="mb-2 flex items-center justify-between rounded-md bg-blue-50 px-3 py-1.5 text-xs text-blue-700 dark:bg-blue-950/50 dark:text-blue-300">
          <span>为操作审批补充说明</span>
          <button
            onClick={() => setPendingSupplement(null)}
            className="ml-2 rounded p-0.5 hover:bg-blue-100 dark:hover:bg-blue-900"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
      <PromptComposer
        onSubmit={handleSubmit}
        isLoading={activeMutation.isPending}
        disabled={isInputDisabled || activeMutation.isPending}
        placeholder={placeholder}
        showInterrupt={isAgentWorking}
        onInterrupt={() => { if (!isInterrupting) interruptMutation.mutate(); }}
        isInterrupting={isInterrupting}
        accentMode={isSupplementMode ? "flowing" : undefined}
      />
    </div>
  );
}
