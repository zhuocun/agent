"use client";

import { useState } from "react";
import {
  ArrowRight,
  Check,
  Copy,
  GitBranch,
  Loader2,
  MoreHorizontal,
  RotateCcw,
  Square,
  ThumbsDown,
  ThumbsUp,
  Volume2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useSpeechSynthesis } from "@/lib/use-speech-synthesis";
import { cn } from "@/lib/utils";
import type {
  Feedback,
  ModelTier,
  ModelTierId,
  ProviderTierOption,
} from "@/lib/types";

interface MessageActionsProps {
  text: string;
  feedback: Feedback;
  canBranch?: boolean;
  isBranching?: boolean;
  canRegenerate?: boolean;
  // Shown only for a Stopped turn: keeps the persisted partial and streams a
  // continuation as a new assistant bubble (see chat-thread `handleContinue`).
  canContinue?: boolean;
  onBranch?: () => void;
  onRegenerate?: () => void;
  // Regenerate with a SPECIFIC model/provider (Feature 4). When provided
  // alongside `regenerateOptions`, the Regenerate control becomes a split
  // dropdown: primary click regenerates with the current tier (`onRegenerate`);
  // menu items pick another tier/provider. Absent ⇒ plain Regenerate button.
  onRegenerateWith?: (tierId: ModelTierId, providerId?: string) => void;
  // The tiers (and provider routes) offered in the regenerate menu. Required for
  // the split-dropdown variant; absent ⇒ plain button. `providerOptions` are the
  // routes for `selectedTierId` (the currently-served tier), so provider items
  // regenerate that tier on the chosen provider.
  regenerateOptions?: {
    tiers: ModelTier[];
    providerOptions: ProviderTierOption[];
    selectedTierId: ModelTierId;
  };
  onContinue?: () => void;
  onFeedback?: (next: Feedback) => void;
}

// Legacy clipboard fallback for insecure origins / denied permission, where
// `navigator.clipboard` is unavailable. Selects an off-screen textarea and
// runs `document.execCommand("copy")`. Returns whether the copy succeeded.
function legacyCopy(value: string): boolean {
  if (typeof document === "undefined") return false;
  const ta = document.createElement("textarea");
  ta.value = value;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.top = "-9999px";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  try {
    ta.focus();
    ta.select();
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    document.body.removeChild(ta);
  }
}

export function MessageActions({
  text,
  feedback,
  canBranch,
  isBranching,
  canRegenerate,
  canContinue,
  onBranch,
  onRegenerate,
  onRegenerateWith,
  regenerateOptions,
  onContinue,
  onFeedback,
}: MessageActionsProps) {
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);
  const speech = useSpeechSynthesis();

  const handleCopy = async () => {
    const markCopied = () => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    };
    // Clipboard API is the happy path; fall back to a legacy off-screen
    // textarea + execCommand so copy still works on insecure origins / when
    // permission is denied (mirrors share-dialog.tsx). Prefer copying over
    // erroring; only surface "Copy failed" if both paths fail.
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        markCopied();
        return;
      }
      throw new Error("clipboard unavailable");
    } catch {
      if (legacyCopy(text)) {
        markCopied();
      } else {
        setCopyFailed(true);
        setTimeout(() => setCopyFailed(false), 1500);
      }
    }
  };

  // Minimal iOS-native pattern on all devices: only Copy + "…" overflow live
  // inline. Regenerate and the two ratings fold into the overflow alongside
  // Read aloud / Continue / Branch / model-choice so the inline strip stays at
  // two hit-targets regardless of pointer type. Secondary items stay MOUNTED
  // inside the popup (DropdownMenu provides reduced-motion, focus trap+restore,
  // keyboard) so they remain one tap/click deep behind the always-shown "…".
  const hasModelChoice = Boolean(
    canRegenerate && onRegenerateWith && regenerateOptions,
  );

  return (
    <div role="toolbar" aria-label="Message actions" className="group/actions inline-flex items-center gap-0.5 rounded-full p-0.5">
      <IconAction
        label={copied ? "Copied" : copyFailed ? "Copy failed" : "Copy"}
        onClick={handleCopy}
        testId="copy"
      >
        {copied ? (
          <Check className="size-4 text-success" />
        ) : (
          <Copy className="size-4" />
        )}
      </IconAction>

      <OverflowMenu
        text={text}
        speech={speech}
        canContinue={canContinue}
        onContinue={onContinue}
        canBranch={canBranch}
        isBranching={isBranching}
        onBranch={onBranch}
        primary={{
          canRegenerate: !!canRegenerate,
          onRegenerate,
          feedback,
          onFeedback,
        }}
        modelChoice={
          hasModelChoice
            ? {
                onRegenerateWith: onRegenerateWith!,
                options: regenerateOptions!,
              }
            : undefined
        }
      />
    </div>
  );
}

