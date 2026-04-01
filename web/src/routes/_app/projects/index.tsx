import { createFileRoute } from "@tanstack/react-router";
import { motion } from "motion/react";
import { ProjectList } from "@/components/projects/project-list";
import { CreateProjectDialog } from "@/components/projects/create-project-dialog";
import { pageVariants, pageTransition } from "@/lib/motion";

export const Route = createFileRoute("/_app/projects/")({
  component: ProjectsPage,
});

function ProjectsPage() {
  return (
    <motion.div
      className="h-full"
      variants={pageVariants}
      initial="initial"
      animate="animate"
      transition={pageTransition}
    >
      <div className="flex items-center justify-between border-b px-6 py-4">
        <h1 className="text-base font-medium">知识库</h1>
        <CreateProjectDialog />
      </div>
      <ProjectList />
    </motion.div>
  );
}
