import type {
  CandidatesResponse,
  DashboardSummary,
  HealthResponse,
  Investigation,
  InvestigationList,
  OllamaModels,
  OllamaStatus,
  PatchProposal,
  Progress,
  ReadmeDraft,
  RecoveryTask,
  Report,
  RepositoryCandidate,
  RuntimeSettings,
  TaskStatus,
  ValidationResult,
} from "@/lib/types";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    });
  } catch {
    throw new ApiError(0, "network_error", "The GhostRepo backend could not be reached.");
  }

  if (!response.ok) {
    throw await toApiError(response);
  }
  return (await response.json()) as T;
}

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const { error } = await response.json();
    return new ApiError(response.status, error.code, error.message, error.details);
  } catch {
    const message =
      response.status >= 500
        ? "The GhostRepo backend is unavailable. Is it running?"
        : `The request failed with status ${response.status}.`;
    return new ApiError(response.status, "unknown_error", message);
  }
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong.";
}

/** A missing draft or patch is a normal state, not an error. */
async function orNull<T>(call: Promise<T>): Promise<T | null> {
  try {
    return await call;
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

const base = (id: string) => `/api/investigations/${encodeURIComponent(id)}`;

export const api = {
  health: () => request<HealthResponse>("/api/health"),
  ollamaStatus: () => request<OllamaStatus>("/api/ollama/status"),
  ollamaModels: () => request<OllamaModels>("/api/ollama/models"),
  dashboard: () => request<DashboardSummary>("/api/dashboard"),

  settings: () => request<RuntimeSettings>("/api/settings"),
  saveSettings: (body: RuntimeSettings) =>
    request<RuntimeSettings>("/api/settings", { method: "PUT", body: JSON.stringify(body) }),

  candidates: () => request<CandidatesResponse>("/api/repositories/candidates"),
  validateRepository: (path: string) =>
    post<ValidationResult>("/api/repositories/validate", { path }),
  createDemo: () => post<RepositoryCandidate>("/api/repositories/demo"),

  investigations: (limit = 50) =>
    request<InvestigationList>(`/api/investigations?limit=${limit}`),
  startInvestigation: (path: string) => post<Investigation>("/api/investigations", { path }),
  progress: (id: string) => request<Progress>(`${base(id)}/progress`),
  report: (id: string) => request<Report>(`${base(id)}/report`),
  reanalyze: (id: string) => post<Investigation>(`${base(id)}/reanalyze`),
  updateTask: (id: string, taskId: string, status: TaskStatus) =>
    request<RecoveryTask>(`${base(id)}/recovery-tasks/${encodeURIComponent(taskId)}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),

  readme: (id: string) => orNull(request<ReadmeDraft>(`${base(id)}/readme`)),
  generateReadme: (id: string, useAi: boolean) =>
    post<ReadmeDraft>(`${base(id)}/generate-readme`, { use_ai: useAi }),
  saveReadme: (id: string, content: string) =>
    request<ReadmeDraft>(`${base(id)}/readme`, {
      method: "PUT",
      body: JSON.stringify({ content }),
    }),

  patch: (id: string) => orNull(request<PatchProposal>(`${base(id)}/patch`)),
  generatePatch: (id: string) => post<PatchProposal>(`${base(id)}/generate-patch`),
  approvePatch: (id: string, patchId: string) =>
    post<PatchProposal>(`${base(id)}/patch/${encodeURIComponent(patchId)}/approve`, {
      confirm: true,
    }),

  exportUrl: (id: string, format: "markdown" | "json") => `${base(id)}/export?format=${format}`,
  patchDownloadUrl: (id: string, patchId: string) =>
    `${base(id)}/patch/${encodeURIComponent(patchId)}/download`,
};
