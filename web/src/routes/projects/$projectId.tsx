import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { getProject } from "@/api/projects";
import { DocumentUpload } from "@/components/projects/document-upload";
import { DocumentList } from "@/components/projects/document-list";
import { ProjectTopologyPanel } from "@/components/projects/project-topology-panel";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

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
      <div className="border-b px-6 py-4">
        <h1 className="text-base font-medium">{project.name}</h1>
        {project.description && (
          <p className="mt-1 text-sm text-muted-foreground">
            {project.description}
          </p>
        )}
      </div>

      <Tabs defaultValue="topology">
        <div className="px-6 pt-4">
          <TabsList>
            <TabsTrigger value="topology">Topology</TabsTrigger>
            <TabsTrigger value="documents">Documents</TabsTrigger>
          </TabsList>
        </div>
        <TabsContent value="topology" className="p-6">
          <ProjectTopologyPanel project={project} />
        </TabsContent>
        <TabsContent value="documents" className="space-y-6 p-6">
          <DocumentUpload projectId={projectId} />
          <DocumentList projectId={projectId} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
