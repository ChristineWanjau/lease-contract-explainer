"use client";

import { useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { loadSample, uploadContract, type SessionOut } from "@/lib/api";

export default function Home() {
  const [session, setSession] = useState<SessionOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  async function run(load: () => Promise<SessionOut>) {
    setLoading(true);
    setError(null);
    try {
      setSession(await load());
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
        <section className="space-y-3" aria-label="Contract clauses">
          <h2 className="text-lg font-medium">
            Clauses ({session.chunks.length})
          </h2>
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
        </section>
      )}
    </main>
  );
}
