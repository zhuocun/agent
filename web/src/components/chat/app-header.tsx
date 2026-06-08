"use client";

import {
  ClipboardCopy,
  Download,
  Menu,
  MoreHorizontal,
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
import { ModelModePicker } from "@/components/chat/model-mode-picker";
import { cn } from "@/lib/utils";
import type {
  ModelTier,
  ModelTierId,
  ProviderTierOption,
  ReasoningEffort,
  ReasoningEffortId,
} from "@/lib/types";

interface AppHeaderProps {
  onNewChat?: () => void;
  onOpenMobileNav?: () => void;
  onOpenSidebar?: () => void;
  onToggleTemporary?: () => void;
  onCopyConversation?: () => void;
  canCopyConversation?: boolean;
  onDownloadConversation?: () => void;
  canDownloadConversation?: boolean;
  onShareConversation?: () => void;
  // Sharing is only offered for a real, persisted (non-temporary) conversation
  // — the BE 404s on temporary chats and there's nothing to share before the
  // first turn lands a row.
  canShareConversation?: boolean;
  isTemporary?: boolean;
  sidebarOpen?: boolean;
  tiers: ModelTier[];
  selectedTierId: ModelTierId;
  onSelectTier: (id: ModelTierId) => void;
  providerOptions: ProviderTierOption[];
  selectedProviderId?: string;
  onSelectProvider: (id: string) => void;
  efforts: ReasoningEffort[];
  selectedEffortId: ReasoningEffortId;
  onSelectEffort: (id: ReasoningEffortId) => void;
  // False when the served provider ignores reasoning effort (e.g. Anthropic):
  // the picker disables the effort rows with a one-line note instead of erroring.
  effortSupported?: boolean;
  searchEnabled: boolean;
  onToggleSearch: (next: boolean) => void;
  jsonModeEnabled: boolean;
  onToggleJsonMode: (next: boolean) => void;
}

const FLOAT_BUTTON =
  "glass-regular size-[45px] rounded-full p-0 text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground aria-expanded:bg-transparent";

const FLOAT_BUTTON_TOUCH =
  "size-11 rounded-lg p-0 text-muted-foreground transition-colors hover:bg-foreground/5 hover:text-foreground active:bg-foreground/[0.06] aria-expanded:bg-transparent md:hidden";

const PILL_HALF =
  "inline-flex h-11 w-11 select-none items-center justify-center rounded-lg text-muted-foreground outline-none transition-[transform,background-color,color] duration-100 touch-manipulation hover:text-foreground hover:bg-foreground/5 focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none active:not-aria-[haspopup]:scale-[0.97] md:h-[45px] md:w-[54px] md:rounded-full";

export function AppHeader({
  onNewChat,
  onOpenMobileNav,
  onOpenSidebar,
  onToggleTemporary,
  onCopyConversation,
  canCopyConversation,
  onDownloadConversation,
  canDownloadConversation,
  onShareConversation,
  canShareConversation,
  isTemporary,
  sidebarOpen,
  tiers,
  selectedTierId,
  onSelectTier,
  providerOptions,
  selectedProviderId,
  onSelectProvider,
  efforts,
  selectedEffortId,
  onSelectEffort,
  effortSupported,
  searchEnabled,
  onToggleSearch,
  jsonModeEnabled,
  onToggleJsonMode,
}: AppHeaderProps) {
  return (
    <header className="relative flex h-11 shrink-0 items-center gap-2 pl-[max(env(safe-area-inset-left),1.25rem)] pr-[max(env(safe-area-inset-right),1.25rem)] sm:pl-[max(env(safe-area-inset-left),1.5rem)] sm:pr-[max(env(safe-area-inset-right),1.5rem)] md:h-16">
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
          providerOptions={providerOptions}
          selectedProviderId={selectedProviderId}
          onSelectProvider={onSelectProvider}
          efforts={efforts}
          selectedEffortId={selectedEffortId}
          onSelectEffort={onSelectEffort}
          effortSupported={effortSupported}
          searchEnabled={searchEnabled}
          onToggleSearch={onToggleSearch}
          jsonModeEnabled={jsonModeEnabled}
          onToggleJsonMode={onToggleJsonMode}
        />
      </div>

      <div className="flex flex-1 items-center justify-end">
        <div className="inline-flex h-11 items-center md:h-[45px] md:glass-regular md:rounded-full">
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
