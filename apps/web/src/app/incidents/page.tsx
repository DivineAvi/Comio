"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, Loader2 } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { listProjects, listIncidents, Incident, Project } from "@/lib/api";

export default function IncidentsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadProjects() {
      try {
        const res = await listProjects();
        setProjects(res.projects);
        if (res.projects.length > 0) {
          setSelectedProjectId(res.projects[0].id);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load projects");
      }
    }
    void loadProjects();
  }, []);

  useEffect(() => {
    if (!selectedProjectId) {
      setIncidents([]);
      return;
    }
    async function loadIncidents() {
      if (!selectedProjectId) return;
      try {
        setLoading(true);
        setError(null);
        const res = await listIncidents(selectedProjectId);
        setIncidents(res.incidents);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load incidents");
      } finally {
        setLoading(false);
      }
    }
    void loadIncidents();
  }, [selectedProjectId]);

  const selectedProject = projects.find((p) => p.id === selectedProjectId) ?? null;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Incidents</h1>
          <p className="text-muted-foreground mt-1">
            View and manage detected incidents across your monitored applications.
          </p>
        </div>
        {projects.length > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Project</span>
            <select
              value={selectedProjectId ?? ""}
              onChange={(e) =>
                setSelectedProjectId(e.target.value || null)
              }
              className="h-8 rounded-md border bg-background px-2 text-xs"
            >
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {error && (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 mr-2 animate-spin" />
          Loading incidents...
        </div>
      ) : incidents.length === 0 ? (
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
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              {selectedProject ? `Incidents for ${selectedProject.name}` : "Incidents"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="divide-y divide-border/50 text-sm">
              {incidents.map((incident) => (
                <div
                  key={incident.id}
                  className="flex items-center justify-between gap-4 py-3"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <Link
                        href={`/incidents/${incident.id}`}
                        className="font-medium hover:underline"
                      >
                        {incident.title}
                      </Link>
                      <Badge variant="outline" className="text-[10px] uppercase">
                        {incident.severity}
                      </Badge>
                      <Badge variant="secondary" className="text-[10px] uppercase">
                        {incident.status}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                      {incident.description}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button asChild size="sm" variant="outline" className="h-7 text-xs">
                      <Link href={`/projects/${incident.project_id}/sandbox`}>
                        Open Sandbox
                      </Link>
                    </Button>
                    <Button asChild size="sm" className="h-7 text-xs">
                      <Link href={`/incidents/${incident.id}`}>View</Link>
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
