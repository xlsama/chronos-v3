import { useCallback, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { uploadFiles } from "@/api/attachments";
import { createIncident } from "@/api/incidents";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { PromptComposer } from "@/components/prompt-composer";

export function CreateIncidentDialog() {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const mutation = useMutation({
    mutationFn: async ({
      description,
      files,
    }: {
      description: string;
      files: File[];
    }) => {
      let attachment_ids: string[] | undefined;
      if (files.length > 0) {
        const attachments = await uploadFiles(files);
        attachment_ids = attachments.map((a) => a.id);
      }
      return createIncident({ description, attachment_ids });
    },
    onSuccess: (incident) => {
      toast.success("Incident created");
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
      setOpen(false);
      navigate({
        to: "/incidents/$incidentId",
        params: { incidentId: incident.id },
      });
    },
  });

  const handleSubmit = useCallback(
    (text: string, files: File[]) => {
      mutation.mutate({ description: text, files });
    },
    [mutation],
  );

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={<Button size="sm" data-testid="create-incident-btn" />}
      >
        New Incident
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Create Incident</DialogTitle>
        </DialogHeader>
        <PromptComposer
          onSubmit={handleSubmit}
          isLoading={mutation.isPending}
          disabled={mutation.isPending}
        />
      </DialogContent>
    </Dialog>
  );
}
