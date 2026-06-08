"use client";

import {
  forwardRef,
  useCallback,
  useEffect,
  useId,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ArrowUp,
  FileText,
  Image as ImageIcon,
  Library,
  LoaderCircle,
  Mic,
  Paperclip,
  Plus,
  Square,
  X,
} from "lucide-react";
import { Popover } from "@base-ui/react/popover";

import { Button } from "@/components/ui/button";
import { useIsMobileSheet } from "@/components/ui/dialog";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  SlashCommandsPopover,
  filterCommands,
} from "@/components/chat/slash-commands-popover";
import {
  TemplatePickerPopover,
  filterTemplates,
} from "@/components/chat/template-picker-popover";
import { MOCK_COMMANDS } from "@/lib/mock-data";
import { estimateTurnCost } from "@/lib/cost-estimate";
import { fetchPromptTemplates } from "@/lib/apiClient";
import { useSpeechRecognition } from "@/lib/use-speech-recognition";
import { haptic } from "@/lib/use-haptic";
import type {
  AttachmentPart,
  ModelTier,
  PromptTemplate,
  SlashCommand,
} from "@/lib/types";
import { cn } from "@/lib/utils";

const SLASH_PATTERN = /^\/(\w*)$/;

// Matches a `{{placeholder}}` token (the variable seam in a prompt template).
// Non-greedy so adjacent placeholders don't merge into one match.
const PLACEHOLDER_PATTERN = /\{\{.*?\}\}/;

// Where to park the cursor after inserting a template body: the START of the
// FIRST `{{…}}` placeholder so the user can type over it, or end-of-text when
// the body has no placeholders. Exported for unit coverage.
export function firstPlaceholderOffset(body: string): number {
  const match = body.match(PLACEHOLDER_PATTERN);
  return match?.index ?? body.length;
}

interface ComposerProps {
  isStreaming: boolean;
  onSend: (text: string, attachments: AttachmentPart[]) => void;
  onStop: () => void;
  sendOnEnter?: boolean;
  supportsAttachments?: boolean;
  // Whether the active tier can INTERPRET images. DISTINCT from
  // `supportsAttachments`: a tier may accept files (PDF/text as transcript)
  // without being multimodal. When attachments are supported but vision is not,
  // the composer auto-removes only IMAGE attachments (PDFs/text stay) with a
  // clear notice. Defaults to true so callers that don't pass it are unaffected.
  supportsVision?: boolean;
  // The provider-effective tier the next turn will use. When present (and not in
  // compare mode), the composer shows a muted pre-send cost/token estimate
  // computed from the live draft (Feature 2). Absent ⇒ no estimate line.
  // Compare mode is toggled from the command palette, not the composer.
  estimateTier?: ModelTier;
}

export interface ComposerHandle {
  setDraft: (text: string) => void;
  clearAttachments: (reason?: "unsupported" | "manual") => void;
  focus: () => void;
  // Toggle on-device dictation (STT). No-op when the browser lacks the Web
  // Speech recognition API. Lets the keyboard shortcut in chat-thread drive the
  // same control as the mic button.
  toggleDictation: () => void;
}

const MAX_HEIGHT = 200;
// Above this measured scrollHeight (px) the textarea is multi-line and the
// capsule drops its perfect pill for a large continuous radius. One line is
// ~44px (leading-7 + py-2); 60 leaves headroom so a single line never trips it.
const ONE_LINE_THRESHOLD = 60;
const STOP_SETTLE_MS = 600;
const MAX_ATTACHMENTS = 4;
const MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024;
const ACCEPTED_ATTACHMENT_TYPES =
  "image/*,application/pdf,text/*,.pdf,.txt,.md,.markdown,.csv,.json,.log";
const BUTTON_BASE =
  "inline-flex size-11 shrink-0 items-center justify-center rounded-full p-0 transition-[background-color,color,box-shadow] duration-300 ease-out";

