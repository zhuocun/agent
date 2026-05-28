import type { ChatMessage, MessagePart } from "@/lib/types";

export function UserMessage({ message }: { message: ChatMessage }) {
  const text = message.parts
    .filter((p): p is Extract<MessagePart, { type: "text" }> => p.type === "text")
    .map((p) => p.text)
    .join("\n\n");

  return (
    <div className="flex justify-end" role="article" aria-label="You">
      <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-3xl bg-muted px-5 py-3 text-[17px] leading-7 text-foreground md:text-[15px]">
        {text}
      </div>
    </div>
  );
}
