interface UserMessageBubbleProps {
  content: string;
}

export function UserMessageBubble({ content }: UserMessageBubbleProps) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[80%] rounded-lg bg-muted px-4 py-2.5 text-foreground">
        <p className="text-sm whitespace-pre-wrap">{content}</p>
      </div>
    </div>
  );
}
