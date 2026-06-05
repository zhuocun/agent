"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// Browser dictation (STT) via the Web Speech API. This is ON-DEVICE: the
// browser captures and transcribes audio locally (Chrome streams to Google's
// engine, Safari uses the OS engine) — NO provider in this app ever sees the
// audio. That distinction drives the honest "processed on your device by your
// browser" label in the composer (D22 transparency spine); we must NOT imply a
// served model or attach a cost to it.
//
// The standard TS DOM lib does not ship `SpeechRecognition` types (the spec is
// still a draft), so the minimal shapes we use are declared here rather than
// pulling in a dependency. Vendor-prefixed `webkitSpeechRecognition` is the
// implementation in Chromium/Safari; the unprefixed name is feature-detected
// first for forward-compat.

interface SpeechRecognitionAlternative {
  readonly transcript: string;
}

interface SpeechRecognitionResult {
  readonly isFinal: boolean;
  readonly length: number;
  item(index: number): SpeechRecognitionAlternative;
  [index: number]: SpeechRecognitionAlternative;
}

interface SpeechRecognitionResultList {
  readonly length: number;
  item(index: number): SpeechRecognitionResult;
  [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionEventLike extends Event {
  readonly resultIndex: number;
  readonly results: SpeechRecognitionResultList;
}

interface SpeechRecognitionErrorEventLike extends Event {
  readonly error: string;
}

interface SpeechRecognitionLike extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onend: ((event: Event) => void) | null;
  onstart: ((event: Event) => void) | null;
}

interface SpeechRecognitionConstructor {
  new (): SpeechRecognitionLike;
}

interface SpeechRecognitionWindow {
  SpeechRecognition?: SpeechRecognitionConstructor;
  webkitSpeechRecognition?: SpeechRecognitionConstructor;
}

function getRecognitionCtor(): SpeechRecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as SpeechRecognitionWindow;
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export interface UseSpeechRecognitionResult {
  // Whether the browser exposes the Web Speech recognition API at all. When
  // false the caller renders the mic control disabled with an explanatory
  // tooltip (graceful degradation — feature-detect, never assume).
  supported: boolean;
  // True between start() and the engine ending the session.
  listening: boolean;
  // Toggle dictation on/off. Idempotent per state: starting while listening is
  // a no-op; the keyboard shortcut and the button share this.
  toggle: () => void;
  start: () => void;
  stop: () => void;
}

/**
 * Drive on-device dictation. Each finalized result chunk is handed to
 * `onTranscript`; the caller appends it to the editable composer draft (the
 * transcript is NEVER auto-sent). Interim (non-final) results are ignored so
 * the draft only grows with stable text — appending interim chunks would
 * duplicate words as the engine revises them.
 */
export function useSpeechRecognition(
  onTranscript: (text: string) => void,
): UseSpeechRecognitionResult {
  // Lazy initializer feature-detects once at first render (SSR-safe: the ctor
  // getter returns null when there is no `window`), so we avoid a bare setState
  // in an effect. These hooks only run inside `"use client"` trees rendered
  // after bootstrap, so the client read is authoritative.
  const [supported] = useState(() => getRecognitionCtor() !== null);
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  // Keep the latest callback without re-creating the recognition instance.
  const onTranscriptRef = useRef(onTranscript);
  useEffect(() => {
    onTranscriptRef.current = onTranscript;
  }, [onTranscript]);

  // Tear the session down on unmount so a dangling recognition can't fire a
  // transcript into an unmounted tree.
  useEffect(() => {
    return () => {
      const recognition = recognitionRef.current;
      if (recognition) {
        recognition.onresult = null;
        recognition.onerror = null;
        recognition.onend = null;
        recognition.onstart = null;
        try {
          recognition.abort();
        } catch {
          // abort() throws if already stopped — safe to ignore on teardown.
        }
        recognitionRef.current = null;
      }
    };
  }, []);

  const stop = useCallback(() => {
    const recognition = recognitionRef.current;
    if (!recognition) return;
    try {
      recognition.stop();
    } catch {
      // stop() throws if the session already ended — the onend handler (or the
      // next start) reconciles state, so swallow it.
    }
  }, []);

  const start = useCallback(() => {
    if (recognitionRef.current) return; // already listening
    const Ctor = getRecognitionCtor();
    if (!Ctor) return;
    const recognition = new Ctor();
    // Use the page language so the engine picks a sensible model; continuous +
    // interim so a longer dictation streams in and we can append final chunks
    // as they settle.
    recognition.lang =
      typeof document !== "undefined" && document.documentElement.lang
        ? document.documentElement.lang
        : "en-US";
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onstart = () => setListening(true);
    recognition.onresult = (event) => {
      let finalChunk = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        if (result.isFinal) {
          finalChunk += result[0].transcript;
        }
      }
      const trimmed = finalChunk.trim();
      if (trimmed.length > 0) {
        onTranscriptRef.current(trimmed);
      }
    };
    recognition.onerror = () => {
      // Permission denied, no-speech, network, etc. End the session and reset
      // so the control returns to an idle, re-armable state rather than wedging.
      setListening(false);
      recognitionRef.current = null;
    };
    recognition.onend = () => {
      setListening(false);
      recognitionRef.current = null;
    };
    recognitionRef.current = recognition;
    try {
      recognition.start();
    } catch {
      // start() throws if invoked twice in quick succession; reset so the user
      // can retry.
      setListening(false);
      recognitionRef.current = null;
    }
  }, []);

  const toggle = useCallback(() => {
    if (recognitionRef.current) {
      stop();
    } else {
      start();
    }
  }, [start, stop]);

  return { supported, listening, toggle, start, stop };
}
