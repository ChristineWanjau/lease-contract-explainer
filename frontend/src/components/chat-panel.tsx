"use client";

import { useEffect, useRef, useState } from "react";

import { citationLabel } from "@/components/risk-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { askQuestion, type Citation } from "@/lib/api";

type Message =
  | { role: "user"; text: string }
  | {
      role: "assistant";
      text: string;
      citations: Citation[];
      supported: boolean;
      pending: boolean;
      error?: boolean;
    };

export function ChatPanel({
  sessionId,
  examples,
  onCite,
}: {
  sessionId: string;
  /** Starter questions for the active contract type. */
  examples: string[];
  onCite: (c: Citation) => void;
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const abort = useRef<AbortController | null>(null);

  // Cancel any in-flight answer on unmount. The parent remounts this panel
  // (via key) for each new contract, which also clears the conversation.
  useEffect(() => () => abort.current?.abort(), []);

  function updateLast(patch: Partial<Extract<Message, { role: "assistant" }>>) {
    setMessages((ms) => {
      const last = ms[ms.length - 1];
      if (last?.role !== "assistant") return ms;
      return [...ms.slice(0, -1), { ...last, ...patch }];
    });
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (!q || busy) return;
    setQuestion("");
    setBusy(true);
    setMessages((ms) => [
      ...ms,
      { role: "user", text: q },
      { role: "assistant", text: "", citations: [], supported: false, pending: true },
    ]);
    abort.current = new AbortController();
    let streamed = "";
    await askQuestion(
      sessionId,
      q,
      (ev) => {
        if (ev.event === "token") {
          streamed += ev.data.text;
          updateLast({ text: streamed.replace(/<think>[\s\S]*?(<\/think>|$)/, "") });
        } else if (ev.event === "answer") {
          updateLast({ ...ev.data, pending: false });
        } else if (ev.event === "error") {
          updateLast({ text: ev.data.message, pending: false, error: true });
        }
      },
      abort.current.signal,
    );
    setBusy(false);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Ask about this contract</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {messages.length === 0 && (
          <div className="space-y-2 text-sm text-muted-foreground">
            {examples.length > 0 && (
              <div className="flex flex-wrap items-center gap-2">
                <span>For example:</span>
                {examples.map((q) => (
                  <button
                    key={q}
                    type="button"
                    onClick={() => setQuestion(q)}
                    className="rounded-full border px-3 py-1 text-foreground hover:bg-muted"
                  >
                    {q}
                  </button>
                ))}
              </div>
            )}
            <p>Answers only use your contract and cite the clause.</p>
          </div>
        )}
        <ol className="space-y-3" aria-live="polite">
          {messages.map((m, i) =>
            m.role === "user" ? (
              <li key={i} className="ml-auto max-w-[85%] rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground">
                {m.text}
              </li>
            ) : (
              <li
                key={i}
                className={`max-w-[85%] space-y-2 rounded-lg border px-3 py-2 text-sm ${m.error ? "border-destructive text-destructive" : ""}`}
              >
                <p className={`whitespace-pre-line ${m.pending && !m.text ? "animate-pulse text-muted-foreground" : ""}`}>
                  {m.text || "Thinking…"}
                </p>
                {m.citations.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {m.citations.map((c, j) => (
                      <button key={j} type="button" onClick={() => onCite(c)}>
                        <Badge variant="outline" className="cursor-pointer hover:bg-muted">
                          [{j + 1}] {citationLabel(c)}
                        </Badge>
                      </button>
                    ))}
                  </div>
                )}
              </li>
            ),
          )}
        </ol>
        <form onSubmit={onSubmit} className="flex gap-2">
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Ask a question about your contract…"
            aria-label="Your question"
            maxLength={2000}
            className="flex-1 rounded-md border bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <Button type="submit" disabled={busy || !question.trim()}>
            {busy ? "Answering…" : "Ask"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
