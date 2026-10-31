import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { vi } from "vitest";

export function renderWithQuery(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

type Route = { status?: number; body: unknown };

/** Replaces fetch with a table of "METHOD /path" responses; unknown routes return 404. */
export function mockApi(routes: Record<string, Route>) {
  const mock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input).split("?")[0];
    const route = routes[`${init?.method ?? "GET"} ${url}`];
    if (!route) {
      return new Response(
        JSON.stringify({ error: { code: "not_found", message: `No mock for ${url}` } }),
        { status: 404 },
      );
    }
    return new Response(JSON.stringify(route.body), { status: route.status ?? 200 });
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}
