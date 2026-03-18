import { useCallback } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { uploadFiles } from "@/api/attachments";
import { sendIncidentMessage } from "@/api/incidents";
import { PromptComposer } from "@/components/prompt-composer";
import { useIncidentStreamStore } from "@/stores/incident-stream";

interface UserInputBarProps {
  incidentId: string;
  incidentStatus?: string;
}

const TERMINAL_STATUSES = ["resolved", "closed", "stopped"];

export function UserInputBar({ incidentId, incidentStatus }: UserInputBarProps) {
  const queryClient = useQueryClient();
  const { askHumanQuestion, setAskHumanQuestion, kbConfirmData, kbConfirmResolved, setKbConfirmResolved, addEvent } = useIncidentStreamStore();

  const isTerminal = !!incidentStatus && TERMINAL_STATUSES.includes(incidentStatus);
  const isWaitingForInput = !!askHumanQuestion || (!!kbConfirmData && !kbConfirmResolved);
  const isAgentWorking = incidentStatus === "investigating" && !isWaitingForInput;
  const isInputDisabled = isTerminal || isAgentWorking;

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
      if (kbConfirmData) setKbConfirmResolved(true);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["incidents", incidentId] });
    },
  });

  const handleSubmit = useCallback(
    (text: string, files: File[]) => {
      mutation.mutate({ content: text, files });
    },
    [mutation],
  );

  const placeholder = isTerminal
    ? "事件已结束"
    : isAgentWorking
      ? "Agent 正在调查中..."
      : kbConfirmData && !kbConfirmResolved
        ? "输入补充信息或点击确认继续..."
        : askHumanQuestion
          ? "回复 Agent 的问题..."
          : "向 Agent 发送消息...";

  return (
    <div className="border-t p-4">
      <PromptComposer
        onSubmit={handleSubmit}
        isLoading={mutation.isPending}
        disabled={isInputDisabled || mutation.isPending}
        placeholder={placeholder}
      />
    </div>
  );
}
