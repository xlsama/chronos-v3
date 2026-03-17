import { Trash2 } from "lucide-react";
import dayjs from "@/lib/dayjs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Markdown } from "@/components/ui/markdown";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
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
    <Sheet open={!!item} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-lg">
        {item && (
          <>
            <SheetHeader>
              <div className="flex items-start justify-between gap-2 pr-8">
                <div className="min-w-0">
                  <SheetTitle className="truncate">{item.title}</SheetTitle>
                  <SheetDescription>
                    <span className="flex items-center gap-2 mt-1">
                      {item.occurrence_count > 1 && (
                        <Badge variant="secondary">
                          {item.occurrence_count} 次
                        </Badge>
                      )}
                      <span>
                        首次: {dayjs(item.created_at).format("YYYY-MM-DD HH:mm")}
                      </span>
                      <span>
                        最近: {dayjs(item.last_seen_at).format("YYYY-MM-DD HH:mm")}
                      </span>
                    </span>
                  </SheetDescription>
                </div>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="shrink-0 text-muted-foreground hover:text-destructive"
                  onClick={() => onDelete(item.id)}
                >
                  <Trash2 className="size-4" />
                </Button>
              </div>
            </SheetHeader>
            <ScrollArea className="flex-1 px-4 pb-4">
              <Markdown content={item.summary_md} />
            </ScrollArea>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
