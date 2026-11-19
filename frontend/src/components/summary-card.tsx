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

/** Renders whatever fields the active contract type pack defines, in pack order. */
export function SummaryCard({ summary }: { summary: Summary }) {
  const fields = summary.fields;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Summary</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">
        {fields.map((field, i) => {
          const value = summary.values[field.name];
          const items = Array.isArray(value) ? value : value ? [value] : [];
          // An odd field count leaves the last field alone on its row; let it span both columns.
          const wide = fields.length % 2 === 1 && i === fields.length - 1;
          return (
            <div key={field.name} className={wide ? "sm:col-span-2" : undefined}>
              <Row label={field.label} items={items} />
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