function attachmentId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `att-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () =>
      reject(reader.error ?? new Error("Could not read file."));
    reader.onload = () => {
      if (typeof reader.result === "string") {
        resolve(reader.result);
      } else {
        reject(new Error("Could not read file."));
      }
    };
    reader.readAsDataURL(file);
  });
}

async function attachmentFromFile(file: File): Promise<AttachmentPart | null> {
  if (file.size <= 0) return null;
  if (file.size > MAX_ATTACHMENT_BYTES) return null;
  const name = file.name || "Attachment";
  const lowerName = name.toLowerCase();
  const pdf =
    file.type === "application/pdf" || name.toLowerCase().endsWith(".pdf");
  const image = file.type.startsWith("image/");
  const text =
    file.type.startsWith("text/") ||
    file.type === "application/json" ||
    file.type === "application/xml" ||
    [".txt", ".md", ".markdown", ".csv", ".json", ".log"].some((suffix) =>
      lowerName.endsWith(suffix),
    );
  if (!pdf && !image && !text) return null;
  const textMimeSupported =
    file.type.startsWith("text/") ||
    file.type === "application/json" ||
    file.type === "application/xml";
  const mimeType = pdf
    ? "application/pdf"
    : text && !textMimeSupported
      ? "text/plain"
      : file.type;
  const rawDataUrl = await readFileAsDataUrl(file);
  const encoded = rawDataUrl.split(",", 2)[1];
  if (!encoded) return null;
  return {
    type: "attachment",
    id: attachmentId(),
    name,
    mediaType: pdf ? "pdf" : image ? "image" : "text",
    mimeType,
    sizeBytes: file.size,
    storagePolicy: "transient",
    dataUrl: `data:${mimeType};base64,${encoded}`,
  };
}

function attachmentIconType(
  mediaType: AttachmentPart["mediaType"],
): "image" | "file" {
  return mediaType === "image" ? "image" : "file";
}

function formatAttachmentSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// USD formatter for the pre-send estimate — mirrors cost-breakdown.tsx's
// `formatUsd` (sub-cent figures get more decimals so a fractional-cent estimate
// doesn't collapse to "$0.00").
function formatEstimateUsd(n: number): string {
  if (n === 0) return "$0.00";
  const decimals = n < 0.01 ? 6 : n < 1 ? 4 : 2;
  return `$${n.toFixed(decimals)}`;
}

const estimateTokenFmt = new Intl.NumberFormat("en-US");

// Icon morph: both glyphs are stacked in a fixed-size box and cross-faded with
// a spring scale so a send↔stop swap reads as an iOS control morph rather than
// a hard cut. The active glyph sits at scale-100/opacity-100; the inactive one
// is absolutely positioned (zero layout shift) at scale-0.6/opacity-0.
//
// The button itself unmounts/remounts on the isStreaming toggle (the stop side
// is Tooltip-wrapped, the send side isn't), so a fresh icon would have no prior
// frame to transition from. We bridge that with a one-frame mount reveal: each
// MorphSendStopIcon mounts with both glyphs in the "incoming, pre-spring" pose
// and flips to the rest pose on the next rAF, so the spring fires on every
// swap. transform/opacity only (GPU-friendly). motion-reduce: collapses to a
// plain opacity swap with no scale/spring.
const MORPH_ICON_BASE =
  "absolute inset-0 flex items-center justify-center transition-[opacity,transform] duration-300 ease-ios-spring motion-reduce:transition-[opacity] motion-reduce:duration-150 motion-reduce:scale-100";

function MorphSendStopIcon({ isStreaming }: { isStreaming: boolean }) {
  // false until the frame after mount → drives the from→to spring on swap.
  const [settled, setSettled] = useState(false);
  useEffect(() => {
    const raf = requestAnimationFrame(() => setSettled(true));
    return () => cancelAnimationFrame(raf);
  }, []);

  // Resting target: the icon matching the current state is visible, the other
  // is shrunk away. Before `settled`, the visible icon is held in the shrunk
  // pre-spring pose so the first painted frame springs up to rest.
  const stopPose =
    settled && isStreaming ? "scale-100 opacity-100" : "scale-[0.6] opacity-0";
  const sendPose =
    settled && !isStreaming ? "scale-100 opacity-100" : "scale-[0.6] opacity-0";

  return (
    <span aria-hidden className="relative block size-4">
      <span className={cn(MORPH_ICON_BASE, stopPose)}>
        <Square className="size-4 fill-current" />
      </span>
      <span className={cn(MORPH_ICON_BASE, sendPose)}>
        <ArrowUp className="size-4" />
      </span>
    </span>
  );
}

export const Composer = forwardRef<ComposerHandle, ComposerProps>(
  function Composer(
    {
      isStreaming,
      onSend,
      onStop,
      sendOnEnter = true,
      supportsAttachments = false,
      supportsVision = true,
      estimateTier,
    },
    forwardedRef,
  ) {
    const [value, setValue] = useState("");
    const [attachments, setAttachments] = useState<AttachmentPart[]>([]);
    const [pendingAttachmentReads, setPendingAttachmentReads] = useState(0);
    const [attachmentNotice, setAttachmentNotice] = useState<string | null>(
      null,
    );
    const [justStopped, setJustStopped] = useState(false);
    // True once the textarea has grown past a single line. A perfect 9999px pill
    // looks wrong at 4–6 lines, so the capsule swaps to a large continuous radius
    // when grown (see the render). Derived from the measured scrollHeight in
    // autoGrow, the same place we set the height, so the two never disagree.
    const [grown, setGrown] = useState(false);
    const [slashSelectedIndex, setSlashSelectedIndex] = useState(0);
    // When the user explicitly dismisses with Escape, suppress the popover until
    // the slash token disappears (e.g. user backspaces out or types past it),
    // then arm again on the next fresh "/…" token.
    const [slashDismissed, setSlashDismissed] = useState(false);
    const ref = useRef<HTMLTextAreaElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    // Anchor for the popover's outside-click guard — clicks anywhere on the
    // composer surface (textarea, send button) must NOT dismiss the popover.
    const capsuleRef = useRef<HTMLDivElement>(null);
    // Tracks the previous value so updateValue can detect transitions — namely a
    // "fresh slash" (prev didn't start with "/", new does) which re-arms the
    // popover even when the user has dismissed an earlier token with Escape.
    const prevValueRef = useRef("");
    const slashListboxId = useId();
    const slashOptionPrefix = useId();
    // Prompt library (D23) — a SIBLING popover layer to the slash commands,
    // opened from a toolbar button (NOT the "/" token), so it never touches the
    // load-bearing slash send/stop/Enter handling. Selecting a template prefills
    // the composer with its body (pure prefill — no model/cost change).
    const [templatePickerOpen, setTemplatePickerOpen] = useState(false);
    const [templates, setTemplates] = useState<PromptTemplate[]>([]);
    // `templatesLoaded` flips true after the first fetch settles so the picker
    // can distinguish "loading" from "genuinely empty". The fetch is lazy: it
    // fires the first time the picker opens, then the result is cached in state.
    const [templatesLoaded, setTemplatesLoaded] = useState(false);
    const [templateSelectedIndex, setTemplateSelectedIndex] = useState(0);
    const templateListboxId = useId();
    const templateOptionPrefix = useId();
    // Disclosure for the secondary-control cluster (Attach / Templates /
    // Dictate). The cluster ALWAYS lives behind this "More actions" ("+")
    // popover — in BOTH the empty/at-rest and composing states — so this open
    // state drives the disclosure in every state (there is no inline-at-rest
    // path any more).
    const [moreActionsOpen, setMoreActionsOpen] = useState(false);
    // Below the `sm` breakpoint we still anchor the same popover used on
    // desktop — a full bottom sheet for three rows is over-weight, and the
    // popover keeps the disclosure cheap enough that the most-used controls
    // (attach, dictate) can stay INLINE in the toolbar instead of one tap
    // behind a sheet. The flag drives those mobile-inline promotions, not the
    // disclosure surface itself.
    const isMobile = useIsMobileSheet();
    const prevStreamingRef = useRef(isStreaming);
    const supportsAttachmentsRef = useRef(supportsAttachments);
    const supportsVisionRef = useRef(supportsVision);
    const attachmentReadGenerationRef = useRef(0);

    const clearAttachments = useCallback(
      (reason: "unsupported" | "manual" = "manual") => {
        attachmentReadGenerationRef.current += 1;
        setAttachments([]);
        setPendingAttachmentReads(0);
        setAttachmentNotice(
          reason === "unsupported"
            ? "Attachments were removed because the current model does not support files."
            : null,
        );
        if (fileInputRef.current) fileInputRef.current.value = "";
      },
      [],
    );

    useEffect(() => {
      supportsAttachmentsRef.current = supportsAttachments;
      if (supportsAttachments) return;
      attachmentReadGenerationRef.current += 1;
      if (fileInputRef.current) fileInputRef.current.value = "";
      window.setTimeout(() => {
        setAttachments((current) => {
          if (current.length > 0) {
            setAttachmentNotice(
              "Attachments were removed because the current model does not support files.",
            );
          }
          return [];
        });
        setPendingAttachmentReads((current) => {
          if (current > 0) {
            setAttachmentNotice(
              "Attachments were removed because the current model does not support files.",
            );
          }
          return 0;
        });
      }, 0);
    }, [supportsAttachments]);

    // Vision gate, parallel to the attachments gate above but narrower: when the
    // active tier accepts files yet can't INTERPRET images (e.g. DeepSeek), drop
    // only the IMAGE attachments and keep PDFs/text. When the tier supports no
    // attachments at all the effect above already cleared everything, so this only
    // matters for attachment-capable-but-non-vision tiers.
    useEffect(() => {
      supportsVisionRef.current = supportsVision;
      if (supportsVision || !supportsAttachments) return;
      window.setTimeout(() => {
        setAttachments((current) => {
          if (!current.some((attachment) => attachment.mediaType === "image")) {
            return current;
          }
          setAttachmentNotice(
            "Images aren't supported by this model and were removed.",
          );
          return current.filter(
            (attachment) => attachment.mediaType !== "image",
          );
        });
      }, 0);
    }, [supportsVision, supportsAttachments]);

    // Stop→Send settling pose: after a stream ends, hold the slot in a quiet
    // neutral state for a beat before reverting to rest, so the transition reads
    // as a single choreographed moment rather than an instant snap.
    useEffect(() => {
      const wasStreaming = prevStreamingRef.current;
      prevStreamingRef.current = isStreaming;
      if (wasStreaming && !isStreaming) {
        setJustStopped(true);
        const t = window.setTimeout(
          () => setJustStopped(false),
          STOP_SETTLE_MS,
        );
        return () => window.clearTimeout(t);
      }
    }, [isStreaming]);

    const slashMatch = value.match(SLASH_PATTERN);
    const slashQuery = slashMatch ? slashMatch[1] : "";
    const slashActive = slashMatch !== null && !slashDismissed;
    const filteredCommands = useMemo(
      () => (slashActive ? filterCommands(MOCK_COMMANDS, slashQuery) : []),
      [slashActive, slashQuery],
    );
    const slashOpen = slashActive;
    const slashHighlightIndex =
      filteredCommands.length === 0
        ? -1
        : Math.min(
            Math.max(slashSelectedIndex, 0),
            filteredCommands.length - 1,
          );
    const slashActiveOptionId =
      slashOpen && slashHighlightIndex >= 0
        ? `${slashOptionPrefix}-${slashHighlightIndex}`
        : undefined;

    // Template picker is opened from the toolbar button (not a text token), so it
    // lists the full library (empty query). `filterTemplates` is still applied so
    // the pure filter stays the single source of truth for both render + keynav.
    const filteredTemplates = useMemo(
      () => (templatePickerOpen ? filterTemplates(templates, "") : []),
      [templatePickerOpen, templates],
    );
    const templateHighlightIndex =
      filteredTemplates.length === 0
        ? -1
        : Math.min(
            Math.max(templateSelectedIndex, 0),
            filteredTemplates.length - 1,
          );

    const autoGrow = () => {
      const ta = ref.current;
      if (!ta) return;
      ta.style.height = "auto";
      const scrollHeight = ta.scrollHeight;
      ta.style.height = `${Math.min(scrollHeight, MAX_HEIGHT)}px`;
      // One line (leading-7 = 28px + py-2 = 16px) measures ~44px; anything past a
      // comfortable margin above that is multi-line, so flip to the large
      // continuous radius. The threshold sits above one line so a single wrapped
      // glyph or descender jitter can't toggle the radius mid-type.
      setGrown(scrollHeight > ONE_LINE_THRESHOLD);
    };

    const updateValue = (next: string) => {
      const prev = prevValueRef.current;
      prevValueRef.current = next;
      setValue(next);
      // A fresh keystroke that produces non-empty content cancels the post-stop
      // settling pose so the send slot can go brand-armed immediately (visual +
      // behavior together).
      if (next.trim().length > 0 && justStopped) {
        setJustStopped(false);
      }
      if (next.match(SLASH_PATTERN)) {
        // Reset highlight on every filter change so the first row stays selected.
        setSlashSelectedIndex(0);
        // Fresh-slash re-arm: if the prior value did NOT start with "/" and the
        // new one does, treat this as a brand-new slash session and clear any
        // earlier Escape dismissal. This covers the flow: type "/foo" → Esc →
        // backspace through to "" → type "/" again. (Backspacing within the
        // same slash token — e.g. "/foo" → "/fo" — preserves dismissal.)
        if (slashDismissed && !prev.startsWith("/") && next.startsWith("/")) {
          setSlashDismissed(false);
        }
      } else {
        // Token no longer present → re-arm the popover for the next "/…".
        if (slashDismissed) setSlashDismissed(false);
        setSlashSelectedIndex(0);
      }
    };

    const pickCommand = (command: SlashCommand) => {
      const next = command.prompt;
      prevValueRef.current = next;
      setValue(next);
      setSlashDismissed(false);
      setSlashSelectedIndex(0);
      const ta = ref.current;
      if (ta) {
        ta.focus();
        requestAnimationFrame(() => {
          const ta2 = ref.current;
          if (!ta2) return;
          const end = next.length;
          ta2.setSelectionRange(end, end);
          autoGrow();
        });
      }
    };

    // Lazily load the user's prompt templates the first time the picker opens,
    // then cache the result in state (re-opens reuse it). Caller-scoped + anon-
    // allowed on the BE; a fetch error degrades to an empty list (the picker
    // shows its empty-state hint).
    const openTemplatePicker = useCallback(() => {
      setTemplateSelectedIndex(0);
      setTemplatePickerOpen((alreadyOpen) => !alreadyOpen);
    }, []);

    useEffect(() => {
      if (!templatePickerOpen || templatesLoaded) return;
      const controller = new AbortController();
      let cancelled = false;
      void (async () => {
        try {
          const rows = await fetchPromptTemplates(controller.signal);
          if (cancelled) return;
          setTemplates(rows);
        } catch {
          if (cancelled) return;
          // Leave `templates` empty; the picker renders the empty-state hint.
        } finally {
          if (!cancelled) setTemplatesLoaded(true);
        }
      })();
      return () => {
        cancelled = true;
        controller.abort();
      };
    }, [templatePickerOpen, templatesLoaded]);

    // Insert a chosen template's body into the composer (pure prefill — no
    // model/cost/provider change). Mirrors `pickCommand`'s focus + rAF
    // selection, but parks the cursor on the FIRST `{{…}}` placeholder (or
    // end-of-text when the body has none) so the user types straight into the
    // first variable.
    const pickTemplate = (template: PromptTemplate) => {
      const next = template.body;
      prevValueRef.current = next;
      setValue(next);
      setTemplatePickerOpen(false);
      setTemplateSelectedIndex(0);
      // A template body is never a "/…" token in practice, but keep the slash
      // popover armed-state coherent with the new draft.
      setSlashDismissed(false);
      setSlashSelectedIndex(0);
      const ta = ref.current;
      if (ta) {
        ta.focus();
        requestAnimationFrame(() => {
          const ta2 = ref.current;
          if (!ta2) return;
          const caret = firstPlaceholderOffset(next);
          ta2.setSelectionRange(caret, caret);
          autoGrow();
        });
      }
    };

    // Dictation (STT) writes each finalized transcript chunk into the composer
    // draft via the SAME state path as typing, so the result is fully EDITABLE and
    // is NEVER auto-sent. We append (with a single separating space) rather than
    // replace, so a user can dictate, tweak, dictate again. After writing we grow
    // the textarea and keep the caret at the end.
    const appendDictation = useCallback((chunk: string) => {
      setValue((current) => {
        const needsSpace = current.length > 0 && !/\s$/.test(current);
        const next = needsSpace ? `${current} ${chunk}` : `${current}${chunk}`;
        prevValueRef.current = next;
        return next;
      });
      requestAnimationFrame(() => {
        const ta = ref.current;
        if (!ta) return;
        ta.style.height = "auto";
        const scrollHeight = ta.scrollHeight;
        ta.style.height = `${Math.min(scrollHeight, MAX_HEIGHT)}px`;
        setGrown(scrollHeight > ONE_LINE_THRESHOLD);
        const end = ta.value.length;
        ta.setSelectionRange(end, end);
      });
    }, []);
    const dictation = useSpeechRecognition(appendDictation);

    useImperativeHandle(forwardedRef, () => ({
      setDraft: (text: string) => {
        prevValueRef.current = text;
        setValue(text);
        // A parent setting a draft (e.g. inserting "/something") is an explicit
        // re-arm: the popover should open if the new draft is a slash token.
        setSlashDismissed(false);
        setSlashSelectedIndex(0);
        const ta = ref.current;
        if (ta) {
          ta.focus();
          requestAnimationFrame(autoGrow);
        }
      },
      clearAttachments,
      focus: () => {
        ref.current?.focus();
      },
      toggleDictation: () => {
        dictation.toggle();
      },
    }));

    const submit = () => {
      const text = value.trim();
      if ((text.length === 0 && attachments.length === 0) || isStreaming)
        return;
      if (pendingAttachmentReads > 0) return;
      if (attachments.length > 0 && !supportsAttachments) return;
      haptic("selection");
      onSend(text, attachments);
      prevValueRef.current = "";
      setValue("");
      setAttachments([]);
      setAttachmentNotice(null);
      // The textarea collapses back to one line on send, so drop the grown radius
      // in lockstep — otherwise the empty pill would briefly keep its large
      // multi-line corners.
      setGrown(false);
      requestAnimationFrame(() => {
        if (ref.current) ref.current.style.height = "auto";
      });
    };

    const onPickFiles = (files: FileList | null) => {
      if (!files || files.length === 0) return;
      if (!supportsAttachmentsRef.current) {
        setAttachmentNotice("The current model does not support files.");
        if (fileInputRef.current) fileInputRef.current.value = "";
        return;
      }
      const slots = Math.max(
        0,
        MAX_ATTACHMENTS - attachments.length - pendingAttachmentReads,
      );
      const allSelected = Array.from(files);
      const selected = allSelected.slice(0, slots);
      if (fileInputRef.current) fileInputRef.current.value = "";
      if (selected.length === 0) {
        setAttachmentNotice(`Attach at most ${MAX_ATTACHMENTS} files.`);
        return;
      }
      if (allSelected.length > selected.length) {
        setAttachmentNotice(`Attach at most ${MAX_ATTACHMENTS} files.`);
      } else {
        setAttachmentNotice(null);
      }
      const generation = attachmentReadGenerationRef.current;
      setPendingAttachmentReads((current) => current + selected.length);
      void Promise.all(
        selected.map((file) =>
          supportsAttachmentsRef.current
            ? attachmentFromFile(file).catch(() => null)
            : Promise.resolve(null),
        ),
      )
        .then((picked) => {
          if (attachmentReadGenerationRef.current !== generation) return;
          if (!supportsAttachmentsRef.current) return;
          setAttachments((current) => {
            const availableSlots = Math.max(
              0,
              MAX_ATTACHMENTS - current.length,
            );
            let next = picked.filter(
              (attachment): attachment is AttachmentPart => attachment !== null,
            );
            if (next.length < picked.length) {
              setAttachmentNotice(
                `Only images, PDFs, and text files up to ${formatAttachmentSize(
                  MAX_ATTACHMENT_BYTES,
                )} can be attached.`,
              );
            }
            // Non-vision tier: accept files but drop images (PDFs/text stay).
            if (!supportsVisionRef.current) {
              const withoutImages = next.filter(
                (attachment) => attachment.mediaType !== "image",
              );
              if (withoutImages.length < next.length) {
                setAttachmentNotice(
                  "Images aren't supported by this model and were removed.",
                );
              }
              next = withoutImages;
            }
            return [...current, ...next.slice(0, availableSlots)];
          });
        })
        .finally(() => {
          if (attachmentReadGenerationRef.current !== generation) return;
          setPendingAttachmentReads((current) =>
            Math.max(0, current - selected.length),
          );
        });
    };

    const removeAttachment = (id: string) => {
      setAttachments((current) =>
        current.filter((attachment) => attachment.id !== id),
      );
      setAttachmentNotice(null);
    };

    const attachedSendBlocked = attachments.length > 0 && !supportsAttachments;
    const attachmentReadPending = pendingAttachmentReads > 0;
    const canSubmit =
      (value.trim().length > 0 || attachments.length > 0) &&
      !attachedSendBlocked &&
      !attachmentReadPending;

    // Quiet-down disclosure (00-principles.md:9, 02-patterns.md:158-164): the
    // secondary cluster (Attach / Templates / Dictate) lives behind a single
    // "More actions" ("+") disclosure so a focused desktop composer reads as
    // `[+] [textarea] [Send]`. On mobile we promote the two most-used controls
    // back inline: typing on a phone, the cost of one extra tap to reach
    // Attach / Dictate is bigger than the benefit of a leaner toolbar, so the
    // mobile composer reads as `[Attach] [Dictate] [+] [textarea] [Send]`
    // (with controls only present when their preconditions are met). Templates
    // and parity-Attach still live in the popover so testids remain reachable
    // through `composer-more-actions` on every viewport.
    //
    // Inline rules:
    //   - Attach inline when supportsAttachments AND mobile.
    //   - Dictate inline when (a) dictation is supported AND mobile, OR (b) a
    //     recording is ACTIVE on any viewport — an active recording must stay
    //     one tap from stop, never folded behind a disclosure.
    const keepAttachInline = isMobile && supportsAttachments;
    const keepDictateInline =
      dictation.listening || (isMobile && dictation.supported);
    // Whether the disclosure has anything left to host. Templates is always
    // present (caller-scoped, anon-allowed), so the popover is effectively
    // always available; Attach is also kept in the popover for parity even
    // when it's promoted inline on mobile.
    const hasCollapsibleControls = true;

    // ---- Secondary-control renderers ---------------------------------------
    // Each control is rendered inside the "More actions" disclosure popover (its
    // single home in both the empty/at-rest and composing states), preserving its
    // exact data-testid + aria contract. The lone exception is the dictate
    // control, which is also rendered inline while a recording is ACTIVE (see
    // `keepDictateInline`) so it stays one tap from stop. The labelled rows in the
    // popover relax the rounded-pill icon button into a full-width labelled row.
    const attachButton = (
      <Button
        type="button"
        variant="ghost"
        onClick={() => {
          fileInputRef.current?.click();
          setMoreActionsOpen(false);
        }}
        disabled={isStreaming}
        aria-label="Attach file"
        className="size-11 shrink-0 rounded-full p-0 text-muted-foreground hover:text-foreground"
      >
        <Paperclip className="size-4" />
      </Button>
    );

    const templatesButton = (
      <Button
        type="button"
        variant="ghost"
        onClick={openTemplatePicker}
        // Disabled mid-stream (parity with attach/dictation). The brand
        // tint gives sighted users the same "open" signal aria-pressed
        // conveys to AT.
        disabled={isStreaming}
        aria-pressed={templatePickerOpen}
        aria-haspopup="listbox"
        aria-label="Insert a prompt template"
        data-testid="composer-templates"
        className={cn(
          "size-11 shrink-0 rounded-full p-0",
          templatePickerOpen
            ? "text-brand hover:text-brand"
            : "text-muted-foreground hover:text-foreground",
        )}
      >
        <Library className="size-4" />
      </Button>
    );

    const dictateButton = (
      <Button
        type="button"
        variant="ghost"
        onClick={() => dictation.toggle()}
        // Feature-detect: when the browser lacks the Web Speech
        // recognition API the control is disabled and the tooltip
        // explains why. Also disabled mid-stream (parity with attach).
        disabled={!dictation.supported || isStreaming}
        // aria-pressed conveys the recording state to AT; the brand tint
        // gives the same "on" signal to sighted users.
        aria-pressed={dictation.listening}
        aria-label={
          !dictation.supported
            ? "Dictation not supported in this browser"
            : dictation.listening
              ? "Stop dictation"
              : "Start dictation"
        }
        data-testid="composer-dictate"
        className={cn(
          "size-11 shrink-0 rounded-full p-0",
          dictation.listening
            ? "text-brand hover:text-brand"
            : "text-muted-foreground hover:text-foreground",
        )}
      >
        <Mic
          className={cn(
            "size-4",
            dictation.listening && "motion-safe:animate-pulse-soft",
          )}
        />
      </Button>
    );

    // Pre-send cost/token estimate (Feature 2). Recomputed as the draft + the
    // selected tier change. Only shown once there's something to estimate; the
    // tier object carries the (bootstrap-supplied) per-M list prices. `usd` is
    // null for Auto / unpriced tiers — we then show "estimate unavailable for
    // Auto" rather than a misleading "$0.00".
    const costEstimate = useMemo(() => {
      if (!estimateTier) return null;
      const trimmed = value.trim();
      if (trimmed.length === 0 && attachments.length === 0) return null;
      return estimateTurnCost({
        text: trimmed,
        attachments,
        tier: estimateTier,
      });
    }, [estimateTier, value, attachments]);

    const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      // IME-safe: leave Esc/Enter to the composition layer (CJK).
      if (e.nativeEvent.isComposing || e.keyCode === 229) return;
      // Template-picker layer runs FIRST and only when the picker is open. Each
      // branch returns, so when the picker is closed none of the slash / stream-
      // stop / send invariants below are touched. Opened from a toolbar button
      // (not a text token), so it never interacts with the "/" branch.
      if (templatePickerOpen) {
        if (e.key === "Escape") {
          e.preventDefault();
          setTemplatePickerOpen(false);
          setTemplateSelectedIndex(0);
          return;
        }
        if (filteredTemplates.length > 0) {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setTemplateSelectedIndex(
              (templateHighlightIndex + 1) % filteredTemplates.length,
            );
            return;
          }
          if (e.key === "ArrowUp") {
            e.preventDefault();
            setTemplateSelectedIndex(
              (templateHighlightIndex - 1 + filteredTemplates.length) %
                filteredTemplates.length,
            );
            return;
          }
          if (
            (e.key === "Enter" && !e.shiftKey) ||
            (e.key === "Tab" && !e.shiftKey)
          ) {
            if (templateHighlightIndex >= 0) {
              e.preventDefault();
              const picked = filteredTemplates[templateHighlightIndex];
              if (picked) pickTemplate(picked);
              return;
            }
          }
        }
      }
      // Slash-command layer runs first so Escape closes the popover (not the
      // stream) and Enter/Tab can pick a highlighted command before falling
      // through to the send path.
      if (slashOpen) {
        if (e.key === "Escape") {
          e.preventDefault();
          setSlashDismissed(true);
          setSlashSelectedIndex(0);
          return;
        }
        if (filteredCommands.length > 0) {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setSlashSelectedIndex(
              (slashHighlightIndex + 1) % filteredCommands.length,
            );
            return;
          }
          if (e.key === "ArrowUp") {
            e.preventDefault();
            setSlashSelectedIndex(
              (slashHighlightIndex - 1 + filteredCommands.length) %
                filteredCommands.length,
            );
            return;
          }
          if (e.key === "Tab" && !e.shiftKey && slashHighlightIndex >= 0) {
            e.preventDefault();
            const picked = filteredCommands[slashHighlightIndex];
            if (picked) pickCommand(picked);
            return;
          }
          if (
            e.key === "Enter" &&
            !e.shiftKey &&
            sendOnEnter &&
            slashHighlightIndex >= 0
          ) {
            e.preventDefault();
            const picked = filteredCommands[slashHighlightIndex];
            if (picked) pickCommand(picked);
            return;
          }
        }
      }
      if (e.key === "Escape" && isStreaming) {
        e.preventDefault();
        onStop();
        return;
      }
      if (sendOnEnter) {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          submit();
        }
      } else {
        if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
          e.preventDefault();
          submit();
        }
      }
    };

    return (
      <div className="group/composer relative mx-auto w-full max-w-3xl px-4 pt-1">
        <SlashCommandsPopover
          open={slashOpen}
          commands={MOCK_COMMANDS}
          query={slashQuery}
          selectedIndex={slashHighlightIndex}
          onSelectedIndexChange={setSlashSelectedIndex}
          onPick={pickCommand}
          onClose={() => setSlashDismissed(true)}
          listboxId={slashListboxId}
          optionIdPrefix={slashOptionPrefix}
          anchorRef={capsuleRef}
        />
        <TemplatePickerPopover
          open={templatePickerOpen}
          items={filteredTemplates}
          query=""
          selectedIndex={templateHighlightIndex}
          onSelectedIndexChange={setTemplateSelectedIndex}
          onPick={pickTemplate}
          onClose={() => setTemplatePickerOpen(false)}
          loading={!templatesLoaded}
          listboxId={templateListboxId}
          optionIdPrefix={templateOptionPrefix}
          anchorRef={capsuleRef}
        />
        {attachments.length > 0 || attachmentReadPending || attachmentNotice ? (
          <div className="mb-2 flex flex-wrap items-center justify-end gap-2">
            {attachmentNotice ? (
              <span className="max-w-full rounded-full bg-background/75 px-3 py-1.5 text-xs text-muted-foreground shadow-[inset_0_0_0_1px_var(--glass-border)]">
                {attachmentNotice}
              </span>
            ) : null}
            {attachments.map((attachment) => (
              <span
                key={attachment.id}
                className={cn(
                  "glass-regular inline-flex h-9 max-w-full items-center gap-2 rounded-full px-3 text-xs text-foreground shadow-[var(--glass-highlight)]",
                  (attachedSendBlocked || attachmentReadPending) &&
                    "text-muted-foreground",
                )}
                title="File content is used for this request only and is not stored."
              >
                {attachmentIconType(attachment.mediaType) === "image" ? (
                  <ImageIcon aria-hidden className="size-3.5 shrink-0" />
                ) : (
                  <FileText aria-hidden className="size-3.5 shrink-0" />
                )}
                <span className="min-w-0 max-w-[12rem] truncate">
                  {attachment.name}
                </span>
                <span className="shrink-0 text-muted-foreground">
                  {formatAttachmentSize(attachment.sizeBytes)}
                </span>
                <button
                  type="button"
                  aria-label={`Remove ${attachment.name}`}
                  onClick={() => removeAttachment(attachment.id)}
                  className="-mr-1 ml-0.5 inline-flex size-7 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-foreground/10 hover:text-foreground focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none"
                >
                  <X className="size-3.5" />
                </button>
              </span>
            ))}
            {attachmentReadPending ? (
              <span className="glass-regular inline-flex h-9 max-w-full items-center gap-2 rounded-full px-3 text-xs text-muted-foreground shadow-[var(--glass-highlight)]">
                <LoaderCircle
                  aria-hidden
                  className="size-3.5 shrink-0 motion-safe:animate-spin"
                />
                <span>
                  {pendingAttachmentReads === 1
                    ? "Reading file"
                    : `Reading ${pendingAttachmentReads} files`}
                </span>
                <button
                  type="button"
                  aria-label="Cancel attachment read"
                  onClick={() => clearAttachments("manual")}
                  className="-mr-1 ml-0.5 inline-flex size-7 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-foreground/10 hover:text-foreground focus-visible:shadow-[var(--focus-ring)] focus-visible:outline-none"
                >
                  <X className="size-3.5" />
                </button>
              </span>
            ) : null}
          </div>
        ) : null}
        <div
          ref={capsuleRef}
          // Radius: a perfect pill at one line, a large continuous radius once
          // grown (a 9999px pill looks wrong at 4–6 lines). `glass-capsule` sets
          // border-radius:9999px in CSS; rather than fight @utility ordering we
          // override deterministically with an inline border-radius only in the
          // grown state (inline style always wins), and leave the pill to the
          // utility default otherwise.
          // Focus halo: dropped `--focus-glow-halo` (a 24px outer glow) from the
          // focus-within stack — iOS text fields don't glow. The thin lit edge
          // (`--focus-glow-edge`) + highlight + ambient/key shadows remain; the
          // brand send button is the real focus signal.
          style={grown ? { borderRadius: "1.75rem" } : undefined}
          className="glass-capsule group flex items-end gap-2 rounded-full px-2 py-1.5 transition-shadow duration-300 ease-out focus-within:shadow-[var(--focus-glow-edge),var(--glass-highlight),var(--glass-shadow-ambient),var(--glass-shadow-key)]"
        >
          {/* Hidden file input: MUST stay mounted whenever the tier supports
            attachments, independent of collapse state — Playwright drives it
            directly via setInputFiles, and the disclosure popover unmounts on
            close. Keeping it here (a sibling of the cluster) keeps it always
            available. */}
          {supportsAttachments ? (
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept={ACCEPTED_ATTACHMENT_TYPES}
              data-testid="composer-file-input"
              className="sr-only"
              onChange={(e) => onPickFiles(e.target.files)}
            />
          ) : null}
          {/* Always-collapsed cluster: in BOTH the empty/at-rest and composing
            states the secondary controls live behind the single "More actions"
            ("+") disclosure, so the composer always reads as `[+] [textarea]
            [Send]`. Send/Stop stays primary; every secondary feature is exactly
            one tap away inside the popover, mounted in ONE place so there are
            never duplicate controls or stray hidden tab stops. An ACTIVE
            recording keeps its mic pinned inline (alongside the disclosure) so a
            stream in progress is always stoppable in one tap. The disclosure
            expands with a zoom/fade; motion-reduce makes the open instant. */}
          <div className="flex items-end gap-2 transition-opacity duration-300 ease-ios-smooth motion-reduce:transition-none">
            {/* Mobile inline promotions: Attach + Dictate sit BEFORE the "+"
                disclosure so phone users don't pay an extra tap to reach the
                two most-used secondary controls. They still also live inside
                the popover for parity (testids reachable on any viewport). */}
            {keepAttachInline ? attachButton : null}
            {keepDictateInline ? (
              dictation.listening ? (
                <Tooltip>
                  <TooltipTrigger render={dictateButton} />
                  <TooltipContent>
                    Stop dictation · processed on your device by your browser
                  </TooltipContent>
                </Tooltip>
              ) : (
                dictateButton
              )
            ) : null}
            {hasCollapsibleControls ? (
              (() => {
                const moreActionsTrigger = (
                  <Button
                    type="button"
                    variant="ghost"
                    disabled={isStreaming}
                    aria-label="More actions"
                    aria-haspopup="dialog"
                    data-testid="composer-more-actions"
                    className={cn(
                      "size-11 shrink-0 rounded-full p-0",
                      moreActionsOpen
                        ? "text-foreground"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    <Plus className="size-4 transition-transform duration-300 ease-ios-spring data-[popup-open]:rotate-45 motion-reduce:transition-none" />
                  </Button>
                );
                const moreActionsRows = (
                  <>
                    {supportsAttachments && !keepAttachInline ? (
                      <div className="flex items-center gap-2">
                        {attachButton}
                        <span className="pr-2 text-sm text-foreground">
                          Attach file
                        </span>
                      </div>
                    ) : null}
                    <div className="flex items-center gap-2">
                      {templatesButton}
                      <span className="pr-2 text-sm text-foreground">
                        Prompt template
                      </span>
                    </div>
                    {keepDictateInline ? null : (
                      <div className="flex items-center gap-2">
                        {dictateButton}
                        <span className="flex flex-col pr-2 text-left">
                          <span className="text-sm text-foreground">
                            {!dictation.supported
                              ? "Dictation unavailable"
                              : "Dictate"}
                          </span>
                          {/* On-device transparency (carried over from the
                              former inline-mic tooltip): state that the
                              browser/device does the work, never a
                              provider/model. Always visible in the open row —
                              strictly better than a hover-only tooltip for
                              touch + AT. */}
                          {dictation.supported ? (
                            <span className="text-2xs text-muted-foreground">
                              Voice is processed on your device by your browser
                            </span>
                          ) : null}
                        </span>
                      </div>
                    )}
                  </>
                );
                return (
                  <Popover.Root
                    open={moreActionsOpen}
                    onOpenChange={setMoreActionsOpen}
                  >
                    <Tooltip>
                      <TooltipTrigger
                        render={<Popover.Trigger render={moreActionsTrigger} />}
                      />
                      <TooltipContent>More actions</TooltipContent>
                    </Tooltip>
                    <Popover.Portal>
                      <Popover.Positioner
                        side="top"
                        align="start"
                        sideOffset={8}
                        className="z-[60] outline-none"
                      >
                        <Popover.Popup
                          // Small anchored actions popover used on every
                          // viewport — a full bottom sheet is over-weight for
                          // the two or three rows the cluster ever holds.
                          // Matches the attribution-row glass + zoom/fade
                          // enter; motion-reduce path is provided by the
                          // global reduced-motion CSS for animate-in.
                          className={cn(
                            "glass-strong flex origin-(--transform-origin) flex-col gap-1 rounded-2xl p-1.5 text-popover-foreground shadow-[var(--glass-highlight),var(--glass-shadow-ambient),var(--glass-shadow-key)] outline-none",
                            "duration-150 data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95",
                            "data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-95",
                          )}
                        >
                          {moreActionsRows}
                        </Popover.Popup>
                      </Popover.Positioner>
                    </Popover.Portal>
                  </Popover.Root>
                );
              })()
            ) : null}
          </div>
          <label htmlFor="composer-input" className="sr-only">
            Message Olune
          </label>
          <textarea
            id="composer-input"
            // E2E target: aria-label is localized + role="combobox" collides with
            // multiple test selectors; the testid is the stable handle.
            data-testid="composer-textarea"
            ref={ref}
            rows={1}
            value={value}
            onChange={(e) => {
              updateValue(e.target.value);
              autoGrow();
            }}
            onKeyDown={onKeyDown}
            placeholder="Message Olune…"
            role="combobox"
            aria-haspopup="listbox"
            aria-autocomplete="list"
            aria-expanded={slashOpen}
            aria-controls={slashOpen ? slashListboxId : undefined}
            aria-activedescendant={slashActiveOptionId}
            className="block max-h-[200px] min-h-[44px] flex-1 resize-none bg-transparent px-1 py-2 text-[1.0625rem] leading-7 text-foreground outline-none placeholder:text-muted-foreground md:text-[0.9375rem]"
          />
          <div className="flex h-11 shrink-0 items-center">
            {/* Send↔stop swap: the stop side is Tooltip-wrapped and the send side
              isn't, so the button remounts on toggle. MorphSendStopIcon owns the
              icon spring and bridges that remount with a one-frame mount reveal,
              so the morph fires on every swap without disturbing handlers,
              aria-label, disabled, testid, or the color/shadow transition. */}
            {isStreaming ? (
              <Tooltip>
                <TooltipTrigger
                  render={
                    <Button
                      type="button"
                      onClick={onStop}
                      aria-label="Stop generating"
                      className={cn(
                        BUTTON_BASE,
                        "bg-foreground/10 text-foreground hover:bg-foreground/15",
                      )}
                    >
                      <MorphSendStopIcon isStreaming />
                    </Button>
                  }
                />
                <TooltipContent>Stop</TooltipContent>
              </Tooltip>
            ) : (
              <Button
                type="button"
                onClick={submit}
                disabled={!canSubmit}
                aria-label={
                  attachmentReadPending
                    ? "Reading attachments"
                    : attachedSendBlocked
                      ? "Attachments are not supported by the current model"
                      : "Send message"
                }
                // E2E target: stable hook for "send the message" — Playwright
                // specs click this to dispatch a turn, since aria-label values
                // could drift with copy changes.
                data-testid="composer-send"
                className={cn(
                  BUTTON_BASE,
                  // Order matters: a fresh keystroke during the settle pose
                  // should read as "armed" (brand + clickable) before the
                  // settle-pose styling can claim the slot.
                  canSubmit
                    ? "bg-brand text-brand-foreground shadow-pill hover:bg-brand/90"
                    : justStopped
                      ? "bg-foreground/10 text-foreground"
                      : "bg-transparent text-muted-foreground group-focus-within:text-foreground",
                )}
              >
                <MorphSendStopIcon isStreaming={false} />
              </Button>
            )}
          </div>
        </div>
        {costEstimate ? (
          <p
            // Calmer default: the estimate is hidden at rest on desktop and only
            // fades in while the composer is focused. Touch devices (no hover)
            // always show it since they have no persistent focus-within signal.
            className={cn(
              "mt-1 px-2 text-right text-2xs leading-snug tabular-nums text-muted-foreground/80",
              "opacity-0 transition-opacity duration-300 group-focus-within/composer:opacity-100 [@media(hover:none)]:opacity-100",
            )}
            data-testid="cost-estimate"
          >
            {costEstimate.usd === null ? (
              <>Estimate unavailable for Auto</>
            ) : (
              <>
                Est. {formatEstimateUsd(costEstimate.usd)} ·{" "}
                {estimateTokenFmt.format(costEstimate.tokens)} tokens in
              </>
            )}
          </p>
        ) : null}
      </div>
    );
  },
);

Composer.displayName = "Composer";
