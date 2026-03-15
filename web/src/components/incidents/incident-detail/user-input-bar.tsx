import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Send } from "lucide-react";

interface UserInputBarProps {
  incidentId: string;
}

export function UserInputBar({ incidentId }: UserInputBarProps) {
  const [message, setMessage] = useState("");

  const mutation = useMutation({
    mutationFn: (content: string) =>
      api(`/incidents/${incidentId}/messages`, {
        method: "POST",
        body: { content },
      }),
    onSuccess: () => setMessage(""),
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (message.trim()) {
      mutation.mutate(message.trim());
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-center gap-2 border-t p-4"
    >
      <input
        type="text"
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        placeholder="Send a message to the agent..."
        className="flex-1 rounded-md border px-3 py-2 text-sm"
      />
      <Button
        type="submit"
        size="sm"
        disabled={!message.trim() || mutation.isPending}
      >
        <Send className="h-4 w-4" />
      </Button>
    </form>
  );
}
