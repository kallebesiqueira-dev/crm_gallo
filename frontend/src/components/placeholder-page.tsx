import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function PlaceholderPage({ title }: { title: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          Coming in a future phase. The MVP scaffold ships with Dashboard, Leads, and the AI
          Assistant — this section is reserved for upcoming work.
        </p>
      </CardContent>
    </Card>
  );
}
