import type { DashboardSummary, HealthResponse, OllamaStatus } from "@/lib/types";

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

export const api = {
  health: () => request<HealthResponse>("/api/health"),
  ollamaStatus: () => request<OllamaStatus>("/api/ollama/status"),
  dashboard: () => request<DashboardSummary>("/api/dashboard"),
};
