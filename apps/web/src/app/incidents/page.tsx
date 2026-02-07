import { AlertTriangle } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function IncidentsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Incidents</h1>
        <p className="text-muted-foreground mt-1">
          View and manage detected incidents across your monitored applications.
        </p>
      </div>

      <Card>
        <CardContent className="flex flex-col items-center justify-center py-16">
          <AlertTriangle className="h-12 w-12 text-muted-foreground/50 mb-4" />
          <h3 className="text-lg font-medium">No incidents yet</h3>
          <p className="text-sm text-muted-foreground mt-1 text-center max-w-md">
            Once your observability pipeline is set up and monitoring is active,
            detected anomalies and incidents will appear here.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
