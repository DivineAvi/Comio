export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type HttpMethod = "GET" | "POST" | "PUT" | "DELETE";

interface RequestOptions<TBody> {
  method?: HttpMethod;
  body?: TBody;
  auth?: boolean;
}

async function request<TResponse, TBody = unknown>(
  path: string,
  options: RequestOptions<TBody> = {}
): Promise<TResponse> {
  const url = `${API_BASE_URL}${path}`;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  // Basic dev auth: read JWT token from localStorage if present.
  if (options.auth !== false && typeof window !== "undefined") {
    const token = window.localStorage.getItem("comio_token");
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
  }

  const res = await fetch(url, {
    method: options.method ?? "GET",
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
    credentials: "include",
  });

  if (!res.ok) {
    let message = `Request failed with status ${res.status}`;
    try {
      const data = await res.json();
      if (data?.detail) {
        message = typeof data.detail === "string" ? data.detail : message;
      }
    } catch {
      // ignore JSON parse errors
    }
    throw new Error(message);
  }

  if (res.status === 204) {
    // No Content
    return undefined as unknown as TResponse;
  }

  return (await res.json()) as TResponse;
}

// ── Types matching backend schemas (simplified) ─────────────

export interface Project {
  id: string;
  created_at: string;
  updated_at: string;
  name: string;
  description: string | null;
  origin: string | null;
  project_type: string | null;
  repo_url: string | null;
  repo_full_name: string | null;
  default_branch: string | null;
  owner_id: string;
}

export interface ProjectListResponse {
  projects: Project[];
  total: number;
}

export interface ProjectCreatePayload {
  name: string;
  description?: string | null;
  project_type: string;
}

export interface ProjectImportPayload {
  repo_url: string;
  name?: string;
  description?: string | null;
}

export interface SandboxStatus {
  id: string;
  status: string;
  container_id: string | null;
  container_status: string;
  git_branch: string | null;
  volume_name: string | null;
  cpu_limit: number | null;
  memory_limit_mb: number | null;
}

export interface ChatSessionSummary {
  id: string;
  title: string;
  is_active: boolean;
  created_at: string;
}

export interface ChatSessionListResponse {
  sessions: ChatSessionSummary[];
  total: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  tool_calls?: unknown;
  files_modified?: string[];
  created_at: string;
}

export interface ChatMessagesResponse {
  messages: ChatMessage[];
  total: number;
}

export interface ChatEvent {
  type: string;
  content?: string;
  tool?: string;
  args?: unknown;
  files_modified?: string[];
}

export interface SendMessageResponse {
  events: ChatEvent[];
}

export interface FileEntry {
  name: string;
  path: string;
  is_directory: boolean;
  size: number | null;
}

export interface ListFilesResponse {
  path: string;
  entries: FileEntry[];
}

export interface ReadFileResponse {
  path: string;
  content: string;
  size: number;
  lines: number;
}

export interface SearchMatch {
  path: string;
  line_number: number;
  content: string;
}

export interface SearchResponse {
  query: string;
  matches: SearchMatch[];
  total: number;
}

// ── Auth types ───────────────────────────────────────────────

export interface User {
  id: string;
  created_at: string;
  updated_at: string;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  github_username?: string | null;
  avatar_url?: string | null;
  llm_provider?: string | null;
}

export interface TokenResponse {
  access_token: string;
  expires_in: number;
  user: User;
}

// ── Incident types ───────────────────────────────────────────

export interface Incident {
  id: string;
  created_at: string;
  updated_at: string;
  title: string;
  description: string | null;
  severity: string;
  status: string;
  source: string;
  project_id: string;
}

export interface IncidentListResponse {
  incidents: Incident[];
  total: number;
}

export interface IncidentDetail extends Incident {
  diagnosis?: {
    root_cause: string;
    category: string;
    confidence: number;
    explanation: string;
  } | null;
  remediation?: {
    diff: string | null;
    files_changed: string[] | null;
    explanation: string | null;
    risk_level: string | null;
    status: string;
    pr_url?: string | null;
  } | null;
}

