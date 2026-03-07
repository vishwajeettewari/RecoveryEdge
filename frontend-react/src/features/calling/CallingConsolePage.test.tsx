import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { CallingConsolePage } from "./CallingConsolePage";

vi.mock("../../auth/AuthProvider", () => ({
  useAuth: () => ({
    user: { username: "agent" },
    role: "CALLING_AGENT",
    hasPermission: () => true,
  }),
}));

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  const apiFetch = vi.fn(async (path: string) => {
    if (path === "/api/system/build_info") {
      return { pilot_mode: true, demo_mode: true, static_token: "t1", app: "x", timestamp: 1 };
    }
    if (String(path).startsWith("/api/tasks")) {
      return {
        rows: [
          {
            id: "tsk-1",
            customer_id: "CUST001",
            customer_name: "Asha",
            owner: "agent",
            amount_due: 1200,
            dpd: 35,
            state: "NEW",
            campaign_id: "cmp-1",
          },
        ],
      };
    }
    if (String(path).startsWith("/api/sessions")) {
      return { sessions: [] };
    }
    return {};
  });
  return { ...actual, apiFetch };
});

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <MantineProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <CallingConsolePage />
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>
  );
}

describe("CallingConsolePage", () => {
  it("renders assigned tasks in queue", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Assigned Queue")).toBeInTheDocument();
      expect(screen.getByText("CUST001")).toBeInTheDocument();
      expect(screen.getByText("Phone Agent Call")).toBeInTheDocument();
      expect(screen.getByText("Starting Language")).toBeInTheDocument();
      expect(screen.getByDisplayValue("Hindi")).toBeInTheDocument();
      expect(screen.getByText("Bulbul Voice")).toBeInTheDocument();
    });
  });
});
