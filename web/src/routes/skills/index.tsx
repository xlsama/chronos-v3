import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { SkillList } from "@/components/skills/skill-list";
import { SkillDialog } from "@/components/skills/create-skill-dialog";
import { Button } from "@/components/ui/button";

export const Route = createFileRoute("/skills/")({
  component: SkillsPage,
});

function SkillsPage() {
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <div className="h-full">
      <div className="flex items-center justify-between border-b px-6 py-4">
        <h1 className="text-base font-medium">技能</h1>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          创建技能
        </Button>
      </div>
      <SkillList />
      <SkillDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}
