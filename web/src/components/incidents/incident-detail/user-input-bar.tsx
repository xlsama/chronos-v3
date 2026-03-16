import { useCallback } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { uploadFiles } from "@/api/attachments";
import { sendIncidentMessage } from "@/api/incidents";
import { PromptComposer } from "@/components/prompt-composer";

interface UserInputBarProps {
  incidentId: string;
}

export function UserInputBar({ incidentId }: UserInputBarProps) {
  const queryClient = useQueryClient();

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
      <PromptComposer
        onSubmit={handleSubmit}
        isLoading={mutation.isPending}
        disabled={mutation.isPending}
        placeholder="Send a message to the agent..."
      />
    </div>
  );
}
