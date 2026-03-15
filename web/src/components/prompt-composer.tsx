import { useCallback, useEffect, useRef, useState } from "react";
import { Paperclip, Send, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  FileUpload,
  FileUploadContent,
  FileUploadTrigger,
} from "@/components/ui/file-upload";
import {
  PromptInput,
  PromptInputAction,
  PromptInputActions,
  PromptInputTextarea,
} from "@/components/ui/prompt-input";

interface FileWithPreview {
  file: File;
  previewUrl: string | null;
}

interface PromptComposerProps {
  onSubmit: (text: string, files: File[]) => void;
  isLoading?: boolean;
  disabled?: boolean;
  placeholder?: string;
}

export function PromptComposer({
  onSubmit,
  isLoading = false,
  disabled = false,
  placeholder = "描述事件情况...",
}: PromptComposerProps) {
  const [text, setText] = useState("");
  const [files, setFiles] = useState<FileWithPreview[]>([]);
  const objectUrlsRef = useRef<string[]>([]);

  useEffect(() => {
    return () => {
      for (const url of objectUrlsRef.current) {
        URL.revokeObjectURL(url);
      }
    };
  }, []);

  const addFiles = useCallback((newFiles: File[]) => {
    const withPreviews = newFiles.map((file) => {
      const isImage = file.type.startsWith("image/");
      const previewUrl = isImage ? URL.createObjectURL(file) : null;
      if (previewUrl) objectUrlsRef.current.push(previewUrl);
      return { file, previewUrl };
    });
    setFiles((prev) => [...prev, ...withPreviews]);
  }, []);

  const removeFile = useCallback((index: number) => {
    setFiles((prev) => {
      const removed = prev[index];
      if (removed.previewUrl) URL.revokeObjectURL(removed.previewUrl);
      return prev.filter((_, i) => i !== index);
    });
  }, []);

  const handleSubmit = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed && files.length === 0) return;
    onSubmit(
      trimmed,
      files.map((f) => f.file),
    );
    setText("");
    setFiles([]);
  }, [text, files, onSubmit]);

  const handlePaste = useCallback(
    (e: React.ClipboardEvent) => {
      const items = e.clipboardData?.items;
      if (!items) return;
      const pastedFiles: File[] = [];
      for (const item of items) {
        if (item.kind === "file") {
          const file = item.getAsFile();
          if (file) pastedFiles.push(file);
        }
      }
      if (pastedFiles.length > 0) {
        addFiles(pastedFiles);
      }
    },
    [addFiles],
  );

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <FileUpload onFilesAdded={addFiles} disabled={disabled}>
      <FileUploadContent>
        <div className="flex flex-col items-center gap-2 text-center">
          <Paperclip className="text-muted-foreground size-10" />
          <p className="text-lg font-medium">拖拽文件到此处</p>
          <p className="text-muted-foreground text-sm">
            支持图片、日志等文件
          </p>
        </div>
      </FileUploadContent>

      <PromptInput
        value={text}
        onValueChange={setText}
        isLoading={isLoading}
        onSubmit={handleSubmit}
        disabled={disabled}
      >
        {files.length > 0 && (
          <div className="flex flex-wrap gap-2 px-2 pt-2">
            {files.map((f, i) => (
              <div
                key={i}
                className="bg-muted group relative flex items-center gap-2 rounded-lg p-1.5 pr-7"
              >
                {f.previewUrl ? (
                  <img
                    src={f.previewUrl}
                    alt={f.file.name}
                    className="size-10 rounded object-cover"
                  />
                ) : (
                  <div className="bg-background flex size-10 items-center justify-center rounded text-xs">
                    <Paperclip className="size-4" />
                  </div>
                )}
                <div className="max-w-[120px]">
                  <p className="truncate text-xs font-medium">{f.file.name}</p>
                  <p className="text-muted-foreground text-xs">
                    {formatSize(f.file.size)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => removeFile(i)}
                  className="bg-muted-foreground/20 hover:bg-muted-foreground/40 absolute top-0.5 right-0.5 rounded-full p-0.5"
                >
                  <X className="size-3" />
                </button>
              </div>
            ))}
          </div>
        )}

        <PromptInputTextarea
          placeholder={placeholder}
          onPaste={handlePaste}
          data-testid="prompt-textarea"
        />

        <PromptInputActions className="justify-between px-2 pb-1">
          <PromptInputAction tooltip="添加附件">
            <FileUploadTrigger asChild>
              <Button variant="ghost" size="icon" className="size-8 rounded-full">
                <Paperclip className="size-4" />
              </Button>
            </FileUploadTrigger>
          </PromptInputAction>

          <Button
            size="icon"
            className="size-8 rounded-full"
            onClick={handleSubmit}
            disabled={disabled || isLoading || (!text.trim() && files.length === 0)}
            data-testid="submit-incident"
          >
            <Send className="size-4" />
          </Button>
        </PromptInputActions>
      </PromptInput>
    </FileUpload>
  );
}
