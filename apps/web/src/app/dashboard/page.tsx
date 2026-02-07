import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Activity,
} from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const stats = [
  {
    title: "Total Incidents (24h)",
    value: "—",
    icon: AlertTriangle,
    trend: "Waiting for data",
  },
  {
    title: "Active Incidents",
    value: "0",
    icon: Activity,
    trend: "All clear",
  },
  {
    title: "Resolved (24h)",
    value: "—",
    icon: CheckCircle2,
    trend: "Waiting for data",
  },
  {
    title: "Avg. Resolution Time",
    value: "—",
    icon: Clock,
    trend: "Waiting for data",
  },
];

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground mt-1">
          Overview of your projects, deployments, and incident status.
        </p>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <Card key={stat.title}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">
                {stat.title}
              </CardTitle>
              <stat.icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stat.value}</div>
              <p className="text-xs text-muted-foreground mt-1">
                {stat.trend}
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
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <div className="h-2 w-2 rounded-full bg-muted" />
              No sandboxes running. Create or import a project to get started.
            </div>
          </CardContent>
        </Card>

        {/* Deployments */}
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
          <Badge variant="secondary">0 new</Badge>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            No incidents yet. Once you deploy a project, Comio automatically
            monitors it and surfaces issues here in real-time.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
