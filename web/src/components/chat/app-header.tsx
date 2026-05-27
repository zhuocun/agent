"use client";

import { PanelLeft, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/chat/theme-toggle";

interface AppHeaderProps {
  title: string;
  onNewChat?: () => void;
}

export function AppHeader({ title, onNewChat }: AppHeaderProps) {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-border px-3 sm:px-4">
      <div className="flex min-w-0 items-center gap-2">
        <Button
          type="button"
          variant="ghost"
          aria-label="Toggle sidebar"
          className="size-9 p-0 text-muted-foreground hover:text-foreground md:hidden"
        >
          <PanelLeft className="size-4" />
        </Button>
        <div className="flex items-center gap-2">
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
          onClick={onNewChat}
          className="h-9 gap-1.5 px-2.5 text-sm"
        >
          <Plus className="size-4" />
          <span className="hidden sm:inline">New chat</span>
        </Button>
        <ThemeToggle />
      </div>
    </header>
  );
}
