const SHELL_TOOLS = new Set(["ssh_bash", "bash"]);

/**
 * 从 tool output 中提取适合展示的文本。
 *
 * - ssh_bash / bash: output 是 JSON {"exit_code", "stdout", "stderr", "error"}，提取可读内容
 * - 其他工具: 直接返回原文
 */
export function formatToolOutput(name: string, output: string): string {
  if (!SHELL_TOOLS.has(name)) return output;

  try {
    const parsed = JSON.parse(output);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return output;

    if (parsed.error) return parsed.error;

    let text = parsed.stdout ?? "";
    if (parsed.stderr) text += (text ? "\n\n--- stderr ---\n" : "") + parsed.stderr;
    return text || output;
  } catch {
    return output;
  }
}
