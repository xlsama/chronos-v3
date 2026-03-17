import { Markdown } from "@/components/ui/markdown";

interface AnswerCardProps {
  content: string;
}

export function AnswerCard({ content }: AnswerCardProps) {
  return (
    <div className="rounded-lg border border-violet-200 bg-violet-50/50 p-4 text-sm">
      <Markdown content={content} variant="compact" />
    </div>
  );
}
