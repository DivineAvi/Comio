 "use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Activity,
  Terminal,
} from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  listProjects,
  listIncidents,
  getSandbox,
  Incident,
  Project,
  SandboxStatus,
} from "@/lib/api";

type Stats = {
  totalIncidents24h: number;
  activeIncidents: number;
  resolved24h: number;
  avgResolutionMinutes: number | null;
  activeSandboxes: number;
  totalProjects: number;
};

type SandboxRow = {
  project: Project;
  sandbox: SandboxStatus | null;
};

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [sandboxRows, setSandboxRows] = useState<SandboxRow[]>([]);
  const [recentIncidents, setRecentIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        setError(null);
        const { projects } = await listProjects();
        const now = new Date();
        const dayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000);

        let allIncidents: Incident[] = [];
        const sandboxData: SandboxRow[] = await Promise.all(
          projects.map(async (project) => {
            let sandbox: SandboxStatus | null = null;
            try {
              sandbox = await getSandbox(project.id);
            } catch {
              // sandbox might not exist yet
            }
            try {
              const incidentRes = await listIncidents(project.id);
              allIncidents = allIncidents.concat(incidentRes.incidents);
            } catch {
              // incidents may not be configured yet
            }
            return { project, sandbox };
          })
        );

        const recent = allIncidents.filter(
          (i) => new Date(i.created_at) >= dayAgo
        );
        const activeStatuses = [
          "OPEN",
          "INVESTIGATING",
          "DIAGNOSED",
          "FIXING",
        ];
        const activeCount = allIncidents.filter((i) =>
          activeStatuses.includes(i.status)
        ).length;
        const resolvedRecent = allIncidents.filter((i) => {
          const updated = new Date(i.updated_at);
          return (
            ["RESOLVED", "CLOSED"].includes(i.status) && updated >= dayAgo
          );
        });
        const durations = resolvedRecent
          .map(
            (i) =>
              new Date(i.updated_at).getTime() -
              new Date(i.created_at).getTime()
          )
          .filter((ms) => ms > 0);
        const avgResolutionMinutes =
          durations.length > 0
            ? durations.reduce((a, b) => a + b, 0) /
              durations.length /
              60000
            : null;

        const activeSandboxCount = sandboxData.filter(
          (row) => row.sandbox
        ).length;

        const sortedIncidents = [...allIncidents].sort(
          (a, b) =>
            new Date(b.created_at).getTime() -
            new Date(a.created_at).getTime()
        );

        setStats({
          totalIncidents24h: recent.length,
          activeIncidents: activeCount,
          resolved24h: resolvedRecent.length,
          avgResolutionMinutes,
          activeSandboxes: activeSandboxCount,
          totalProjects: projects.length,
        });
        setSandboxRows(sandboxData);
        setRecentIncidents(sortedIncidents.slice(0, 5));
      } catch (e) {
        setError(
          e instanceof Error
            ? e.message
            : "Failed to load dashboard data"
        );
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, []);

  const statCards = [
    {
      title: "Total Incidents (24h)",
      value: stats ? String(stats.totalIncidents24h) : "—",
      icon: AlertTriangle,
      trend: stats
        ? stats.totalIncidents24h === 0
          ? "No incidents in the last 24h"
          : "Incidents detected in the last 24h"
        : "Loading...",
    },
    {
      title: "Active Incidents",
      value: stats ? String(stats.activeIncidents) : "—",
      icon: Activity,
      trend:
        stats && stats.activeIncidents === 0
          ? "All clear"
          : "Requires attention",
    },
    {
      title: "Resolved (24h)",
      value: stats ? String(stats.resolved24h) : "—",
      icon: CheckCircle2,
      trend: stats
        ? stats.resolved24h === 0
          ? "No recent resolutions"
          : "Incidents resolved in the last 24h"
        : "Loading...",
    },
    {
      title: "Avg. Resolution Time",
      value:
        stats && stats.avgResolutionMinutes !== null
          ? `${Math.round(stats.avgResolutionMinutes)} min`
          : "—",
      icon: Clock,
      trend:
        stats && stats.avgResolutionMinutes !== null
          ? "Based on resolved incidents"
          : "Waiting for data",
    },
  ];

  const activeSandboxRows = sandboxRows.filter((r) => r.sandbox);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground mt-1">
          Overview of your projects, deployments, and incident status.
        </p>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {statCards.map((stat) => (
          <Card key={stat.title}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">
                {stat.title}
              </CardTitle>
              <stat.icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">
                {loading ? "…" : stat.value}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {loading ? "Loading..." : stat.trend}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Active Sandboxes */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Active Sandboxes</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <div className="h-2 w-2 rounded-full bg-muted" />
                Loading sandboxes...
              </div>
            ) : activeSandboxRows.length === 0 ? (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <div className="h-2 w-2 rounded-full bg-muted" />
                No sandboxes running. Create or import a project to get started.
              </div>
            ) : (
              <div className="space-y-2 text-sm">
                {activeSandboxRows.slice(0, 3).map(({ project, sandbox }) => (
                  <div
                    key={project.id}
                    className="flex items-center justify-between gap-2"
                  >
                    <div className="flex items-center gap-2">
                      <Terminal className="h-3 w-3 text-muted-foreground" />
                      <Link
                        href={`/projects/${project.id}/sandbox`}
                        className="font-medium hover:underline"
                      >
                        {project.name}
                      </Link>
                    </div>
                    {sandbox && (
                      <Badge variant="outline" className="text-[10px] uppercase">
                        {sandbox.status}
                      </Badge>
                    )}
                  </div>
                ))}
                {activeSandboxRows.length > 3 && (
                  <p className="text-[11px] text-muted-foreground">
                    +{activeSandboxRows.length - 3} more.{" "}
                    <Link
                      href="/sandboxes"
                      className="underline underline-offset-2"
                    >
                      View all
                    </Link>
                  </p>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Deployments (placeholder – real data once deployment API is wired) */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Deployments</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <div className="h-2 w-2 rounded-full bg-muted" />
              No active deployments. Deploy a project from its sandbox.
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Recent Incidents */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-lg">Recent Incidents</CardTitle>
          <Badge variant="secondary">
            {stats ? `${stats.totalIncidents24h} in last 24h` : "Loading..."}
          </Badge>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">
              Loading recent incidents...
            </p>
          ) : recentIncidents.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No incidents yet. Once you deploy a project, Comio automatically
              monitors it and surfaces issues here in real-time.
            </p>
          ) : (
            <div className="divide-y divide-border/50 text-sm">
              {recentIncidents.map((incident) => (
                <div
                  key={incident.id}
                  className="flex items-center justify-between gap-4 py-2"
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
                  <Link
                    href={`/projects/${incident.project_id}/sandbox`}
                    className="text-xs underline underline-offset-2 text-muted-foreground"
                  >
                    Open sandbox
                  </Link>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
