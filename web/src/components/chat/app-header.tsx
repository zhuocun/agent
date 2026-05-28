"use client";

import { Ghost, PanelLeft, Plus, Settings } from "lucide-react";

import { Button } from "@/components/ui/button";
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
    <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-border px-3 sm:px-4">
      <div className="flex min-w-0 items-center gap-2">
        {/* Mobile: open the navigation drawer. */}
        <Button
          type="button"
          variant="ghost"
          aria-label="Open navigation"
          onClick={onOpenMobileNav}
          className="size-9 p-0 text-muted-foreground hover:text-foreground md:hidden"
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
        <Button
          type="button"
          variant="ghost"
          aria-label="Temporary chat"
          aria-pressed={isTemporary}
          onClick={onToggleTemporary}
          className={cn(
            "size-9 p-0 text-muted-foreground hover:text-foreground",
            isTemporary && "text-foreground",
          )}
        >
          <Ghost className="size-4" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          onClick={onNewChat}
          className="h-9 gap-1.5 px-2.5 text-sm"
        >
          <Plus className="size-4" />
          <span className="hidden sm:inline">New chat</span>
        </Button>
        <Button
          type="button"
          variant="ghost"
          aria-label="Open settings"
          onClick={onOpenSettings}
          className="size-9 p-0 text-muted-foreground hover:text-foreground"
        >
          <Settings className="size-4" />
        </Button>
        <ThemeToggle />
      </div>
    </header>
  );
}
