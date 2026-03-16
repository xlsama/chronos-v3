import { createFileRoute } from "@tanstack/react-router";
import { ProjectList } from "@/components/projects/project-list";
import { CreateProjectDialog } from "@/components/projects/create-project-dialog";

export const Route = createFileRoute("/projects/")({
  component: ProjectsPage,
});

function ProjectsPage() {
  return (
    <div className="h-full">
      <div className="flex items-center justify-between border-b px-6 py-4">
        <h1 className="text-xl font-semibold">知识库</h1>
        <CreateProjectDialog />
      </div>
      <ProjectList />
    </div>
  );
}
