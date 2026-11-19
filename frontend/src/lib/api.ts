export type Chunk = {
  text: string;
  clause: string | null;
  page: number;
};

export type SessionOut = {
  session_id: string;
  chunks: Chunk[];
};

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Summary = {
  parties: string[];
  key_dates: string[];
  payments: string[];
  duration: string;
  obligations: string[];
};

export type Citation = {
  clause: string | null;
  page: number;
  quote: string;
};

export type Severity = "high" | "medium" | "low";

export type RiskFlag = {
  category: string;
  category_label: string;
  severity: Severity;
  explanation: string;
  question_to_ask: string;
  citations: Citation[];
};

export type AnalysisEvent =
  | { event: "summary"; data: { summary: Summary; disclaimer: string } }
  | { event: "risk_flag"; data: RiskFlag }
  | { event: "done"; data: { skipped_clauses: (string | null)[] } }
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
    onEvent({ event: "summary", data: JSON.parse(msg.data) });
  });
  source.addEventListener("risk_flag", (msg) => {
    onEvent({ event: "risk_flag", data: JSON.parse(msg.data) });
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

export async function loadSample(): Promise<SessionOut> {
  const res = await fetch(`${API_URL}/api/sample`, { method: "POST" });
  if (!res.ok) {
    throw new Error(`Could not load the sample contract (HTTP ${res.status}).`);
  }
  return res.json();
}

export async function uploadContract(file: File): Promise<SessionOut> {
  const body = new FormData();
  body.append("file", file);
  const res = await fetch(`${API_URL}/api/upload`, { method: "POST", body });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    const message: unknown = data?.detail?.message;
    throw new Error(
      typeof message === "string"
        ? message
        : `Could not upload the contract (HTTP ${res.status}).`,
    );
  }
  return res.json();
}
