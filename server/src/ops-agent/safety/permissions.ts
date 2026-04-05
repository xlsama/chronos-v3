import type { CommandType, PermissionResult } from "../types";

/**
 * CommandType → PermissionResult 映射
 * read → allow, write → ask MEDIUM, dangerous → ask HIGH, blocked → deny
 */
export function toPermissionResult(type: CommandType, detail: string): PermissionResult {
  switch (type) {
    case "read":
      return { behavior: "allow", reason: "", riskLevel: "" };
    case "write":
      return { behavior: "ask", reason: detail, riskLevel: "MEDIUM" };
    case "dangerous":
      return { behavior: "ask", reason: detail, riskLevel: "HIGH" };
    case "blocked":
      return { behavior: "deny", reason: detail, riskLevel: "" };
  }
}
