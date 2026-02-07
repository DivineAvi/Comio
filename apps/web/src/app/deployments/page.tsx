import { Rocket } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";

export default function DeploymentsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Deployments</h1>
        <p className="text-muted-foreground mt-1">
          View and manage deployed applications across all projects.
        </p>
      </div>

      <Card>
        <CardContent className="flex flex-col items-center justify-center py-16">
          <Rocket className="h-12 w-12 text-muted-foreground/50 mb-4" />
          <h3 className="text-lg font-medium">No deployments yet</h3>
          <p className="text-sm text-muted-foreground mt-1 text-center max-w-md">
            Deploy a project from its sandbox chat or click the Deploy button.
            Deployed apps are automatically monitored by Comio&apos;s
            observability pipeline.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
