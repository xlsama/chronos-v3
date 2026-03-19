import { createFileRoute } from "@tanstack/react-router";
import { VersionHistoryPage } from "@/components/version-history/version-history-page";

export const Route = createFileRoute(
  "/projects/$projectId/documents/$documentId/history",
)({
  component: DocumentHistoryPage,
});

function DocumentHistoryPage() {
  const { documentId } = Route.useParams();
  return (
    <VersionHistoryPage
      entityType="agents_md"
      entityId={documentId}
      title="AGENTS.md 更新历史"
      backTo={`/projects`}
    />
  );
}
