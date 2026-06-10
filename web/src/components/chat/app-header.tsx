"use client";

import type { ReactNode } from "react";
import {
  ClipboardCopy,
  Download,
  FileText,
  Menu,
  MoreHorizontal,
  Printer,
  Share,
  SquarePen,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

interface AppHeaderProps {
  onNewChat?: () => void;
  onOpenMobileNav?: () => void;
  onOpenSidebar?: () => void;
  onToggleTemporary?: () => void;
  onCopyConversation?: () => void;
  canCopyConversation?: boolean;
  onDownloadConversation?: () => void;
  canDownloadConversation?: boolean;
  // Export the active conversation as a PDF (browser print dialog → Save as
  // PDF) or as a Word (.docx) download. Gated by the same content check as the
  // Markdown download.
  onPrintConversation?: () => void;
  onDownloadDocx?: () => void;
  onShareConversation?: () => void;
  // Sharing is only offered for a real, persisted (non-temporary) conversation
  // — the BE 404s on temporary chats and there's nothing to share before the
  // first turn lands a row.
  canShareConversation?: boolean;
  isTemporary?: boolean;
  sidebarOpen?: boolean;
  // Decorative centered slot between the left/right control groups — used by
  // the welcome state for the serif wordmark. Absolutely positioned so it
  // never shifts the control groups, and pointer-events-none so taps fall
  // through; pass non-interactive content only.
  centerSlot?: ReactNode;
}

// Dark theme swaps the chrome's glass fill up one tier (regular → strong) by
// re-pointing the token the `glass-regular` utility reads. Over the welcome
// hero gradient (and any colored content scrolling under the chrome) the
// 0.74-alpha regular fill lets the brand wash tint the circle and erode icon
// contrast; the strong fill is the darker scrim that keeps the glyphs reading.
// Token-to-token only — no literal color — and the reduced-transparency /
// forced-colors fallbacks bypass the var, so they're unaffected.
const FLOAT_SCRIM_DARK = "dark:[--glass-regular-bg:var(--glass-strong-bg)]";

const FLOAT_BUTTON = cn(
  "glass-regular size-[45px] rounded-full p-0 text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground aria-expanded:bg-transparent",
  FLOAT_SCRIM_DARK,
);

const FLOAT_BUTTON_TOUCH = cn(
  "glass-regular size-[45px] rounded-full p-0 text-foreground/80 shadow-sm ring-1 ring-foreground/10 transition-colors hover:bg-foreground/5 hover:text-foreground aria-expanded:bg-transparent md:hidden",
  FLOAT_SCRIM_DARK,
);

const PILL_HALF =
  "inline-flex h-[45px] w-[54px] select-none items-center justify-center rounded-full text-muted-foreground outline-none transition-[transform,background-color,color] duration-100 touch-manipulation hover:text-foreground hover:bg-foreground/5 focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none active:not-aria-[haspopup]:scale-[0.97]";

export function AppHeader({
  onNewChat,
  onOpenMobileNav,
  onOpenSidebar,
  onToggleTemporary,
  onCopyConversation,
  canCopyConversation,
  onDownloadConversation,
  canDownloadConversation,
  onPrintConversation,
  onDownloadDocx,
  onShareConversation,
  canShareConversation,
  isTemporary,
  sidebarOpen,
  centerSlot,
}: AppHeaderProps) {
  return (
    <header className="relative flex h-[52px] shrink-0 items-center gap-2 pl-[max(env(safe-area-inset-left),1.25rem)] pr-[max(env(safe-area-inset-right),1.25rem)] sm:pl-[max(env(safe-area-inset-left),1.5rem)] sm:pr-[max(env(safe-area-inset-right),1.5rem)] md:h-16">
      {centerSlot ? (
        <div className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 select-none">
          {centerSlot}
        </div>
      ) : null}
      <div className="flex min-w-0 flex-1 items-center justify-start gap-2">
        <Button
          type="button"
          variant="ghost"
          aria-label="Open sidebar"
          onClick={onOpenMobileNav}
          className={cn(FLOAT_BUTTON_TOUCH)}
        >
          <Menu className="size-[18px]" strokeWidth={2.25} />
        </Button>
        {!sidebarOpen ? (
          <Button
            type="button"
            variant="ghost"
            aria-label="Open sidebar"
            onClick={onOpenSidebar}
            className={cn("hidden md:inline-flex", FLOAT_BUTTON)}
          >
            <Menu className="size-[18px]" strokeWidth={2.25} />
          </Button>
        ) : null}
        {/* The model/mode picker moved out of the header into the composer
            toolbar (Lovable-style) — see composer.tsx's `modelPicker` slot. */}
      </div>

      <div className="flex min-w-0 flex-1 items-center justify-end">
        {/* Same dark scrim as the float buttons — the trailing pill floats on
            the identical gradient backdrop, so the materials must match. */}
        <div
          className={cn(
            "glass-regular inline-flex h-[45px] items-center rounded-full",
            FLOAT_SCRIM_DARK,
          )}
        >
          <button
            type="button"
            aria-label="New chat"
            onClick={onNewChat}
            className={cn(
              "hidden md:inline-flex",
              PILL_HALF,
              sidebarOpen && "md:hidden",
            )}
          >
            <SquarePen className="size-[18px]" strokeWidth={2.25} />
          </button>
          <span
            aria-hidden
            className={cn(
              "hidden md:block h-4 w-px bg-foreground/10",
              sidebarOpen && "md:hidden",
            )}
          />
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <button
                  type="button"
                  aria-label="Chat menu"
                  className={cn(PILL_HALF)}
                >
                  <MoreHorizontal className="size-[18px]" strokeWidth={2.25} />
                </button>
              }
            />
            <DropdownMenuContent align="end" sideOffset={8} className="min-w-56">
              <DropdownMenuCheckboxItem
                checked={isTemporary}
                onCheckedChange={onToggleTemporary}
              >
                Temporary chat
              </DropdownMenuCheckboxItem>
              {onCopyConversation ? (
                <DropdownMenuItem
                  onClick={onCopyConversation}
                  disabled={!canCopyConversation}
                  className="gap-2"
                >
                  <ClipboardCopy className="size-4" aria-hidden />
                  <span>Copy conversation</span>
                </DropdownMenuItem>
              ) : null}
              {onDownloadConversation ? (
                <DropdownMenuItem
                  onClick={onDownloadConversation}
                  disabled={!canDownloadConversation}
                  className="gap-2"
                >
                  <Download className="size-4" aria-hidden />
                  <span>Download Markdown</span>
                </DropdownMenuItem>
              ) : null}
              {onDownloadDocx ? (
                <DropdownMenuItem
                  onClick={onDownloadDocx}
                  disabled={!canDownloadConversation}
                  className="gap-2"
                >
                  <FileText className="size-4" aria-hidden />
                  <span>Download Word (.docx)</span>
                </DropdownMenuItem>
              ) : null}
              {onPrintConversation ? (
                <DropdownMenuItem
                  onClick={onPrintConversation}
                  disabled={!canDownloadConversation}
                  className="gap-2"
                >
                  <Printer className="size-4" aria-hidden />
                  <span>Save as PDF</span>
                </DropdownMenuItem>
              ) : null}
              {onShareConversation ? (
                <DropdownMenuItem
                  onClick={onShareConversation}
                  disabled={!canShareConversation}
                  className="gap-2"
                >
                  <Share className="size-4" aria-hidden />
                  <span>Share chat</span>
                </DropdownMenuItem>
              ) : null}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </header>
  );
}
