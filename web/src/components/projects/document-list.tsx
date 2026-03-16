import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { FileText, Trash2 } from "lucide-react";
import dayjs from "@/lib/dayjs";
import { deleteDocument, getDocuments } from "@/api/documents";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { DocumentViewer } from "./document-viewer";

interface DocumentListProps {
  projectId: string;
}

const statusColors: Record<string, string> = {
  ready: "bg-green-100 text-green-800 border-transparent",
  processing: "bg-yellow-100 text-yellow-800 border-transparent",
  error: "bg-red-100 text-red-800 border-transparent",
};

export function DocumentList({ projectId }: DocumentListProps) {
  const queryClient = useQueryClient();
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);

  const { data: documents, isLoading } = useQuery({
    queryKey: ["documents", projectId],
    queryFn: () => getDocuments(projectId),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteDocument,
    onSuccess: () => {
      toast.success("Document deleted");
      queryClient.invalidateQueries({ queryKey: ["documents", projectId] });
    },
  });

  if (isLoading) {
    return (
      <div className="divide-y rounded-lg border">
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3 p-3">
            <Skeleton className="h-4 w-4" />
            <div className="flex-1 space-y-1.5">
              <Skeleton className="h-3.5 w-32" />
              <Skeleton className="h-3 w-48" />
            </div>
            <Skeleton className="h-5 w-14 rounded-full" />
            <Skeleton className="h-8 w-8" />
          </div>
        ))}
      </div>
    );
  }

  if (!documents?.length) {
    return (
      <Empty className="rounded-lg border py-8">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <FileText />
          </EmptyMedia>
          <EmptyTitle>No documents uploaded</EmptyTitle>
          <EmptyDescription>
            Upload a document above to get started.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <>
      <div className="divide-y rounded-lg border">
        {documents.map((doc) => (
          <div
            key={doc.id}
            className="flex cursor-pointer items-center gap-3 p-3 hover:bg-muted/50"
            onClick={() => setSelectedDocId(doc.id)}
          >
            <FileText className="h-4 w-4 text-muted-foreground" />
            <div className="flex-1">
              <p className="text-sm font-medium">{doc.filename}</p>
              <p className="text-xs text-muted-foreground">
                {doc.doc_type} &middot;{" "}
                {dayjs(doc.created_at).fromNow()}
              </p>
            </div>
            <Badge
              className={
                statusColors[doc.status] ??
                "bg-gray-100 text-gray-800 border-transparent"
              }
            >
              {doc.status}
            </Badge>
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                deleteMutation.mutate(doc.id);
              }}
              disabled={deleteMutation.isPending}
            >
              <Trash2 className="h-4 w-4 text-destructive" />
            </Button>
          </div>
        ))}
      </div>
      <DocumentViewer
        documentId={selectedDocId}
        onClose={() => setSelectedDocId(null)}
      />
    </>
  );
}
