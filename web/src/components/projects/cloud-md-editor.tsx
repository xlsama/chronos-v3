import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { updateProjectCloudMd } from "@/api/projects";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { Project } from "@/lib/types";

interface CloudMdEditorProps {
  project: Project;
}

export function CloudMdEditor({ project }: CloudMdEditorProps) {
  const [content, setContent] = useState(project.cloud_md || "");
  const queryClient = useQueryClient();
  const isDirty = content !== (project.cloud_md || "");

  const mutation = useMutation({
    mutationFn: () => updateProjectCloudMd(project.id, content),
    onSuccess: () => {
      toast.success("Cloud.md saved");
      queryClient.invalidateQueries({ queryKey: ["project", project.id] });
    },
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Describe your project's cloud architecture, deployment topology, and
          key services.
        </p>
        <Button
          size="sm"
          onClick={() => mutation.mutate()}
          disabled={!isDirty || mutation.isPending}
        >
          {mutation.isPending ? "Saving..." : "Save"}
        </Button>
      </div>
      <Textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        rows={20}
        placeholder="# Cloud Architecture&#10;&#10;Describe your infrastructure here..."
        className="font-mono"
      />
    </div>
  );
}
