"use client";

import { forwardRef, useImperativeHandle, useRef, useState } from "react";
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
  sendOnEnter?: boolean;
}

export interface ComposerHandle {
  setDraft: (text: string) => void;
}

const MAX_HEIGHT = 200;

export const Composer = forwardRef<ComposerHandle, ComposerProps>(function Composer(
  {
    isStreaming,
    selectedTierId,
    onSelectTier,
    usage,
    onSend,
    onStop,
    sendOnEnter = true,
  },
  forwardedRef,
) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  const autoGrow = () => {
    const ta = ref.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, MAX_HEIGHT)}px`;
  };

  useImperativeHandle(forwardedRef, () => ({
    setDraft: (text: string) => {
      setValue(text);
      const ta = ref.current;
      if (ta) {
        ta.focus();
        requestAnimationFrame(autoGrow);
      }
    },
  }));

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
    // IME-safe: leave Esc/Enter to the composition layer (CJK).
    if (e.nativeEvent.isComposing || e.keyCode === 229) return;
    if (e.key === "Escape" && isStreaming) {
      e.preventDefault();
      onStop();
      return;
    }
    if (sendOnEnter) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        submit();
      }
    } else {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        submit();
      }
    }
  };

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pt-1">
      <div className="glass-capsule rounded-[28px] p-3 transition-shadow duration-300 ease-out focus-within:shadow-[var(--focus-glow-edge),var(--focus-glow-halo),var(--glass-highlight),var(--glass-shadow-ambient),var(--glass-shadow-key)]">
        <label htmlFor="composer-input" className="sr-only">
          Message Olune
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
          placeholder="Message Olune…"
          className="block max-h-[200px] min-h-[44px] w-full resize-none bg-transparent px-2 pt-2 text-[17px] leading-7 text-foreground outline-none placeholder:text-muted-foreground md:text-base"
        />
        <div className="mt-1 flex items-center justify-between gap-2">
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
              className="size-10 shrink-0 rounded-full bg-foreground p-0 text-background shadow-pill hover:bg-foreground/90"
            >
              <Square className="size-3.5 fill-current" />
            </Button>
          ) : (
            <Button
              type="button"
              onClick={submit}
              disabled={!value.trim()}
              aria-label="Send message"
              className="size-10 shrink-0 rounded-full bg-foreground p-0 text-background shadow-pill hover:bg-foreground/90 disabled:opacity-40 disabled:shadow-none"
            >
              <ArrowUp className="size-4" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
});

Composer.displayName = "Composer";
