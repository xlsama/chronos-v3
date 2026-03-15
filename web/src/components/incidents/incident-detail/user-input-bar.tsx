import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Send } from "lucide-react";
import { sendIncidentMessage } from "@/api/incidents";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface UserInputBarProps {
  incidentId: string;
}

export function UserInputBar({ incidentId }: UserInputBarProps) {
  const [message, setMessage] = useState("");

  const mutation = useMutation({
    mutationFn: (content: string) => sendIncidentMessage(incidentId, content),
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
      <Input
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        placeholder="Send a message to the agent..."
        className="flex-1"
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
