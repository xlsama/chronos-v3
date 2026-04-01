import { useState } from "react";
import { Bell, History, UserRound } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { IncidentHistoryPanel } from "./incident-history-panel";
import { NotificationSettings } from "./notification-settings";
import { ProfileSettings } from "./profile-settings";

interface SettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const tabs = [
  { id: "profile", label: "个人资料", icon: UserRound },
  { id: "notifications", label: "通知", icon: Bell },
  { id: "incident-history", label: "历史事件", icon: History },
] as const;

type TabId = (typeof tabs)[number]["id"];

export function SettingsDialog({ open, onOpenChange }: SettingsDialogProps) {
  const [activeTab, setActiveTab] = useState<TabId>("profile");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-5xl p-0 gap-0">
        <DialogHeader className="border-b px-6 py-4">
          <DialogTitle>设置</DialogTitle>
        </DialogHeader>
        <div className="flex h-[600px]">
          <nav className="flex w-48 shrink-0 flex-col gap-1 border-r p-2">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                  activeTab === tab.id
                    ? "bg-accent text-accent-foreground font-medium"
                    : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                )}
              >
                <tab.icon className="size-4" />
                {tab.label}
              </button>
            ))}
          </nav>
          <ScrollArea className="flex-1 p-5 pt-2">
            {activeTab === "profile" && <ProfileSettings />}
            {activeTab === "notifications" && <NotificationSettings />}
            {activeTab === "incident-history" && <IncidentHistoryPanel />}
          </ScrollArea>
        </div>
      </DialogContent>
    </Dialog>
  );
}
