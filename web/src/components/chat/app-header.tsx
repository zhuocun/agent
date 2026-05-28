"use client";

import { PanelLeft, Plus, Settings } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface AppHeaderProps {
  onNewChat?: () => void;
  onOpenMobileNav?: () => void;
  onOpenSidebar?: () => void;
  sidebarOpen?: boolean;
  onOpenSettings?: () => void;
}

const FLOAT_BUTTON =
  "glass-regular size-9 rounded-full p-0 text-muted-foreground transition-colors hover:bg-transparent hover:text-foreground aria-expanded:bg-transparent";

const FLOAT_BUTTON_TOUCH =
  "glass-regular size-11 rounded-full p-0 text-muted-foreground transition-colors hover:bg-transparent hover:text-foreground aria-expanded:bg-transparent md:hidden";

export function AppHeader({
  onNewChat,
  onOpenMobileNav,
  onOpenSidebar,
  sidebarOpen,
  onOpenSettings,
}: AppHeaderProps) {
  return (
    <header className="relative flex h-11 shrink-0 items-center gap-2 pl-[max(env(safe-area-inset-left),0.75rem)] pr-[max(env(safe-area-inset-right),0.75rem)] sm:pl-[max(env(safe-area-inset-left),1rem)] sm:pr-[max(env(safe-area-inset-right),1rem)] md:h-16">
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

      <div className="flex flex-1 items-center justify-end gap-2">
        <Button
          type="button"
          variant="ghost"
          aria-label="New chat"
          onClick={onNewChat}
          className={cn(FLOAT_BUTTON)}
        >
          <Plus className="size-4" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          aria-label="Open settings"
          onClick={onOpenSettings}
          className={cn(FLOAT_BUTTON)}
        >
          <Settings className="size-4" />
        </Button>
      </div>
    </header>
  );
}
