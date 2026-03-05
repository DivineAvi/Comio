"use client";

import { useEffect, useState, use } from "react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";
import { getProject, getSandbox, type Project, type SandboxStatus } from "@/lib/api";

interface ProjectDetailPageProps {
  params: Promise<{ id: string }>;
}

export default function ProjectDetailPage({ params }: ProjectDetailPageProps) {
  const { id } = use(params);
  const [project, setProject] = useState<Project | null>(null);
  const [sandbox, setSandbox] = useState<SandboxStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [proj, sb] = await Promise.all([
          getProject(id),
          getSandbox(id).catch(() => null),
        ]);
        setProject(proj);
        setSandbox(sb);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load project");
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [id]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24 text-muted-foreground">
        <Loader2 className="h-5 w-5 mr-2 animate-spin" />
        Loading project...
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="rounded-md border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
        {error ?? "Project not found"}
      </div>
    );
  }

  const sandboxStatus = sandbox?.status ?? "none";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold tracking-tight">{project.name}</h1>
            <Badge variant="secondary">
              {project.origin === "cloned" ? "Imported" : "Created"}
            </Badge>
          </div>
          <p className="text-muted-foreground mt-1">
            {project.description || "Project overview, metrics, and sandbox management."}
          </p>
        </div>
        <Button asChild>
          <Link href={`/projects/${id}/sandbox`}>Open Sandbox</Link>
        </Button>
      </div>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Health</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-500">Healthy</div>
            <p className="text-xs text-muted-foreground mt-1">
              All metrics within normal range
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Sandbox</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold capitalize">{sandboxStatus}</div>
            <p className="text-xs text-muted-foreground mt-1">
              {sandboxStatus === "running"
                ? "Sandbox is running. Open the sandbox chat to work with Comio."
                : "Start sandbox from the sandbox page to use the AI assistant."}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Incidents</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">0</div>
            <p className="text-xs text-muted-foreground mt-1">
              No active incidents
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent Activity</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Project activity and events will appear here.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
