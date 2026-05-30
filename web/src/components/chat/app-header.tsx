"use client";

import { ClipboardCopy, Menu, MoreHorizontal, SquarePen } from "lucide-react";

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
  onCopyConversation?: () => void;
  canCopyConversation?: boolean;
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
  "glass-regular size-[45px] rounded-full p-0 text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground aria-expanded:bg-transparent";

const FLOAT_BUTTON_TOUCH =
  "glass-regular size-[45px] rounded-full p-0 text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground aria-expanded:bg-transparent md:hidden";

const PILL_HALF =
  "inline-flex h-[45px] w-[54px] select-none items-center justify-center rounded-full text-muted-foreground outline-none transition-[transform,background-color,color] duration-100 touch-manipulation hover:text-foreground hover:bg-foreground/5 focus-visible:ring-2 focus-visible:ring-ring active:not-aria-[haspopup]:scale-[0.97]";

export function AppHeader({
  onNewChat,
  onOpenMobileNav,
  onOpenSidebar,
  onOpenSettings,
  onToggleTemporary,
  onCopyConversation,
  canCopyConversation,
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
    <header className="relative flex h-[46px] shrink-0 items-center gap-2 pl-[max(env(safe-area-inset-left),1.25rem)] pr-[max(env(safe-area-inset-right),1.25rem)] sm:pl-[max(env(safe-area-inset-left),1.5rem)] sm:pr-[max(env(safe-area-inset-right),1.5rem)] md:h-16">
      <div className="flex flex-1 items-center justify-start gap-2">
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
        <div className="glass-regular inline-flex h-[45px] items-center rounded-full">
          <button
            type="button"
            aria-label="New chat"
            onClick={onNewChat}
            className={cn(PILL_HALF)}
          >
            <SquarePen className="size-[18px]" strokeWidth={2.25} />
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