// Secondary actions, folded behind a single "…" overflow (W1). Reuses the
// shared DropdownMenu primitive (reduced-motion + focus trap/restore + keyboard
// for free). The trigger is always painted so it never hides the only route to
// Regenerate / ratings / Read aloud / Continue / Branch / model-choice. All
// reparented items keep their original data-testid and accessible names.
function OverflowMenu({
  text,
  speech,
  canContinue,
  onContinue,
  canBranch,
  isBranching,
  onBranch,
  primary,
  modelChoice,
}: {
  text: string;
  speech: ReturnType<typeof useSpeechSynthesis>;
  canContinue?: boolean;
  onContinue?: () => void;
  canBranch?: boolean;
  isBranching?: boolean;
  onBranch?: () => void;
  // The inline strip is just Copy + "…" on every device. Regenerate and the
  // two ratings live at the top of the menu so they stay one tap/click deep.
  primary?: {
    canRegenerate: boolean;
    onRegenerate?: () => void;
    feedback: Feedback;
    onFeedback?: (next: Feedback) => void;
  };
  modelChoice?: {
    onRegenerateWith: (tierId: ModelTierId, providerId?: string) => void;
    options: {
      tiers: ModelTier[];
      providerOptions: ProviderTierOption[];
      selectedTierId: ModelTierId;
    };
  };
}) {
  const readAloudLabel = !speech.supported
    ? "Read aloud not supported in this browser"
    : speech.speaking
      ? "Stop reading"
      : "Read aloud";
  const readAloudHint = !speech.supported
    ? "Isn't supported in this browser"
    : "Spoken on your device by your browser";

  // Only offer provider items when there's a genuine choice (>1 available
  // route) — a single provider would just duplicate the tier row.
  const availableProviders =
    modelChoice?.options.providerOptions.filter(
      (provider) => provider.status === "available",
    ) ?? [];
  const showProviders = availableProviders.length > 1;

  return (
    <DropdownMenu>
      <Tooltip>
        <TooltipTrigger
          render={
            <DropdownMenuTrigger
              render={
                <Button
                  type="button"
                  variant="ghost"
                  aria-label="More actions"
                  data-testid="message-actions-overflow"
                  className="size-11 rounded-full p-0 text-muted-foreground hover:text-foreground md:size-9"
                >
                  <MoreHorizontal className="size-4" />
                </Button>
              }
            />
          }
        />
        <TooltipContent>More actions</TooltipContent>
      </Tooltip>
      <DropdownMenuContent
        align="start"
        sideOffset={8}
        className="w-60 max-w-[min(18rem,calc(100vw-1.5rem))] rounded-2xl"
      >
        {primary ? (
          <DropdownMenuGroup>
            {primary.canRegenerate ? (
              <DropdownMenuItem
                label="Regenerate"
                aria-label="Regenerate"
                onClick={primary.onRegenerate}
                className="py-2"
              >
                <RotateCcw className="size-4" />
                <span className="truncate font-medium">Regenerate</span>
              </DropdownMenuItem>
            ) : null}
            <DropdownMenuItem
              label="Helpful"
              aria-label="Helpful"
              aria-pressed={primary.feedback === "up"}
              closeOnClick={false}
              onClick={() =>
                primary.onFeedback?.(
                  primary.feedback === "up" ? null : "up",
                )
              }
              className="py-2"
            >
              <ThumbsUp className="size-4" />
              <span className="truncate font-medium">Helpful</span>
              {primary.feedback === "up" ? (
                <Check className="ml-auto size-4 text-success" aria-hidden />
              ) : null}
            </DropdownMenuItem>
            <DropdownMenuItem
              label="Not helpful"
              aria-label="Not helpful"
              aria-pressed={primary.feedback === "down"}
              closeOnClick={false}
              onClick={() =>
                primary.onFeedback?.(
                  primary.feedback === "down" ? null : "down",
                )
              }
              className="py-2"
            >
              <ThumbsDown className="size-4" />
              <span className="truncate font-medium">Not helpful</span>
              {primary.feedback === "down" ? (
                <Check className="ml-auto size-4 text-success" aria-hidden />
              ) : null}
            </DropdownMenuItem>
          </DropdownMenuGroup>
        ) : null}
        <DropdownMenuGroup>
          <DropdownMenuItem
            label={readAloudLabel}
            aria-label={readAloudLabel}
            aria-pressed={speech.supported ? speech.speaking : undefined}
            disabled={!speech.supported}
            // On-device TTS (D22): never implies a served model or cost. The
            // hint says the browser/OS speaks locally.
            closeOnClick={false}
            onClick={() => speech.toggle(text)}
            data-testid="read-aloud"
            className="py-2"
          >
            {speech.speaking ? (
              <Square className="size-4 fill-current" />
            ) : (
              <Volume2 className="size-4" />
            )}
            <div className="min-w-0 flex-1">
              <span className="truncate font-medium">{readAloudLabel}</span>
              <p className="mt-0.5 truncate text-xs leading-snug text-muted-foreground group-focus/dropdown-menu-item:text-accent-foreground/80">
                {readAloudHint}
              </p>
            </div>
          </DropdownMenuItem>

          {canContinue ? (
            <DropdownMenuItem
              label="Continue"
              aria-label="Continue"
              onClick={onContinue}
              data-testid="continue-turn"
              className="py-2"
            >
              <ArrowRight className="size-4" />
              <span className="truncate font-medium">Continue</span>
            </DropdownMenuItem>
          ) : null}

          {onBranch ? (
            <DropdownMenuItem
              label={isBranching ? "Branching" : "Branch in new chat"}
              aria-label={isBranching ? "Branching" : "Branch in new chat"}
              disabled={!canBranch || isBranching}
              onClick={onBranch}
              data-testid="branch"
              className="py-2"
            >
              {isBranching ? (
                <Loader2 className="size-4 motion-safe:animate-spin" />
              ) : (
                <GitBranch className="size-4" />
              )}
              <span className="truncate font-medium">
                {isBranching ? "Branching" : "Branch in new chat"}
              </span>
            </DropdownMenuItem>
          ) : null}
        </DropdownMenuGroup>

        {modelChoice ? (
          <>
            <DropdownMenuGroup>
              <DropdownMenuLabel className="text-2xs font-semibold tracking-wide uppercase">
                Regenerate with
              </DropdownMenuLabel>
              {/* The split-regenerate trigger keeps its testid so the model
                  CHOICE list (a different model than the current tier) is still
                  reachable — it now lives inside the overflow rather than as a
                  sibling chevron. The one-click current-tier Regenerate stays
                  inline as a primary action above. */}
              <span className="sr-only" data-testid="regenerate-with-trigger" />
              {modelChoice.options.tiers.map((tier) => (
                <DropdownMenuItem
                  key={tier.id}
                  label={tier.label}
                  onClick={() => modelChoice.onRegenerateWith(tier.id)}
                  data-testid={`regenerate-with-tier-${tier.id}`}
                  className="py-2"
                >
                  <div className="min-w-0 flex-1">
                    <span className="truncate font-medium">{tier.label}</span>
                    {tier.modelLabel ? (
                      <p className="mt-0.5 truncate text-xs leading-snug text-muted-foreground group-focus/dropdown-menu-item:text-accent-foreground/80">
                        {tier.modelLabel}
                      </p>
                    ) : null}
                  </div>
                </DropdownMenuItem>
              ))}
            </DropdownMenuGroup>
            {showProviders ? (
              <DropdownMenuGroup>
                <DropdownMenuLabel className="text-2xs font-semibold tracking-wide uppercase">
                  Provider
                </DropdownMenuLabel>
                {availableProviders.map((provider) => (
                  <DropdownMenuItem
                    key={provider.providerId}
                    label={provider.label}
                    onClick={() =>
                      modelChoice.onRegenerateWith(
                        modelChoice.options.selectedTierId,
                        provider.providerId,
                      )
                    }
                    className="py-2"
                  >
                    <div className="min-w-0 flex-1">
                      <span className="truncate font-medium">
                        {provider.label}
                      </span>
                      {provider.modelLabel ? (
                        <p className="mt-0.5 truncate text-xs leading-snug text-muted-foreground group-focus/dropdown-menu-item:text-accent-foreground/80">
                          {provider.modelLabel}
                        </p>
                      ) : null}
                    </div>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuGroup>
            ) : null}
          </>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function IconAction({
  label,
  pressed,
  disabled,
  onClick,
  testId,
  children,
}: {
  label: string;
  pressed?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  testId?: string;
  children: React.ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            type="button"
            variant="ghost"
            onClick={onClick}
            disabled={disabled}
            data-testid={testId}
            aria-label={label}
            aria-pressed={typeof pressed === "boolean" ? pressed : undefined}
            className={cn(
              "size-11 rounded-full p-0 text-muted-foreground hover:text-foreground md:size-9",
              pressed && "bg-foreground/[0.06] text-foreground",
            )}
          >
            {children}
          </Button>
        }
      />
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}
