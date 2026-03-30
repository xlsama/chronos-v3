import { useState, memo } from "react";
import { Sparkles } from "lucide-react";
import { SkillViewer } from "@/components/skills/skill-viewer";

export const SkillReadCard = memo(function SkillReadCard({ skillName, skillSlug }: { skillName: string; skillSlug: string }) {
  const [viewingSlug, setViewingSlug] = useState<string | null>(null);

  return (
    <>
      <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
        <Sparkles className="h-3.5 w-3.5 text-blue-400" />
        <span>读取技能：</span>
        <button
          className="cursor-pointer font-medium text-blue-700 underline decoration-dotted underline-offset-2 hover:text-blue-900"
          onClick={() => setViewingSlug(skillSlug)}
        >
          {skillName}
        </button>
      </div>
      <SkillViewer skillSlug={viewingSlug} onClose={() => setViewingSlug(null)} readOnly />
    </>
  );
});
