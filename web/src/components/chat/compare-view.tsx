"use client";

import {
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type Ref,
} from "react";

import { UserMessage } from "@/components/chat/user-message";
import {
  CompareColumn,
  type CompareColumnHandle,
} from "@/components/chat/compare-column";
import { TierPicker } from "@/components/chat/tier-picker";
import { cn } from "@/lib/utils";
import type { ChatMessage, ModelTier, ModelTierId } from "@/lib/types";

// Two-slot tier selector shown above the composer in compare mode. Reuses the
// existing single TierPicker twice (one per column), so the desktop dropdown /
// mobile bottom-sheet conventions come for free. The parent keeps the two
// slots distinct (handleSelectCompareTier swaps on collision).
export function CompareTierBar({
  tiers,
  compareTierIds,
  onSelect,
  disabled,
}: {
  tiers: ModelTier[];
  compareTierIds: [ModelTierId, ModelTierId];
  onSelect: (slot: 0 | 1, id: ModelTierId) => void;
  disabled?: boolean;
}) {
  return (
    <div
      className="mx-auto mb-2 flex w-full max-w-3xl items-center justify-center gap-2 px-4"
      data-testid="compare-tier-bar"
    >
      <span className="text-xs text-muted-foreground">Compare</span>
      <div data-testid="compare-slot-0">
        <TierPicker
          tiers={tiers}
          selectedId={compareTierIds[0]}
          onSelect={(id) => onSelect(0, id)}
          disabled={disabled}
        />
      </div>
      <span aria-hidden className="text-xs text-muted-foreground">
        vs
      </span>
      <div data-testid="compare-slot-1">
        <TierPicker
          tiers={tiers}
          selectedId={compareTierIds[1]}
          onSelect={(id) => onSelect(1, id)}
          disabled={disabled}
        />
      </div>
    </div>
  );
}

// One in-flight compare turn. `token` is a monotonically-increasing id minted
// per send so the fan-out effect fires exactly once per send (re-renders that
// don't change the token must not re-POST). `conversationId` is the SHARED
// temporary conversation every column POSTs to.
export interface CompareTurn {
  token: number;
  text: string;
  conversationId: string;
  // Per-column client message ids, minted at send-time so each parallel POST is
  // independently idempotent. Index-aligned with `tiers`.
  clientMessageIds: string[];
}

export interface CompareViewHandle {
  // Global Stop fans out to every column's own `stop()`.
  stopAll: () => void;
}

interface CompareViewProps {
  // The two (distinct) tiers being compared, in column order.
  tiers: ModelTier[];
  // The most-recent prompt bubble (mirrors the single-thread user bubble).
  userMessage: ChatMessage | null;
  // The active turn to fan out, or null before the first compare send.
  turn: CompareTurn | null;
  defaultReasoningOpen?: boolean;
  handleRef: Ref<CompareViewHandle>;
  // True while ANY column is still streaming — drives the composer's Stop
  // affordance in the parent.
  onStreamingChange?: (active: boolean) => void;
}

// The 2-up compare surface. Owns N CompareColumn instances (each with its own
// `useApiStream`), renders the shared user prompt above them, and fans a send
// out to every column when a new `turn` lands. Transient by construction — no
// conversation is persisted, so this never reconciles server ids or writes to
// the sidebar.
export function CompareView({
  tiers,
  userMessage,
  turn,
  defaultReasoningOpen = false,
  handleRef,
  onStreamingChange,
}: CompareViewProps) {
  // One handle per column, addressed by tier id so re-orders can't cross wires.
  const columnHandlesRef = useRef<Map<string, CompareColumnHandle | null>>(
    new Map(),
  );
  // The last turn token we fanned out — guards the effect against re-POSTing on
  // unrelated re-renders.
  const lastTokenRef = useRef<number | null>(null);
  // Mobile-only: which column's tab is showing. Desktop renders both side by
  // side and ignores this.
  const [activeTab, setActiveTab] = useState(0);
  // Per-column streaming flags, aggregated into the single up-reported boolean.
  const streamingByTierRef = useRef<Map<string, boolean>>(new Map());
  const onStreamingChangeRef = useRef(onStreamingChange);
  useEffect(() => {
    onStreamingChangeRef.current = onStreamingChange;
  }, [onStreamingChange]);

  const reportStreaming = useCallback(
    (tierId: string, streaming: boolean): void => {
      streamingByTierRef.current.set(tierId, streaming);
      const anyActive = Array.from(streamingByTierRef.current.values()).some(
        Boolean,
      );
      onStreamingChangeRef.current?.(anyActive);
    },
    [],
  );

  useImperativeHandle(
    handleRef,
    () => ({
      stopAll: () => {
        for (const handle of columnHandlesRef.current.values()) {
          handle?.stop();
        }
      },
    }),
    [],
  );

  // Fan-out: when a fresh turn lands, start() every column against the shared
  // temporary conversation with its own client message id. Runs once per token.
  useEffect(() => {
    if (!turn) return;
    if (lastTokenRef.current === turn.token) return;
    lastTokenRef.current = turn.token;
    tiers.forEach((tier, index) => {
      const handle = columnHandlesRef.current.get(tier.id);
      handle?.start({
        conversationId: turn.conversationId,
        clientMessageId:
          turn.clientMessageIds[index] ?? crypto.randomUUID(),
        text: turn.text,
      });
    });
  }, [turn, tiers]);

  return (
    <div
      className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4"
      data-testid="compare-view"
    >
      {userMessage ? <UserMessage message={userMessage} /> : null}

      {/* Mobile tab strip — desktop shows both columns at once, so the tabs are
          hidden at md:. Each tab swaps which single column is visible below. */}
      <div
        role="tablist"
        aria-label="Compare responses"
        className="flex gap-2 md:hidden"
      >
        {tiers.map((tier, index) => (
          <button
            key={tier.id}
            type="button"
            role="tab"
            id={`compare-tab-${tier.id}`}
            aria-selected={activeTab === index}
            aria-controls={`compare-panel-${tier.id}`}
            onClick={() => setActiveTab(index)}
            data-testid="compare-tab"
            className={cn(
              "min-h-9 flex-1 rounded-full px-3 text-sm font-medium transition-colors",
              activeTab === index
                ? "bg-foreground/[0.08] text-foreground"
                : "text-muted-foreground hover:bg-foreground/[0.04]",
            )}
          >
            {tier.label}
          </button>
        ))}
      </div>

      {/* Desktop: side-by-side grid. Mobile: a single column; the inactive
          column is hidden but stays MOUNTED so its stream keeps running in the
          background (switching tabs reveals its live/settled state). */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 md:gap-8">
        {tiers.map((tier, index) => (
          <div
            key={tier.id}
            role="tabpanel"
            id={`compare-panel-${tier.id}`}
            aria-labelledby={`compare-tab-${tier.id}`}
            className={cn(activeTab === index ? "block" : "hidden md:block")}
          >
            <CompareColumn
              tier={tier}
              position={index + 1}
              total={tiers.length}
              defaultReasoningOpen={defaultReasoningOpen}
              handleRef={(instance) => {
                if (instance) columnHandlesRef.current.set(tier.id, instance);
                else columnHandlesRef.current.delete(tier.id);
              }}
              onStreamingChange={reportStreaming}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
