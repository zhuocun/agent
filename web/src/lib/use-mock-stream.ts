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

// The final, authoritative content delivered once the stream terminates.
export interface MockStreamResult {
  status: "done" | "stopped";
  reasoning: string;
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
//
// `onTerminal` fires exactly once per turn when it ends (done/stopped),
// carrying the final content from refs — so the consumer commits the message
// in a callback rather than watching status in an effect.
export function useMockStream(onTerminal?: (result: MockStreamResult) => void) {
  const [state, setState] = useState<MockStreamState>(INITIAL);

  const rafRef = useRef<number | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  const pendingRef = useRef("");
  const targetRef = useRef<"reasoning" | "answer">("reasoning");
  const stoppedRef = useRef(false);

  // Authoritative accumulators (refs so terminal handlers never read stale state).
  const reasoningRef = useRef("");
  const answerRef = useRef("");
  const durationRef = useRef(0);

  // Keep the latest callback without making start/stop depend on it.
  const onTerminalRef = useRef(onTerminal);
  useEffect(() => {
    onTerminalRef.current = onTerminal;
  }, [onTerminal]);

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

  const emitTerminal = useCallback((status: "done" | "stopped") => {
    onTerminalRef.current?.({
      status,
      reasoning: reasoningRef.current,
      reasoningDurationSec: durationRef.current,
      answer: answerRef.current,
    });
  }, []);

  // rAF flush loop — drains the buffer into the accumulator + state once per frame.
  const flushLoop = useCallback(() => {
    if (pendingRef.current) {
      const chunk = pendingRef.current;
      pendingRef.current = "";
      if (targetRef.current === "reasoning") {
        reasoningRef.current += chunk;
        const next = reasoningRef.current;
        setState((s) => ({ ...s, reasoning: next }));
      } else {
        answerRef.current += chunk;
        const next = answerRef.current;
        setState((s) => ({ ...s, answer: next }));
      }
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
      reasoningRef.current = "";
      answerRef.current = "";
      durationRef.current = 0;
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
            durationRef.current = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
            const dur = durationRef.current;
            targetRef.current = "answer";
            setState((s) => ({ ...s, reasoningStreaming: false, reasoningDurationSec: dur }));

            streamText(answer, () => {
              if (stoppedRef.current) return;
              timersRef.current.push(
                setTimeout(() => {
                  if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
                  rafRef.current = null;
                  setState((s) => ({ ...s, status: "done" }));
                  emitTerminal("done");
                }, 50),
              );
            });
          });
        }, 650),
      );
    },
    [clearAll, emitTerminal, flushLoop, streamText],
  );

  // Stop preserves partial output (PRD 01 §4.1): flush the buffer, freeze, mark stopped.
  const stop = useCallback(() => {
    if (stoppedRef.current) return;
    stoppedRef.current = true;
    const chunk = pendingRef.current;
    if (chunk) {
      if (targetRef.current === "reasoning") reasoningRef.current += chunk;
      else answerRef.current += chunk;
    }
    clearAll();
    const reasoning = reasoningRef.current;
    const answer = answerRef.current;
    setState((s) => ({
      ...s,
      reasoning,
      answer,
      status: "stopped",
      reasoningStreaming: false,
    }));
    emitTerminal("stopped");
  }, [clearAll, emitTerminal]);

  const reset = useCallback(() => {
    stoppedRef.current = true;
    clearAll();
    reasoningRef.current = "";
    answerRef.current = "";
    durationRef.current = 0;
    setState(INITIAL);
  }, [clearAll]);

  return { state, start, stop, reset };
}
