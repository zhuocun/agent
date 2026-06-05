"use client";

import { useState } from "react";
import {
  ArrowRight,
  Check,
  ChevronDown,
  Copy,
  GitBranch,
  Loader2,
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

  return (
    <div role="toolbar" aria-label="Message actions" className="group/actions inline-flex items-center gap-0.5 rounded-full p-0.5">
      <IconAction
        label={copied ? "Copied" : copyFailed ? "Copy failed" : "Copy"}
        onClick={handleCopy}
      >
        {copied ? (
          <Check className="size-4 text-success" />
        ) : (
          <Copy className="size-4" />
        )}
      </IconAction>

      <ReadAloud
        speaking={speech.speaking}
        supported={speech.supported}
        onToggle={() => speech.toggle(text)}
      />

      {canContinue ? (
        <IconAction
          label="Continue"
          onClick={onContinue}
          testId="continue-turn"
        >
          <ArrowRight className="size-4" />
        </IconAction>
      ) : null}

      {canRegenerate ? (
        onRegenerateWith && regenerateOptions ? (
          <RegenerateMenu
            onRegenerate={onRegenerate}
            onRegenerateWith={onRegenerateWith}
            options={regenerateOptions}
          />
        ) : (
          <IconAction label="Regenerate" onClick={onRegenerate}>
            <RotateCcw className="size-4" />
          </IconAction>
        )
      ) : null}

      {onBranch ? (
        <IconAction
          label={isBranching ? "Branching" : "Branch in new chat"}
          disabled={!canBranch || isBranching}
          onClick={onBranch}
        >
          {isBranching ? (
            <Loader2 className="size-4 motion-safe:animate-spin" />
          ) : (
            <GitBranch className="size-4" />
          )}
        </IconAction>
      ) : null}

      <IconAction
        label="Helpful"
        pressed={feedback === "up"}
        onClick={() => onFeedback?.(feedback === "up" ? null : "up")}
      >
        <ThumbsUp className="size-4" />
      </IconAction>

      <IconAction
        label="Not helpful"
        pressed={feedback === "down"}
        onClick={() => onFeedback?.(feedback === "down" ? null : "down")}
      >
        <ThumbsDown className="size-4" />
      </IconAction>
    </div>
  );
}

// Split Regenerate control (Feature 4): a primary button that regenerates with
// the current tier, plus a chevron that opens a menu to regenerate with a
// different model (or provider route). Mirrors the model-mode-picker dropdown.
function RegenerateMenu({
  onRegenerate,
  onRegenerateWith,
  options,
}: {
  onRegenerate?: () => void;
  onRegenerateWith: (tierId: ModelTierId, providerId?: string) => void;
  options: {
    tiers: ModelTier[];
    providerOptions: ProviderTierOption[];
    selectedTierId: ModelTierId;
  };
}) {
  // Only offer provider items when there's a genuine choice (>1 available
  // route) — a single provider would just duplicate the tier row.
  const availableProviders = options.providerOptions.filter(
    (provider) => provider.status === "available",
  );
  const showProviders = availableProviders.length > 1;

  return (
    <div className="inline-flex items-center">
      {/* Primary: regenerate with the current tier (back-compat behaviour). */}
      <IconAction label="Regenerate" onClick={onRegenerate}>
        <RotateCcw className="size-4" />
      </IconAction>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              type="button"
              variant="ghost"
              aria-label="Regenerate with a different model"
              data-testid="regenerate-with-trigger"
              className="size-11 rounded-full p-0 text-muted-foreground hover:text-foreground md:size-9"
            >
              <ChevronDown className="size-4" />
            </Button>
          }
        />
        <DropdownMenuContent
          align="start"
          sideOffset={8}
          className="w-60 max-w-[min(18rem,calc(100vw-1.5rem))] rounded-2xl"
        >
          <DropdownMenuGroup>
            <DropdownMenuLabel className="text-2xs font-semibold">
              Regenerate with
            </DropdownMenuLabel>
            {options.tiers.map((tier) => (
              <DropdownMenuItem
                key={tier.id}
                label={tier.label}
                onClick={() => onRegenerateWith(tier.id)}
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
              <DropdownMenuLabel className="text-2xs font-semibold">
                Provider
              </DropdownMenuLabel>
              {availableProviders.map((provider) => (
                <DropdownMenuItem
                  key={provider.providerId}
                  label={provider.label}
                  onClick={() =>
                    onRegenerateWith(options.selectedTierId, provider.providerId)
                  }
                  className="py-2"
                >
                  <div className="min-w-0 flex-1">
                    <span className="truncate font-medium">{provider.label}</span>
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
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}

// Read-aloud (TTS) control. Speaks the assistant message text with the browser
// `speechSynthesis` voice and toggles play/stop. This is ON-DEVICE — the
// browser/OS speaks locally and NO provider is involved — so the tooltip says
// so honestly and never implies a served model or cost (D22 transparency
// spine). Feature-detects: when speechSynthesis is unavailable the control is
// disabled with an explanatory tooltip. Kept distinct from the generic
// `IconAction` so the tooltip can carry the transparency note while the
// aria-label stays concise.
function ReadAloud({
  speaking,
  supported,
  onToggle,
}: {
  speaking: boolean;
  supported: boolean;
  onToggle: () => void;
}) {
  const label = !supported
    ? "Read aloud not supported in this browser"
    : speaking
      ? "Stop reading"
      : "Read aloud";
  const tooltip = !supported
    ? "Read aloud isn't supported in this browser"
    : speaking
      ? "Stop reading · spoken on your device by your browser"
      : "Read aloud · spoken on your device by your browser";
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            type="button"
            variant="ghost"
            onClick={onToggle}
            disabled={!supported}
            data-testid="read-aloud"
            aria-label={label}
            aria-pressed={supported ? speaking : undefined}
            className={cn(
              "size-11 rounded-full p-0 text-muted-foreground hover:text-foreground md:size-9",
              speaking && "bg-foreground/[0.06] text-foreground",
            )}
          >
            {speaking ? (
              <Square className="size-4 fill-current" />
            ) : (
              <Volume2 className="size-4" />
            )}
          </Button>
        }
      />
      <TooltipContent>{tooltip}</TooltipContent>
    </Tooltip>
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
