import Link from "next/link";
import ReactMarkdown from "react-markdown";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { getIncident } from "@/lib/api";

export default async function IncidentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const incident = await getIncident(id);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold tracking-tight">
              {incident.title}
            </h1>
            <Badge variant="outline" className="uppercase text-[10px]">
              {incident.severity}
            </Badge>
            <Badge variant="secondary" className="uppercase text-[10px]">
              {incident.status}
            </Badge>
          </div>
          <p className="text-muted-foreground mt-1">
            {incident.description ||
              "Incident details, AI diagnosis, and proposed fixes."}
          </p>
        </div>
        <Button variant="outline" asChild>
          <Link href={`/projects/${incident.project_id}/sandbox`}>
            Open in Sandbox
          </Link>
        </Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* AI Diagnosis */}
        <Card>
          <CardHeader>
            <CardTitle>AI Diagnosis</CardTitle>
          </CardHeader>
          <CardContent>
            {incident.diagnosis ? (
              <div className="space-y-3 text-sm">
                <div className="text-xs text-muted-foreground">
                  Root cause category:{" "}
                  <span className="font-medium">
                    {incident.diagnosis.category}
                  </span>{" "}
                  · Confidence{" "}
                  <span className="font-medium">
                    {(incident.diagnosis.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <ReactMarkdown>{incident.diagnosis.explanation}</ReactMarkdown>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                AI diagnosis will appear here once the RCA engine analyzes this
                incident.
              </p>
            )}
          </CardContent>
        </Card>

        {/* Proposed Fix */}
        <Card>
          <CardHeader>
            <CardTitle>Proposed Fix</CardTitle>
          </CardHeader>
          <CardContent>
            {incident.remediation ? (
              <div className="space-y-3 text-sm">
                {incident.remediation.explanation && (
                  <p className="text-muted-foreground">
                    {incident.remediation.explanation}
                  </p>
                )}
                {incident.remediation.diff && (
                  <div className="rounded-md bg-muted/40 border border-border/40 max-h-72 overflow-auto">
                    <pre className="text-xs p-3 whitespace-pre">
                      {incident.remediation.diff}
                    </pre>
                  </div>
                )}
                {incident.remediation.pr_url && (
                  <p className="text-xs text-muted-foreground">
                    PR:&nbsp;
                    <a
                      href={incident.remediation.pr_url}
                      target="_blank"
                      rel="noreferrer"
                      className="underline"
                    >
                      {incident.remediation.pr_url}
                    </a>
                  </p>
                )}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                The fix generator will propose code changes here for review and
                approval.
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <Separator />

      {/* Timeline (placeholder for now) */}
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
