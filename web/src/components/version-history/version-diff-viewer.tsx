import { useState } from "react";
import { MultiFileDiff } from "@pierre/diffs/react";
import { Columns2, Rows2 } from "lucide-react";
import { Button } from "@/components/ui/button";

interface VersionDiffViewerProps {
  oldValue: string;
  newValue: string;
  oldTitle?: string;
  newTitle?: string;
  language?: string;
}

export function VersionDiffViewer({
  oldValue,
  newValue,
  oldTitle = "旧版本",
  newTitle = "新版本",
  language = "markdown",
}: VersionDiffViewerProps) {
  const [layout, setLayout] = useState<"unified" | "split">("split");

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-end gap-2 border-b px-4 py-2">
        <Button
          size="sm"
          variant={layout === "split" ? "default" : "outline"}
          onClick={() => setLayout("split")}
        >
          <Columns2 className="mr-1.5 h-3.5 w-3.5" />
          双栏
        </Button>
        <Button
          size="sm"
          variant={layout === "unified" ? "default" : "outline"}
          onClick={() => setLayout("unified")}
        >
          <Rows2 className="mr-1.5 h-3.5 w-3.5" />
          单栏
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        <MultiFileDiff
          oldFile={{ name: oldTitle, contents: oldValue, lang: language }}
          newFile={{ name: newTitle, contents: newValue, lang: language }}
          options={{
            diffStyle: layout,
            theme: { dark: "github-dark", light: "github-light" },
            diffIndicators: "classic",
            lineDiffType: "word",
            overflow: "wrap",
            disableFileHeader: true,
          }}
        />
      </div>
    </div>
  );
}
