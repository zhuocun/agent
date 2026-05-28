"use client";

import { useRef, useState } from "react";
import { ArrowUp, Square } from "lucide-react";

import { Button } from "@/components/ui/button";
import { TierPicker } from "@/components/chat/tier-picker";
import { UsageMeter } from "@/components/chat/usage-meter";
import { MODEL_TIERS } from "@/lib/model-tiers";
import type { ModelTierId, UsageBudget } from "@/lib/types";

interface ComposerProps {
  isStreaming: boolean;
  selectedTierId: ModelTierId;
  onSelectTier: (id: ModelTierId) => void;
  usage: UsageBudget;
  onSend: (text: string) => void;
  onStop: () => void;
}

const MAX_HEIGHT = 200;

// Composer (PRD 01 §4.3, §5.3): Enter sends, Shift+Enter newlines, Esc stops
// while streaming (IME-safe). Send morphs into Stop in the same slot.
export function Composer({
  isStreaming,
  selectedTierId,
  onSelectTier,
  usage,
  onSend,
  onStop,
}: ComposerProps) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  const autoGrow = () => {
    const ta = ref.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, MAX_HEIGHT)}px`;
  };

  const submit = () => {
    const text = value.trim();
    if (!text || isStreaming) return;
    onSend(text);
    setValue("");
    requestAnimationFrame(() => {
      if (ref.current) ref.current.style.height = "auto";
    });
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Leave Esc and Enter to the IME while composing (CJK), per PRD 01 §5.3.
    if (e.nativeEvent.isComposing || e.keyCode === 229) return;
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    } else if (e.key === "Escape" && isStreaming) {
      e.preventDefault();
      onStop();
    }
  };

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-4 pt-1">
      <div className="rounded-2xl border border-border bg-card shadow-sm transition-shadow focus-within:ring-2 focus-within:ring-ring/60">
        <label htmlFor="composer-input" className="sr-only">
          Message Aperture
        </label>
        <textarea
          id="composer-input"
          ref={ref}
          rows={1}
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            autoGrow();
          }}
          onKeyDown={onKeyDown}
          placeholder="Message Aperture…"
          className="block max-h-[200px] w-full resize-none bg-transparent px-4 pt-3.5 text-[15px] leading-7 text-foreground outline-none placeholder:text-muted-foreground"
        />
        <div className="flex items-end justify-between gap-2 px-2.5 pb-2.5 pt-1">
          <div className="flex min-w-0 items-center gap-2">
            <TierPicker
              tiers={MODEL_TIERS}
              selectedId={selectedTierId}
              onSelect={onSelectTier}
            />
            <span className="hidden sm:block">
              <UsageMeter usage={usage} />
            </span>
          </div>

          {isStreaming ? (
            <Button
              type="button"
              onClick={onStop}
              aria-label="Stop generating"
              className="size-9 shrink-0 rounded-full p-0"
            >
              <Square className="size-3.5 fill-current" />
            </Button>
          ) : (
            <Button
              type="button"
              onClick={submit}
              disabled={!value.trim()}
              aria-label="Send message"
              className="size-9 shrink-0 rounded-full bg-brand p-0 text-brand-foreground hover:bg-brand/90 disabled:opacity-40"
            >
              <ArrowUp className="size-4" />
            </Button>
          )}
        </div>
      </div>
      <p className="mt-2 text-center text-xs text-muted-foreground">
        Aperture shows which model answered and what it cost. Verify important
        information.
      </p>
    </div>
  );
}
