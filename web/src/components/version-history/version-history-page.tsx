import { Link } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { VersionHistoryContent } from "./version-history-content";

interface VersionHistoryPageProps {
  entityType: string;
  entityId: string;
  title: string;
  backTo: string;
}

export function VersionHistoryPage({
  entityType,
  entityId,
  title,
  backTo,
}: VersionHistoryPageProps) {
  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 border-b px-6 py-4">
        <Link to={backTo}>
          <Button variant="ghost" size="icon-sm">
            <ArrowLeft className="h-4 w-4" />
          </Button>
        </Link>
        <h1 className="text-base font-medium">{title}</h1>
      </div>

      <VersionHistoryContent entityType={entityType} entityId={entityId} />
    </div>
  );
}
