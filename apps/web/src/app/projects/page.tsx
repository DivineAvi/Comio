import { FolderGit2, Plus, Sparkles, GitBranch } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function ProjectsPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Projects</h1>
          <p className="text-muted-foreground mt-1">
            Create new projects or import existing repositories.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline">
            <GitBranch className="h-4 w-4 mr-2" />
            Import Repo
          </Button>
          <Button>
            <Sparkles className="h-4 w-4 mr-2" />
            Create Project
          </Button>
        </div>
      </div>

      <Card>
        <CardContent className="flex flex-col items-center justify-center py-16">
          <FolderGit2 className="h-12 w-12 text-muted-foreground/50 mb-4" />
          <h3 className="text-lg font-medium">No projects yet</h3>
          <p className="text-sm text-muted-foreground mt-1 text-center max-w-md">
            Create a new project from scratch with AI, or import an existing
            GitHub repository. Each project gets its own Docker sandbox with
            an AI coding assistant, and can be deployed with one click.
          </p>
          <div className="flex gap-3 mt-4">
            <Button variant="outline">
              <GitBranch className="h-4 w-4 mr-2" />
              Import Repository
            </Button>
            <Button>
              <Sparkles className="h-4 w-4 mr-2" />
              Create with AI
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