// ── Git diff / PR types ─────────────────────────────────────

export interface GitDiffResponse {
  diff: string;
  has_changes: boolean;
}

export interface CreatePrResponse {
  status: string;
  pr_url: string;
}

// ── Project APIs ─────────────────────────────────────────────

export async function listProjects(): Promise<ProjectListResponse> {
  return request<ProjectListResponse>("/projects");
}

export async function createProject(
  payload: ProjectCreatePayload
): Promise<Project> {
  return request<Project, ProjectCreatePayload>("/projects/create", {
    method: "POST",
    body: payload,
  });
}

export async function importProject(
  payload: ProjectImportPayload
): Promise<Project> {
  return request<Project, ProjectImportPayload>("/projects/import", {
    method: "POST",
    body: payload,
  });
}

export async function getProject(projectId: string): Promise<Project> {
  return request<Project>(`/projects/${projectId}`);
}

export async function updateProject(
  projectId: string,
  payload: { name?: string; description?: string }
): Promise<Project> {
  return request<Project, typeof payload>(`/projects/${projectId}`, {
    method: "PUT",
    body: payload,
  });
}

export async function deleteProject(projectId: string): Promise<void> {
  return request<void>(`/projects/${projectId}`, {
    method: "DELETE",
  });
}

// ── Sandbox lifecycle & files ───────────────────────────────

export async function getSandbox(
  projectId: string
): Promise<SandboxStatus> {
  return request<SandboxStatus>(`/projects/${projectId}/sandbox`);
}

export async function startSandbox(projectId: string): Promise<SandboxStatus> {
  return request<SandboxStatus>(`/projects/${projectId}/sandbox/start`, {
    method: "POST",
  });
}

export async function stopSandbox(projectId: string): Promise<void> {
  return request<void>(`/projects/${projectId}/sandbox/stop`, {
    method: "POST",
  });
}

export async function syncSandboxRepo(projectId: string): Promise<{
  status: string;
  message: string;
}> {
  return request(`/projects/${projectId}/sandbox/stop`, {
    method: "POST",
  });
}

export async function runSandboxProcess(
  projectId: string,
  command: string
): Promise<{ status: string; pid: string; message: string }> {
  return request(`/projects/${projectId}/sandbox/run`, {
    method: "POST",
    body: { command },
  });
}

export interface ExecCommandResponse {
  exit_code: number;
  stdout: string;
  stderr: string;
}

export async function execSandboxCommand(
  projectId: string,
  command: string,
  timeout?: number
): Promise<ExecCommandResponse> {
  return request<ExecCommandResponse, { command: string; timeout?: number }>(
    `/projects/${projectId}/sandbox/exec`,
    {
      method: "POST",
      body: { command, timeout },
    }
  );
}

export interface RunningPort {
  port: number;
  pid: number | null;
  command: string;
}

export async function listRunningPorts(
  projectId: string
): Promise<{ ports: RunningPort[] }> {
  return request(`/projects/${projectId}/sandbox/run/ports`);
}

export async function killPort(
  projectId: string,
  port: number
): Promise<{ status: string; port: number; output: string }> {
  return request(`/projects/${projectId}/sandbox/run/ports/${port}`, {
    method: "DELETE",
  });
}

export async function listSandboxFiles(
  projectId: string,
  path: string = ".",
  recursive = false
): Promise<ListFilesResponse> {
  const params = new URLSearchParams();
  params.set("path", path);
  params.set("recursive", String(recursive));
  return request<ListFilesResponse>(
    `/projects/${projectId}/sandbox/files?${params.toString()}`
  );
}

export async function readSandboxFile(
  projectId: string,
  filePath: string
): Promise<ReadFileResponse> {
  return request<ReadFileResponse>(
    `/projects/${projectId}/sandbox/files/${encodeURIComponent(filePath)}`
  );
}

export async function searchSandbox(
  projectId: string,
  query: string,
  glob?: string
): Promise<SearchResponse> {
  return request<SearchResponse, { query: string; glob?: string }>(
    `/projects/${projectId}/sandbox/search`,
    {
      method: "POST",
      body: { query, glob },
    }
  );
}

