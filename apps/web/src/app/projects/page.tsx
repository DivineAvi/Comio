"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { FolderGit2, Sparkles, GitBranch, Loader2, Trash2 } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Project,
  ProjectCreatePayload,
  ProjectImportPayload,
  listProjects,
  createProject,
  importProject,
  getSandbox,
  deleteProject,
  updateProject,
} from "@/lib/api";

type ProjectWithSandbox = Project & {
  sandboxStatus?: string;
};

export default function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectWithSandbox[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isImportOpen, setIsImportOpen] = useState(false);
  const [editingProject, setEditingProject] = useState<ProjectWithSandbox | null>(null);

  const [createForm, setCreateForm] = useState<ProjectCreatePayload>({
    name: "",
    description: "",
    project_type: "api",
  });
  const [importForm, setImportForm] = useState<ProjectImportPayload>({
    repo_url: "",
    name: "",
    description: "",
  });

  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let mounted = true;

    async function load(isInitial = false) {
      if (isInitial) setLoading(true);
      try {
        const data = await listProjects();
        if (!mounted) return;

        const items: ProjectWithSandbox[] = await Promise.all(
          data.projects.map(async (p) => {
            try {
              const sandbox = await getSandbox(p.id);
              return { ...p, sandboxStatus: sandbox.status };
            } catch {
              return { ...p, sandboxStatus: "none" };
            }
          })
        );
        if (mounted) {
          setProjects(items);
          setError(null);
        }
      } catch (e) {
        if (mounted && isInitial) {
          setError(e instanceof Error ? e.message : "Failed to load projects");
        }
      } finally {
        if (mounted && isInitial) setLoading(false);
      }
    }

    void load(true);

    const interval = setInterval(() => {
      void load(false);
    }, 5000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  async function handleCreateProject() {
    if (!createForm.name.trim() || !createForm.description?.trim()) {
      setError("Name and description are required to create a project.");
      return;
    }

    const payload: ProjectCreatePayload = {
      name: createForm.name.trim(),
      description: createForm.description.trim(),
      project_type: createForm.project_type || "other",
    };

    try {
      setSubmitting(true);
      const project = await createProject(payload);
      setProjects((prev) =>
        prev
          ? [{ ...project, sandboxStatus: "creating" }, ...prev]
          : [{ ...project, sandboxStatus: "creating" }]
      );
      setIsCreateOpen(false);
      setCreateForm({ name: "", description: "", project_type: "api" });
      window.location.href = `/projects/${project.id}/sandbox`;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create project");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleImportProject() {
    try {
      setSubmitting(true);
      const project = await importProject(importForm);
      setProjects((prev) =>
        prev
          ? [{ ...project, sandboxStatus: "creating" }, ...prev]
          : [{ ...project, sandboxStatus: "creating" }]
      );
      setIsImportOpen(false);
      setImportForm({ repo_url: "", name: "", description: "" });
      window.location.href = `/projects/${project.id}/sandbox`;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to import project");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(projectId: string) {
    if (!confirm("Are you sure you want to delete this project and its sandbox permanently?")) return;
    try {
      setSubmitting(true);
      await deleteProject(projectId);
      setProjects((prev) => prev?.filter((p) => p.id !== projectId) || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete project");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleUpdateProject() {
    if (!editingProject) return;
    try {
      setSubmitting(true);
      const updated = await updateProject(editingProject.id, {
        name: editingProject.name,
        description: editingProject.description || "",
      });
      setProjects((prev) =>
        prev?.map((p) => (p.id === updated.id ? { ...p, ...updated } : p)) || []
      );
      setEditingProject(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update project");
    } finally {
      setSubmitting(false);
    }
  }

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
          <Button variant="outline" onClick={() => setIsImportOpen(true)}>
            <GitBranch className="h-4 w-4 mr-2" />
            Import Repo
          </Button>
          <Button onClick={() => setIsCreateOpen(true)}>
            <Sparkles className="h-4 w-4 mr-2" />
            Create Project
          </Button>
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-16 text-muted-foreground">
          <Loader2 className="h-5 w-5 mr-2 animate-spin" />
          Loading projects...
        </div>
      ) : projects && projects.length > 0 ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <Card key={project.id}>
              <CardContent className="p-4 space-y-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <Link
                        href={`/projects/${project.id}`}
                        className="text-base font-medium hover:underline"
                      >
                        {project.name}
                      </Link>
                      <button
                        className="text-xs text-muted-foreground hover:text-foreground underline underline-offset-2"
                        onClick={(e) => {
                          e.preventDefault();
                          setEditingProject(project);
                        }}
                      >
                        Edit
                      </button>
                    </div>
                    <p className="text-xs text-muted-foreground line-clamp-2">
                      {project.description || "No description"}
                    </p>
                  </div>
                  <Badge variant="outline" className="text-xs">
                    {project.origin === "cloned" ? "Imported" : "Created"}
                  </Badge>
                </div>
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>Type: {project.project_type || "unknown"}</span>
                  <span>
                    Sandbox:{" "}
                    <span className="font-medium">
                      {project.sandboxStatus ?? "unknown"}
                    </span>
                  </span>
                </div>
                <div className="flex justify-between items-center mt-2">
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-8 text-xs text-destructive hover:text-destructive hover:bg-destructive/10"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      handleDelete(project.id);
                    }}
                    disabled={submitting}
                  >
                    <Trash2 className="h-3.5 w-3.5 mr-1" />
                    Delete
                  </Button>
                  <Button
                    size="sm"
                    asChild
                    variant="outline"
                    className="h-8 text-xs"
                  >
                    <Link href={`/projects/${project.id}/sandbox`}>
                      Open Sandbox
                    </Link>
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
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
              <Button variant="outline" onClick={() => setIsImportOpen(true)}>
                <GitBranch className="h-4 w-4 mr-2" />
                Import Repository
              </Button>
              <Button onClick={() => setIsCreateOpen(true)}>
                <Sparkles className="h-4 w-4 mr-2" />
                Create with AI
              </Button>
            </div>
          </CardContent>
        </Card>
      )
      }

      {
        isCreateOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur">
            <div className="w-full max-w-md rounded-lg border bg-card p-6 shadow-lg space-y-4">
              <div className="space-y-1">
                <h2 className="text-lg font-semibold">Create Project</h2>
                <p className="text-sm text-muted-foreground">
                  Describe a new project. Comio will create a sandbox and you can
                  start building via chat.
                </p>
              </div>
              <div className="space-y-3">
                <div className="space-y-1">
                  <label className="text-sm font-medium">Name</label>
                  <Input
                    value={createForm.name}
                    onChange={(e) =>
                      setCreateForm((f) => ({ ...f, name: e.target.value }))
                    }
                    placeholder="Recipe API"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-medium">Description</label>
                  <Input
                    value={createForm.description ?? ""}
                    onChange={(e) =>
                      setCreateForm((f) => ({
                        ...f,
                        description: e.target.value,
                      }))
                    }
                    placeholder="A REST API for managing recipes with user auth"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-medium">Project Type</label>
                  <Input
                    value={createForm.project_type}
                    onChange={(e) =>
                      setCreateForm((f) => ({
                        ...f,
                        project_type: e.target.value,
                      }))
                    }
                    placeholder="api | web | fullstack"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button
                  variant="outline"
                  onClick={() => setIsCreateOpen(false)}
                  disabled={submitting}
                >
                  Cancel
                </Button>
                <Button onClick={handleCreateProject} disabled={submitting}>
                  {submitting && (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  )}
                  Create &amp; Open Sandbox
                </Button>
              </div>
            </div>
          </div>
        )
      }

      {
        isImportOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur">
            <div className="w-full max-w-md rounded-lg border bg-card p-6 shadow-lg space-y-4">
              <div className="space-y-1">
                <h2 className="text-lg font-semibold">Import Repository</h2>
                <p className="text-sm text-muted-foreground">
                  Import an existing GitHub repository. Comio will clone it into a
                  sandbox for AI-powered editing.
                </p>
              </div>
              <div className="space-y-3">
                <div className="space-y-1">
                  <label className="text-sm font-medium">Repository URL</label>
                  <Input
                    value={importForm.repo_url}
                    onChange={(e) =>
                      setImportForm((f) => ({
                        ...f,
                        repo_url: e.target.value,
                      }))
                    }
                    placeholder="https://github.com/user/my-api"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-medium">
                    Name (optional)
                  </label>
                  <Input
                    value={importForm.name ?? ""}
                    onChange={(e) =>
                      setImportForm((f) => ({
                        ...f,
                        name: e.target.value,
                      }))
                    }
                    placeholder="My API"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-sm font-medium">
                    Description (optional)
                  </label>
                  <Input
                    value={importForm.description ?? ""}
                    onChange={(e) =>
                      setImportForm((f) => ({
                        ...f,
                        description: e.target.value,
                      }))
                    }
                    placeholder="Short description for this project"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button
                  variant="outline"
                  onClick={() => setIsImportOpen(false)}
                  disabled={submitting}
                >
                  Cancel
                </Button>
                <Button onClick={handleImportProject} disabled={submitting}>
                  {submitting && (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  )}
                  Import &amp; Open Sandbox
                </Button>
              </div>
            </div>
          </div>
        )
      }

      {
        editingProject && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur">
            <div className="w-full max-w-md rounded-lg border bg-card p-6 shadow-lg space-y-4">
              <div className="space-y-1">
                <h2 className="text-lg font-semibold">Edit Project</h2>
                <p className="text-sm text-muted-foreground">
                  Update the name and description of your project.
                </p>
              </div>
              <div className="space-y-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium">Name</label>
                  <Input
                    placeholder="e.g. backend-api"
                    value={editingProject.name}
                    onChange={(e) =>
                      setEditingProject({ ...editingProject, name: e.target.value })
                    }
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium">Description</label>
                  <Input
                    placeholder="e.g. A fast api wrapper"
                    value={editingProject.description || ""}
                    onChange={(e) =>
                      setEditingProject({
                        ...editingProject,
                        description: e.target.value,
                      })
                    }
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button
                  variant="outline"
                  onClick={() => setEditingProject(null)}
                  disabled={submitting}
                >
                  Cancel
                </Button>
                <Button onClick={handleUpdateProject} disabled={submitting}>
                  {submitting ? "Saving..." : "Save Changes"}
                </Button>
              </div>
            </div>
          </div>
        )
      }
    </div >
  );
}
