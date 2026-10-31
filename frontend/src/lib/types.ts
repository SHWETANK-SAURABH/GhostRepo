export type Severity = "critical" | "high" | "medium" | "low" | "info";

export const SEVERITIES: Severity[] = ["critical", "high", "medium", "low", "info"];

export interface HealthResponse {
  status: string;
  version: string;
  database: string;
  workspace_available: boolean;
}

export interface OllamaStatus {
  enabled: boolean;
  reachable: boolean;
  version: string | null;
  model: string;
  model_available: boolean;
  message: string;
}

export interface RecentInvestigation {
  id: string;
  repository_name: string;
  status: string;
  ai_status: string;
  health_score: number | null;
  finding_count: number;
  created_at: string;
}

export interface DashboardSummary {
  investigations: number;
  verified_findings: number;
  pending_recovery_tasks: number;
  average_health_score: number | null;
  severity_counts: Record<Severity, number>;
  recent: RecentInvestigation[];
}
