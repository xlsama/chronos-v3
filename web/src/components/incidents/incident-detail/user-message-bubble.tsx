import { Paperclip } from "lucide-react";
import { getAttachmentUrl } from "@/api/attachments";

interface OptimisticAttachment {
  filename: string;
  content_type: string;
  size: number;
  preview_url: string | null;
}

interface UserMessageBubbleProps {
  content: string;
  attachments?: OptimisticAttachment[];
  attachment_ids?: string[];
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function UserMessageBubble({
  content,
  attachments,
  attachment_ids,
}: UserMessageBubbleProps) {
  const hasOptimistic = attachments && attachments.length > 0;
  const hasServerIds = attachment_ids && attachment_ids.length > 0;

  return (
    <div className="flex justify-end">
      <div className="max-w-[80%] rounded-lg bg-blue-50 px-4 py-2.5 text-blue-900 dark:bg-blue-950/50 dark:text-blue-100">
        <p className="text-sm whitespace-pre-wrap">{content}</p>

        {/* Optimistic attachments (from local upload, before server confirms) */}
        {hasOptimistic && (
          <div className="mt-2 flex flex-wrap gap-2">
            {attachments.map((a, i) =>
              a.preview_url ? (
                <img
                  key={i}
                  src={a.preview_url}
                  alt={a.filename}
                  className="max-h-48 rounded-md object-cover"
                />
              ) : (
                <div
                  key={i}
                  className="flex items-center gap-1.5 rounded-md bg-blue-100 px-2.5 py-1.5 text-xs dark:bg-blue-900/50"
                >
                  <Paperclip className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate max-w-[160px]">{a.filename}</span>
                  <span className="text-blue-600 dark:text-blue-300">
                    {formatFileSize(a.size)}
                  </span>
                </div>
              ),
            )}
          </div>
        )}

        {/* Server-side attachments (replay from DB) */}
        {!hasOptimistic && hasServerIds && (
          <div className="mt-2 flex flex-wrap gap-2">
            {attachment_ids.map((id) => {
              const url = getAttachmentUrl(id);
              return (
                <a
                  key={id}
                  href={url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 rounded-md bg-blue-100 px-2.5 py-1.5 text-xs hover:bg-blue-200 dark:bg-blue-900/50 dark:hover:bg-blue-900/70"
                >
                  <Paperclip className="h-3.5 w-3.5 shrink-0" />
                  <span>附件</span>
                </a>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
