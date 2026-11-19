import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Citation, LegalSource, MissingItem, RiskFlag, Severity } from "@/lib/api";

const SEVERITY_STYLE: Record<Severity, string> = {
  high: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200",
  medium: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200",
  low: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-200",
};

export function citationLabel(c: Citation) {
  return `${c.clause ? `Clause ${c.clause}` : "Preamble"}, p. ${c.page}`;
}

function SeverityTag({ severity }: { severity: Severity }) {
  return (
    <span
      className={`rounded px-2 py-0.5 text-xs font-semibold uppercase ${SEVERITY_STYLE[severity]}`}
    >
      {severity}
    </span>
  );
}

/** The Act citation for a legal rule, with a warning until a professional has reviewed it. */
function LegalCitation({ legal }: { legal: LegalSource }) {
  return (
    <div className="space-y-2">
      <a
        href={legal.link}
        target="_blank"
        rel="noreferrer"
        className="inline-block text-sm underline underline-offset-2"
      >
        {legal.act}, {legal.section}
      </a>
      {!legal.verified && (
        <p className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          <strong>Unverified rule.</strong> This legal rule hasn&apos;t been reviewed by a
          qualified professional yet. Check the Act before relying on it.
        </p>
      )}
    </div>
  );
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
          <SeverityTag severity={flag.severity} />
          {flag.category_label}
          {flag.kind === "legal_rule" && <Badge variant="secondary">Legal requirement</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p>{flag.explanation}</p>
        <p>
          <span className="font-medium">Ask before signing: </span>
          <span className="text-muted-foreground">{flag.question_to_ask}</span>
        </p>
        {flag.legal && <LegalCitation legal={flag.legal} />}
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

export function MissingItemCard({ item }: { item: MissingItem }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          <SeverityTag severity={item.severity} />
          {item.topic}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p>{item.requirement}</p>
        <p>
          <span className="font-medium">Ask before signing: </span>
          <span className="text-muted-foreground">{item.question_to_ask}</span>
        </p>
        <LegalCitation legal={item.legal} />
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
