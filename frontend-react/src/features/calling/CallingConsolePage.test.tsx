import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CallingConsolePage } from "./CallingConsolePage";

type SessionTimelineEvent = {
  ts: number;
  type: string;
  payload?: Record<string, unknown>;
};

const apiFetchMock = vi.fn();

const scenario = {
  buildInfo: { pilot_mode: true, demo_mode: true, static_token: "t1", app: "x", timestamp: 1 },
  tasks: [
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
  ] as Array<Record<string, unknown>>,
  sessions: [] as Array<Record<string, unknown>>,
  timelines: {} as Record<string, SessionTimelineEvent[]>,
  agentCallResponse: {
    ok: true,
    session_id: "tel-agent-1",
    result: { call_sid: "CA123", call_status: "queued", delivery_status: "queued", normalized_to: "+919950022999" },
  },
};

vi.mock("../../auth/AuthProvider", () => ({
  useAuth: () => ({
    user: { username: "agent" },
    role: "CALLING_AGENT",
    hasPermission: () => true,
  }),
}));

vi.mock("@mantine/notifications", () => ({
  notifications: { show: vi.fn() },
}));

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    apiFetch: (...args: Parameters<typeof actual.apiFetch>) => apiFetchMock(...args),
  };
});

function buildApiMock() {
  apiFetchMock.mockImplementation(async (path: string) => {
    if (path === "/api/system/build_info") {
      return scenario.buildInfo;
    }
    if (path === "/api/telephony/agent_call") {
      return scenario.agentCallResponse;
    }
    if (String(path).startsWith("/api/tasks/") && String(path).endsWith("/claim")) {
      return { ok: true };
    }
    if (String(path).startsWith("/api/tasks/")) {
      const taskId = String(path).split("/").pop() || "";
      return scenario.tasks.find((row) => String(row.id) === taskId) || {};
    }
    if (String(path).startsWith("/api/tasks")) {
      return { rows: scenario.tasks };
    }
    if (path === "/api/sessions") {
      return { sessions: scenario.sessions };
    }
    if (String(path).startsWith("/api/sessions/") && String(path).endsWith("/timeline")) {
      const parts = String(path).split("/");
      const sessionId = decodeURIComponent(parts[3] || "");
      return { session_id: sessionId, timeline: scenario.timelines[sessionId] || [] };
    }
    return {};
  });
}

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
  beforeEach(() => {
    scenario.buildInfo = { pilot_mode: true, demo_mode: true, static_token: "t1", app: "x", timestamp: 1 };
    scenario.tasks = [
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
    ];
    scenario.sessions = [];
    scenario.timelines = {};
    scenario.agentCallResponse = {
      ok: true,
      session_id: "tel-agent-1",
      result: { call_sid: "CA123", call_status: "queued", delivery_status: "queued", normalized_to: "+919950022999" },
    };
    apiFetchMock.mockReset();
    buildApiMock();
  });

  it("renders assigned tasks in queue", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Assigned Queue")).toBeInTheDocument();
      expect(screen.getByText("CUST001")).toBeInTheDocument();
      expect(screen.getAllByText("Phone Agent Call")[0]).toBeInTheDocument();
      expect(screen.getByText("Starting Language")).toBeInTheDocument();
      expect(screen.getByDisplayValue("Hindi")).toBeInTheDocument();
      expect(screen.getByText("Bulbul Voice")).toBeInTheDocument();
    });
  });

  it("keeps transcript and timeline visible for direct phone testing without assigned tasks", async () => {
    scenario.tasks = [];
    scenario.timelines = {
      "tel-agent-1": [
        {
          ts: 1773134578.407,
          type: "message",
          payload: { role: "assistant", content_redacted: "Namaste. This is the live bridge test call." },
        },
        {
          ts: 1773134580.111,
          type: "message",
          payload: { role: "user", content_redacted: "Hello, I can hear you." },
        },
        {
          ts: 1773134581.222,
          type: "workflow_update",
          payload: { state: "identity_confirm" },
        },
      ],
    };

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Voice Test Desk")).toBeInTheDocument();
      expect(screen.getByText("Transcript and session telemetry")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Call Number" }));

    await waitFor(() => {
      expect(screen.getAllByText("tel-agent-1").length).toBeGreaterThan(0);
      expect(screen.getByText("Namaste. This is the live bridge test call.")).toBeInTheDocument();
      expect(screen.getByText("Hello, I can hear you.")).toBeInTheDocument();
      expect(screen.getByText("Session Timeline")).toBeInTheDocument();
    });
  });
});
