import { useCallback, useEffect, useRef, useState } from "react";
import { Check, Mic, Paperclip, Send, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
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
import { useVoiceInput } from "@/hooks/use-voice-input";
import { AudioVisualizer } from "@/components/voice-input/audio-visualizer";

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

  const preRecordTextRef = useRef("");

  const { state: voiceState, interimText, analyserNode, startRecording, stopRecording, cancelRecording } =
    useVoiceInput({
      onTranscript: useCallback((transcript: string) => {
        setText((prev) => {
          const separator = prev && !prev.endsWith("\n") ? "\n" : "";
          return prev + separator + transcript;
        });
      }, []),
      onCancel: useCallback(() => {
        setText(preRecordTextRef.current);
      }, []),
    });

  const isRecording = voiceState === "recording" || voiceState === "connecting";

  useEffect(() => {
    if (voiceState === "connecting") {
      preRecordTextRef.current = text;
    }
  }, [voiceState, text]);

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
        {files.length > 0 && !isRecording && (
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
          disabled={isRecording}
          data-testid="prompt-textarea"
        />

        <AnimatePresence>
          {isRecording && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="flex items-center gap-3 overflow-hidden border-t px-4 py-2"
            >
              <AudioVisualizer analyserNode={analyserNode} className="shrink-0" />
              <span className="text-muted-foreground min-w-0 flex-1 truncate text-sm">
                {voiceState === "connecting"
                  ? "正在连接..."
                  : interimText || "正在聆听..."}
              </span>
            </motion.div>
          )}
        </AnimatePresence>

        <PromptInputActions className="justify-between px-2 pb-1">
          <PromptInputAction tooltip="添加附件">
            <FileUploadTrigger asChild>
              <Button variant="ghost" size="icon" className="size-8 rounded-full" disabled={isRecording}>
                <Paperclip className="size-4" />
              </Button>
            </FileUploadTrigger>
          </PromptInputAction>

          <div className="flex items-center gap-1">
            <AnimatePresence mode="wait">
              {isRecording ? (
                <motion.div
                  key="recording-actions"
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.8 }}
                  className="flex items-center gap-1"
                >
                  <Button
                    variant="ghost"
                    size="icon"
                    className="size-8 rounded-full"
                    onClick={cancelRecording}
                  >
                    <X className="size-4" />
                  </Button>
                  <Button
                    size="icon"
                    className="bg-primary size-8 rounded-full"
                    onClick={stopRecording}
                  >
                    <Check className="size-4" />
                  </Button>
                </motion.div>
              ) : (
                <motion.div
                  key="normal-actions"
                  initial={false}
                  className="flex items-center gap-1"
                >
                  <PromptInputAction tooltip="语音输入">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-8 rounded-full"
                      onClick={startRecording}
                      disabled={disabled || isLoading}
                    >
                      <Mic className="size-4" />
                    </Button>
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
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </PromptInputActions>
      </PromptInput>
    </FileUpload>
  );
}
