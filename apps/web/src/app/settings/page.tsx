"use client";

import { useEffect, useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { getCurrentUser, updateLlmSettings, User } from "@/lib/api";

export default function SettingsPage() {
  const [user, setUser] = useState<User | null>(null);
  const [provider, setProvider] = useState("openai");
  const [llmApiKey, setLlmApiKey] = useState("");
  const [llmSaved, setLlmSaved] = useState(false);
  const [llmSaving, setLlmSaving] = useState(false);
  const [llmError, setLlmError] = useState<string | null>(null);
  const [sandboxCpu, setSandboxCpu] = useState("1");
  const [sandboxMemory, setSandboxMemory] = useState("512");
  const [sandboxSaved, setSandboxSaved] = useState(false);
  const [githubToken, setGithubToken] = useState("");
  const [githubSaving, setGithubSaving] = useState(false);
  const [githubError, setGithubError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const me = await getCurrentUser();
        setUser(me);
        setProvider(
          me.llm_provider ??
            process.env.NEXT_PUBLIC_DEFAULT_LLM_PROVIDER ??
            "openai"
        );
      } catch {
        // ignore; user may not be logged in
      }
    }
    void load();
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const cpu =
      window.localStorage.getItem("comio_sandbox_cpu") ??
      "1";
    const mem =
      window.localStorage.getItem("comio_sandbox_memory") ??
      "512";
    setSandboxCpu(cpu);
    setSandboxMemory(mem);
  }, []);

  async function handleSaveLLM() {
    if (!provider.trim() || !llmApiKey.trim()) return;
    try {
      setLlmSaving(true);
      setLlmError(null);
      const updated = await updateLlmSettings(provider.trim(), llmApiKey.trim());
      setUser(updated);
      setLlmApiKey("");
      setLlmSaved(true);
      setTimeout(() => setLlmSaved(false), 2000);
    } catch (e) {
      setLlmError(
        e instanceof Error ? e.message : "Failed to save LLM settings"
      );
    } finally {
      setLlmSaving(false);
    }
  }

  function handleSaveSandboxDefaults() {
    if (typeof window !== "undefined") {
      window.localStorage.setItem("comio_sandbox_cpu", sandboxCpu);
      window.localStorage.setItem("comio_sandbox_memory", sandboxMemory);
    }
    setSandboxSaved(true);
    setTimeout(() => setSandboxSaved(false), 2000);
  }

  async function handleConnectGithub() {
    if (!githubToken.trim()) return;
    try {
      setGithubSaving(true);
      setGithubError(null);
      const res = await fetch(
        `${
          process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
        }/auth/github/connect`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(typeof window !== "undefined" &&
            window.localStorage.getItem("comio_token")
              ? {
                  Authorization: `Bearer ${window.localStorage.getItem(
                    "comio_token"
                  )}`,
                }
              : {}),
          },
          body: JSON.stringify({
            personal_access_token: githubToken.trim(),
          }),
        }
      );
      if (!res.ok) {
        let message = `GitHub connection failed (${res.status})`;
        try {
          const data = await res.json();
          if (data?.detail && typeof data.detail === "string") {
            message = data.detail;
          }
        } catch {
          // ignore
        }
        throw new Error(message);
      }
      const updatedUser = (await res.json()) as User;
      setUser(updatedUser);
      setGithubToken("");
    } catch (e) {
      setGithubError(
        e instanceof Error ? e.message : "Failed to connect to GitHub"
      );
    } finally {
      setGithubSaving(false);
    }
  }

  const githubConnected = !!user?.github_username;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground mt-1">
          Configure your Comio instance, LLM providers, and preferences.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">LLM Provider</CardTitle>
              <Badge variant="outline" className="text-xs uppercase">
                {provider}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Configure your preferred LLM provider (OpenAI, Anthropic, or
              Ollama) and API keys for AI-powered diagnosis and code generation.
            </p>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">
                Provider
              </label>
              <Input
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                placeholder="openai | anthropic | ollama"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">
                API key (stored on the server for your user)
              </label>
              <Input
                type="password"
                value={llmApiKey}
                onChange={(e) => setLlmApiKey(e.target.value)}
                placeholder="sk-..."
              />
            </div>
            <Button
              size="sm"
              onClick={handleSaveLLM}
              disabled={llmSaving || !provider.trim() || !llmApiKey.trim()}
            >
              {llmSaving ? "Saving..." : "Save LLM settings"}
            </Button>
            {llmError && (
              <p className="text-[11px] text-destructive mt-1">{llmError}</p>
            )}
            {llmSaved && !llmError && (
              <p className="text-[11px] text-muted-foreground">
                Saved to your account. New chats will use this key from the database.
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">GitHub Integration</CardTitle>
              <Badge
                variant={githubConnected ? "secondary" : "outline"}
                className="text-xs"
              >
                {githubConnected
                  ? `Connected as ${user?.github_username}`
                  : "Not connected"}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Connect your GitHub account to enable repository access, sandbox
              creation, and automatic PR generation for fixes.
            </p>
            <div className="space-y-1">
              <label className="text-xs font-medium text-muted-foreground">
                GitHub Personal Access Token (repo scope)
              </label>
              <Input
                type="password"
                value={githubToken}
                onChange={(e) => setGithubToken(e.target.value)}
                placeholder="ghp_..."
              />
            </div>
            <Button
              size="sm"
              onClick={handleConnectGithub}
              disabled={githubSaving || !githubToken.trim()}
            >
              {githubSaving ? "Connecting..." : "Connect GitHub"}
            </Button>
            {githubError && (
              <p className="text-[11px] text-destructive mt-1">
                {githubError}
              </p>
            )}
            <p className="text-[11px] text-muted-foreground">
              We verify this token with GitHub and store it securely on the
              server for PR creation. You can rotate or revoke it from your
              GitHub settings at any time.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Sandbox Defaults</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Set default resource limits (CPU, memory, disk) for new project
              sandboxes. These values are stored locally in your browser for now
              and will be wired to backend policies later.
            </p>
            <div className="flex gap-3">
              <div className="space-y-1 flex-1">
                <label className="text-xs font-medium text-muted-foreground">
                  CPU cores
                </label>
                <Input
                  value={sandboxCpu}
                  onChange={(e) => setSandboxCpu(e.target.value)}
                  placeholder="1"
                />
              </div>
              <div className="space-y-1 flex-1">
                <label className="text-xs font-medium text-muted-foreground">
                  Memory (MB)
                </label>
                <Input
                  value={sandboxMemory}
                  onChange={(e) => setSandboxMemory(e.target.value)}
                  placeholder="512"
                />
              </div>
            </div>
            <Button size="sm" onClick={handleSaveSandboxDefaults}>
              Save defaults
            </Button>
            {sandboxSaved && (
              <p className="text-[11px] text-muted-foreground">
                Saved locally for this browser.
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Notifications</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Configure Slack integration, email notifications, and alert
              thresholds for incidents. This panel documents your preferences;
              backend webhooks and Slack apps are configured in the API and
              infrastructure.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
