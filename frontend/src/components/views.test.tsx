import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AutopsyView } from "@/components/investigation/autopsy-view";
import { FindingsView } from "@/components/investigation/findings-view";
import { PatchesView } from "@/components/investigation/patches-view";
import { PlanView } from "@/components/investigation/plan-view";
import { ProgressPanel } from "@/components/investigation/progress-panel";
import { ReadmeView } from "@/components/investigation/readme-view";
import { MarkdownPreview } from "@/components/markdown-preview";
import { NewInvestigation, pathSchema } from "@/components/new-investigation";
import { settingsSchema } from "@/components/settings-view";
import { api, ApiError } from "@/lib/api";
import { AI_REPORT, REPORT } from "@/test/fixtures";
import { mockApi, renderWithQuery } from "@/test/utils";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => "/",
}));

const OLLAMA_READY = {
  "GET /api/ollama/status": {
    body: {
      enabled: true,
      reachable: true,
      version: "1",
      model: "gemma3:4b",
      model_available: true,
      message: "Ready.",
    },
  },
};

describe("repository form", () => {
  const candidates = {
    "GET /api/repositories/candidates": {
      body: {
        workspace_available: true,
        candidates: [
          { name: "haunted-demo", relative_path: "haunted-demo", is_git: true, is_demo: true },
        ],
      },
    },
  };

  it("validates the path before calling the API", async () => {
    const fetchMock = mockApi(candidates);
    renderWithQuery(<NewInvestigation />);
    await userEvent.click(screen.getByRole("button", { name: "Validate" }));
    expect(await screen.findByText("Enter a repository path.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/repositories/validate",
      expect.anything(),
    );
  });

  it("schema rejects blank and oversized paths", () => {
    expect(pathSchema.safeParse({ path: "  " }).success).toBe(false);
    expect(pathSchema.safeParse({ path: "x".repeat(5000) }).success).toBe(false);
    expect(pathSchema.safeParse({ path: "repo" }).success).toBe(true);
  });

  it("shows the server's rejection and offers no way to start", async () => {
    mockApi({
      ...candidates,
      "POST /api/repositories/validate": {
        body: {
          valid: false,
          code: "outside_workspace",
          message: "The repository must be inside the configured workspace root.",
          name: null,
          relative_path: null,
          is_git: false,
          manifests: [],
          has_readme: false,
        },
      },
    });
    renderWithQuery(<NewInvestigation />);
    await userEvent.type(screen.getByLabelText("Repository path"), "../../etc");
    await userEvent.click(screen.getByRole("button", { name: "Validate" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("inside the configured workspace");
    expect(screen.queryByRole("button", { name: /start investigation/ })).not.toBeInTheDocument();
  });

  it("confirms the repository, then starts and navigates", async () => {
    mockApi({
      ...candidates,
      "POST /api/repositories/validate": {
        body: {
          valid: true,
          code: null,
          message: "The repository is ready to investigate.",
          name: "haunted-demo",
          relative_path: "haunted-demo",
          is_git: true,
          manifests: ["requirements.txt"],
          has_readme: true,
        },
      },
      "POST /api/investigations": { status: 202, body: { id: "new-id" } },
    });
    renderWithQuery(<NewInvestigation />);
    expect(await screen.findByText("Demo")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /haunted-demo/ }));
    const start = await screen.findByRole("button", { name: /start investigation/ });
    expect(screen.getByText("requirements.txt")).toBeInTheDocument();
    await userEvent.click(start);
    await waitFor(() => expect(push).toHaveBeenCalledWith("/investigations/new-id"));
  });
});

describe("settings form", () => {
  const valid = {
    ollama_endpoint: "http://localhost:11434",
    ollama_model: "gemma3:4b",
    ai_enabled: true,
    workspace_root: "/repos",
    max_file_size_kb: "1000",
    excluded_dirs: ".git",
    analysis_timeout_seconds: "120",
  };

  it("accepts valid values and coerces numbers", () => {
    const parsed = settingsSchema.parse(valid);
    expect(parsed.max_file_size_kb).toBe(1000);
  });

  it.each([
    ["ollama_endpoint", "not a url"],
    ["ollama_model", "bad model; rm -rf"],
    ["workspace_root", " "],
    ["max_file_size_kb", "0"],
    ["analysis_timeout_seconds", "1"],
  ])("rejects an invalid %s", (field, value) => {
    expect(settingsSchema.safeParse({ ...valid, [field]: value }).success).toBe(false);
  });
});

describe("API errors", () => {
  it("surfaces the server's message and code", async () => {
    mockApi({
      "GET /api/health": {
        status: 409,
        body: { error: { code: "not_ready", message: "Not ready yet." } },
      },
    });
    const failure = await api.health().catch((error) => error);
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure.code).toBe("not_ready");
    expect(failure.message).toBe("Not ready yet.");
  });

  it("explains an unreachable backend", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("failed");
      }),
    );
    await expect(api.health()).rejects.toThrow("could not be reached");
  });

  it("handles a non-JSON proxy failure", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>", { status: 502 })));
    await expect(api.health()).rejects.toThrow("Is it running?");
  });

  it("shows report errors with a retry action", async () => {
    mockApi({
      "GET /api/investigations/inv1/report": {
        status: 500,
        body: { error: { code: "internal_error", message: "An unexpected error occurred." } },
      },
    });
    renderWithQuery(<FindingsView id="inv1" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("unexpected error");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});

describe("investigation progress", () => {
  it("shows each stage, the percentage and stage errors", async () => {
    mockApi({
      "GET /api/investigations/inv1/progress": {
        body: {
          id: "inv1",
          status: "running",
          current_stage: "git",
          percent: 25,
          error_message: null,
          ai_status: "pending",
          ai_error: null,
          stages: [
            { key: "discovery", label: "Repository discovery", status: "completed", message: null },
            { key: "git", label: "Git history analysis", status: "running", message: null },
            {
              key: "dependencies",
              label: "Dependency inspection",
              status: "failed",
              message: "Dependency inspection failed on this repository.",
            },
            { key: "ai", label: "AI analysis", status: "pending", message: null },
          ],
        },
      },
    });
    renderWithQuery(<ProgressPanel id="inv1" />);
    expect(await screen.findByText("Git history analysis")).toBeInTheDocument();
    expect(screen.getByText("25%")).toBeInTheDocument();
    expect(screen.getByText("Running")).toBeInTheDocument();
    expect(screen.getByText("Dependency inspection failed on this repository.")).toBeInTheDocument();
  });

  it("shows a failed investigation's error", async () => {
    mockApi({
      "GET /api/investigations/inv1/progress": {
        body: {
          id: "inv1",
          status: "failed",
          current_stage: "git",
          percent: 12,
          error_message: "The analysis time limit was reached.",
          ai_status: "skipped",
          ai_error: null,
          stages: [],
        },
      },
    });
    renderWithQuery(<ProgressPanel id="inv1" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("time limit");
  });
});

describe("findings display", () => {
  function mockReport(report: typeof REPORT) {
    mockApi({ "GET /api/investigations/inv1/report": { body: report } });
  }

  it("shows every required field on a verified finding", async () => {
    mockReport(REPORT);
    renderWithQuery(<FindingsView id="inv1" />);
    expect(await screen.findByText("No README")).toBeInTheDocument();
    expect(screen.getAllByText("Add a README.").length).toBe(2);
    expect(screen.getAllByText("documentation-inspector:structure-check").length).toBe(2);
    expect(screen.getAllByText("100%").length).toBe(2);
    expect(screen.getAllByText("ev-doc-001").length).toBeGreaterThan(0);
    expect(screen.getByText(".env")).toBeInTheDocument();
  });

  it("keeps AI hypotheses separate and labeled", async () => {
    mockReport(AI_REPORT);
    renderWithQuery(<FindingsView id="inv1" />);
    const hypothesis = await screen.findByText("Project may have moved elsewhere");
    const verified = screen.getByRole("region", { name: /Verified findings/ });
    const aiSection = screen.getByRole("region", { name: /AI-generated/ });
    expect(verified).not.toContainElement(hypothesis);
    expect(aiSection).toContainElement(hypothesis);
    expect(screen.getByText("Hypothesis")).toBeInTheDocument();
    expect(screen.getByText(/1 AI item\(s\) rejected/)).toBeInTheDocument();
  });

  it("does not pretend AI ran when it did not", async () => {
    mockReport(REPORT);
    renderWithQuery(<FindingsView id="inv1" />);
    expect(await screen.findByText("No AI results")).toBeInTheDocument();
  });

  it("filters by severity", async () => {
    mockReport(REPORT);
    renderWithQuery(<FindingsView id="inv1" />);
    await screen.findByText("No README");
    await userEvent.click(screen.getByRole("button", { name: /Critical/ }));
    expect(screen.queryByText("No README")).not.toBeInTheDocument();
    expect(screen.getByText("Secret file is committed: .env")).toBeInTheDocument();
  });

  it("autopsy warns about AI failure and offers a retry", async () => {
    mockApi({
      "GET /api/investigations/inv1/report": {
        body: {
          ...REPORT,
          profile: {
            git: {
              available: true,
              branch: "main",
              commit_count: 3,
              days_since_last_commit: 2000,
              latest_commit: { hash: "abc", author: "Ada", date: "2021-01-01", subject: "x" },
              activity: { last_30_days: 0, last_90_days: 0, last_365_days: 0 },
              message_patterns: { conventional_commit_share: 0, merge_commit_share: 0 },
            },
          },
        },
      },
    });
    renderWithQuery(<AutopsyView id="inv1" />);
    expect(await screen.findByText("AI analysis did not complete.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry AI analysis" })).toBeInTheDocument();
    expect(screen.getByText(/age alone does not\s+mean it is abandoned/)).toBeInTheDocument();
  });
});

describe("recovery plan display", () => {
  it("shows priorities, estimates and AI labels, and updates status", async () => {
    const fetchMock = mockApi({
      "GET /api/investigations/inv1/report": { body: REPORT },
      "PATCH /api/investigations/inv1/recovery-tasks/t1": {
        body: { ...REPORT.recovery_tasks[0], status: "done" },
      },
    });
    renderWithQuery(<PlanView id="inv1" />);
    expect(await screen.findByText("1 to 2 hours")).toBeInTheDocument();
    expect(screen.getAllByText(/rough estimate, not a measurement/).length).toBe(1);
    expect(screen.getByText("AI suggestion")).toBeInTheDocument();
    expect(screen.getByText("Follow the README on a clean machine.")).toBeInTheDocument();

    const [select] = screen.getAllByLabelText("Status");
    await userEvent.selectOptions(select, "done");
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/investigations/inv1/recovery-tasks/t1",
        expect.objectContaining({ method: "PATCH", body: JSON.stringify({ status: "done" }) }),
      ),
    );
  });
});

