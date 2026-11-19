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

export async function loadSample(): Promise<SessionOut> {
  const res = await fetch(`${API_URL}/api/sample`, { method: "POST" });
  if (!res.ok) {
    throw new Error(`Could not load the sample contract (HTTP ${res.status}).`);
  }
  return res.json();
}
