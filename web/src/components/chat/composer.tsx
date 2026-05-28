"use client";

import {
  forwardRef,
  useId,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import { ArrowUp, Square } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  SlashCommandsPopover,
  filterCommands,
} from "@/components/chat/slash-commands-popover";
import { MOCK_COMMANDS } from "@/lib/mock-data";
import type { SlashCommand } from "@/lib/types";

const SLASH_PATTERN = /^\/(\w*)$/;

interface ComposerProps {
  isStreaming: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
  sendOnEnter?: boolean;
}

export interface ComposerHandle {
  setDraft: (text: string) => void;
  focus: () => void;
}

const MAX_HEIGHT = 200;

export const Composer = forwardRef<ComposerHandle, ComposerProps>(function Composer(
  {
    isStreaming,
    onSend,
    onStop,
    sendOnEnter = true,
  },
  forwardedRef,
) {
  const [value, setValue] = useState("");
  const [slashSelectedIndex, setSlashSelectedIndex] = useState(0);
  // When the user explicitly dismisses with Escape, suppress the popover until
  // the slash token disappears (e.g. user backspaces out or types past it),
  // then arm again on the next fresh "/…" token.
  const [slashDismissed, setSlashDismissed] = useState(false);
  const ref = useRef<HTMLTextAreaElement>(null);
  // Anchor for the popover's outside-click guard — clicks anywhere on the
  // composer surface (textarea, send button) must NOT dismiss the popover.
  const capsuleRef = useRef<HTMLDivElement>(null);
  // Tracks the previous value so updateValue can detect transitions — namely a
  // "fresh slash" (prev didn't start with "/", new does) which re-arms the
  // popover even when the user has dismissed an earlier token with Escape.
  const prevValueRef = useRef("");
  const slashListboxId = useId();
  const slashOptionPrefix = useId();

  const slashMatch = value.match(SLASH_PATTERN);
  const slashQuery = slashMatch ? slashMatch[1] : "";
  const slashActive = slashMatch !== null && !slashDismissed;
  const filteredCommands = useMemo(
    () => (slashActive ? filterCommands(MOCK_COMMANDS, slashQuery) : []),
    [slashActive, slashQuery],
  );
  const slashOpen = slashActive;
  const slashHighlightIndex =
    filteredCommands.length === 0
      ? -1
      : Math.min(Math.max(slashSelectedIndex, 0), filteredCommands.length - 1);
  const slashActiveOptionId =
    slashOpen && slashHighlightIndex >= 0
      ? `${slashOptionPrefix}-${slashHighlightIndex}`
      : undefined;

  const autoGrow = () => {
    const ta = ref.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, MAX_HEIGHT)}px`;
  };

  const updateValue = (next: string) => {
    const prev = prevValueRef.current;
    prevValueRef.current = next;
    setValue(next);
    if (next.match(SLASH_PATTERN)) {
      // Reset highlight on every filter change so the first row stays selected.
      setSlashSelectedIndex(0);
      // Fresh-slash re-arm: if the prior value did NOT start with "/" and the
      // new one does, treat this as a brand-new slash session and clear any
      // earlier Escape dismissal. This covers the flow: type "/foo" → Esc →
      // backspace through to "" → type "/" again. (Backspacing within the
      // same slash token — e.g. "/foo" → "/fo" — preserves dismissal.)
      if (slashDismissed && !prev.startsWith("/") && next.startsWith("/")) {
        setSlashDismissed(false);
      }
    } else {
      // Token no longer present → re-arm the popover for the next "/…".
      if (slashDismissed) setSlashDismissed(false);
      setSlashSelectedIndex(0);
    }
  };

  const pickCommand = (command: SlashCommand) => {
    const next = command.prompt;
    prevValueRef.current = next;
    setValue(next);
    setSlashDismissed(false);
    setSlashSelectedIndex(0);
    const ta = ref.current;
    if (ta) {
      ta.focus();
      requestAnimationFrame(() => {
        const ta2 = ref.current;
        if (!ta2) return;
        const end = next.length;
        ta2.setSelectionRange(end, end);
        autoGrow();
      });
    }
  };

  useImperativeHandle(forwardedRef, () => ({
    setDraft: (text: string) => {
      prevValueRef.current = text;
      setValue(text);
      // A parent setting a draft (e.g. inserting "/something") is an explicit
      // re-arm: the popover should open if the new draft is a slash token.
      setSlashDismissed(false);
      setSlashSelectedIndex(0);
      const ta = ref.current;
      if (ta) {
        ta.focus();
        requestAnimationFrame(autoGrow);
      }
    },
    focus: () => {
      ref.current?.focus();
    },
  }));

  const submit = () => {
    const text = value.trim();
    if (!text || isStreaming) return;
    onSend(text);
    prevValueRef.current = "";
    setValue("");
    requestAnimationFrame(() => {
      if (ref.current) ref.current.style.height = "auto";
    });
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // IME-safe: leave Esc/Enter to the composition layer (CJK).
    if (e.nativeEvent.isComposing || e.keyCode === 229) return;
    // Slash-command layer runs first so Escape closes the popover (not the
    // stream) and Enter/Tab can pick a highlighted command before falling
    // through to the send path.
    if (slashOpen) {
      if (e.key === "Escape") {
        e.preventDefault();
        setSlashDismissed(true);
        setSlashSelectedIndex(0);
        return;
      }
      if (filteredCommands.length > 0) {
        if (e.key === "ArrowDown") {
          e.preventDefault();
          setSlashSelectedIndex(
            (slashHighlightIndex + 1) % filteredCommands.length,
          );
          return;
        }
        if (e.key === "ArrowUp") {
          e.preventDefault();
          setSlashSelectedIndex(
            (slashHighlightIndex - 1 + filteredCommands.length) %
              filteredCommands.length,
          );
          return;
        }
        if (e.key === "Tab" && !e.shiftKey && slashHighlightIndex >= 0) {
          e.preventDefault();
          const picked = filteredCommands[slashHighlightIndex];
          if (picked) pickCommand(picked);
          return;
        }
        if (
          e.key === "Enter" &&
          !e.shiftKey &&
          sendOnEnter &&
          slashHighlightIndex >= 0
        ) {
          e.preventDefault();
          const picked = filteredCommands[slashHighlightIndex];
          if (picked) pickCommand(picked);
          return;
        }
      }
    }
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
    <div className="relative mx-auto w-full max-w-3xl px-4 pt-1">
      <SlashCommandsPopover
        open={slashOpen}
        commands={MOCK_COMMANDS}
        query={slashQuery}
        selectedIndex={slashHighlightIndex}
        onSelectedIndexChange={setSlashSelectedIndex}
        onPick={pickCommand}
        onClose={() => setSlashDismissed(true)}
        listboxId={slashListboxId}
        optionIdPrefix={slashOptionPrefix}
        anchorRef={capsuleRef}
      />
      <div
        ref={capsuleRef}
        className="glass-capsule flex items-end gap-2 rounded-3xl px-2 py-1.5 transition-shadow duration-300 ease-out focus-within:shadow-[var(--focus-glow-edge),var(--focus-glow-halo),var(--glass-highlight),var(--glass-shadow-ambient),var(--glass-shadow-key)]"
      >
        <label htmlFor="composer-input" className="sr-only">
          Message Olune
        </label>
        <textarea
          id="composer-input"
          ref={ref}
          rows={1}
          value={value}
          onChange={(e) => {
            updateValue(e.target.value);
            autoGrow();
          }}
          onKeyDown={onKeyDown}
          placeholder="Message Olune…"
          role="combobox"
          aria-haspopup="listbox"
          aria-autocomplete="list"
          aria-expanded={slashOpen}
          aria-controls={slashOpen ? slashListboxId : undefined}
          aria-activedescendant={slashActiveOptionId}
          className="block max-h-[200px] min-h-[44px] flex-1 resize-none bg-transparent px-1 py-2 text-[17px] leading-7 text-foreground outline-none placeholder:text-muted-foreground md:text-base"
        />
        <div className="flex h-11 shrink-0 items-center">
          {isStreaming ? (
            <Tooltip>
              <TooltipTrigger
                render={
                  <Button
                    type="button"
                    onClick={onStop}
                    aria-label="Stop generating"
                    className="inline-flex size-11 shrink-0 items-center justify-center rounded-full bg-foreground p-0 text-background shadow-pill hover:bg-foreground/90"
                  >
                    <Square className="size-4 fill-current" />
                  </Button>
                }
              />
              <TooltipContent>Stop</TooltipContent>
            </Tooltip>
          ) : (
            <Button
              type="button"
              onClick={submit}
              disabled={!value.trim()}
              aria-label="Send message"
              className="inline-flex size-11 shrink-0 items-center justify-center rounded-full bg-foreground p-0 text-background shadow-pill hover:bg-foreground/90 disabled:opacity-40 disabled:shadow-none"
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
