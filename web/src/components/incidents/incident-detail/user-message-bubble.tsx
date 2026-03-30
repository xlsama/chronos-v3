import { memo, useState } from "react";
import { FileText, Paperclip } from "lucide-react";
import { getAttachmentUrl } from "@/api/attachments";
import {
  AttachmentPreviewDialog,
  ImageLightbox,
} from "@/components/incidents/attachment-preview-dialog";
import type { PreviewableAttachment } from "@/components/incidents/attachment-preview-dialog";

interface OptimisticAttachment {
  filename: string;
  content_type: string;
  size: number;
  preview_url: string | null;
}

interface AttachmentMeta {
  id: string;
  filename: string;
  content_type: string;
  size: number;
}

interface UserMessageBubbleProps {
  content: string;
  attachments?: OptimisticAttachment[];
  attachment_ids?: string[];
  attachments_meta?: AttachmentMeta[];
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export const UserMessageBubble = memo(function UserMessageBubble({
  content,
  attachments,
  attachment_ids,
  attachments_meta,
}: UserMessageBubbleProps) {
  const hasOptimistic = attachments && attachments.length > 0;
  const hasMeta = attachments_meta && attachments_meta.length > 0;
  const hasServerIds = attachment_ids && attachment_ids.length > 0;

  const [lightbox, setLightbox] = useState<{
    url: string;
    filename: string;
  } | null>(null);
  const [previewAttachment, setPreviewAttachment] =
    useState<PreviewableAttachment | null>(null);

  return (
    <>
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-lg bg-blue-50 px-4 py-2.5 text-blue-900 dark:bg-blue-950/50 dark:text-blue-100">
          <p className="text-sm whitespace-pre-wrap">{content}</p>

          {/* Optimistic attachments (from local upload, before server confirms) */}
          {hasOptimistic && (
            <div className="mt-2 flex items-center gap-1.5">
              {attachments.map((a, i) =>
                a.preview_url && a.content_type.startsWith("image/") ? (
                  <button
                    key={i}
                    type="button"
                    onClick={() =>
                      setLightbox({
                        url: a.preview_url!,
                        filename: a.filename,
                      })
                    }
                    className="shrink-0 overflow-hidden rounded border transition-opacity hover:opacity-80"
                  >
                    <img
                      src={a.preview_url}
                      alt={a.filename}
                      className="size-8 rounded object-cover"
                    />
                  </button>
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

          {/* Server-side attachments with metadata (new messages) */}
          {!hasOptimistic && hasMeta && (
            <div className="mt-2 flex items-center gap-1.5">
              {attachments_meta.map((meta) => {
                const url = getAttachmentUrl(meta.id);
                return meta.content_type.startsWith("image/") ? (
                  <button
                    key={meta.id}
                    type="button"
                    onClick={() => setPreviewAttachment(meta)}
                    className="shrink-0 overflow-hidden rounded border transition-opacity hover:opacity-80"
                  >
                    <img
                      src={url}
                      alt={meta.filename}
                      className="size-8 rounded object-cover"
                    />
                  </button>
                ) : (
                  <button
                    key={meta.id}
                    type="button"
                    onClick={() => setPreviewAttachment(meta)}
                    className="flex items-center gap-1.5 rounded-md bg-blue-100 px-2.5 py-1.5 text-xs hover:bg-blue-200 dark:bg-blue-900/50 dark:hover:bg-blue-900/70"
                  >
                    <FileText className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate max-w-[160px]">
                      {meta.filename}
                    </span>
                    <span className="text-blue-600 dark:text-blue-300">
                      {formatFileSize(meta.size)}
                    </span>
                  </button>
                );
              })}
            </div>
          )}

          {/* Server-side attachments without metadata (old messages, backward compat) */}
          {!hasOptimistic && !hasMeta && hasServerIds && (
            <div className="mt-2 flex items-center gap-1.5">
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

      {lightbox && (
        <ImageLightbox
          src={lightbox.url}
          filename={lightbox.filename}
          onClose={() => setLightbox(null)}
        />
      )}
      <AttachmentPreviewDialog
        attachment={previewAttachment}
        open={!!previewAttachment}
        onOpenChange={(open) => !open && setPreviewAttachment(null)}
      />
    </>
  );
});
