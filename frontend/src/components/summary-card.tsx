import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Summary } from "@/lib/api";

function Row({ label, items }: { label: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="space-y-1">
      <h3 className="text-sm font-medium">{label}</h3>
      <ul className="list-disc space-y-0.5 pl-5 text-sm text-muted-foreground">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export function SummaryCard({ summary }: { summary: Summary }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Summary</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">
        <Row label="Parties" items={summary.parties} />
        <Row label="Duration" items={[summary.duration]} />
        <Row label="Key dates" items={summary.key_dates} />
        <Row label="Payments" items={summary.payments} />
        <div className="sm:col-span-2">
          <Row label="Your obligations" items={summary.obligations} />
        </div>
      </CardContent>
    </Card>
  );
}
