import { useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { motion } from "motion/react";
import { SkillList } from "@/components/skills/skill-list";
import { SkillDialog } from "@/components/skills/create-skill-dialog";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
      <Tabs defaultValue="all" className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b px-6 py-4">
          <TabsList>
            <TabsTrigger value="all">全部</TabsTrigger>
            <TabsTrigger value="published">已发布</TabsTrigger>
            <TabsTrigger value="draft">草稿</TabsTrigger>
          </TabsList>
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            创建技能
          </Button>
        </div>
        <p className="px-6 py-2 text-xs text-muted-foreground">
          事件解决后，系统会自动从排查对话中提取可复用的标准化排查流程。匹配到已有技能时会合并更新，否则创建新的草稿技能供审核。
        </p>
        <TabsContent value="all" className="mt-0 min-h-0 flex-1 overflow-y-auto">
          <SkillList />
        </TabsContent>
        <TabsContent value="published" className="mt-0 min-h-0 flex-1 overflow-y-auto">
          <SkillList filter="published" />
        </TabsContent>
        <TabsContent value="draft" className="mt-0 min-h-0 flex-1 overflow-y-auto">
          <SkillList filter="draft" />
        </TabsContent>
      </Tabs>
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
