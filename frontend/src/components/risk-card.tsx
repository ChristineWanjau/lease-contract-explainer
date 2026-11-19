import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Citation, RiskFlag, Severity } from "@/lib/api";

const SEVERITY_STYLE: Record<Severity, string> = {
  high: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200",
  medium: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200",
  low: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-200",
};

export function citationLabel(c: Citation) {
  return `${c.clause ? `Clause ${c.clause}` : "Preamble"}, p. ${c.page}`;
}

export function RiskCard({
  flag,
  onCite,
}: {
  flag: RiskFlag;
  onCite: (c: Citation) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          <span
            className={`rounded px-2 py-0.5 text-xs font-semibold uppercase ${SEVERITY_STYLE[flag.severity]}`}
          >
            {flag.severity}
          </span>
          {flag.category_label}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p>{flag.explanation}</p>
        <p>
          <span className="font-medium">Ask before signing: </span>
          <span className="text-muted-foreground">{flag.question_to_ask}</span>
        </p>
        <div className="flex flex-wrap gap-2">
          {flag.citations.map((c, i) => (
            <button key={i} type="button" onClick={() => onCite(c)}>
              <Badge variant="outline" className="cursor-pointer hover:bg-muted">
                {citationLabel(c)}
              </Badge>
            </button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

export function CitationPanel({
  citation,
  onClose,
}: {
  citation: Citation | null;
  onClose: () => void;
}) {
  if (!citation) return null;
  return (
    <aside
      role="dialog"
      aria-label="Quoted contract text"
      className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col gap-4 border-l bg-background p-6 shadow-xl"
    >
      <div className="flex items-center justify-between">
        <h2 className="font-medium">{citationLabel(citation)}</h2>
        <button
          type="button"
          onClick={onClose}
          className="rounded px-2 text-muted-foreground hover:bg-muted"
          aria-label="Close"
        >
          ✕
        </button>
      </div>
      <blockquote className="overflow-y-auto whitespace-pre-line border-l-4 pl-4 text-sm">
        {citation.quote}
      </blockquote>
      <p className="text-xs text-muted-foreground">
        Quoted exactly from your contract.
      </p>
    </aside>
  );
}
