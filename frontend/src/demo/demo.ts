/**
 * Demo mode: replays recordings of the real backend (made with `make record-demo`
 * on local Ollama) so the hosted demo needs no backend and no model.
 * Enabled at build time with NEXT_PUBLIC_DEMO=1.
 */
import recordings from "./recordings.json";

export const DEMO = process.env.NEXT_PUBLIC_DEMO === "1";

export const REPO_URL = "https://github.com/ChristineWanjau/lease-contract-explainer";

type RawEvent = { event: string; data: unknown };

type Recording = {
  model: string;
  recorded_at: string;
  packs: unknown[];
  samples: Record<
    string,
    { session: unknown; analysis: RawEvent[]; chat: Record<string, RawEvent[]> }
  >;
};

export const demo = recordings as unknown as Recording;

/** Pause between replayed analysis events, so cards still appear one by one. */
const EVENT_DELAY_MS = 450;
/** Pause between replayed chat tokens. */
const TOKEN_DELAY_MS = 25;

export function sampleFor(pack: string) {
  const s = demo.samples[pack];
  if (!s) throw new Error(`No recorded sample for ${pack}.`);
  return s;
}

/** The pack a demo session id belongs to ("demo-<pack>"). */
export function packOf(sessionId: string): string {
  return sessionId.replace(/^demo-/, "");
}

/** Every question with a recorded answer for this pack's sample, in recorded order. */
export function recordedQuestions(pack: string): string[] {
  return Object.keys(demo.samples[pack]?.chat ?? {});
}

/** Replay events with a delay each; returns a cancel function. */
export function replay(
  events: RawEvent[],
  onEvent: (e: RawEvent) => void,
  delay: number,
): () => void {
  let cancelled = false;
  let i = 0;
  const step = () => {
    if (cancelled || i >= events.length) return;
    onEvent(events[i++]);
    timer = setTimeout(step, delay);
  };
  let timer = setTimeout(step, delay);
  return () => {
    cancelled = true;
    clearTimeout(timer);
  };
}

export const CHAT_TOKEN_DELAY_MS = TOKEN_DELAY_MS;
export const ANALYSIS_EVENT_DELAY_MS = EVENT_DELAY_MS;
