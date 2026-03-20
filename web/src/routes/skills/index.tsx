import { useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { motion } from "motion/react";
import { SkillList } from "@/components/skills/skill-list";
import { SkillDialog } from "@/components/skills/create-skill-dialog";
import { Button } from "@/components/ui/button";
import { pageVariants, pageTransition } from "@/lib/motion";

export const Route = createFileRoute("/skills/")({
  component: SkillsPage,
});

function SkillsPage() {
  const [createOpen, setCreateOpen] = useState(false);
  const navigate = useNavigate();

  return (
    <motion.div
      className="flex h-full flex-col"
      variants={pageVariants}
      initial="initial"
      animate="animate"
      transition={pageTransition}
    >
      <div className="flex items-center justify-between border-b px-6 py-4">
        <h1 className="text-base font-medium">技能</h1>
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          创建技能
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <SkillList />
      </div>
      <SkillDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={(slug) => {
          navigate({ to: "/skills/$slug", params: { slug } });
        }}
      />
    </motion.div>
  );
}
