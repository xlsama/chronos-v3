import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { uploadDocument } from "@/api/documents";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Field, FieldLabel } from "@/components/ui/field";

interface DocumentUploadProps {
  projectId: string;
}

export function DocumentUpload({ projectId }: DocumentUploadProps) {
  const [filename, setFilename] = useState("");
  const [content, setContent] = useState("");
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () =>
      uploadDocument(projectId, { filename, content, doc_type: "markdown" }),
    onSuccess: () => {
      toast.success("Document uploaded");
      queryClient.invalidateQueries({ queryKey: ["documents", projectId] });
      setFilename("");
      setContent("");
    },
  });

  return (
    <div className="space-y-4 rounded-lg border p-4">
      <h3 className="text-sm font-medium">Upload Document</h3>
      <Field>
        <FieldLabel>Filename</FieldLabel>
        <Input
          placeholder="e.g. deploy-guide.md"
          value={filename}
          onChange={(e) => setFilename(e.target.value)}
        />
      </Field>
      <Field>
        <FieldLabel>Content</FieldLabel>
        <Textarea
          placeholder="Paste document content here..."
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={8}
          className="font-mono"
        />
      </Field>
      <Button
        size="sm"
        onClick={() => mutation.mutate()}
        disabled={!filename || !content || mutation.isPending}
      >
        {mutation.isPending ? "Uploading..." : "Upload"}
      </Button>
    </div>
  );
}
