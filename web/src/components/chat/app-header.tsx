"use client";

import { Menu, MoreHorizontal, SquarePen } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ModelModePicker } from "@/components/chat/model-mode-picker";
import { cn } from "@/lib/utils";
import type {
  ModelTier,
  ModelTierId,
  ReasoningEffort,
  ReasoningEffortId,
} from "@/lib/types";

interface AppHeaderProps {
  onNewChat?: () => void;
  onOpenMobileNav?: () => void;
  onOpenSidebar?: () => void;
  onOpenSettings?: () => void;
  onToggleTemporary?: () => void;
  isTemporary?: boolean;
  sidebarOpen?: boolean;
  tiers: ModelTier[];
  selectedTierId: ModelTierId;
  onSelectTier: (id: ModelTierId) => void;
  efforts: ReasoningEffort[];
  selectedEffortId: ReasoningEffortId;
  onSelectEffort: (id: ReasoningEffortId) => void;
}

const FLOAT_BUTTON =
  "glass-regular size-11 rounded-full p-0 text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground aria-expanded:bg-transparent";

const FLOAT_BUTTON_TOUCH =
  "glass-regular size-11 rounded-full p-0 text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground aria-expanded:bg-transparent md:hidden";

const PILL_HALF =
  "inline-flex size-11 items-center justify-center rounded-full text-muted-foreground transition-colors outline-none hover:text-foreground hover:bg-foreground/5 focus-visible:ring-2 focus-visible:ring-ring";

export function AppHeader({
  onNewChat,
  onOpenMobileNav,
  onOpenSidebar,
  onOpenSettings,
  onToggleTemporary,
  isTemporary,
  sidebarOpen,
  tiers,
  selectedTierId,
  onSelectTier,
  efforts,
  selectedEffortId,
  onSelectEffort,
}: AppHeaderProps) {
  return (
    <header className="relative flex h-11 shrink-0 items-center gap-2 pl-[max(env(safe-area-inset-left),1rem)] pr-[max(env(safe-area-inset-right),1rem)] sm:pl-[max(env(safe-area-inset-left),1.25rem)] sm:pr-[max(env(safe-area-inset-right),1.25rem)] md:h-16">
      <div className="flex flex-1 items-center justify-start gap-2">
        <Button
          type="button"
          variant="ghost"
          aria-label="Open sidebar"
          onClick={onOpenMobileNav}
          className={cn(FLOAT_BUTTON_TOUCH)}
        >
          <Menu className="size-4" />
        </Button>
        {!sidebarOpen ? (
          <Button
            type="button"
            variant="ghost"
            aria-label="Open sidebar"
            onClick={onOpenSidebar}
            className={cn("hidden md:inline-flex", FLOAT_BUTTON)}
          >
            <Menu className="size-4" />
          </Button>
        ) : null}
        <ModelModePicker
          tiers={tiers}
          selectedTierId={selectedTierId}
          onSelectTier={onSelectTier}
          efforts={efforts}
          selectedEffortId={selectedEffortId}
          onSelectEffort={onSelectEffort}
        />
      </div>

      <div className="flex flex-1 items-center justify-end">
        <div className="glass-regular inline-flex h-11 items-center rounded-full">
          <button
            type="button"
            aria-label="New chat"
            onClick={onNewChat}
            className={cn(PILL_HALF)}
          >
            <SquarePen className="size-4" />
          </button>
          <span aria-hidden className="h-4 w-px bg-foreground/10" />
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <button
                  type="button"
                  aria-label="Chat menu"
                  className={cn(PILL_HALF)}
                >
                  <MoreHorizontal className="size-4" />
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
              <DropdownMenuItem onClick={onOpenSettings}>
                Settings
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </header>
  );
}
