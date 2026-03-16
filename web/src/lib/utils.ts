import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"
import dayjs from "dayjs"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Format relative time from base: "+3s", "+1m 12s" */
export function formatRelativeTime(timestampIso: string, baseTimestampIso: string): string {
  const diffMs = dayjs(timestampIso).diff(dayjs(baseTimestampIso));
  if (diffMs < 0) return "+0s";
  const totalSec = Math.round(diffMs / 1000);
  if (totalSec < 60) return `+${totalSec}s`;
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  return sec > 0 ? `+${min}m ${sec}s` : `+${min}m`;
}

/** Format duration between two timestamps: "3s", "1m 12s" */
export function formatDuration(startIso: string, endIso: string): string {
  const diffMs = dayjs(endIso).diff(dayjs(startIso));
  if (diffMs < 0) return "0s";
  const totalSec = Math.round(diffMs / 1000);
  if (totalSec < 60) return `${totalSec}s`;
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  return sec > 0 ? `${min}m ${sec}s` : `${min}m`;
}
