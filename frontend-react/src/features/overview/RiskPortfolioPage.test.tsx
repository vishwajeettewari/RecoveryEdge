import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { RiskPortfolioPage } from "./RiskPortfolioPage";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  const apiFetch = vi.fn(async (path: string) => {
    if (path === "/api/campaigns") {
      return {
        rows: [
          { campaign_id: "cmp-1", name: "North Star Pilot", status: "live", total_accounts: 120, created_at: 1 },
          { campaign_id: "cmp-2", name: "Control Book", status: "created", total_accounts: 85, created_at: 2 },
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
        daily_counts: [2, 3, 2],
        total_recovered: 54000,
        portfolio_value: 400000,
        recovery_rate_pct: 13.5,
        window_days: 30,
        reconciliation: [],
      };
    }
    if (String(path).startsWith("/api/metrics/roll-forward")) {
      return {
        buckets: ["0", "1-30", "31-60", "61-90", "90+"],
        matrix: {
          "0": { "0": 9, "1-30": 0, "31-60": 0, "61-90": 0, "90+": 0 },
          "1-30": { "0": 2, "1-30": 12, "31-60": 4, "61-90": 0, "90+": 0 },
          "31-60": { "0": 3, "1-30": 3, "31-60": 14, "61-90": 5, "90+": 0 },
          "61-90": { "0": 1, "1-30": 0, "31-60": 2, "61-90": 8, "90+": 4 },
          "90+": { "0": 0, "1-30": 0, "31-60": 0, "61-90": 1, "90+": 7 },
        },
        total_transitions: 75,
        roll_forward_count: 13,
        roll_forward_pct: 21.7,
        rollback_count: 8,
        rollback_pct: 10.7,
        cure_count: 6,
        cure_rate_pct: 8,
        window_days: 30,
      };
    }
    if (String(path).startsWith("/api/metrics/agents")) {
      return {
        agents: [
          {
            rank: 1,
            display_name: "Asha",
            total_calls: 44,
            connect_rate_pct: 61,
            avg_handle_time_s: 151,
            ptp_count: 8,
            ptp_conversion_pct: 29,
            escalations: 1,
            compliance_violations: 0,
          },
        ],
      };
    }
    if (String(path).startsWith("/api/metrics")) {
      return {
        sessions_today: 16,
        ptp_count: 12,
        callback_count: 7,
        escalations: 2,
        retries_pending: 3,
        avg_handle_seconds: 142,
        conversion_by_campaign: {
          "cmp-1": { total: 120, completed: 58, rate: 48.3 },
          "cmp-2": { total: 85, completed: 20, rate: 23.5 },
        },
        bucket_heatmap: { "1-30": 30, "31-60": 52, "61-90": 22, "90+": 11 },
        expected_recovery_amount: 72000,
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
        profanity_incidents: 2,
        queue_snapshot: { NEW: 24, IN_PROGRESS: 31, PTP: 19, CALLBACK: 10, ESCALATED: 4, CLOSED: 27 },
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
  return { ...actual, apiFetch };
});

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <MantineProvider>
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <RiskPortfolioPage />
        </MemoryRouter>
      </QueryClientProvider>
    </MantineProvider>
  );
}

describe("RiskPortfolioPage", () => {
  it("renders the dedicated risk and portfolio sections", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Risk / Portfolio Dashboard")).toBeInTheDocument();
      expect(screen.getByText("Portfolio Risk Ladder")).toBeInTheDocument();
      expect(screen.getByText("Attention Board")).toBeInTheDocument();
      expect(screen.getByText("Transition Outlook")).toBeInTheDocument();
      expect(screen.getByText("Recovery Outlook")).toBeInTheDocument();
      expect(screen.getAllByText("Cure Rate").length).toBeGreaterThan(0);
      expect(screen.getByText("Operating pressure")).toBeInTheDocument();
      expect(screen.getAllByText("North Star Pilot").length).toBeGreaterThan(0);
    });
  });
});
