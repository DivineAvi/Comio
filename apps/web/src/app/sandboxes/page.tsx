import { Terminal } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";

export default function SandboxesPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Sandboxes</h1>
        <p className="text-muted-foreground mt-1">
          Manage Docker sandbox containers for your projects.
        </p>
      </div>

      <Card>
        <CardContent className="flex flex-col items-center justify-center py-16">
          <Terminal className="h-12 w-12 text-muted-foreground/50 mb-4" />
          <h3 className="text-lg font-medium">No active sandboxes</h3>
          <p className="text-sm text-muted-foreground mt-1 text-center max-w-md">
            Sandboxes are created automatically when you connect a project.
            Each project gets an isolated Docker container with your code
            and an AI coding assistant.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
