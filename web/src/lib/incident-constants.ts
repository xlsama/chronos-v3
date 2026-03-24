export const severityColors: Record<string, string> = {
  P0: "bg-red-100 text-red-800 border-transparent",
  P1: "bg-orange-100 text-orange-800 border-transparent",
  P2: "bg-yellow-100 text-yellow-800 border-transparent",
  P3: "bg-blue-100 text-blue-800 border-transparent",
};

export const statusColors: Record<string, string> = {
  open: "bg-red-100 text-red-800 border-transparent",
  investigating: "bg-yellow-100 text-yellow-800 border-transparent",
  resolved: "bg-green-100 text-green-800 border-transparent",
  stopped: "bg-gray-100 text-gray-800 border-transparent",
  error: "bg-red-100 text-red-800 border-transparent",
};

export const statusLabels: Record<string, string> = {
  open: "待处理",
  investigating: "调查中",
  resolved: "已解决",
  stopped: "已停止",
  error: "error",
};
