// Voice v1 (D22): dictation (STT) + read-aloud (TTS) via the browser Web Speech
// API, processed ON-DEVICE.
//
// These assertions cover the two things that matter for v1 and are testable
// without real audio:
//   (a) both controls RENDER (mic in the composer, read-aloud on an assistant
//       message) and
//   (b) they GATE on feature detection — enabled with an honest "on your
//       device" tooltip when the Web Speech APIs exist, disabled with an
//       explanatory tooltip when they don't.
//
// We never invoke real recognition/synthesis. `addInitScript` runs before any
// page script, so we inject a deterministic fake (or remove the APIs) before
// the React feature-detect (a lazy useState reading `window`) ever runs.
//
// Runs against the REAL BE + FakeProvider (PROVIDER_BACKEND=fake) so an
// assistant turn is available for the read-aloud control.

import { expect, test, type Page } from "@playwright/test";

import { waitForBootstrap } from "./helpers";

// Inject a no-op Web Speech recognition + synthesis pair. Enough surface for
// the feature-detect (constructor present, speechSynthesis present) and for a
// click to be a harmless no-op — we never assert real transcription/audio.
async function stubWebSpeech(page: Page): Promise<void> {
  await page.addInitScript(() => {
    class FakeRecognition {
      lang = "";
      continuous = false;
      interimResults = false;
      onresult: ((e: unknown) => void) | null = null;
      onerror: ((e: unknown) => void) | null = null;
      onend: ((e: unknown) => void) | null = null;
      onstart: ((e: unknown) => void) | null = null;
      start() {
        this.onstart?.(new Event("start"));
      }
      stop() {
        this.onend?.(new Event("end"));
      }
      abort() {
        this.onend?.(new Event("end"));
      }
      addEventListener() {}
      removeEventListener() {}
      dispatchEvent() {
        return true;
      }
    }
    // Both the prefixed and unprefixed names — the hook prefers unprefixed.
    Object.defineProperty(window, "SpeechRecognition", {
      configurable: true,
      writable: true,
      value: FakeRecognition,
    });
    Object.defineProperty(window, "webkitSpeechRecognition", {
      configurable: true,
      writable: true,
      value: FakeRecognition,
    });
    // A minimal speechSynthesis so `'speechSynthesis' in window` is true and a
    // click is a no-op. SpeechSynthesisUtterance is native in Chromium.
    Object.defineProperty(window, "speechSynthesis", {
      configurable: true,
      writable: true,
      value: {
        speak() {},
        cancel() {},
        pause() {},
        resume() {},
        getVoices() {
          return [];
        },
      },
    });
  });
}

// Remove the Web Speech APIs entirely so the feature-detect reports them
// unsupported. Chromium ships speechSynthesis/webkitSpeechRecognition natively,
// so the unsupported path must be forced.
async function removeWebSpeech(page: Page): Promise<void> {
  await page.addInitScript(() => {
    Object.defineProperty(window, "SpeechRecognition", {
      configurable: true,
      value: undefined,
    });
    Object.defineProperty(window, "webkitSpeechRecognition", {
      configurable: true,
      value: undefined,
    });
    // Delete the native speechSynthesis so `'speechSynthesis' in window` fails.
    try {
      // @ts-expect-error — intentionally removing a native global for the test.
      delete window.speechSynthesis;
    } catch {
      Object.defineProperty(window, "speechSynthesis", {
        configurable: true,
        value: undefined,
      });
    }
  });
}

async function sendMessage(page: Page, text: string): Promise<void> {
  const composer = page.getByTestId("composer-textarea");
  await composer.fill(text);
  await composer.press("Enter");
  const assistant = page.getByTestId("assistant-message").last();
  await expect(assistant).toBeVisible({ timeout: 15_000 });
  await expect(assistant).toHaveAttribute("data-status", "done", {
    timeout: 15_000,
  });
}

test.describe("voice v1 — feature detection", () => {
  test("mic + read-aloud are enabled with an on-device label when supported", async ({
    page,
  }) => {
    await stubWebSpeech(page);
    await page.goto("/");
    await waitForBootstrap(page);

    // (a) Dictation control lives behind the composer "More actions" (+)
    // disclosure; open it, then assert the control renders and is enabled.
    await page.getByTestId("composer-more-actions").click();
    const mic = page.getByTestId("composer-dictate");
    await expect(mic).toBeVisible();
    await expect(mic).toBeEnabled();
    await expect(mic).toHaveAttribute("aria-label", "Start dictation");
    await expect(mic).toHaveAttribute("aria-pressed", "false");

    // On-device transparency: an always-visible row must say the browser/device
    // does it, and must NOT imply a provider/model.
    await expect(
      page.getByText("voice is processed on your device by your browser"),
    ).toBeVisible();

    // Toggling flips to the recording state (aria-pressed + stop label) without
    // sending anything. The fake recognition fires onstart synchronously.
    await mic.click();
    await expect(mic).toHaveAttribute("aria-pressed", "true");
    await expect(mic).toHaveAttribute("aria-label", "Stop dictation");
    await mic.click();
    await expect(mic).toHaveAttribute("aria-pressed", "false");

    // (b) Read-aloud renders on an assistant message and is enabled. Close the
    // + popover first so sending isn't blocked, then open the message "…"
    // overflow menu where read-aloud now lives.
    await page.keyboard.press("Escape");
    await sendMessage(page, "Hello voice");
    await page.getByTestId("message-actions-overflow").last().click();
    const readAloud = page.getByTestId("read-aloud").last();
    await expect(readAloud).toBeVisible();
    await expect(readAloud).toBeEnabled();
    await expect(readAloud).toHaveAttribute("aria-label", "Read aloud");
    await expect(
      page.getByText("spoken on your device by your browser"),
    ).toBeVisible();
  });

  test("mic + read-aloud are disabled with an explanatory label when unsupported", async ({
    page,
  }) => {
    await removeWebSpeech(page);
    await page.goto("/");
    await waitForBootstrap(page);

    // Dictation control is present but disabled (graceful degradation). It
    // lives behind the composer "More actions" (+) disclosure; open it first.
    await page.getByTestId("composer-more-actions").click();
    const mic = page.getByTestId("composer-dictate");
    await expect(mic).toBeVisible();
    await expect(mic).toBeDisabled();
    await expect(mic).toHaveAttribute(
      "aria-label",
      "Dictation not supported in this browser",
    );

    // Read-aloud on an assistant message is present but disabled. Close the +
    // popover first so sending isn't blocked, then open the message "…" overflow
    // menu where read-aloud now lives.
    await page.keyboard.press("Escape");
    await sendMessage(page, "Hello no voice");
    await page.getByTestId("message-actions-overflow").last().click();
    const readAloud = page.getByTestId("read-aloud").last();
    await expect(readAloud).toBeVisible();
    await expect(readAloud).toBeDisabled();
    await expect(readAloud).toHaveAttribute(
      "aria-label",
      "Read aloud not supported in this browser",
    );
  });
});
