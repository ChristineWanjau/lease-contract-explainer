export type Chunk = {
  text: string;
  clause: string | null;
  page: number;
};

export type SessionOut = {
  session_id: string;
  pack: string;
  /** What automatic detection chose on upload; null when the type was already known. */
  detected: { pack: string; confidence: number } | null;
  chunks: Chunk[];
};

export type PackOut = {
  id: string;
  name: string;
  sample_label: string;
  example_questions: string[];
};

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type SummaryField = {
  name: string;
  label: string;
  kind: "single" | "list";
};

/** Values keyed by field name; shape depends on the active contract type pack. */
export type Summary = {
  fields: SummaryField[];
  values: Record<string, string | string[]>;
};

export type Citation = {
  clause: string | null;
  page: number;
  quote: string;
};

export type Severity = "high" | "medium" | "low";

/** Where a legal requirement comes from. Always from configuration, never the model. */
export type LegalSource = {
  act: string;
  section: string;
  link: string;
  verified: boolean;
  last_reviewed: string | null;
};

export type RiskFlag = {
  kind: "contract_risk" | "legal_rule";
  category: string;
  category_label: string;
  severity: Severity;
  explanation: string;
  question_to_ask: string;
  citations: Citation[];
  legal: LegalSource | null;
};

/** A legal requirement the contract says nothing about: cites the Act, not a clause. */
export type MissingItem = {
  rule: string;
  topic: string;
  severity: Severity;
  requirement: string;
  question_to_ask: string;
  legal: LegalSource;
};

export type AnalysisEvent =
  | { event: "summary"; data: { summary: Summary; disclaimer: string } }
  | { event: "risk_flag"; data: RiskFlag }
  | { event: "missing_item"; data: MissingItem }
  | {
      event: "done";
      data: { skipped_clauses: (string | null)[]; skipped_rules: string[] };
    }
  | { event: "error"; data: { message: string } };

/** Stream the analysis of a session; calls onEvent for each Server-Sent Event. */
export function streamAnalysis(
  sessionId: string,
  onEvent: (e: AnalysisEvent) => void,
): () => void {
  const source = new EventSource(
    `${API_URL}/api/sessions/${sessionId}/analyze`,
  );
  source.addEventListener("summary", (msg) => {
    const raw: {
      summary: Summary["values"];
      fields: SummaryField[];
      disclaimer: string;
    } = JSON.parse(msg.data);
    onEvent({
      event: "summary",
      data: {
        summary: { fields: raw.fields, values: raw.summary },
        disclaimer: raw.disclaimer,
      },
    });
  });
  source.addEventListener("risk_flag", (msg) => {
    onEvent({ event: "risk_flag", data: JSON.parse(msg.data) });
  });
  source.addEventListener("missing_item", (msg) => {
    onEvent({ event: "missing_item", data: JSON.parse(msg.data) });
  });
  source.addEventListener("done", (msg) => {
    source.close();
    onEvent({ event: "done", data: JSON.parse(msg.data) });
  });
  // "error" is both the server's error event (has data) and the browser's
  // connection-failure event (no data), so one listener handles both.
  source.addEventListener("error", (msg) => {
    source.close();
    const data = (msg as MessageEvent).data;
    onEvent({
      event: "error",
      data: data
        ? JSON.parse(data)
        : { message: "Lost connection to the backend. Is it running?" },
    });
  });
  return () => source.close();
}

async function errorMessage(res: Response, fallback: string): Promise<string> {
  const data = await res.json().catch(() => null);
  const message: unknown = data?.detail?.message;
  return typeof message === "string" ? message : `${fallback} (HTTP ${res.status}).`;
}

export async function listPacks(): Promise<PackOut[]> {
  const res = await fetch(`${API_URL}/api/packs`);
  if (!res.ok) throw new Error(await errorMessage(res, "Could not load contract types"));
  return res.json();
}

export async function loadSample(pack?: string): Promise<SessionOut> {
  const query = pack ? `?pack=${encodeURIComponent(pack)}` : "";
  const res = await fetch(`${API_URL}/api/sample${query}`, { method: "POST" });
  if (!res.ok) throw new Error(await errorMessage(res, "Could not load the sample contract"));
  return res.json();
}

export async function setPack(sessionId: string, pack: string): Promise<SessionOut> {
  const res = await fetch(`${API_URL}/api/sessions/${sessionId}/pack`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pack }),
  });
  if (!res.ok) throw new Error(await errorMessage(res, "Could not change the contract type"));
  return res.json();
}

export async function uploadContract(file: File): Promise<SessionOut> {
  const body = new FormData();
  body.append("file", file);
  const res = await fetch(`${API_URL}/api/upload`, { method: "POST", body });
  if (!res.ok) throw new Error(await errorMessage(res, "Could not upload the contract"));
  return res.json();
}

export type ChatAnswer = {
  text: string;
  supported: boolean;
  citations: Citation[];
};

export type ChatEvent =
  | { event: "token"; data: { text: string } }
  | { event: "answer"; data: ChatAnswer }
  | { event: "done"; data: Record<string, never> }
  | { event: "error"; data: { message: string } };

/** POST a question and parse the Server-Sent Events response (EventSource is GET-only). */
export async function askQuestion(
  sessionId: string,
  question: string,
  onEvent: (e: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/sessions/${sessionId}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
      signal,
    });
  } catch {
    if (signal?.aborted) return;
    onEvent({ event: "error", data: { message: "Lost connection to the backend. Is it running?" } });
    return;
  }
  if (!res.ok || !res.body) {
    onEvent({ event: "error", data: { message: `Could not ask the question (HTTP ${res.status}).` } });
    return;
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let end: number;
    while ((end = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      let event = "";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (event && data) onEvent({ event, data: JSON.parse(data) } as ChatEvent);
    }
  }
}
