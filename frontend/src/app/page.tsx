"use client";

import { useEffect, useRef, useState } from "react";

import { CitationPanel, RiskCard } from "@/components/risk-card";
import { SummaryCard } from "@/components/summary-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  loadSample,
  streamAnalysis,
  uploadContract,
  type Citation,
  type RiskFlag,
  type SessionOut,
  type Summary,
} from "@/lib/api";

type Analysis = {
  stage: "summarizing" | "scanning" | "done" | "error";
  summary: Summary | null;
  flags: RiskFlag[];
  skipped: (string | null)[];
  message?: string;
};

const START: Analysis = { stage: "summarizing", summary: null, flags: [], skipped: [] };

export default function Home() {
  const [session, setSession] = useState<SessionOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [citation, setCitation] = useState<Citation | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  // Start the analysis whenever a new contract is loaded.
  useEffect(() => {
    if (!session) return;
    return streamAnalysis(session.session_id, (e) => {
      setAnalysis((a) => {
        const prev = a ?? START;
        switch (e.event) {
          case "summary":
            return { ...prev, stage: "scanning", summary: e.data.summary };
          case "risk_flag":
            return { ...prev, flags: [...prev.flags, e.data] };
          case "done":
            return { ...prev, stage: "done", skipped: e.data.skipped_clauses };
          case "error":
            return { ...prev, stage: "error", message: e.data.message };
        }
      });
    });
  }, [session]);

  async function run(load: () => Promise<SessionOut>) {
    setLoading(true);
    setError(null);
    try {
      const loaded = await load();
      setAnalysis(START);
      setCitation(null);
      setSession(loaded);
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Something went wrong. Is the backend running?",
      );
    } finally {
      setLoading(false);
    }
  }

  function onFileChosen(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file after an error
    if (file) run(() => uploadContract(file));
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-6 py-12">
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">
          Lease &amp; Contract Explainer
        </h1>
        <p className="text-muted-foreground">
          Understand what you are signing. Everything runs locally on your
          machine, so your contract never leaves it.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={() => fileInput.current?.click()} disabled={loading}>
          Upload PDF
        </Button>
        <input
          ref={fileInput}
          type="file"
          accept="application/pdf,.pdf"
          className="sr-only"
          aria-label="Upload a contract PDF"
          onChange={onFileChosen}
        />
        <Button variant="outline" onClick={() => run(loadSample)} disabled={loading}>
          {loading ? "Loading…" : "Try sample"}
        </Button>
        <span className="text-sm text-muted-foreground">
          Text PDFs up to 30 pages / 10 MB. Or try a fictional lease.
        </span>
      </div>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      {session && (
        <p
          role="note"
          className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
        >
          <strong>Not legal advice.</strong> This is an automated explanation
          that may be incomplete or wrong. For important decisions, consult a
          qualified lawyer.
        </p>
      )}

      {analysis?.stage === "summarizing" && (
        <p className="animate-pulse text-sm text-muted-foreground" aria-live="polite">
          Reading your contract with the local model… this can take a minute or two.
        </p>
      )}
      {analysis?.stage === "error" && (
        <p role="alert" className="text-sm text-destructive">
          {analysis.message}
        </p>
      )}
      {analysis?.summary && <SummaryCard summary={analysis.summary} />}

      {analysis && analysis.stage !== "summarizing" && (
        <section className="space-y-3" aria-label="Risk flags" aria-live="polite">
          <h2 className="text-lg font-medium">
            Risk flags ({analysis.flags.length})
          </h2>
          {analysis.flags.map((flag, i) => (
            <RiskCard key={i} flag={flag} onCite={setCitation} />
          ))}
          {analysis.stage === "scanning" && (
            <p className="animate-pulse text-sm text-muted-foreground">
              Checking clauses for risks…
            </p>
          )}
          {analysis.stage === "done" && analysis.flags.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No clauses matched the risk checklist. Still read the contract carefully.
            </p>
          )}
          {analysis.stage === "done" && analysis.skipped.length > 0 && (
            <p className="text-sm text-muted-foreground">
              Couldn&apos;t check:{" "}
              {analysis.skipped.map((c) => (c ? `Clause ${c}` : "Preamble")).join(", ")}.
            </p>
          )}
        </section>
      )}

      <CitationPanel citation={citation} onClose={() => setCitation(null)} />

      {session && (
        <details className="group space-y-3">
          <summary className="cursor-pointer text-lg font-medium">
            Clauses ({session.chunks.length})
          </summary>
          <div className="mt-3 space-y-3">
            {session.chunks.map((chunk, i) => (
              <Card key={`${chunk.clause ?? "pre"}-${i}`}>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Badge variant="secondary">
                      {chunk.clause ? `Clause ${chunk.clause}` : "Preamble"}
                    </Badge>
                    <CardDescription>p. {chunk.page}</CardDescription>
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="whitespace-pre-line text-sm">{chunk.text}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </details>
      )}
    </main>
  );
}
