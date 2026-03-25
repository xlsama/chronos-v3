import { useState } from "react";
import { useMutation, useQuery, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { motion } from "motion/react";
import { toast } from "sonner";
import { ChevronLeft, ChevronRight, Copy, EllipsisVertical, FolderOpen, Pencil, Trash2 } from "lucide-react";
import dayjs from "@/lib/dayjs";
import { deleteProject, getProjects } from "@/api/projects";
import type { Project } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Card,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { listVariants, cardItemVariants } from "@/lib/motion";
import { QueryContent } from "@/components/query-content";
import { EditProjectDialog } from "@/components/projects/edit-project-dialog";

const GRADIENTS = [
  "from-violet-500 to-purple-600",
  "from-blue-500 to-cyan-500",
  "from-emerald-500 to-teal-600",
  "from-orange-500 to-amber-500",
  "from-pink-500 to-rose-600",
  "from-indigo-500 to-blue-600",
  "from-fuchsia-500 to-pink-600",
  "from-cyan-500 to-sky-600",
  "from-lime-500 to-green-600",
  "from-red-500 to-orange-600",
];

function getGradient(name: string) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = (hash << 5) - hash + name.charCodeAt(i);
    hash |= 0;
  }
  return GRADIENTS[Math.abs(hash) % GRADIENTS.length];
}

function getInitial(name: string) {
  return name.charAt(0).toUpperCase();
}

function ProjectCard({ project }: { project: Project }) {
  const queryClient = useQueryClient();
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [showEditDialog, setShowEditDialog] = useState(false);

  const deleteMutation = useMutation({
    mutationFn: () => deleteProject(project.id),
    onSuccess: () => {
      toast.success("知识库已删除");
      setShowDeleteDialog(false);
      queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });

  return (
    <>
      <Link
        to="/projects/$projectId"
        params={{ projectId: project.id }}
        className="no-underline"
      >
        <Card className="group pt-0 overflow-hidden transition-colors hover:bg-accent/50">
          <div
            className={`relative flex h-24 items-center justify-center bg-gradient-to-br ${getGradient(project.name)}`}
          >
            <span className="text-3xl font-bold text-white">
              {getInitial(project.name)}
            </span>
            <DropdownMenu>
              <DropdownMenuTrigger
                render={<Button variant="ghost" size="icon-sm" className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 text-white hover:bg-white/20 hover:text-white" />}
                onClick={(e) => {
                  e.stopPropagation();
                  e.preventDefault();
                }}
              >
                <EllipsisVertical className="h-4 w-4" />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  onClick={(e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    setShowEditDialog(true);
                  }}
                >
                  <Pencil className="mr-2 h-4 w-4" />
                  编辑
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={(e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    navigator.clipboard.writeText(project.id);
                    toast.success("已复制项目 ID");
                  }}
                >
                  <Copy className="mr-2 h-4 w-4" />
                  复制项目 ID
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  variant="destructive"
                  onClick={(e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    setShowDeleteDialog(true);
                  }}
                >
                  <Trash2 className="mr-2 h-4 w-4" />
                  删除
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
          <CardHeader>
            <CardTitle className="line-clamp-1">{project.name}</CardTitle>
            {project.description && (
              <CardDescription className="line-clamp-2">
                {project.description}
              </CardDescription>
            )}
          </CardHeader>
          <CardFooter>
            <span className="text-xs text-muted-foreground">
              {dayjs(project.created_at).fromNow()}
            </span>
          </CardFooter>
        </Card>
      </Link>

      <EditProjectDialog
        project={project}
        open={showEditDialog}
        onOpenChange={setShowEditDialog}
      />

      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认删除知识库</AlertDialogTitle>
            <AlertDialogDescription>
              确定要删除 <strong>{project.name}</strong> 吗？该操作将删除所有文档和向量数据，且无法撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => deleteMutation.mutate()}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? "删除中..." : "删除"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

export function ProjectList() {
  const [page, setPage] = useState(1);
  const pageSize = 50;

  const { data, isLoading, isPlaceholderData } = useQuery({
    queryKey: ["projects", page],
    queryFn: () => getProjects({ page, page_size: pageSize }),
    placeholderData: keepPreviousData,
  });

  const projects = data?.items;
  const total = data?.total ?? 0;
  const totalPages = Math.ceil(total / pageSize);

  return (
    <QueryContent
      isLoading={isLoading}
      data={data}
      isEmpty={(d) => !d.items?.length}
      skeleton={
        <div className="grid grid-cols-1 gap-4 p-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Card key={i} className="pt-0 overflow-hidden">
              <Skeleton className="h-24 rounded-none" />
              <CardHeader>
                <Skeleton className="h-5 w-32" />
                <Skeleton className="h-4 w-full" />
              </CardHeader>
              <CardFooter>
                <Skeleton className="h-3 w-24" />
              </CardFooter>
            </Card>
          ))}
        </div>
      }
      empty={
        <Empty className="pt-[20vh]">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <FolderOpen />
            </EmptyMedia>
            <EmptyTitle>暂无项目</EmptyTitle>
            <EmptyDescription>创建一个以开始使用。</EmptyDescription>
          </EmptyHeader>
        </Empty>
      }
    >
      {() => (
        <div className={isPlaceholderData ? "opacity-60 transition-opacity" : "transition-opacity"}>
          <motion.div className="grid grid-cols-1 gap-4 p-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4" variants={listVariants} initial="initial" animate="animate">
            {projects!.map((project) => (
              <motion.div key={project.id} variants={cardItemVariants}>
                <ProjectCard project={project} />
              </motion.div>
            ))}
          </motion.div>
          {totalPages > 1 && (
            <div className="flex items-center justify-between px-6 py-3">
              <span className="text-sm text-muted-foreground">
                共 {total} 个项目
              </span>
              <div className="flex items-center gap-1">
                <Button
                  variant="outline"
                  size="icon-sm"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <span className="px-2 text-sm">
                  {page} / {totalPages}
                </span>
                <Button
                  variant="outline"
                  size="icon-sm"
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </QueryContent>
  );
}
