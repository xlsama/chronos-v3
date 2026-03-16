import { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Upload } from "lucide-react";
import { uploadDocument, uploadDocumentFile } from "@/api/documents";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Field, FieldLabel } from "@/components/ui/field";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const ACCEPTED_TYPES: Record<string, string[]> = {
  "application/pdf": [".pdf"],
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [
    ".docx",
  ],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [
    ".xlsx",
  ],
  "application/vnd.ms-excel": [".xls"],
  "text/csv": [".csv"],
  "text/markdown": [".md"],
  "text/plain": [".txt"],
};

interface DocumentUploadProps {
  projectId: string;
}

export function DocumentUpload({ projectId }: DocumentUploadProps) {
  const [filename, setFilename] = useState("");
  const [content, setContent] = useState("");
  const queryClient = useQueryClient();

  const textMutation = useMutation({
    mutationFn: () =>
      uploadDocument(projectId, { filename, content, doc_type: "markdown" }),
    onSuccess: () => {
      toast.success("Document uploaded");
      queryClient.invalidateQueries({ queryKey: ["documents", projectId] });
      setFilename("");
      setContent("");
    },
  });

  const fileMutation = useMutation({
    mutationFn: (file: File) => uploadDocumentFile(projectId, file),
    onSuccess: () => {
      toast.success("File uploaded and indexed");
      queryClient.invalidateQueries({ queryKey: ["documents", projectId] });
    },
    onError: (err: Error) => {
      toast.error(err.message);
    },
  });

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      for (const file of acceptedFiles) {
        fileMutation.mutate(file);
      }
    },
    [fileMutation],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPTED_TYPES,
    multiple: true,
  });

  return (
    <div className="space-y-4 rounded-lg border p-4">
      <h3 className="text-sm font-medium">Upload Document</h3>

      <Tabs defaultValue="file">
        <TabsList variant="line">
          <TabsTrigger value="file">File Upload</TabsTrigger>
          <TabsTrigger value="text">Paste Text</TabsTrigger>
        </TabsList>

        <TabsContent value="file" className="pt-4">
          <div
            {...getRootProps()}
            className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors ${
              isDragActive
                ? "border-primary bg-primary/5"
                : "border-muted-foreground/25 hover:border-primary/50"
            }`}
          >
            <input {...getInputProps()} />
            <Upload className="mb-2 h-8 w-8 text-muted-foreground" />
            {isDragActive ? (
              <p className="text-sm text-primary">Drop files here...</p>
            ) : (
              <>
                <p className="text-sm text-muted-foreground">
                  Drag & drop files here, or click to select
                </p>
                <p className="mt-1 text-xs text-muted-foreground/70">
                  PDF, Word, Excel, CSV, Markdown, Text
                </p>
              </>
            )}
            {fileMutation.isPending && (
              <p className="mt-2 text-sm text-primary animate-pulse">
                Uploading...
              </p>
            )}
          </div>
        </TabsContent>

        <TabsContent value="text" className="space-y-4 pt-4">
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
            onClick={() => textMutation.mutate()}
            disabled={!filename || !content || textMutation.isPending}
          >
            {textMutation.isPending ? "Uploading..." : "Upload"}
          </Button>
        </TabsContent>
      </Tabs>
    </div>
  );
}
