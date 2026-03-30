import { memo } from "react";
import { CircleCheck, CirclePause, CircleStop } from "lucide-react";
import { cn } from "@/lib/utils";

const dividerConfig = {
  done: {
    label: "Agent 排查完成",
    icon: CircleCheck,
    lineColor: "bg-green-200 dark:bg-green-800",
    pillBg: "bg-green-50 dark:bg-green-950/50",
    pillBorder: "border-green-200 dark:border-green-800",
    pillText: "text-green-700 dark:text-green-300",
    iconColor: "text-green-500",
  },
  agent_interrupted: {
    label: "已中断",
    icon: CirclePause,
    lineColor: "bg-orange-200 dark:bg-orange-800",
    pillBg: "bg-orange-50 dark:bg-orange-950/50",
    pillBorder: "border-orange-200 dark:border-orange-800",
    pillText: "text-orange-700 dark:text-orange-300",
    iconColor: "text-orange-500",
  },
  incident_stopped: {
    label: "事件已被手动停止",
    icon: CircleStop,
    lineColor: "bg-gray-200 dark:bg-gray-700",
    pillBg: "bg-gray-50 dark:bg-gray-800/50",
    pillBorder: "border-gray-200 dark:border-gray-700",
    pillText: "text-gray-600 dark:text-gray-400",
    iconColor: "text-gray-400",
  },
} as const;

interface TimelineDividerProps {
  type: keyof typeof dividerConfig;
}

export const TimelineDivider = memo(function TimelineDivider({ type }: TimelineDividerProps) {
  const config = dividerConfig[type];
  const Icon = config.icon;

  return (
    <div className="flex items-center py-2">
      <div className={cn("h-px flex-1", config.lineColor)} />
      <span
        className={cn(
          "mx-3 inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium",
          config.pillBg,
          config.pillBorder,
          config.pillText,
        )}
      >
        <Icon className={cn("h-3.5 w-3.5", config.iconColor)} />
        {config.label}
      </span>
      <div className={cn("h-px flex-1", config.lineColor)} />
    </div>
  );
});
