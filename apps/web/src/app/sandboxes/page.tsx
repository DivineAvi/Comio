 "use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Terminal, Loader2 } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { listProjects, getSandbox, Project, SandboxStatus } from "@/lib/api";

type SandboxRow = {
  project: Project;
  sandbox: SandboxStatus | null;
};

export default function SandboxesPage() {
  const [rows, setRows] = useState<SandboxRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        setError(null);
        const { projects } = await listProjects();
        const sandboxRows: SandboxRow[] = await Promise.all(
          projects.map(async (project) => {
            try {
              const sandbox = await getSandbox(project.id);
              return { project, sandbox };
            } catch {
              return { project, sandbox: null };
            }
          })
        );
        setRows(sandboxRows);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load sandboxes");
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, []);

  const activeRows = rows.filter((r) => r.sandbox);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Sandboxes</h1>
        <p className="text-muted-foreground mt-1">
          Manage Docker sandbox containers for your projects.
        </p>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 mr-2 animate-spin" />
          Loading sandboxes...
        </div>
      ) : activeRows.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <Terminal className="h-12 w-12 text-muted-foreground/50 mb-4" />
            <h3 className="text-lg font-medium">No sandboxes yet</h3>
            <p className="text-sm text-muted-foreground mt-1 text-center max-w-md">
              Sandboxes are created automatically when you create or import a
              project. Each project gets an isolated Docker container with your
              code and an AI coding assistant.
            </p>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Project Sandboxes</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="divide-y divide-border/50 text-sm">
              {activeRows.map(({ project, sandbox }) => (
                <div
                  key={project.id}
                  className="flex items-center justify-between gap-4 py-3"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <Link
                        href={`/projects/${project.id}`}
                        className="font-medium hover:underline"
                      >
                        {project.name}
                      </Link>
                      <Badge variant="outline" className="text-[10px] uppercase">
                        {project.origin === "cloned" ? "Imported" : "Created"}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                      {project.description || "No description"}
                    </p>
                    {sandbox && (
                      <p className="mt-1 text-[11px] text-muted-foreground">
                        Branch: {sandbox.git_branch || "main"} · Volume:{" "}
                        {sandbox.volume_name || "n/a"}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {sandbox && (
                      <Badge
                        variant="outline"
                        className="text-[10px] uppercase"
                      >
                        {sandbox.status}
                      </Badge>
                    )}
                    <Button
                      asChild
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs"
                    >
                      <Link href={`/projects/${project.id}/sandbox`}>
                        Open Sandbox
                      </Link>
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
