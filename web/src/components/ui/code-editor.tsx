import { Suspense, lazy } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const MonacoEditor = lazy(() => import("@monaco-editor/react"));

const EXT_LANGUAGE_MAP: Record<string, string> = {
  sh: "shell",
  bash: "shell",
  py: "python",
  yaml: "yaml",
  yml: "yaml",
  json: "json",
  js: "javascript",
  ts: "typescript",
  tsx: "typescript",
  jsx: "javascript",
  md: "markdown",
  sql: "sql",
  xml: "xml",
  html: "html",
  css: "css",
  toml: "ini",
  ini: "ini",
  conf: "ini",
  env: "ini",
  dockerfile: "dockerfile",
  tf: "hcl",
};

export function getLanguageFromPath(path: string): string {
  const fileName = path.split("/").pop() ?? "";
  if (fileName.toLowerCase() === "dockerfile") return "dockerfile";
  const ext = fileName.split(".").pop()?.toLowerCase() ?? "";
  return EXT_LANGUAGE_MAP[ext] ?? "plaintext";
}

interface CodeEditorProps {
  value: string;
  onChange?: (value: string) => void;
  language: string;
  readOnly?: boolean;
  className?: string;
}

export function CodeEditor({
  value,
  onChange,
  language,
  readOnly,
  className,
}: CodeEditorProps) {
  return (
    <Suspense
      fallback={
        <div className="flex h-full items-center justify-center">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      }
    >
      <div className={cn("h-full", className)}>
        <MonacoEditor
          language={language}
          theme="light"
          value={value}
          onChange={(v) => onChange?.(v ?? "")}
          options={{
            readOnly,
            minimap: { enabled: false },
            fontSize: 13,
            lineNumbers: "on",
            wordWrap: "on",
            automaticLayout: true,
            scrollBeyondLastLine: false,
          }}
        />
      </div>
    </Suspense>
  );
}
