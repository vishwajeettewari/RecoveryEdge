import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CommandCenterPage } from "./CommandCenterPage";

const apiFetchMock = vi.fn(async (path: string) => {
  if (path === "/api/campaigns") {
    return {
      rows: [
        { campaign_id: "cmp-1", name: "North Star Pilot", status: "active", total_accounts: 120, created_at: 1 },
        { campaign_id: "cmp-2", name: "South Rollout", status: "created", total_accounts: 82, created_at: 2 },
      ],
    };
  }
  if (path === "/api/system/build_info") {
    return { pilot_mode: true, demo_mode: true, static_token: "t1", app: "x", timestamp: 1 };
  }
  if (String(path).startsWith("/api/metrics/recovery")) {
    return {
      dates: ["2026-03-01", "2026-03-02", "2026-03-03"],
      amounts: [12000, 24000, 18000],
      total_recovered: 54000,
      portfolio_value: 400000,
      recovery_rate_pct: 13.5,
      window_days: 30,
      reconciliation: [
        { date: "2026-03-03", customer_id: "cust-1", amount: 24000 },
        { date: "2026-03-02", customer_id: "cust-2", amount: 30000 },
      ],
    };
  }
  if (String(path).startsWith("/api/metrics/roll-forward")) {
    return {
      buckets: ["0", "1-30", "31-60", "61-90", "90+"],
      matrix: {
        "0": { "0": 12, "1-30": 0, "31-60": 0, "61-90": 0, "90+": 0 },
        "1-30": { "0": 4, "1-30": 11, "31-60": 3, "61-90": 0, "90+": 0 },
        "31-60": { "0": 2, "1-30": 3, "31-60": 9, "61-90": 5, "90+": 1 },
        "61-90": { "0": 0, "1-30": 1, "31-60": 2, "61-90": 7, "90+": 4 },
        "90+": { "0": 0, "1-30": 0, "31-60": 0, "61-90": 2, "90+": 5 },
      },
      total_transitions: 71,
      roll_forward_count: 13,
      roll_forward_pct: 18.3,
      rollback_count: 10,
      rollback_pct: 14.1,
      cure_count: 6,
      cure_rate_pct: 8.5,
      window_days: 30,
    };
  }
  if (String(path).startsWith("/api/metrics/agents")) {
    return {
      agents: [
        {
          rank: 1,
          agent_id: "usr-1",
          display_name: "Asha",
          total_calls: 44,
          connect_rate_pct: 61,
          avg_handle_time_s: 151,
          ptp_count: 8,
          ptp_conversion_pct: 29,
          escalations: 1,
          compliance_violations: 0,
        },
        {
          rank: 2,
          agent_id: "usr-2",
          display_name: "Rohan",
          total_calls: 31,
          connect_rate_pct: 55,
          avg_handle_time_s: 164,
          ptp_count: 5,
          ptp_conversion_pct: 22,
          escalations: 2,
          compliance_violations: 1,
        },
      ],
    };
  }
  if (String(path).startsWith("/api/tasks/summary")) {
    return { NEW: 12, IN_PROGRESS: 20, PTP: 9, CALLBACK: 7, ESCALATED: 3, CLOSED: 18 };
  }
  if (String(path).startsWith("/api/sessions")) {
    return {
      sessions: [
        {
          session_id: "sess-1",
          customer_id: "cust-1",
          customer_name: "Sneha Patel",
          phone: "+919950022999",
          amount_due: 48000,
          dpd_bucket: "31-60",
          disposition: "live",
          current_step: "payment_discussion",
        },
      ],
    };
  }
  if (String(path).startsWith("/api/tasks?")) {
    return {
      rows: [
        {
          id: "tsk-1",
          campaign_id: "cmp-1",
          customer_id: "cust-1",
          customer_name: "Sneha Patel",
          phone: "+919950022999",
          amount_due: 48000,
          dpd: 46,
          state: "CALLBACK",
          owner: "agent-1",
        },
        {
          id: "tsk-2",
          campaign_id: "cmp-1",
          customer_id: "cust-2",
          customer_name: "Vikram Singh",
          phone: "+919980400111",
          amount_due: 72000,
          dpd: 71,
          state: "ESCALATED",
          owner: "agent-2",
        },
      ],
      total: 2,
      page: 1,
      page_size: 6,
    };
  }
  if (String(path).startsWith("/api/metrics")) {
    return {
      sessions_today: 16,
      ptp_count: 12,
      callback_count: 7,
      escalations: 3,
      retries_pending: 4,
      avg_handle_seconds: 142,
      bucket_heatmap: { "1-30": 30, "31-60": 52, "61-90": 22, "90+": 11 },
      expected_recovery_amount: 720000,
      sla_breaches: 2,
      accounts_assigned: 115,
      accounts_contacted: 73,
      contact_rate_pct: 63.5,
      followups_scheduled_total: 48,
      followups_pending_total: 12,
      followups_sent_total: 28,
      followups_missed_total: 8,
      followups_due_today: 10,
      followups_completed_today: 7,
      followup_discipline_rate_pct: 70,
      ptp_miss_count: 6,
      ptp_miss_open_alerts: 3,
      queue_snapshot: { NEW: 12, IN_PROGRESS: 20, PTP: 9, CALLBACK: 7, ESCALATED: 3, CLOSED: 18 },
      ptp_rate_by_bucket: {
        "1-30": { total: 20, ptp: 7, rate: 35 },
        "31-60": { total: 40, ptp: 11, rate: 27.5 },
        "61-90": { total: 21, ptp: 3, rate: 14.3 },
        "90+": { total: 12, ptp: 1, rate: 8.3 },
      },
    };
  }
  return {};
});

