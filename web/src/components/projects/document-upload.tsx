import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "@tanstack/react-form";
import { useNavigate } from "@tanstack/react-router";
import { toast } from "sonner";
import { FilePlus, Upload } from "lucide-react";
import { uploadDocument, uploadDocumentFile } from "@/api/documents";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const ACCEPTED_EXTENSIONS = ".pdf,.docx,.xlsx,.xls,.csv,.md,.txt";

interface DocumentUploadProps {
  projectId: string;
}

export function UploadDocumentButton({ projectId }: DocumentUploadProps) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fileMutation = useMutation({
    mutationFn: (file: File) => uploadDocumentFile(projectId, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents", projectId] });
    },
    onError: (err: Error) => {
      toast.error(err.message);
    },
  });

  return (
    <>
      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPTED_EXTENSIONS}
        multiple
        className="hidden"
        onChange={(e) => {
          const files = e.target.files;
          if (!files) return;
          for (const file of Array.from(files)) {
            fileMutation.mutate(file);
          }
          e.target.value = "";
        }}
      />
      <Button
        variant="outline"
        size="sm"
        onClick={() => fileInputRef.current?.click()}
        disabled={fileMutation.isPending}
      >
        <Upload className="mr-1 h-3.5 w-3.5" />
        {fileMutation.isPending ? "上传中..." : "上传文档"}
      </Button>
    </>
  );
}

export function CreateDocumentButton({ projectId }: DocumentUploadProps) {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const createMutation = useMutation({
    mutationFn: (data: { filename: string }) =>
      uploadDocument(projectId, {
        filename: data.filename,
        content: "",
        doc_type: "markdown",
      }),
    onSuccess: (doc) => {
      toast.success("文档已创建");
      queryClient.invalidateQueries({ queryKey: ["documents", projectId] });
      setOpen(false);
      form.reset();
      navigate({
        to: "/projects/$projectId/documents/$documentId",
        params: { projectId, documentId: doc.id },
      });
    },
  });

  const form = useForm({
    defaultValues: { filename: "" },
    onSubmit: ({ value }) => {
      const filename = value.filename.endsWith(".md")
        ? value.filename
        : `${value.filename}.md`;
      createMutation.mutate({ filename });
    },
  });

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        <FilePlus className="mr-1 h-3.5 w-3.5" />
        新建文档
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>新建文档</DialogTitle>
          </DialogHeader>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              form.handleSubmit();
            }}
            className="space-y-4"
          >
            <form.Field
              name="filename"
              validators={{
                onSubmit: ({ value }) =>
                  !value ? "文件名不能为空" : undefined,
              }}
            >
              {(field) => (
                <Field
                  data-invalid={
                    field.state.meta.errors.length > 0 || undefined
                  }
                >
                  <FieldLabel>文件名</FieldLabel>
                  <Input
                    placeholder="例如: deploy-guide.md"
                    value={field.state.value}
                    onChange={(e) => field.handleChange(e.target.value)}
                    onBlur={field.handleBlur}
                  />
                  <FieldError
                    errors={field.state.meta.errors.map((e) => ({
                      message: String(e),
                    }))}
                  />
                </Field>
              )}
            </form.Field>
            <DialogFooter>
              <DialogClose render={<Button variant="outline" />}>
                取消
              </DialogClose>
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? "创建中..." : "创建"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
