"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// Browser read-aloud (TTS) via the Web Speech `speechSynthesis` API. Like
// dictation this is ON-DEVICE — the browser/OS voice speaks the text locally,
// no provider is involved — so the UI labels it honestly and attaches no cost
// (D22 transparency spine). `SpeechSynthesis`/`SpeechSynthesisUtterance` ARE in
// the standard DOM lib, so no local type declarations are needed here.
//
// Beyond play/stop, the hook exposes read-aloud POLISH (T09): a speaking RATE
// (0.5×–2×) and a chosen VOICE drawn from `speechSynthesis.getVoices()`. Both
// preferences persist to localStorage so a user's pick survives reloads, and
// they're applied to every utterance.

const RATE_STORAGE_KEY = "olune.tts.rate";
const VOICE_STORAGE_KEY = "olune.tts.voiceURI";
export const MIN_RATE = 0.5;
export const MAX_RATE = 2;
const DEFAULT_RATE = 1;

export interface SpeechVoiceOption {
  voiceURI: string;
  name: string;
  lang: string;
  isDefault: boolean;
}

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
  // Speaking rate (0.5×–2×), persisted. `setRate` clamps to the valid range.
  rate: number;
  setRate: (rate: number) => void;
  // Available system voices and the user's chosen one (by `voiceURI`); null ⇒
  // the browser default. Persisted across reloads.
  voices: SpeechVoiceOption[];
  voiceURI: string | null;
  setVoiceURI: (voiceURI: string | null) => void;
}

function clampRate(rate: number): number {
  if (!Number.isFinite(rate)) return DEFAULT_RATE;
  return Math.min(MAX_RATE, Math.max(MIN_RATE, rate));
}

function readStoredRate(): number {
  if (typeof window === "undefined") return DEFAULT_RATE;
  try {
    const raw = window.localStorage.getItem(RATE_STORAGE_KEY);
    if (raw === null) return DEFAULT_RATE;
    return clampRate(Number.parseFloat(raw));
  } catch {
    return DEFAULT_RATE;
  }
}

function readStoredVoiceURI(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(VOICE_STORAGE_KEY);
  } catch {
    return null;
  }
}

function listVoices(): SpeechVoiceOption[] {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return [];
  return window.speechSynthesis.getVoices().map((voice) => ({
    voiceURI: voice.voiceURI,
    name: voice.name,
    lang: voice.lang,
    isDefault: voice.default,
  }));
}

export function useSpeechSynthesis(): UseSpeechSynthesisResult {
  // Lazy initializer feature-detects once at first render (SSR-safe: false when
  // there is no `window`), avoiding a bare setState in an effect. Read on the
  // client (this hook runs inside a `"use client"` tree) it is authoritative.
  const [supported] = useState(
    () => typeof window !== "undefined" && "speechSynthesis" in window,
  );
  const [speaking, setSpeaking] = useState(false);
  const [rate, setRateState] = useState<number>(readStoredRate);
  const [voiceURI, setVoiceURIState] = useState<string | null>(readStoredVoiceURI);
  const [voices, setVoices] = useState<SpeechVoiceOption[]>(listVoices);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  // Mirror the live rate/voice into refs so `speak` reads the latest without
  // being re-created on every preference change.
  const rateRef = useRef(rate);
  const voiceURIRef = useRef(voiceURI);
  useEffect(() => {
    rateRef.current = rate;
  }, [rate]);
  useEffect(() => {
    voiceURIRef.current = voiceURI;
  }, [voiceURI]);

  // Voices populate asynchronously in some browsers (Chrome fires
  // `voiceschanged` once the list is ready). Subscribe and refresh; setState
  // happens inside the event handler, never synchronously in the effect body.
  useEffect(() => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    const synth = window.speechSynthesis;
    const refresh = () => setVoices(listVoices());
    synth.addEventListener?.("voiceschanged", refresh);
    // Some engines need a nudge before they expose the list.
    refresh();
    return () => synth.removeEventListener?.("voiceschanged", refresh);
  }, []);

  const setRate = useCallback((next: number) => {
    const clamped = clampRate(next);
    setRateState(clamped);
    if (typeof window !== "undefined") {
      try {
        window.localStorage.setItem(RATE_STORAGE_KEY, String(clamped));
      } catch {
        // Storage disabled / full — the in-memory rate still applies.
      }
    }
  }, []);

  const setVoiceURI = useCallback((next: string | null) => {
    setVoiceURIState(next);
    if (typeof window !== "undefined") {
      try {
        if (next === null) {
          window.localStorage.removeItem(VOICE_STORAGE_KEY);
        } else {
          window.localStorage.setItem(VOICE_STORAGE_KEY, next);
        }
      } catch {
        // Best-effort persistence.
      }
    }
  }, []);

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

  const speak = useCallback((text: string) => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    const trimmed = text.trim();
    if (trimmed.length === 0) return;
    // Cancel any in-flight utterance first so voices never overlap.
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(trimmed);
    utterance.rate = clampRate(rateRef.current);
    // Apply the chosen voice when it's still present in the live list.
    const chosenUri = voiceURIRef.current;
    if (chosenUri) {
      const match = window.speechSynthesis
        .getVoices()
        .find((voice) => voice.voiceURI === chosenUri);
      if (match) utterance.voice = match;
    }
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
  }, []);

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

  return {
    supported,
    speaking,
    speak,
    cancel,
    toggle,
    rate,
    setRate,
    voices,
    voiceURI,
    setVoiceURI,
  };
}
