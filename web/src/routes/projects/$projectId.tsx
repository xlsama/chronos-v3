import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { getProject } from "@/api/projects";
import { CreateDocumentButton, UploadDocumentButton } from "@/components/projects/document-upload";
import { DocumentList } from "@/components/projects/document-list";
import { LinkedServersEditor } from "@/components/projects/linked-servers-editor";
import { Skeleton } from "@/components/ui/skeleton";

export const Route = createFileRoute("/projects/$projectId")({
  component: ProjectDetailPage,
});

function ProjectDetailPage() {
  const { projectId } = Route.useParams();

  const { data: project, isLoading } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId),
  });

  if (isLoading) {
    return (
      <div className="space-y-4 p-6">
        <Skeleton className="h-7 w-48" />
        <Skeleton className="h-4 w-72" />
      </div>
    );
  }

  if (!project) {
    return <div className="p-6 text-muted-foreground">Project not found.</div>;
  }

  return (
    <div className="h-full">
      <div className="border-b px-6 py-4 space-y-3">
        <div>
          <h1 className="text-base font-medium">{project.name}</h1>
          {project.description && (
            <p className="mt-1 text-sm text-muted-foreground">
              {project.description}
            </p>
          )}
        </div>
        <LinkedServersEditor project={project} />
      </div>

      <div className="space-y-4 p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium">文档</h2>
          <div className="flex items-center gap-2">
            <UploadDocumentButton projectId={projectId} />
            <CreateDocumentButton projectId={projectId} />
          </div>
        </div>
        <DocumentList projectId={projectId} />
      </div>
    </div>
  );
}
