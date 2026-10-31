import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DashboardView } from "@/components/dashboard-view";
import { mockApi, renderWithQuery } from "@/test/utils";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const OLLAMA_OFFLINE = {
  enabled: true,
  reachable: false,
  version: null,
  model: "gemma3:4b",
  model_available: false,
  message: "Ollama is not reachable at the configured endpoint.",
};

const EMPTY = {
  investigations: 0,
  verified_findings: 0,
  pending_recovery_tasks: 0,
  average_health_score: null,
  severity_counts: { critical: 0, high: 0, medium: 0, low: 0, info: 0 },
  recent: [],
};

describe("DashboardView", () => {
  it("shows the primary action and an empty state", async () => {
    mockApi({
      "GET /api/dashboard": { body: EMPTY },
      "GET /api/ollama/status": { body: OLLAMA_OFFLINE },
    });
    renderWithQuery(<DashboardView />);

    expect(screen.getByRole("link", { name: /Summon Ghost — Inspect Repository/ })).toHaveAttribute(
      "href",
      "/investigations/new",
    );
    expect(await screen.findByText("No investigations yet")).toBeInTheDocument();
    expect(await screen.findByText("Ollama offline")).toBeInTheDocument();
  });

  it("renders summary numbers and recent investigations", async () => {
    mockApi({
      "GET /api/dashboard": {
        body: {
          ...EMPTY,
          investigations: 3,
          verified_findings: 12,
          pending_recovery_tasks: 5,
          average_health_score: 64,
          severity_counts: { critical: 1, high: 2, medium: 4, low: 3, info: 2 },
          recent: [
            {
              id: "abc",
              repository_name: "old-crawler",
              status: "completed",
              ai_status: "failed",
              health_score: 64,
              finding_count: 12,
              created_at: "2026-10-01T10:00:00+00:00",
            },
          ],
        },
      },
      "GET /api/ollama/status": { body: OLLAMA_OFFLINE },
    });
    renderWithQuery(<DashboardView />);

    expect(await screen.findByText("old-crawler")).toBeInTheDocument();
    expect(screen.getAllByText("64").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /old-crawler/ })).toHaveAttribute(
      "href",
      "/investigations/abc",
    );
  });

  it("shows an error when the backend fails", async () => {
    mockApi({
      "GET /api/dashboard": {
        status: 500,
        body: { error: { code: "internal_error", message: "An unexpected error occurred." } },
      },
      "GET /api/ollama/status": { body: OLLAMA_OFFLINE },
    });
    renderWithQuery(<DashboardView />);

    expect(await screen.findByRole("alert")).toHaveTextContent("An unexpected error occurred.");
  });
});
