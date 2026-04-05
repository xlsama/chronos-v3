export function truncateOutput(output: string, maxChars: number): string {
  if (output.length <= maxChars) return output;

  const half = Math.floor(maxChars / 2);
  return (
    output.slice(0, half) +
    `\n\n...[输出已截断，原始长度 ${output.length} 字符]...\n\n` +
    output.slice(-half)
  );
}
