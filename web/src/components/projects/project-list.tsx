import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { FolderOpen } from "lucide-react";
import dayjs from "@/lib/dayjs";
import { getProjects } from "@/api/projects";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";

export function ProjectList() {
  const { data: projects, isLoading } = useQuery({
    queryKey: ["projects"],
    queryFn: getProjects,
  });

  if (isLoading) {
    return (
      <div className="divide-y">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 p-4">
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-48" />
            </div>
            <Skeleton className="h-3 w-24" />
          </div>
        ))}
      </div>
    );
  }

  if (!projects?.length) {
    return (
      <Empty className="py-12">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <FolderOpen />
          </EmptyMedia>
          <EmptyTitle>No projects yet</EmptyTitle>
          <EmptyDescription>Create one to get started.</EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <div className="divide-y">
      {projects.map((project) => (
        <Link
          key={project.id}
          to="/projects/$projectId"
          params={{ projectId: project.id }}
          className="flex items-center gap-4 p-4 transition-colors hover:bg-muted/50"
        >
          <div className="flex-1 space-y-1">
            <p className="font-medium">{project.name}</p>
            <p className="text-sm text-muted-foreground line-clamp-1">
              {project.description || project.slug}
            </p>
          </div>
          <span className="text-xs text-muted-foreground">
            {dayjs(project.created_at).fromNow()}
          </span>
        </Link>
      ))}
    </div>
  );
}
