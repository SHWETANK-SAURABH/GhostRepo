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

export interface OllamaModel {
  name: string;
  size_bytes: number | null;
  family: string | null;
  parameter_size: string | null;
  quantization: string | null;
}

export interface OllamaModels {
  reachable: boolean;
  models: OllamaModel[];
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

export interface RuntimeSettings {
  ollama_endpoint: string;
  ollama_model: string;
  ai_enabled: boolean;
  workspace_root: string;
  max_file_size_bytes: number;
  excluded_dirs: string[];
  analysis_timeout_seconds: number;
}

export interface RepositoryCandidate {
  name: string;
  relative_path: string;
  is_git: boolean;
  is_demo: boolean;
}

export interface CandidatesResponse {
  workspace_available: boolean;
  candidates: RepositoryCandidate[];
}

export interface ValidationResult {
  valid: boolean;
  code: string | null;
  message: string;
  name: string | null;
  relative_path: string | null;
  is_git: boolean;
  manifests: string[];
  has_readme: boolean;
}

export interface Stage {
  key: string;
  label: string;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  message: string | null;
}

export interface Investigation {
  id: string;
  repository: {
    id: string;
    name: string;
    relative_path: string | null;
    detected_languages: string[];
    detected_frameworks: string[];
  };
  status: string;
  current_stage: string | null;
  stages: Stage[];
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  health_score: number | null;
  ai_status: string;
  ai_model: string | null;
  ai_error: string | null;
  verified_finding_count: number;
  ai_finding_count: number;
}

export interface InvestigationList {
  items: Investigation[];
  total: number;
}

export interface Progress {
  id: string;
  status: string;
  current_stage: string | null;
  stages: Stage[];
  percent: number;
  error_message: string | null;
  ai_status: string;
  ai_error: string | null;
}

export interface Evidence {
  key: string;
  category: string;
  source_file: string | null;
  description: string;
  structured_data: Record<string, unknown>;
  detection_method: string;
}

export interface Finding {
  id: string;
  rule_id: string | null;
  title: string;
  description: string;
  severity: Severity;
  category: string;
  confidence: number;
  evidence_references: string[];
  is_hypothesis: boolean;
  recommendation: string;
  source_file: string | null;
  detection_method: string;
  origin: "deterministic" | "ai";
}

export type TaskStatus = "pending" | "in_progress" | "done" | "dismissed";

export interface RecoveryTask {
  id: string;
  title: string;
  description: string;
  why_it_matters: string | null;
  solution: string | null;
  files: string[];
  effort_estimate: string | null;
  verification_steps: string[];
  priority: "high" | "medium" | "low";
  rank: number;
  status: TaskStatus;
  evidence_references: string[];
  origin: "deterministic" | "ai";
}

export interface RejectedItem {
  item_type: "finding" | "recovery_task" | "statement";
  title: string;
  reason: string;
}

/** Analyzer output. Sections are absent when their stage failed. */
export interface Profile {
  repository?: {
    name: string;
    file_count: number;
    total_bytes: number;
    primary_language: string | null;
    secondary_languages: string[];
    languages: { name: string; files: number; share: number; deep_support: boolean }[];
    frameworks: string[];
    build_tools: string[];
    entry_points: string[];
    limits: Record<string, boolean | number>;
  };
  git?: {
    available: boolean;
    reason?: string;
    branch?: string | null;
    commit_count?: number;
    shallow_clone?: boolean;
    latest_commit?: { hash: string; author: string; date: string; subject: string };
    first_commit_date?: string;
    days_since_last_commit?: number;
    contributor_count?: number;
    top_contributors?: { name: string; commits: number }[];
    activity?: { last_30_days: number; last_90_days: number; last_365_days: number };
    message_patterns?: { conventional_commit_share: number; merge_commit_share: number };
  };
  dependencies?: {
    manifests: string[];
    malformed_manifests: string[];
    ecosystems: string[];
    dependency_count: number;
    direct_runtime_count: number;
    dev_count: number;
    pinning: Record<string, number>;
    lockfiles: string[];
    frameworks: string[];
    freshness_note: string;
  };
  configuration?: {
    env_templates: string[];
    env_variables: string[];
    deployment: string[];
    ci_files: string[];
    license: string | null;
    license_files: string[];
  };
  documentation?: {
    criteria: Record<string, boolean>;
    completeness_score: number;
  };
  tests?: {
    executed: boolean;
    test_file_count: number;
    source_file_count: number;
    test_directories: string[];
    frameworks: string[];
    commands: { command: string; source: string; file: string | null }[];
  };
}

export interface Report {
  investigation: Investigation;
  profile: Profile;
  health: { score: number | null; note: string };
  provenance: "deterministic" | "deterministic_and_ai" | "none";
  evidence: Evidence[];
  verified_findings: Finding[];
  ai: {
    status: string;
    model: string | null;
    error: string | null;
    summary: string | null;
    health_assessment: string | null;
    findings: Finding[];
    rejected: RejectedItem[];
  };
  recovery_tasks: RecoveryTask[];
}

export interface ReadmeDraft {
  id: string;
  content: string;
  origin: "deterministic" | "deterministic_and_ai" | "edited";
  ai_model: string | null;
  warning: string | null;
  unverified_sections: string[];
  created_at: string;
}

export interface PatchFile {
  path: string;
  change_type: "create" | "modify";
  explanation: string;
  additions: number;
  deletions: number;
}

export interface PatchProposal {
  id: string;
  status: "proposed" | "approved";
  diff: string;
  files: PatchFile[];
  refused_paths: string[];
  message: string;
  approved_at: string | null;
  created_at: string;
}
