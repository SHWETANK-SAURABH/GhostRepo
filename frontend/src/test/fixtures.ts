import type { Finding, Investigation, Report } from "@/lib/types";

export const INVESTIGATION: Investigation = {
  id: "inv1",
  repository: {
    id: "repo1",
    name: "old-crawler",
    relative_path: "old-crawler",
    detected_languages: ["Python"],
    detected_frameworks: ["Flask"],
  },
  status: "completed",
  current_stage: null,
  stages: [
    { key: "discovery", label: "Repository discovery", status: "completed", message: null },
    { key: "ai", label: "AI analysis", status: "failed", message: "Ollama is not reachable." },
  ],
  created_at: "2026-10-01T10:00:00+00:00",
  started_at: "2026-10-01T10:00:00+00:00",
  completed_at: "2026-10-01T10:00:10+00:00",
  error_message: null,
  health_score: 64,
  ai_status: "unavailable",
  ai_model: "gemma3:4b",
  ai_error: "Ollama is not reachable at the configured endpoint.",
  verified_finding_count: 2,
  ai_finding_count: 0,
};

export const VERIFIED: Finding = {
  id: "f1",
  rule_id: "docs-no-readme",
  title: "No README",
  description: "No README file was found at the repository root.",
  severity: "high",
  category: "documentation",
  confidence: 1,
  evidence_references: ["ev-doc-001"],
  is_hypothesis: false,
  recommendation: "Add a README.",
  source_file: null,
  detection_method: "documentation-inspector:structure-check",
  origin: "deterministic",
};

export const CRITICAL: Finding = {
  ...VERIFIED,
  id: "f2",
  rule_id: "config-secret-file-committed",
  title: "Secret file is committed: .env",
  severity: "critical",
  category: "configuration",
  evidence_references: ["ev-cfg-001"],
  source_file: ".env",
};

export const HYPOTHESIS: Finding = {
  ...VERIFIED,
  id: "f3",
  rule_id: null,
  title: "Project may have moved elsewhere",
  severity: "low",
  category: "maintenance",
  is_hypothesis: true,
  detection_method: "local-ai:gemma3:4b",
  origin: "ai",
};

export const REPORT: Report = {
  investigation: INVESTIGATION,
  profile: {},
  health: { score: 64, note: "An indicator from verified findings." },
  provenance: "deterministic",
  evidence: [
    {
      key: "ev-doc-001",
      category: "documentation",
      source_file: null,
      description: "No README file was found at the repository root.",
      structured_data: {},
      detection_method: "documentation-inspector:structure-check",
    },
  ],
  verified_findings: [CRITICAL, VERIFIED],
  ai: {
    status: "unavailable",
    model: "gemma3:4b",
    error: "Ollama is not reachable at the configured endpoint.",
    summary: null,
    health_assessment: null,
    findings: [],
    rejected: [],
  },
  recovery_tasks: [
    {
      id: "t1",
      title: "No README",
      description: "No README file was found.",
      why_it_matters: "Nobody can tell how to start the project.",
      solution: "Add a README.",
      files: ["README.md"],
      effort_estimate: "1 to 2 hours",
      verification_steps: ["Follow the README on a clean machine."],
      priority: "high",
      rank: 0,
      status: "pending",
      evidence_references: ["ev-doc-001"],
      origin: "deterministic",
    },
    {
      id: "t2",
      title: "Write setup docs",
      description: "Add install steps.",
      why_it_matters: null,
      solution: null,
      files: [],
      effort_estimate: null,
      verification_steps: [],
      priority: "medium",
      rank: 1,
      status: "pending",
      evidence_references: ["ev-doc-001"],
      origin: "ai",
    },
  ],
};

export const AI_REPORT: Report = {
  ...REPORT,
  provenance: "deterministic_and_ai",
  ai: {
    status: "completed",
    model: "gemma3:4b",
    error: null,
    summary: "The repository needs documentation work.",
    health_assessment: "Hygiene is mixed.",
    findings: [HYPOTHESIS],
    rejected: [{ item_type: "finding", title: "Invented", reason: "It cites 1 evidence id(s) that do not exist." }],
  },
};
