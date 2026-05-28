"use client";

import { Ghost, MoreVertical, PanelLeft, Plus, Settings } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ThemeToggle } from "@/components/chat/theme-toggle";
import { cn } from "@/lib/utils";

interface AppHeaderProps {
  title: string;
  onNewChat?: () => void;
  onOpenMobileNav?: () => void;
  onOpenSidebar?: () => void;
  sidebarOpen?: boolean;
  onOpenSettings?: () => void;
  isTemporary?: boolean;
  onToggleTemporary?: () => void;
}

export function AppHeader({
  title,
  onNewChat,
  onOpenMobileNav,
  onOpenSidebar,
  sidebarOpen,
  onOpenSettings,
  isTemporary,
  onToggleTemporary,
}: AppHeaderProps) {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-border px-3 pt-[env(safe-area-inset-top)] pl-[max(env(safe-area-inset-left),0.75rem)] pr-[max(env(safe-area-inset-right),0.75rem)] sm:px-4 sm:pl-[max(env(safe-area-inset-left),1rem)] sm:pr-[max(env(safe-area-inset-right),1rem)]">
      <div className="flex min-w-0 items-center gap-2">
        {/* Mobile: open the navigation drawer. 44px touch target on mobile. */}
        <Button
          type="button"
          variant="ghost"
          aria-label="Open navigation"
          onClick={onOpenMobileNav}
          className="size-11 p-0 text-muted-foreground hover:text-foreground md:hidden"
        >
          <PanelLeft className="size-4" />
        </Button>
        {/* Desktop: reopen the collapsed sidebar rail. */}
        {!sidebarOpen ? (
          <Button
            type="button"
            variant="ghost"
            aria-label="Open sidebar"
            onClick={onOpenSidebar}
            className="hidden size-9 p-0 text-muted-foreground hover:text-foreground md:inline-flex"
          >
            <PanelLeft className="size-4" />
          </Button>
        ) : null}
        {/* Brand: always on mobile; on desktop only when the sidebar is collapsed
            (the open sidebar already shows the wordmark). */}
        <div className={cn("flex items-center gap-2", sidebarOpen && "md:hidden")}>
          <div className="flex size-7 items-center justify-center rounded-lg bg-brand text-sm font-bold text-brand-foreground">
            A
          </div>
          <span className="text-sm font-semibold">Aperture</span>
        </div>
      </div>

      <div className="hidden min-w-0 flex-1 px-4 text-center sm:block">
        <span className="block truncate text-sm text-muted-foreground">
          {title}
        </span>
      </div>

      <div className="flex items-center gap-1">
        {/* Temporary-chat: inline from md: up; collapsed into the overflow menu
            below md: so four 44px controls don't crowd a 360px viewport. */}
        <Button
          type="button"
          variant="ghost"
          aria-label="Temporary chat"
          aria-pressed={isTemporary}
          onClick={onToggleTemporary}
          className={cn(
            "hidden size-9 p-0 text-muted-foreground hover:text-foreground md:inline-flex",
            isTemporary && "text-foreground",
          )}
        >
          <Ghost className="size-4" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          onClick={onNewChat}
          className="size-11 p-0 sm:h-9 sm:w-auto sm:gap-1.5 sm:px-2.5 sm:text-sm"
        >
          <Plus className="size-4" />
          <span className="hidden sm:inline">New chat</span>
        </Button>
        {/* Settings: inline from md: up; in the overflow menu below md:. */}
        <Button
          type="button"
          variant="ghost"
          aria-label="Open settings"
          onClick={onOpenSettings}
          className="hidden size-9 p-0 text-muted-foreground hover:text-foreground md:inline-flex"
        >
          <Settings className="size-4" />
        </Button>
        <ThemeToggle />

        {/* Mobile overflow: collapses temporary-chat + settings into a 44px
            kebab so each touch target stays ≥44px without overflow. */}
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button
                type="button"
                variant="ghost"
                aria-label="More options"
                className="size-11 p-0 text-muted-foreground hover:text-foreground md:hidden"
              >
                <MoreVertical className="size-4" />
              </Button>
            }
          />
          <DropdownMenuContent align="end" className="w-48">
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
