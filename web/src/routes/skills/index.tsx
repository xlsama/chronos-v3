import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/skills/")({
  component: SkillsPage,
});

function SkillsPage() {
  return (
    <div className="h-full">
      <div className="flex items-center justify-between border-b px-6 py-4">
        <h1 className="text-base font-medium">技能</h1>
      </div>
      <div className="flex h-[calc(100%-65px)] items-center justify-center text-muted-foreground">
        即将推出
      </div>
    </div>
  );
}
