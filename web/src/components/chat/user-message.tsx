import type { ChatMessage, MessagePart } from "@/lib/types";

export function UserMessage({ message }: { message: ChatMessage }) {
  const text = message.parts
    .filter((p): p is Extract<MessagePart, { type: "text" }> => p.type === "text")
    .map((p) => p.text)
    .join("\n\n");

  return (
    <div className="flex justify-end" role="article" aria-label="You">
      <div className="max-w-[80%] whitespace-pre-wrap break-words rounded-2xl rounded-tr-md bg-message-user px-4 py-2.5 text-[15px] leading-7 text-message-user-foreground shadow-glass-ambient">
        {text}
      </div>
    </div>
  );
}
