"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { StreamStatus } from "@/lib/types";

export interface MockStreamState {
  status: StreamStatus;
  reasoning: string;
  reasoningStreaming: boolean;
  reasoningDurationSec: number;
  answer: string;
}

const INITIAL: MockStreamState = {
  status: "idle",
  reasoning: "",
  reasoningStreaming: false,
  reasoningDurationSec: 0,
  answer: "",
};

// Simulates a streamed assistant turn with the production rendering pattern
// (PRD 01 §5.4): tokens are buffered in a ref and flushed once per
// requestAnimationFrame rather than on every token, so the UI batches paints
// instead of thrashing setState. Reasoning streams first, then the answer.
export function useMockStream() {
  const [state, setState] = useState<MockStreamState>(INITIAL);

  const rafRef = useRef<number | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  const pendingRef = useRef("");
  const targetRef = useRef<"reasoning" | "answer">("reasoning");
  const stoppedRef = useRef(false);

  const clearAll = useCallback(() => {
    if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = null;
    timersRef.current.forEach(clearTimeout);
    timersRef.current = [];
    pendingRef.current = "";
  }, []);

  useEffect(() => () => clearAll(), [clearAll]);

  // rAF flush loop — drains the buffer into state at most once per frame.
  const flushLoop = useCallback(() => {
    if (pendingRef.current) {
      const chunk = pendingRef.current;
      pendingRef.current = "";
      setState((s) =>
        targetRef.current === "reasoning"
          ? { ...s, reasoning: s.reasoning + chunk }
          : { ...s, answer: s.answer + chunk },
      );
    }
    rafRef.current = requestAnimationFrame(flushLoop);
  }, []);

  const streamText = useCallback((text: string, onDone: () => void) => {
    const tokens = text.match(/\S+\s*/g) ?? [text];
    let i = 0;
    intervalRef.current = setInterval(() => {
      if (stoppedRef.current) return;
      const burst = 1 + (Math.random() < 0.4 ? 1 : 0);
      for (let k = 0; k < burst && i < tokens.length; k++, i++) {
        pendingRef.current += tokens[i];
      }
      if (i >= tokens.length) {
        if (intervalRef.current) clearInterval(intervalRef.current);
        intervalRef.current = null;
        timersRef.current.push(setTimeout(onDone, 70)); // let the last frame flush
      }
    }, 26);
  }, []);

  const start = useCallback(
    ({ reasoning, answer }: { reasoning: string; answer: string }) => {
      clearAll();
      stoppedRef.current = false;
      setState({ ...INITIAL, status: "submitted" });

      // Pre-first-token delay, then begin streaming reasoning.
      timersRef.current.push(
        setTimeout(() => {
          if (stoppedRef.current) return;
          targetRef.current = "reasoning";
          setState((s) => ({ ...s, status: "streaming", reasoningStreaming: true }));
          rafRef.current = requestAnimationFrame(flushLoop);

          const startedAt = Date.now();
          streamText(reasoning, () => {
            if (stoppedRef.current) return;
            const dur = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
            targetRef.current = "answer";
            setState((s) => ({
              ...s,
              reasoningStreaming: false,
              reasoningDurationSec: dur,
            }));

            streamText(answer, () => {
              if (stoppedRef.current) return;
              timersRef.current.push(
                setTimeout(() => {
                  if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
                  rafRef.current = null;
                  setState((s) => ({ ...s, status: "done" }));
                }, 50),
              );
            });
          });
        }, 650),
      );
    },
    [clearAll, flushLoop, streamText],
  );

  // Stop preserves partial output (PRD 01 §4.1): flush the buffer, freeze, mark stopped.
  const stop = useCallback(() => {
    stoppedRef.current = true;
    const chunk = pendingRef.current;
    clearAll();
    setState((s) => {
      const merged =
        targetRef.current === "reasoning"
          ? { ...s, reasoning: s.reasoning + chunk }
          : { ...s, answer: s.answer + chunk };
      return { ...merged, status: "stopped", reasoningStreaming: false };
    });
  }, [clearAll]);

  const reset = useCallback(() => {
    stoppedRef.current = true;
    clearAll();
    setState(INITIAL);
  }, [clearAll]);

  return { state, start, stop, reset };
}
