import dayjs from "@/lib/dayjs";
import { Badge } from "@/components/ui/badge";
import { Markdown } from "@/components/ui/markdown";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import type { IncidentHistory } from "@/lib/types";

interface IncidentHistoryDetailSheetProps {
  item: IncidentHistory | null;
  onOpenChange: (open: boolean) => void;
  onDelete: (id: string) => void;
}

export function IncidentHistoryDetailSheet({
  item,
  onOpenChange,
  onDelete,
}: IncidentHistoryDetailSheetProps) {
  return (
    <Dialog open={!!item} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[90vh] flex-col sm:max-w-[80vw]">
        {item && (
          <>
            <DialogHeader>
              <DialogTitle className="truncate">{item.title}</DialogTitle>
              <DialogDescription>
                <span className="flex items-center gap-6 mt-1">
                  {item.occurrence_count > 1 && (
                    <Badge variant="secondary">
                      {item.occurrence_count} 次
                    </Badge>
                  )}
                  <span>
                    创建时间: {dayjs(item.created_at).format("YYYY-MM-DD HH:mm")}
                  </span>
                  <span>
                    最后一次更新时间: {dayjs(item.last_seen_at).format("YYYY-MM-DD HH:mm")}
                  </span>
                </span>
              </DialogDescription>
            </DialogHeader>
            <ScrollArea className="min-h-0 flex-1">
              <Markdown content={item.summary_md} variant="compact" />
            </ScrollArea>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
