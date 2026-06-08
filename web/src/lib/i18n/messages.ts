// English message catalog — the baseline locale and the source of truth for
// every translatable key. Additional locales mirror this shape; `useT()` falls
// back to the `en` string (and finally to the key itself) when a translation is
// missing, so a partial catalog never renders a blank.
//
// Keys are dot-namespaced by surface (`composer.*`, `sidebar.*`, `usage.*`).
// Interpolation uses `{name}` placeholders filled from the `vars` argument to
// `t()`.

export const en = {
  // Composer
  "composer.placeholder": "Message Olune…",
  "composer.inputLabel": "Message Olune",
  "composer.send": "Send message",
  "composer.stop": "Stop generating",
  "composer.moreActions": "More actions",
  "composer.attach": "Attach file",
  "composer.takePhoto": "Take photo",
  "composer.photoLibrary": "Photo library",
  "composer.template": "Insert a prompt template",
  "composer.startDictation": "Start dictation",
  "composer.stopDictation": "Stop dictation",
  "composer.dictationUnsupported": "Dictation not supported in this browser",
  "composer.readingAttachments": "Reading attachments",

  // Sidebar
  "sidebar.newChat": "New chat",
  "sidebar.search": "Search",
  "sidebar.searchPlaceholder": "Search chats",
  "sidebar.collapse": "Collapse sidebar",

  // Usage meter
  "usage.billedToKey": "Billed to your key",
  "usage.budgetReached": "Budget reached",
  "usage.noUsageLeft": "No usage left",
  "usage.meteringActive": "Usage metering active",
  "usage.left": "{amount} left",

  // Follow-up suggestions
  "followups.tellMore": "Tell me more",
  "followups.example": "Give an example",
} as const;

export type MessageKey = keyof typeof en;
export type MessageCatalog = Record<MessageKey, string>;

export const catalogs: Record<string, Partial<MessageCatalog>> = {
  en,
};

// Locales that read right-to-left. Used to derive the document direction when a
// non-default locale is active (the `?rtl=1` test hook overrides this directly).
export const RTL_LOCALES = new Set(["ar", "he", "fa", "ur"]);
