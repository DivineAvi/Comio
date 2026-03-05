"use client";

import { use, useEffect, useMemo, useRef, useState } from "react";
import {
  Send,
  FolderTree,
  GitBranch,
  RefreshCw,
  Play,
  Loader2,
  ChevronRight,
  ChevronDown,
  Plus,
  X,
  ExternalLink,
  PauseCircle,
  PlayCircle,
} from "lucide-react";
import ReactMarkdown from "react-markdown";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  ChatEvent,
  ChatMessage,
  FileEntry,
  createChatSession,
  getChatMessages,
  getSandbox,
  listChatSessions,
  listSandboxFiles,
  readSandboxFile,
  sendChatMessage,
  getSandboxDiff,
  createSandboxPullRequest,
  startSandbox,
  stopSandbox,
  runSandboxProcess,
  deleteChatSession,
} from "@/lib/api";

type SandboxStatusType = "running" | "stopped" | "creating" | "error" | "none" | string;

interface SandboxPageProps {
  params: Promise<{ id: string }>;
}

interface FileNode {
  name: string;
  path: string;
  isDirectory: boolean;
  children?: FileNode[];
}

function buildFileTree(entries: FileEntry[]): FileNode[] {
  type NodeWithMap = FileNode & { childrenMap?: Record<string, NodeWithMap> };

  const root: Record<string, NodeWithMap> = {};

  for (const entry of entries) {
    const parts = entry.path.split("/");
    let level = root;
    let currentPath = "";

    parts.forEach((part, index) => {
      currentPath = currentPath ? `${currentPath}/${part}` : part;
      const isLeaf = index === parts.length - 1;

      if (!level[part]) {
        level[part] = {
          name: part,
          path: currentPath,
          isDirectory: isLeaf ? entry.is_directory : true,
          children: [],
          childrenMap: {},
        };
      }

      const node = level[part];

      if (!isLeaf && !node.isDirectory) {
        node.isDirectory = true;
      }

      if (!isLeaf) {
        if (!node.childrenMap) {
          node.childrenMap = {};
        }
        level = node.childrenMap;
      }
    });
  }

  function toArray(map: Record<string, NodeWithMap>): FileNode[] {
    const nodes = Object.values(map).map((node) => ({
      name: node.name,
      path: node.path,
      isDirectory: node.isDirectory,
      children: node.childrenMap ? toArray(node.childrenMap) : [],
    }));

    nodes.sort((a, b) => {
      if (a.isDirectory && !b.isDirectory) return -1;
      if (!a.isDirectory && b.isDirectory) return 1;
      return a.name.localeCompare(b.name);
    });

    return nodes;
  }

  return toArray(root);
}

function FileTree({
  nodes,
  onSelectFile,
  expanded,
  onToggleDir,
}: {
  nodes: FileNode[];
  onSelectFile: (path: string) => void;
  expanded: Record<string, boolean>;
  onToggleDir: (path: string) => void;
}) {
  return (
    <div className="space-y-1 text-xs">
      {nodes.map((node) => (
        <div key={node.path}>
          <button
            type="button"
            className="flex w-full items-center gap-1 rounded px-1 py-0.5 text-left hover:bg-muted"
            onClick={() => {
              if (node.isDirectory) {
                onToggleDir(node.path);
              } else {
                onSelectFile(node.path);
              }
            }}
          >
            {node.isDirectory ? (
              <>
                {expanded[node.path] ? (
                  <ChevronDown className="h-3 w-3 shrink-0" />
                ) : (
                  <ChevronRight className="h-3 w-3 shrink-0" />
                )}
                <span className="font-medium">{node.name}/</span>
              </>
            ) : (
              <span className="pl-4">{node.name}</span>
            )}
          </button>
          {node.isDirectory &&
            expanded[node.path] &&
            node.children &&
            node.children.length > 0 && (
              <div className="ml-3 border-l border-border/40 pl-2">
                <FileTree
                  nodes={node.children}
                  onSelectFile={onSelectFile}
                  expanded={expanded}
                  onToggleDir={onToggleDir}
                />
              </div>
            )}
        </div>
      ))}
    </div>
  );
}

