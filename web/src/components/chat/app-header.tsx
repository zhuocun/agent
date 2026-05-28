"use client";

import { Ghost, MoreVertical, PanelLeft, Plus, Settings } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

interface AppHeaderProps {
  title: string;
  /**
   * Optional second line under the title (model/agent context). When omitted
   * the header renders a single centered line.
   */
  subtitle?: string;
  onNewChat?: () => void;
  onOpenMobileNav?: () => void;
  onOpenSidebar?: () => void;
  sidebarOpen?: boolean;
  onOpenSettings?: () => void;
  isTemporary?: boolean;
  onToggleTemporary?: () => void;
}

// Shared chrome treatment for every header affordance — a small circular
// "floating" button that sits on the page background rather than inside a bar.
// Mirrors the Claude / Codex iOS chrome: chrome floats, content shows through.
// Button base already provides `inline-flex items-center justify-center`, so
// we don't repeat display utilities here — doing so would beat tailwind-merge
// when callers stack `hidden md:inline-flex` ahead of FLOAT_BUTTON and silently
// reveal mobile-hidden chrome.
const FLOAT_BUTTON =
  "glass-regular size-9 rounded-full p-0 text-muted-foreground transition-colors hover:bg-transparent hover:text-foreground aria-expanded:bg-transparent";

// Mobile drawer / menu kebab use a 44px target for thumb reach; on desktop
// they collapse so the 36px chrome controls take over.
const FLOAT_BUTTON_TOUCH =
  "glass-regular size-11 rounded-full p-0 text-muted-foreground transition-colors hover:bg-transparent hover:text-foreground aria-expanded:bg-transparent md:hidden";

export function AppHeader({
  title,
  subtitle,
  onNewChat,
  onOpenMobileNav,
  onOpenSidebar,
  sidebarOpen,
  onOpenSettings,
  isTemporary,
  onToggleTemporary,
}: AppHeaderProps) {
  return (
    <header
      // The parent chrome strip owns the safe-area-top padding and the z-index;
      // we handle the horizontal safe-area insets that the strip can't.
      className="relative flex h-11 shrink-0 items-center gap-2 pl-[max(env(safe-area-inset-left),0.75rem)] pr-[max(env(safe-area-inset-right),0.75rem)] sm:pl-[max(env(safe-area-inset-left),1rem)] sm:pr-[max(env(safe-area-inset-right),1rem)] md:h-16"
    >
      {/* LEFT cluster — drawer (mobile) and sidebar reopen (desktop, when collapsed). */}
      <div className="flex flex-1 items-center justify-start gap-2">
        <Button
          type="button"
          variant="ghost"
          aria-label="Open navigation"
          onClick={onOpenMobileNav}
          className={cn(FLOAT_BUTTON_TOUCH)}
        >
          <PanelLeft className="size-4" />
        </Button>
        {!sidebarOpen ? (
          <Button
            type="button"
            variant="ghost"
            aria-label="Open sidebar"
            onClick={onOpenSidebar}
            className={cn("hidden md:inline-flex", FLOAT_BUTTON)}
          >
            <PanelLeft className="size-4" />
          </Button>
        ) : null}
      </div>

      {/* CENTER — two-line title block, absolutely centered to the viewport so
          the number of side buttons never shifts the title off-axis.
          `pointer-events-none` lets clicks fall through to nothing (the title
          is not a control); inner text remains selectable for a11y tools.
          When the caller passes "New chat" we render "Olune" so the chrome
          reads as the app shell rather than restating the empty state. */}
      <div className="pointer-events-none absolute inset-x-0 top-0 flex h-11 flex-col items-center justify-center px-24 text-center md:h-16 md:px-44">
        <span className="block max-w-full truncate text-sm font-semibold leading-tight text-foreground">
          {title === "New chat" ? "Olune" : title}
        </span>
        {subtitle ? (
          <span className="block max-w-full truncate text-xs leading-tight text-muted-foreground">
            {subtitle}
          </span>
        ) : null}
      </div>

      {/* RIGHT cluster — desktop: temp chat + new chat + settings inline.
          Mobile: collapses to a single kebab overflow so the top-right has
          exactly one button. */}
      <div className="flex flex-1 items-center justify-end gap-2">
        {/* Temporary-chat: inline from md: up; collapsed into the overflow menu
            below md: so the right cluster doesn't crowd small viewports. */}
        <Button
          type="button"
          variant="ghost"
          aria-label="Temporary chat"
          aria-pressed={isTemporary}
          onClick={onToggleTemporary}
          className={cn(
            "hidden md:inline-flex",
            FLOAT_BUTTON,
            isTemporary && "text-foreground",
          )}
        >
          <Ghost className="size-4" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          aria-label="New chat"
          onClick={onNewChat}
          className={cn("hidden md:inline-flex", FLOAT_BUTTON)}
        >
          <Plus className="size-4" />
        </Button>
        {/* Settings: inline from md: up; in the overflow menu below md:. */}
        <Button
          type="button"
          variant="ghost"
          aria-label="Open settings"
          onClick={onOpenSettings}
          className={cn("hidden md:inline-flex", FLOAT_BUTTON)}
        >
          <Settings className="size-4" />
        </Button>
        {/* Mobile overflow: collapses new chat + temporary chat + settings into
            a single 44px kebab so the top-right has exactly one affordance. */}
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button
                type="button"
                variant="ghost"
                aria-label="More options"
                className={cn(FLOAT_BUTTON_TOUCH)}
              >
                <MoreVertical className="size-4" />
              </Button>
            }
          />
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuItem
              label="New chat"
              onClick={onNewChat}
              className="gap-2"
            >
              <Plus className="size-4" aria-hidden />
              <span>New chat</span>
            </DropdownMenuItem>
            <DropdownMenuItem
              label="Temporary chat"
              aria-pressed={isTemporary}
              onClick={onToggleTemporary}
              className="gap-2"
            >
              <Ghost className="size-4" aria-hidden />
              <span>Temporary chat</span>
            </DropdownMenuItem>
            <DropdownMenuItem
              label="Open settings"
              onClick={onOpenSettings}
              className="gap-2"
            >
              <Settings className="size-4" aria-hidden />
              <span>Settings</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
