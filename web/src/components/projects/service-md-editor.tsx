import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { updateProjectServiceMd } from "@/api/projects";
import { Button } from "@/components/ui/button";
import { MarkdownEditor } from "@/components/ui/markdown-editor";
import type { Project } from "@/lib/types";

interface ServiceMdEditorProps {
  project: Project;
}

export function ServiceMdEditor({ project }: ServiceMdEditorProps) {
  const [content, setContent] = useState(project.service_md || "");
  const queryClient = useQueryClient();
  const isDirty = content !== (project.service_md || "");

  const mutation = useMutation({
    mutationFn: () => updateProjectServiceMd(project.id, content),
    onSuccess: () => {
      toast.success("SERVICE.md saved");
      queryClient.invalidateQueries({ queryKey: ["project", project.id] });
    },
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Describe your project's infrastructure, services, deployment topology,
          and key dependencies.
        </p>
        <Button
          size="sm"
          onClick={() => mutation.mutate()}
          disabled={!isDirty || mutation.isPending}
        >
          {mutation.isPending ? "Saving..." : "Save"}
        </Button>
      </div>
      <MarkdownEditor
        value={content}
        onChange={setContent}
        minHeight={400}
        placeholder="Describe your infrastructure and services here..."
      />
    </div>
  );
}