export default function SandboxPage({ params }: SandboxPageProps) {
  const { id } = use(params);

  const [sandboxStatus, setSandboxStatus] = useState<SandboxStatusType>("none");
  const [sandboxLoading, setSandboxLoading] = useState(true);

  const [sessions, setSessions] = useState<
    { id: string; title: string; created_at: string }[]
  >([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [messageInput, setMessageInput] = useState("");
  const [chatError, setChatError] = useState<string | null>(null);
  const [creatingSession, setCreatingSession] = useState(false);

  const [files, setFiles] = useState<FileEntry[] | null>(null);
  const [fileTree, setFileTree] = useState<FileNode[] | null>(null);
  const [selectedFilePath, setSelectedFilePath] = useState<string | null>(null);
  const [selectedFileContent, setSelectedFileContent] = useState<string | null>(null);
  const [fileLoading, setFileLoading] = useState(false);

  const [diffOpen, setDiffOpen] = useState(false);
  const [diffContent, setDiffContent] = useState<string | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffError, setDiffError] = useState<string | null>(null);

  const [prCreating, setPrCreating] = useState(false);
  const [prResult, setPrResult] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const [expandedDirs, setExpandedDirs] = useState<Record<string, boolean>>({});

  const [previewOpen, setPreviewOpen] = useState(false);
  const [runCommand, setRunCommand] = useState("python -m http.server 8000");
  const [runPort, setRunPort] = useState("8000");
  const [previewRunning, setPreviewRunning] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth", block: "end" });
    }
  }, [messages.length]);

  function toggleDir(path: string) {
    setExpandedDirs((prev) => ({
      ...prev,
      [path]: prev[path] === undefined ? true : !prev[path],
    }));
  }

  useEffect(() => {
    async function initialize() {
      try {
        const [sandbox, sessionList] = await Promise.all([
          getSandbox(id).catch(() => null),
          listChatSessions(id).catch(() => ({ sessions: [], total: 0 })),
        ]);

        if (sandbox) {
          setSandboxStatus(sandbox.status);
        } else {
          setSandboxStatus("none");
        }

        setSessions(sessionList.sessions);

        let sessionId: string | null = null;
        if (sessionList.sessions.length > 0) {
          sessionId = sessionList.sessions[0].id;
        } else if (sandbox && sandbox.status === "running") {
          const created = await createChatSession(id, "New Chat");
          sessionId = created.id;
          setSessions([{ id: created.id, title: created.title, created_at: created.created_at }]);
        }

        if (sessionId) {
          setActiveSessionId(sessionId);
          const history = await getChatMessages(id, sessionId);
          setMessages(history.messages);
        }

        if (sandbox && sandbox.status === "running") {
          try {
            const res = await listSandboxFiles(id, ".", true);
            setFiles(res.entries);
          } catch {
            // ignore file loading errors on init
          }
        }
      } finally {
        setSandboxLoading(false);
      }
    }

    void initialize();
  }, [id]);

  useEffect(() => {
    // Realtime polling
    const interval = setInterval(() => {
      refreshStatus();
    }, 5000); // Check every 5 seconds

    return () => clearInterval(interval);
  }, [id]);

  useEffect(() => {
    if (files) {
      const tree = buildFileTree(files);
      setFileTree(tree);
    } else {
      setFileTree(null);
    }
  }, [files]);

  const canChat = sandboxStatus === "running" && !!activeSessionId;

  async function refreshStatus() {
    try {
      setSandboxLoading(true);
      const sandbox = await getSandbox(id);
      setSandboxStatus(sandbox.status);
      if (sandbox.status === "running") {
        const res = await listSandboxFiles(id, ".", true);
        setFiles(res.entries);
      }
    } catch {
      setSandboxStatus("error");
    } finally {
      setSandboxLoading(false);
    }
  }

  async function refreshFiles() {
    if (sandboxStatus !== "running") return;
    try {
      const res = await listSandboxFiles(id, ".", true);
      setFiles(res.entries);
    } catch {
      // silent
    }
  }

  async function handleStartSandbox() {
    try {
      setSandboxLoading(true);
      await startSandbox(id);
      await refreshStatus();
      if (!activeSessionId) {
        const created = await createChatSession(id, "New Chat");
        setSessions((prev) => [
          { id: created.id, title: created.title, created_at: created.created_at },
          ...prev,
        ]);
        setActiveSessionId(created.id);
      }
    } catch (e) {
      setChatError(e instanceof Error ? e.message : "Failed to start sandbox");
    } finally {
      setSandboxLoading(false);
    }
  }

  async function handleNewSession() {
    if (sandboxStatus !== "running") return;
    try {
      setCreatingSession(true);
      setChatError(null);
      const sessionNum = sessions.length + 1;
      const created = await createChatSession(id, `Chat ${sessionNum}`);
      setSessions((prev) => [
        ...prev,
        { id: created.id, title: created.title, created_at: created.created_at },
      ]);
      setActiveSessionId(created.id);
      setMessages([]);
    } catch (e) {
      setChatError(e instanceof Error ? e.message : "Failed to create session");
    } finally {
      setCreatingSession(false);
    }
  }

  async function handleSendMessage() {
    if (!canChat || !messageInput.trim() || !activeSessionId) return;
    const content = messageInput.trim();
    setMessageInput("");
    setSending(true);
    setChatError(null);

    const optimistic: ChatMessage = {
      id: `local-${Date.now()}`,
      role: "user",
      content,
      created_at: new Date().toISOString(),
      tool_calls: undefined,
      files_modified: undefined,
    };
    setMessages((prev) => [...prev, optimistic]);

    try {
      const res = await sendChatMessage(id, activeSessionId, content);

      const events: ChatEvent[] = res.events;
      const assistantText = events
        .filter((e) => e.type === "text" && e.content)
        .map((e) => e.content)
        .join("");
      const doneEvent = events.find((e) => e.type === "done");
      const filesModified = doneEvent?.files_modified ?? [];

      if (assistantText) {
        const assistantMessage: ChatMessage = {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          content: assistantText,
          created_at: new Date().toISOString(),
          tool_calls: undefined,
          files_modified: filesModified,
        };
        setMessages((prev) => [...prev, assistantMessage]);

        // Always refresh the file tree after an AI response — the agent
        // may have created/modified files regardless of files_modified list
        try {
          const resFiles = await listSandboxFiles(id, ".", true);
          setFiles(resFiles.entries);
        } catch {
          // best-effort
        }
      }
    } catch (e) {
      setChatError(
        e instanceof Error ? e.message : "Failed to send message to sandbox AI"
      );
    } finally {
      setSending(false);
    }
  }

  async function handleSelectSession(sessionId: string) {
    setActiveSessionId(sessionId);
    try {
      const history = await getChatMessages(id, sessionId);
      setMessages(history.messages);
    } catch (e) {
      setChatError(
        e instanceof Error ? e.message : "Failed to load chat history"
      );
    }
  }

  async function handleDeleteSession(e: React.MouseEvent, sessionId: string) {
    e.stopPropagation();
    if (!confirm("Delete this chat session permanently?")) return;

    try {
      await deleteChatSession(id, sessionId);
      const remaining = sessions.filter(s => s.id !== sessionId);
      setSessions(remaining);

      if (activeSessionId === sessionId) {
        if (remaining.length > 0) {
          handleSelectSession(remaining[0].id);
        } else {
          setActiveSessionId(null);
          setMessages([]);
        }
      }
    } catch (err) {
      setChatError(err instanceof Error ? err.message : "Failed to delete session");
    }
  }

  async function handleSelectFile(path: string) {
    setSelectedFilePath(path);
    setSelectedFileContent(null);
    setFileLoading(true);
    try {
      const res = await readSandboxFile(id, path);
      setSelectedFileContent(res.content);
    } catch (e) {
      setSelectedFileContent(
        e instanceof Error ? `Failed to load file: ${e.message}` : "Failed to load file"
      );
    } finally {
      setFileLoading(false);
    }
  }

  async function handleToggleSandbox() {
    try {
      setSandboxLoading(true);
      if (sandboxStatus === "running") {
        await stopSandbox(id);
      } else {
        await startSandbox(id);
      }
      await refreshStatus();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to toggle sandbox");
    } finally {
      setSandboxLoading(false);
    }
  }

  async function handleRunPreview() {
    if (!runCommand || !runPort) return;
    try {
      setPreviewRunning(true);
      await runSandboxProcess(id, runCommand);
      // Give it a couple seconds to start up before showing iframe
      setTimeout(() => {
        const token = window.localStorage.getItem("comio_token") || "";
        setPreviewUrl(`/projects/${id}/sandbox/proxy/${runPort}/?token=${token}`);
        setPreviewRunning(false);
      }, 3000);
    } catch (e) {
      alert(e instanceof Error ? e.message : "Failed to run project");
      setPreviewRunning(false);
    }
  }

  const statusBadge = useMemo(() => {
    const base = "text-xs border border-border/40";
    switch (sandboxStatus) {
      case "running":
        return (
          <Badge
            variant="outline"
            className={`${base} bg-emerald-500/10 text-emerald-500 border-emerald-500/30`}
          >
            Running
          </Badge>
        );
      case "stopped":
        return (
          <Badge
            variant="outline"
            className={`${base} bg-red-500/10 text-red-500 border-red-500/30`}
          >
            Stopped
          </Badge>
        );
      case "creating":
        return (
          <Badge
            variant="outline"
            className={`${base} bg-amber-500/10 text-amber-500 border-amber-500/30`}
          >
            Provisioning
          </Badge>
        );
      default:
        return (
          <Badge variant="outline" className={base}>
            {sandboxStatus}
          </Badge>
        );
    }
  }, [sandboxStatus]);

  async function handleViewDiff() {
    setDiffOpen(true);
    setDiffContent(null);
    setDiffLoading(true);
    setDiffError(null);
    try {
      const res = await getSandboxDiff(id);
      setDiffContent(res.diff && res.diff.trim() ? res.diff : "No changes in this sandbox yet.\n\nFiles created or modified by Comio will appear here as a git diff.");
    } catch (e) {
      setDiffError(e instanceof Error ? e.message : "Failed to load diff");
    } finally {
      setDiffLoading(false);
    }
  }

  async function handleCreatePr() {
    setPrCreating(true);
    setPrResult(null);
    try {
      const title = `Comio sandbox changes for project ${id}`;
      const body =
        "This PR was created from the Comio sandbox to apply AI-generated code changes.";
      const res = await createSandboxPullRequest(id, title, body);
      setPrResult(res.pr_url);
    } catch (e) {
      setPrResult(
        e instanceof Error ? `Failed to create PR: ${e.message}` : "Failed to create PR"
      );
    } finally {
      setPrCreating(false);
    }
  }

  return (
    <div className="-m-6 flex h-[calc(100vh-3.5rem-2rem)] gap-4 overflow-hidden px-4 pt-2 pb-2">
      {/* Left Panel — File Browser */}
      <Card className="w-64 flex-shrink-0 flex flex-col min-h-0">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <FolderTree className="h-4 w-4" />
              Files
            </CardTitle>
            <div className="flex items-center gap-1">
              <Badge variant="outline" className="text-xs flex items-center gap-1">
                <GitBranch className="h-3 w-3" />
                main
              </Badge>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={refreshFiles}
                title="Refresh file tree"
                disabled={sandboxStatus !== "running"}
              >
                <RefreshCw className="h-3 w-3" />
              </Button>
            </div>
          </div>
        </CardHeader>
        <Separator />
        <CardContent className="flex-1 min-h-0 p-3">
          <ScrollArea className="h-full">
            {sandboxStatus !== "running" ? (
              <p className="text-xs text-muted-foreground py-8 text-center">
                Start the sandbox to browse project files.
              </p>
            ) : !fileTree || fileTree.length === 0 ? (
              <p className="text-xs text-muted-foreground py-8 text-center">
                No files yet. Ask Comio to scaffold your project.
              </p>
            ) : (
              <FileTree
                nodes={fileTree}
                onSelectFile={handleSelectFile}
                expanded={expandedDirs}
                onToggleDir={toggleDir}
              />
            )}
          </ScrollArea>
        </CardContent>
      </Card>

      {/* Right Panel — Chat */}
      <Card className="flex-1 flex flex-col min-h-0 min-w-0 overflow-hidden">
        <CardHeader className="p-3 flex-shrink-0">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <CardTitle className="text-sm font-medium">
                Sandbox Chat
              </CardTitle>
              {statusBadge}
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={refreshStatus}
                disabled={sandboxLoading}
              >
                <RefreshCw className="h-3.5 w-3.5" />
              </Button>
              {sandboxStatus === "running" ? (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8"
                  onClick={handleToggleSandbox}
                  disabled={sandboxLoading || sandboxStatus !== "running"}
                >
                  <PauseCircle className="h-3 w-3 mr-1.5" />
                  Pause
                </Button>
              ) : sandboxStatus === "stopped" ? (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8"
                  onClick={handleToggleSandbox}
                  disabled={sandboxLoading}
                >
                  <PlayCircle className="h-3 w-3 mr-1.5" />
                  Start
                </Button>
              ) : null}
              <Button
                variant="outline"
                size="sm"
                className="h-8"
                onClick={() => setPreviewOpen(true)}
                disabled={sandboxStatus !== "running"}
              >
                <Play className="h-3 w-3 mr-1.5" />
                Run App
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-8"
                onClick={handleViewDiff}
                disabled={sandboxStatus !== "running"}
              >
                View Changes
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-8"
                onClick={handleCreatePr}
                disabled={sandboxStatus !== "running" || prCreating}
              >
                {prCreating ? (
                  <Loader2 className="h-3 w-3 mr-1.5 animate-spin" />
                ) : (
                  <GitBranch className="h-3 w-3 mr-1.5" />
                )}
                Create PR
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-8"
                onClick={handleStartSandbox}
                disabled={sandboxLoading || sandboxStatus === "running"}
              >
                {sandboxLoading ? (
                  <Loader2 className="h-3 w-3 mr-1.5 animate-spin" />
                ) : (
                  <Play className="h-3 w-3 mr-1.5" />
                )}
                {sandboxStatus === "running" ? "Running" : "Start"}
              </Button>
            </div>
          </div>
        </CardHeader>
        <Separator />
        {/* Session selector */}
        <div className="border-b border-border/40 px-3 py-1.5 flex items-center gap-2 text-xs flex-shrink-0 overflow-x-auto">
          <div className="flex items-center gap-1.5 flex-1 min-w-0 overflow-x-auto">
            {sessions.map((s) => (
              <div
                key={s.id}
                className={`flex items-center gap-1 rounded-full pl-3 pr-1 py-1 flex-shrink-0 cursor-pointer ${activeSessionId === s.id
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:bg-muted/80"
                  }`}
                onClick={() => handleSelectSession(s.id)}
              >
                <span className="whitespace-nowrap truncate max-w-[150px]">{s.title}</span>
                <button
                  type="button"
                  className="rounded-full p-0.5 opacity-70 hover:opacity-100 hover:bg-black/10 transition-all ml-1"
                  onClick={(e) => handleDeleteSession(e, s.id)}
                  title="Delete chat session"
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            ))}
            {sessions.length === 0 && (
              <span className="text-muted-foreground">
                No sessions yet. Start the sandbox to create one.
              </span>
            )}
          </div>
          {sandboxStatus === "running" && (
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 flex-shrink-0 ml-1"
              onClick={handleNewSession}
              disabled={creatingSession}
              title="New chat session"
            >
              {creatingSession ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Plus className="h-3 w-3" />
              )}
            </Button>
          )}
        </div>

        {/* Messages Area — plain div so flex-1 works correctly */}
        <div className="flex-1 min-h-0 overflow-y-auto px-4 pt-3 pb-2">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center">
              <div className="flex items-center justify-center h-12 w-12 rounded-lg bg-orange-500/10 mb-4">
                <span className="text-orange-500 font-bold text-lg">C</span>
              </div>
              <h3 className="text-lg font-medium">Comio AI Assistant</h3>
              <p className="text-sm text-muted-foreground mt-1 text-center max-w-sm">
                Start the sandbox and ask Comio to create a project, explain the
                code, or make changes. It will read and edit files inside this
                sandboxed workspace.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"
                    }`}
                >
                  <div
                    className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${msg.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-muted text-foreground"
                      }`}
                  >
                    {msg.role === "assistant" ? (
                      <div className="prose prose-sm dark:prose-invert max-w-none">
                        <ReactMarkdown>{msg.content}</ReactMarkdown>
                      </div>
                    ) : (
                      msg.content
                    )}
                    {msg.files_modified && msg.files_modified.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {msg.files_modified.map((f) => (
                          <span
                            key={f}
                            className="text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded px-1.5 py-0.5"
                          >
                            {f}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        <Separator />

        {/* Input Area */}
        <div className="p-4 space-y-2 flex-shrink-0">
          {chatError && (
            <p className="text-xs text-destructive">{chatError}</p>
          )}
          <div className="flex gap-2">
            <Input
              placeholder={
                sandboxStatus === "running"
                  ? "Ask Comio to create, edit, deploy, or explain your code..."
                  : "Start the sandbox to begin chatting"
              }
              value={messageInput}
              onChange={(e) => setMessageInput(e.target.value)}
              className="flex-1"
              disabled={!canChat || sending}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void handleSendMessage();
                }
              }}
            />
            <Button
              size="icon"
              onClick={handleSendMessage}
              disabled={!canChat || sending || !messageInput.trim()}
            >
              {sending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Project {id} · Sandbox must be running to chat
          </p>
        </div>
      </Card>

      {/* Simple file viewer overlay */}
      {selectedFilePath && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur">
          <div className="w-full max-w-2xl h-[80vh] rounded-lg border bg-card shadow-lg flex flex-col">
            <div className="flex items-center justify-between px-4 py-2 border-b flex-shrink-0">
              <div className="text-sm font-medium truncate">
                {selectedFilePath}
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setSelectedFilePath(null);
                  setSelectedFileContent(null);
                }}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
            <div className="flex-1 overflow-auto p-4">
              {fileLoading ? (
                <div className="flex items-center justify-center text-muted-foreground text-sm h-full">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Loading file...
                </div>
              ) : (
                <pre className="text-xs whitespace-pre-wrap break-words font-mono">
                  {selectedFileContent ?? "No content"}
                </pre>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Diff viewer overlay */}
      {diffOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur">
          <div className="w-full max-w-3xl h-[80vh] rounded-lg border bg-card shadow-lg flex flex-col">
            <div className="flex items-center justify-between px-4 py-3 border-b flex-shrink-0">
              <div className="text-sm font-semibold">
                Sandbox Changes — Project {id}
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setDiffOpen(false);
                  setDiffContent(null);
                  setDiffError(null);
                }}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
            <div className="flex-1 overflow-auto p-4">
              {diffLoading ? (
                <div className="flex items-center justify-center text-muted-foreground text-sm h-full">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Loading diff...
                </div>
              ) : diffError ? (
                <p className="text-sm text-destructive">{diffError}</p>
              ) : (
                <pre className="text-xs font-mono whitespace-pre-wrap break-words">
                  {!diffContent ? (
                    <span className="text-muted-foreground">Loading...</span>
                  ) : !diffContent.includes("diff --git") && !diffContent.includes("@@") ? (
                    <span className="text-muted-foreground">{diffContent}</span>
                  ) : (
                    diffContent
                      .split("\n")
                      .map((line, idx) => {
                        if (line.startsWith("+") && !line.startsWith("+++")) {
                          return (
                            <span key={idx} className="block text-emerald-400 bg-emerald-950/30">
                              {line}
                            </span>
                          );
                        }
                        if (line.startsWith("-") && !line.startsWith("---")) {
                          return (
                            <span key={idx} className="block text-red-400 bg-red-950/30">
                              {line}
                            </span>
                          );
                        }
                        if (line.startsWith("@@")) {
                          return (
                            <span key={idx} className="block text-sky-400 bg-sky-950/20">
                              {line}
                            </span>
                          );
                        }
                        if (
                          line.startsWith("diff ") ||
                          line.startsWith("index ") ||
                          line.startsWith("--- ") ||
                          line.startsWith("+++ ")
                        ) {
                          return (
                            <span key={idx} className="block text-muted-foreground font-bold">
                              {line}
                            </span>
                          );
                        }
                        return (
                          <span key={idx} className="block">
                            {line}
                          </span>
                        );
                      })
                  )}
                </pre>
              )}
            </div>
            {prResult && (
              <div className="border-t px-4 py-2 text-xs text-muted-foreground flex-shrink-0">
                {prResult.startsWith("http") ? (
                  <>
                    PR created:&nbsp;
                    <a
                      href={prResult}
                      target="_blank"
                      rel="noreferrer"
                      className="underline"
                    >
                      {prResult}
                    </a>
                  </>
                ) : (
                  prResult
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Preview overlay */}
      {previewOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur p-4">
          <div className="w-full max-w-5xl h-[90vh] rounded-lg border bg-card shadow-lg flex flex-col">
            <div className="flex items-center justify-between px-4 py-3 border-b flex-shrink-0">
              <div className="text-sm font-semibold flex items-center gap-2">
                <ExternalLink className="h-4 w-4" />
                Sandbox Preview
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setPreviewOpen(false);
                  setPreviewUrl(null);
                }}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>

            {!previewUrl ? (
              <div className="flex-1 flex flex-col items-center justify-center p-6 space-y-6">
                <div className="max-w-md w-full space-y-4">
                  <div className="space-y-2">
                    <label className="text-sm font-medium">Start Command</label>
                    <Input
                      value={runCommand}
                      onChange={(e) => setRunCommand(e.target.value)}
                      placeholder="e.g. npm run dev, python app.py"
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-sm font-medium">Port to Expose</label>
                    <Input
                      value={runPort}
                      onChange={(e) => setRunPort(e.target.value)}
                      placeholder="e.g. 3000, 8000"
                    />
                  </div>
                  <Button
                    className="w-full"
                    onClick={handleRunPreview}
                    disabled={previewRunning || !runCommand || !runPort}
                  >
                    {previewRunning ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Starting and linking...
                      </>
                    ) : (
                      <>
                        <Play className="mr-2 h-4 w-4" />
                        Run & Preview
                      </>
                    )}
                  </Button>
                  <p className="text-xs text-muted-foreground text-center">
                    This runs the command in the background and proxies requests to the specified port.
                  </p>
                </div>
              </div>
            ) : (
              <div className="flex-1 min-h-0 relative bg-white">
                <iframe
                  src={`http://localhost:8000${previewUrl}`}
                  className="w-full h-full border-none"
                  title="App Preview"
                  sandbox="allow-scripts allow-forms allow-popups allow-same-origin"
                />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
