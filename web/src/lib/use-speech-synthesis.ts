"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// Browser read-aloud (TTS) via the Web Speech `speechSynthesis` API. Like
// dictation this is ON-DEVICE — the browser/OS voice speaks the text locally,
// no provider is involved — so the UI labels it honestly and attaches no cost
// (D22 transparency spine). `SpeechSynthesis`/`SpeechSynthesisUtterance` ARE in
// the standard DOM lib, so no local type declarations are needed here.

export interface UseSpeechSynthesisResult {
  // Whether the browser exposes speechSynthesis. When false the read-aloud
  // control renders disabled with an explanatory tooltip (feature-detect).
  supported: boolean;
  // True while THIS hook instance is speaking (one utterance at a time).
  speaking: boolean;
  // Speak `text`. Cancels any in-flight utterance first so a second click on a
  // different message doesn't overlap two voices.
  speak: (text: string) => void;
  // Stop immediately.
  cancel: () => void;
  // Speak if idle, stop if currently speaking the SAME text — the play/stop
  // toggle the message read-aloud button binds to.
  toggle: (text: string) => void;
}

export function useSpeechSynthesis(): UseSpeechSynthesisResult {
  // Lazy initializer feature-detects once at first render (SSR-safe: false when
  // there is no `window`), avoiding a bare setState in an effect. Read on the
  // client (this hook runs inside a `"use client"` tree) it is authoritative.
  const [supported] = useState(
    () => typeof window !== "undefined" && "speechSynthesis" in window,
  );
  const [speaking, setSpeaking] = useState(false);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

  const cancel = useCallback(() => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    utteranceRef.current = null;
    setSpeaking(false);
  }, []);

  // Stop speaking if the tab is torn down — otherwise the OS keeps reading
  // after navigation in some browsers.
  useEffect(() => {
    return () => {
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  const speak = useCallback(
    (text: string) => {
      if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
      const trimmed = text.trim();
      if (trimmed.length === 0) return;
      // Cancel any in-flight utterance first so voices never overlap.
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(trimmed);
      utterance.onend = () => {
        if (utteranceRef.current === utterance) {
          utteranceRef.current = null;
          setSpeaking(false);
        }
      };
      utterance.onerror = () => {
        if (utteranceRef.current === utterance) {
          utteranceRef.current = null;
          setSpeaking(false);
        }
      };
      utteranceRef.current = utterance;
      setSpeaking(true);
      window.speechSynthesis.speak(utterance);
    },
    [],
  );

  const toggle = useCallback(
    (text: string) => {
      if (speaking) {
        cancel();
      } else {
        speak(text);
      }
    },
    [speaking, speak, cancel],
  );

  return { supported, speaking, speak, cancel, toggle };
}
