import { useCallback } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { uploadFiles } from "@/api/attachments";
import { sendIncidentMessage } from "@/api/incidents";
import { PromptComposer } from "@/components/prompt-composer";
import { useIncidentStreamStore } from "@/stores/incident-stream";

interface UserInputBarProps {
  incidentId: string;
}

export function UserInputBar({ incidentId }: UserInputBarProps) {
  const queryClient = useQueryClient();
  const { askHumanQuestion, setAskHumanQuestion } = useIncidentStreamStore();

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
    onSuccess: () => {
      setAskHumanQuestion(null);
      queryClient.invalidateQueries({ queryKey: ["incidents", incidentId] });
    },
  });

  const handleSubmit = useCallback(
    (text: string, files: File[]) => {
      mutation.mutate({ content: text, files });
    },
    [mutation],
  );

  return (
    <div className="border-t p-4">
      {askHumanQuestion && (
        <div
          className="mb-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700"
          data-testid="ask-human-banner"
        >
          Agent 正在等待你的回复：{askHumanQuestion}
        </div>
      )}
      <PromptComposer
        onSubmit={handleSubmit}
        isLoading={mutation.isPending}
        disabled={mutation.isPending}
        placeholder={
          askHumanQuestion
            ? "回复 Agent 的问题..."
            : "Send a message to the agent..."
        }
      />
    </div>
  );
}
