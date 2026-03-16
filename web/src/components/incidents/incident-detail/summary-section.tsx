import { useState } from "react";
import { CheckCircle, Brain, BrainCircuit } from "lucide-react";
import { saveToMemory } from "@/api/incidents";
import { Markdown } from "@/components/ui/markdown";

interface SummarySectionProps {
  markdown: string;
  incidentId?: string;
  savedToMemory?: boolean;
}

export function SummarySection({
  markdown,
  incidentId,
  savedToMemory: initialSaved,
}: SummarySectionProps) {
  const [saved, setSaved] = useState(initialSaved ?? false);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    if (!incidentId || saved || saving) return;
    setSaving(true);
    try {
      const result = await saveToMemory(incidentId);
      if (result.ok) {
        setSaved(true);
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="rounded-lg border border-green-200 bg-green-50/30 p-4"
      data-testid="summary-section"
    >
      <div className="flex items-center gap-2 text-sm font-semibold text-green-800">
        <CheckCircle className="h-5 w-5" />
        Investigation Complete
      </div>
      <Markdown content={markdown} variant="compact" className="mt-3" />
      {incidentId && (
        <div className="mt-4 flex items-center">
          {saved ? (
            <span
              className="inline-flex items-center gap-1.5 text-sm text-green-700"
              data-testid="saved-to-memory"
            >
              <BrainCircuit className="h-4 w-4" />
              已保存到记忆
            </span>
          ) : (
            <button
              onClick={handleSave}
              disabled={saving}
              className="inline-flex items-center gap-1.5 rounded-md border border-green-300 bg-white px-3 py-1.5 text-sm font-medium text-green-700 hover:bg-green-50 disabled:opacity-50"
              data-testid="save-to-memory-btn"
            >
              <Brain className="h-4 w-4" />
              {saving ? "保存中..." : "添加到记忆"}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
