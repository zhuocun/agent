import type {
  ChatMessage,
  Conversation,
  ModelAttribution,
  UsageBudget,
} from "@/lib/types";

// A served-on-Smart turn: requested Smart, flat (Anthropic-style) pricing.
const smartAttribution: ModelAttribution = {
  requestedTierId: "smart",
  servedTierId: "smart",
  servedModelLabel: "Claude Sonnet 4.6",
  isByok: false,
  costUsd: 0.004182,
  costConfidence: "exact",
  breakdown: {
    currency: "USD",
    listPriceInPerM: 3,
    listPriceOutPerM: 15,
    inputTokens: 184,
    outputTokens: 268,
    reasoningTokens: 96,
    cachedInputTokens: 0,
    longContext: { flat: true, tokensRepriced: "none" },
    promoApplied: false,
    subtotalUsd: 0.004182,
    sessionSurchargeUsd: 0,
  },
};

// A substitution turn: requested Pro, served Fast because Pro was rate-limited.
const substitutedAttribution: ModelAttribution = {
  requestedTierId: "pro",
  servedTierId: "fast",
  servedModelLabel: "Gemini 2.5 Flash",
  isByok: false,
  costUsd: 0.000071,
  costConfidence: "exact",
  breakdown: {
    currency: "USD",
    listPriceInPerM: 0.075,
    listPriceOutPerM: 0.3,
    inputTokens: 512,
    outputTokens: 142,
    reasoningTokens: 0,
    cachedInputTokens: 256,
    longContext: { flat: false, tierScope: "overage", tokensRepriced: "none" },
    promoApplied: false,
    subtotalUsd: 0.000071,
    sessionSurchargeUsd: 0,
  },
  substitution: {
    reasonCode: "rate_limited",
    reasonText: "Answered by Fast because Pro was rate-limited.",
  },
};

export const MOCK_MESSAGES: ChatMessage[] = [
  {
    id: "m1",
    role: "user",
    createdAt: "2026-05-27T16:10:00Z",
    parts: [
      {
        type: "text",
        text: "I'm getting `TypeError: cannot read properties of undefined (reading 'map')` in this React component when the data is still loading. How do I fix it cleanly?",
      },
    ],
  },
  {
    id: "m2",
    role: "assistant",
    createdAt: "2026-05-27T16:10:04Z",
    status: "done",
    feedback: null,
    attribution: smartAttribution,
    parts: [
      {
        type: "reasoning",
        durationSec: 6,
        text: "The error means `data` is `undefined` on first render while the fetch is in flight, and `.map` is called on it. The clean fixes are: guard the render, default the value, or render a loading state. Best practice is to default the array and/or short-circuit before mapping.",
      },
      {
        type: "text",
        text: "The crash happens because `data` is `undefined` on the **first render** (before your fetch resolves), and you're calling `.map` on it. Two clean fixes:\n\n**1. Default the value** so it's always an array:\n\n```tsx\nconst [items, setItems] = useState<Item[]>([]); // not undefined\n```\n\n**2. Short-circuit while loading** so you render intent, not a crash:\n\n```tsx\nfunction List({ items, isLoading }: ListProps) {\n  if (isLoading) return <Spinner />;\n  if (!items?.length) return <Empty />;\n\n  return (\n    <ul>\n      {items.map((item) => (\n        <li key={item.id}>{item.name}</li>\n      ))}\n    </ul>\n  );\n}\n```\n\nPrefer **defaulting state to `[]`** over sprinkling `?.` everywhere — it keeps the mapping code clean and makes the loading/empty states explicit. Use optional chaining only at the true boundary where a value can legitimately be absent.",
      },
    ],
  },
  {
    id: "m3",
    role: "user",
    createdAt: "2026-05-27T16:11:20Z",
    parts: [
      {
        type: "text",
        text: "Nice. Can you show the same thing but using a custom hook so I can reuse the loading/empty handling?",
      },
    ],
  },
  {
    id: "m4",
    role: "assistant",
    createdAt: "2026-05-27T16:11:24Z",
    status: "done",
    feedback: "up",
    attribution: substitutedAttribution,
    parts: [
      {
        type: "text",
        text: "Sure — extract the fetch + states into a hook and keep the component declarative:\n\n```tsx\nfunction useItems(url: string) {\n  const [items, setItems] = useState<Item[]>([]);\n  const [isLoading, setLoading] = useState(true);\n\n  useEffect(() => {\n    let active = true;\n    fetch(url)\n      .then((r) => r.json())\n      .then((d) => active && setItems(d))\n      .finally(() => active && setLoading(false));\n    return () => {\n      active = false;\n    };\n  }, [url]);\n\n  return { items, isLoading };\n}\n```\n\nNow the component is just `const { items, isLoading } = useItems(\"/api/items\")` and the same loading/empty guards apply.",
      },
    ],
  },
];

// The next assistant turn the composer "sends" — streamed live for the demo.
export const MOCK_STREAM_REASONING =
  "They want to avoid a flash of empty state when data arrives quickly. A short delay before showing the spinner (or a min-display duration) prevents the flicker. I'll suggest a deferred loading flag.";

export const MOCK_STREAM_ANSWER = `Good instinct — the flicker comes from the spinner mounting for a few milliseconds before data lands. Two options:

**Defer the spinner** so it only shows if loading takes a noticeable beat:

\`\`\`tsx
const [showSpinner, setShowSpinner] = useState(false);

useEffect(() => {
  if (!isLoading) return;
  const t = setTimeout(() => setShowSpinner(true), 200);
  return () => clearTimeout(t);
}, [isLoading]);
\`\`\`

This way fast responses never flash a spinner, and slow ones still get feedback after ~200ms. It's the same trick \`React.useDeferredValue\` uses conceptually: don't react to transient states the user won't perceive.`;

export const MOCK_USAGE: UsageBudget = {
  used: 312,
  limit: 1000,
  periodLabel: "this month",
  isByok: false,
};

export const MOCK_CONVERSATION: Conversation = {
  id: "c1",
  title: "Fixing a React map() crash",
  messages: MOCK_MESSAGES,
  selectedTierId: "smart",
  isTemporary: false,
};
