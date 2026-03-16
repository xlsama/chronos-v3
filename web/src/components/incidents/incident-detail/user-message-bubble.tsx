interface UserMessageBubbleProps {
  content: string;
  relativeTime?: string;
}

export function UserMessageBubble({ content, relativeTime }: UserMessageBubbleProps) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[80%] rounded-lg bg-primary px-4 py-2.5 text-primary-foreground">
        <p className="text-sm whitespace-pre-wrap">{content}</p>
        {relativeTime && (
          <p className="mt-1 text-right text-xs opacity-70">{relativeTime}</p>
        )}
      </div>
    </div>
  );
}