describe("README preview", () => {
  const DRAFT = {
    id: "d1",
    content: "# Haunted\n\n**Needs confirmation:** add a description.\n",
    origin: "deterministic",
    ai_model: null,
    warning: null,
    unverified_sections: ["Features"],
    created_at: "2026-10-01T10:00:00+00:00",
  };

  it("does not render raw HTML or script links from a repository", () => {
    const { container } = renderWithQuery(
      <MarkdownPreview
        content={
          '<script>alert(1)</script>\n\n<img src=x onerror="alert(1)">\n\n[click](javascript:alert(1))\n\n![pic](http://tracker.example/x.png)'
        }
      />,
    );
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector('a[href^="javascript"]')).toBeNull();
  });

  it("previews, edits and saves a draft without touching the repository", async () => {
    const fetchMock = mockApi({
      ...OLLAMA_READY,
      "GET /api/investigations/inv1/readme": { body: DRAFT },
      "PUT /api/investigations/inv1/readme": {
        body: { ...DRAFT, id: "d2", content: "# Edited\n", origin: "edited" },
      },
    });
    renderWithQuery(<ReadmeView id="inv1" />);
    expect(await screen.findByRole("heading", { name: "Haunted" })).toBeInTheDocument();
    expect(screen.getByText("Needs your confirmation: Features.")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "Edit" }));
    const editor = screen.getByLabelText("README Markdown");
    await userEvent.clear(editor);
    await userEvent.type(editor, "# Edited");
    await userEvent.click(screen.getByRole("button", { name: /Save draft/ }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/investigations/inv1/readme",
        expect.objectContaining({ method: "PUT" }),
      ),
    );
    expect(await screen.findByText("Edited by you")).toBeInTheDocument();
  });

  it("offers generation when there is no draft", async () => {
    mockApi({
      ...OLLAMA_READY,
      "GET /api/investigations/inv1/readme": {
        status: 404,
        body: { error: { code: "not_found", message: "A README draft was not found." } },
      },
    });
    renderWithQuery(<ReadmeView id="inv1" />);
    expect(await screen.findByText("No README draft yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate README draft" })).toBeEnabled();
  });
});

