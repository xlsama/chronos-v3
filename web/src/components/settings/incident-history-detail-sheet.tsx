import { useState } from "react";
import { History } from "lucide-react";
import dayjs from "@/lib/dayjs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Markdown } from "@/components/ui/markdown";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { VersionHistoryDialog } from "@/components/version-history/version-history-dialog";
import type { IncidentHistory } from "@/lib/types";

interface IncidentHistoryDetailSheetProps {
  item: IncidentHistory | null;
  onOpenChange: (open: boolean) => void;
}

export function IncidentHistoryDetailSheet({
  item,
  onOpenChange,
}: IncidentHistoryDetailSheetProps) {
  const [showHistory, setShowHistory] = useState(false);

  return (
    <Dialog open={!!item} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[90vh] flex-col sm:max-w-[80vw]">
        {item && (
          <>
            <DialogHeader className="flex-row items-start justify-between gap-2 space-y-0">
              <div className="min-w-0 flex-1">
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
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setShowHistory(true)}
                className="mr-6 shrink-0"
              >
                <History className="mr-1.5 h-3.5 w-3.5" />
                更新历史
              </Button>
            </DialogHeader>
            <ScrollArea className="min-h-0 flex-1">
              <Markdown content={item.summary_md} />
            </ScrollArea>
            <VersionHistoryDialog
              open={showHistory}
              onOpenChange={setShowHistory}
              entityType="incident_history"
              entityId={item.id}
              title="事件历史更新记录"
            />
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
