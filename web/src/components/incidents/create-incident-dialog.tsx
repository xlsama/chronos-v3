import { useCallback } from "react";
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
} from "@/components/ui/dialog";
import { Kbd } from "@/components/ui/kbd";
import { PromptComposer } from "@/components/prompt-composer";
import { useCreateIncidentDialogStore } from "@/stores/create-incident-dialog";

export function CreateIncidentDialog() {
  const { open, setOpen } = useCreateIncidentDialogStore();
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
      return createIncident({
        description,
        attachment_ids,
      });
    },
    onSuccess: (incident) => {
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
      setOpen(false);
      navigate({
        to: "/incidents/$incidentId",
        params: { incidentId: incident.id },
      });
    },
    onError: () => {
      toast.error("事件创建失败，请重试");
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
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>创建事件</DialogTitle>
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

export function CreateIncidentTrigger() {
  const setOpen = useCreateIncidentDialogStore((s) => s.setOpen);

  return (
    <Button size="sm" className="gap-1.5" data-testid="create-incident-btn" onClick={() => setOpen(true)}>
      新建事件
      <Kbd className="ml-1 text-[10px] h-4 min-w-4">⌘K</Kbd>
    </Button>
  );
}
