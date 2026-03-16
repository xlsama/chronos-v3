import { useCallback, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { uploadFiles } from "@/api/attachments";
import { createIncident } from "@/api/incidents";
import { getProjects } from "@/api/projects";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Field, FieldLabel } from "@/components/ui/field";
import { PromptComposer } from "@/components/prompt-composer";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export function CreateIncidentDialog() {
  const [open, setOpen] = useState(false);
  const [projectId, setProjectId] = useState<string>("");
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { data: projects } = useQuery({
    queryKey: ["projects"],
    queryFn: getProjects,
  });

  const mutation = useMutation({
    mutationFn: async ({
      description,
      files,
      projectId,
    }: {
      description: string;
      files: File[];
      projectId?: string;
    }) => {
      let attachment_ids: string[] | undefined;
      if (files.length > 0) {
        const attachments = await uploadFiles(files);
        attachment_ids = attachments.map((a) => a.id);
      }
      return createIncident({
        description,
        attachment_ids,
        project_id: projectId || undefined,
      });
    },
    onSuccess: (incident) => {
      toast.success("Incident created");
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
      setOpen(false);
      setProjectId("");
      navigate({
        to: "/incidents/$incidentId",
        params: { incidentId: incident.id },
      });
    },
  });

  const handleSubmit = useCallback(
    (text: string, files: File[]) => {
      mutation.mutate({ description: text, files, projectId });
    },
    [mutation, projectId],
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
        <div className="mb-4">
          <Field>
            <FieldLabel>Project</FieldLabel>
            <Select value={projectId} onValueChange={(value) => setProjectId(value ?? "")}>
              <SelectTrigger>
                <SelectValue placeholder="Optional: choose a project boundary" />
              </SelectTrigger>
              <SelectContent>
                {projects?.map((project) => (
                  <SelectItem key={project.id} value={project.id}>
                    {project.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        </div>
        <PromptComposer
          onSubmit={handleSubmit}
          isLoading={mutation.isPending}
          disabled={mutation.isPending}
        />
      </DialogContent>
    </Dialog>
  );
}
