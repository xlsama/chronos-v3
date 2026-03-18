import { useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { SkillList } from "@/components/skills/skill-list";
import { SkillDialog } from "@/components/skills/create-skill-dialog";
import { Button } from "@/components/ui/button";

export const Route = createFileRoute("/skills/")({
  component: SkillsPage,
});

function SkillsPage() {
  const [createOpen, setCreateOpen] = useState(false);
  const navigate = useNavigate();

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b px-6 py-4">
        <h1 className="text-base font-medium">技能</h1>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          创建技能
        </Button>
      </div>
      <div className="flex flex-1 flex-col">
        <SkillList />
      </div>
      <SkillDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={(slug) => {
          navigate({ to: "/skills/$slug", params: { slug } });
        }}
      />
    </div>
  );
}
