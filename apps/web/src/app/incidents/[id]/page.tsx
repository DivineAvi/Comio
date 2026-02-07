import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

export default async function IncidentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold tracking-tight">
              Incident #{id}
            </h1>
            <Badge variant="secondary">Pending</Badge>
          </div>
          <p className="text-muted-foreground mt-1">
            Incident details, AI diagnosis, and proposed fixes.
          </p>
        </div>
        <Button variant="outline">Open in Sandbox</Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* AI Diagnosis */}
        <Card>
          <CardHeader>
            <CardTitle>AI Diagnosis</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              AI diagnosis will appear here once the RCA engine analyzes this
              incident.
            </p>
          </CardContent>
        </Card>

        {/* Proposed Fix */}
        <Card>
          <CardHeader>
            <CardTitle>Proposed Fix</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              The fix generator will propose code changes here for review and
              approval.
            </p>
          </CardContent>
        </Card>
      </div>

      <Separator />

      {/* Timeline */}
      <Card>
        <CardHeader>
          <CardTitle>Timeline</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Incident event timeline will be populated as events occur.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
