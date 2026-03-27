export const severityColors: Record<string, string> = {
  P0: "bg-red-50 text-red-700 border-transparent dark:bg-red-950/40 dark:text-red-400",
  P1: "bg-orange-50 text-orange-700 border-transparent dark:bg-orange-950/40 dark:text-orange-400",
  P2: "bg-amber-50 text-amber-700 border-transparent dark:bg-amber-950/40 dark:text-amber-400",
  P3: "bg-sky-50 text-sky-700 border-transparent dark:bg-sky-950/40 dark:text-sky-400",
};

export const statusColors: Record<string, string> = {
  open: "bg-red-50 text-red-700 border-transparent dark:bg-red-950/40 dark:text-red-400",
  investigating: "bg-amber-50 text-amber-700 border-transparent dark:bg-amber-950/40 dark:text-amber-400",
  resolved: "bg-emerald-50 text-emerald-700 border-transparent dark:bg-emerald-950/40 dark:text-emerald-400",
  stopped: "bg-slate-100 text-slate-600 border-transparent dark:bg-slate-800/40 dark:text-slate-400",
  interrupted: "bg-orange-50 text-orange-700 border-transparent dark:bg-orange-950/40 dark:text-orange-400",
  error: "bg-red-50 text-red-700 border-transparent dark:bg-red-950/40 dark:text-red-400",
};

export const statusLabels: Record<string, string> = {
  open: "待处理",
  investigating: "调查中",
  resolved: "已解决",
  stopped: "已停止",
  interrupted: "已中断",
  error: "error",
};