// ── Chat APIs ───────────────────────────────────────────────

export async function listChatSessions(
  projectId: string
): Promise<ChatSessionListResponse> {
  return request<ChatSessionListResponse>(
    `/projects/${projectId}/sandbox/chat/sessions`
  );
}

export async function deleteChatSession(
  projectId: string,
  sessionId: string
): Promise<void> {
  return request<void>(
    `/projects/${projectId}/sandbox/chat/sessions/${sessionId}`,
    {
      method: "DELETE",
    }
  );
}

export async function createChatSession(
  projectId: string,
  title: string
): Promise<ChatSessionSummary> {
  return request<ChatSessionSummary, { title: string }>(
    `/projects/${projectId}/sandbox/chat/sessions`,
    {
      method: "POST",
      body: { title },
    }
  );
}



export async function getChatMessages(
  projectId: string,
  sessionId: string
): Promise<ChatMessagesResponse> {
  return request<ChatMessagesResponse>(
    `/projects/${projectId}/sandbox/chat/sessions/${sessionId}/messages`
  );
}

export async function sendChatMessage(
  projectId: string,
  sessionId: string,
  content: string
): Promise<SendMessageResponse> {
  return request<SendMessageResponse, { content: string }>(
    `/projects/${projectId}/sandbox/chat/sessions/${sessionId}/messages`,
    {
      method: "POST",
      body: { content },
    }
  );
}

// ── Auth APIs ────────────────────────────────────────────────

export async function login(
  email: string,
  password: string
): Promise<TokenResponse> {
  const url = `${API_BASE_URL}/auth/login`;
  const params = new URLSearchParams();
  params.set("username", email);
  params.set("password", password);

  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: params.toString(),
  });

  if (!res.ok) {
    let message = `Login failed with status ${res.status}`;
    try {
      const data = await res.json();
      if (data?.detail) {
        message = typeof data.detail === "string" ? data.detail : message;
      }
    } catch {
      // ignore
    }
    throw new Error(message);
  }

  return (await res.json()) as TokenResponse;
}

export async function registerUser(
  email: string,
  password: string,
  fullName: string
): Promise<TokenResponse> {
  return request<TokenResponse, { email: string; password: string; full_name: string }>(
    "/auth/register",
    {
      method: "POST",
      body: {
        email,
        password,
        full_name: fullName,
      },
      auth: false,
    }
  );
}

export async function getCurrentUser(): Promise<User> {
  return request<User>("/auth/me");
}

export async function updateLlmSettings(
  llmProvider: string,
  llmApiKey: string
): Promise<User> {
  return request<User, { llm_provider: string; llm_api_key: string }>(
    "/auth/llm",
    {
      method: "POST",
      body: {
        llm_provider: llmProvider,
        llm_api_key: llmApiKey,
      },
    }
  );
}

// ── Incident APIs ────────────────────────────────────────────

export async function listIncidents(
  projectId: string
): Promise<IncidentListResponse> {
  const params = new URLSearchParams();
  params.set("project_id", projectId);
  return request<IncidentListResponse>(`/incidents?${params.toString()}`);
}

export async function getIncident(
  incidentId: string
): Promise<IncidentDetail> {
  return request<IncidentDetail>(`/incidents/${incidentId}`);
}

// ── Git diff & PR APIs ──────────────────────────────────────

export async function getSandboxDiff(
  projectId: string
): Promise<GitDiffResponse> {
  return request<GitDiffResponse>(`/projects/${projectId}/sandbox/git/diff`);
}

export async function createSandboxPullRequest(
  projectId: string,
  title: string,
  body: string,
  baseBranch: string = "main"
): Promise<CreatePrResponse> {
  return request<CreatePrResponse, { title: string; body: string; base_branch: string }>(
    `/projects/${projectId}/sandbox/git/pr`,
    {
      method: "POST",
      body: { title, body, base_branch: baseBranch },
    }
  );
}