describe("patch approval", () => {
  const PATCH = {
    id: "p1",
    status: "proposed",
    diff: "diff --git a/.env.example b/.env.example\n+DB_URL=\n",
    files: [
      {
        path: ".env.example",
        change_type: "create",
        explanation: "Documents the environment variables.",
        additions: 1,
        deletions: 0,
      },
    ],
    refused_paths: [],
    message: "1 file(s) proposed. Nothing has been changed in the repository.",
    approved_at: null,
    created_at: "2026-10-01T10:00:00+00:00",
  };

  it("hides the download until approval is confirmed in a dialog", async () => {
    const fetchMock = mockApi({
      "GET /api/investigations/inv1/patch": { body: PATCH },
      "POST /api/investigations/inv1/patch/p1/approve": {
        body: { ...PATCH, status: "approved", approved_at: "2026-10-01T10:01:00+00:00" },
      },
    });
    renderWithQuery(<PatchesView id="inv1" />);
    expect(await screen.findByText("Documents the environment variables.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Download patch/ })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Approve patch" }));
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/investigations/inv1/patch/p1/approve",
      expect.anything(),
    );
    await userEvent.click(await screen.findByRole("button", { name: /I reviewed it/ }));

    const link = await screen.findByRole("link", { name: /Download patch/ });
    expect(link).toHaveAttribute("href", "/api/investigations/inv1/patch/p1/download");
  });
});