vi.mock("recharts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("recharts")>();
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: ReactNode }) => (
      <div style={{ width: 960, height: 320 }}>{children}</div>
    ),
  };
});

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return { ...actual, apiFetch: (...args: Parameters<typeof actual.apiFetch>) => apiFetchMock(...args) };
});

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <MantineProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <CommandCenterPage />
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>
  );
}

describe("CommandCenterPage", () => {
  beforeEach(() => {
    apiFetchMock.mockClear();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: vi.fn(),
    });
  });

  it("renders campaign-backed command center sections and removes seeded demo content", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("AI Collections Command Center")).toBeInTheDocument();
      expect(screen.getAllByText("North Star Pilot").length).toBeGreaterThan(0);
      expect(screen.getByText("Portfolio Health Overview")).toBeInTheDocument();
      expect(screen.getByText("Collections Operations Monitoring")).toBeInTheDocument();
      expect(screen.getByText("Recommended Actions")).toBeInTheDocument();
      expect(screen.getAllByText("Sneha Patel").length).toBeGreaterThan(0);
      expect(screen.getByText("sess-1")).toBeInTheDocument();
      expect(screen.getByText("Clear overdue callback queue")).toBeInTheDocument();
      expect(screen.getByText("Stabilize the 31-60 bucket")).toBeInTheDocument();
    });

    expect(screen.queryByText("Call Tonight")).not.toBeInTheDocument();
    expect(screen.queryByText("Rajesh Kumar")).not.toBeInTheDocument();
  });

  it("threads task state and bucket filters through analytics queries", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("AI Collections Command Center");

    await user.click(screen.getByDisplayValue("All task states"));
    await user.click(await screen.findByRole("option", { name: "Callback" }));
    await user.click(screen.getByDisplayValue("All buckets"));
    await user.click(await screen.findByRole("option", { name: "31-60 DPD" }));

    await waitFor(() => {
      expect(apiFetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/metrics?campaign_id=cmp-1&state=CALLBACK&dpd_bucket=31-60"));
      expect(apiFetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/metrics/roll-forward?campaign_id=cmp-1&state=CALLBACK&dpd_bucket=31-60"));
      expect(apiFetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/metrics/recovery?campaign_id=cmp-1&state=CALLBACK&dpd_bucket=31-60"));
      expect(apiFetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/metrics/agents?campaign_id=cmp-1&state=CALLBACK&dpd_bucket=31-60"));
      expect(apiFetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/tasks/summary?campaign_id=cmp-1&state=CALLBACK&dpd_bucket=31-60"));
      expect(apiFetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/sessions?campaign_id=cmp-1&state=CALLBACK&bucket=31-60"));
      expect(apiFetchMock).toHaveBeenCalledWith(expect.stringContaining("/api/tasks?campaign_id=cmp-1&state=CALLBACK&dpd_bucket=31-60"));
    });
  });

  it("wires export actions to csv download and print output", async () => {
    const user = userEvent.setup();
    const createObjectURL = vi.fn(() => "blob:command-center");
    const revokeObjectURL = vi.fn();
    const printWindow = {
      document: {
        open: vi.fn(),
        write: vi.fn(),
        close: vi.fn(),
      },
      focus: vi.fn(),
      print: vi.fn(),
    } as unknown as Window;
    const openSpy = vi.spyOn(window, "open").mockReturnValue(printWindow);
    const anchorClickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    const originalCreateObjectURL = URL.createObjectURL;
    const originalRevokeObjectURL = URL.revokeObjectURL;
    URL.createObjectURL = createObjectURL;
    URL.revokeObjectURL = revokeObjectURL;

    renderPage();
    await screen.findByText("AI Collections Command Center");

    await user.click(screen.getByRole("button", { name: "Export" }));
    await user.click(await screen.findByText("Export to Excel"));

    await waitFor(() => {
      expect(createObjectURL).toHaveBeenCalledTimes(1);
    });

    await user.click(screen.getByRole("button", { name: "Export" }));
    await user.click(await screen.findByText("Export to PDF"));

    expect(openSpy).toHaveBeenCalledTimes(1);
    expect(printWindow.document.write).toHaveBeenCalledTimes(1);
    expect(printWindow.print).toHaveBeenCalledTimes(1);

    URL.createObjectURL = originalCreateObjectURL;
    URL.revokeObjectURL = originalRevokeObjectURL;
    anchorClickSpy.mockRestore();
    openSpy.mockRestore();
  });
});
